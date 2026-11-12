"""Loopback-only desktop UI, using the project's actual local model adapters."""
import asyncio
from contextlib import asynccontextmanager
import base64
import binascii
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
from pathlib import Path
import secrets
import threading
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from server.modules.audio_io import read_wav
from server.modules.integration import load_registry
from server.gateway.protocol import ProtocolError

STATIC = Path(__file__).parent/'static'
MAX_WAV = 8*1024*1024
MAX_REQUEST = 12*1024*1024
STAGES = {'M1':'识别语音片段','M2':'转写语音内容','M3':'理解回答与要点','M4':'匹配要点与证据'}
ERRORS = {'INVALID_PAYLOAD':'音频格式不符合要求，请使用 16 kHz、单声道、16 位 PCM WAV。',
    'NO_SPEECH':'未检测到语音，请检查录音音量或换一段音频。','NO_TRANSCRIPT':'检测到音频，但未识别出文字，请换一段清晰录音。',
    'MODEL_UNAVAILABLE':'模型加载失败，请查看启动日志并确认模型包完整。'}

class DesktopEngine:
    def __init__(self, models, output, sample=None, loader=load_registry):
        self.models,self.output = Path(models),Path(output)
        self.sample = Path(sample) if sample else None
        self.loader = loader
        self.output.mkdir(parents=True,exist_ok=True)
        self.jobs = {}
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1,thread_name_prefix='desktop-analysis')
        self.active = None
        self.handlers = None
        self.manifest = None
        self.model_state = 'NOT_LOADED'
        self.load_ms = None

    def view(self, job_id):
        with self.lock:
            if job_id not in self.jobs: raise KeyError(job_id)
            return copy.deepcopy(self.jobs[job_id])

    def submit(self, name, raw, points, synthetic=False):
        if not raw or len(raw)>MAX_WAV: raise ValueError('音频文件大小须在 0–8 MB 之间。')
        points = [text.strip() for text in points if isinstance(text,str) and text.strip()]
        if not 1<=len(points)<=100 or any(len(text)>1000 for text in points):
            raise ValueError('请填写 1–100 个参考要点，每项不超过 1000 字。')
        with self.lock:
            if self.active is not None: raise RuntimeError('当前任务尚未结束，请等待。')
            job_id = uuid.uuid4().hex
            task = {'id':job_id,'name':str(name).replace('\\','/').split('/')[-1][:160],
                'status':'QUEUED','stage':'准备音频','progress':2,'cancel_requested':False,
                'synthetic':synthetic,'created_at':time.time(),'result':None,'error':None,'timings':{}}
            self.jobs[job_id] = task
            self.active = job_id
            for key in list(self.jobs)[:-30]:
                del self.jobs[key]
            self.pool.submit(self.run,job_id,raw,points)
            return job_id

    def update(self, job_id, **values):
        with self.lock: self.jobs[job_id].update(values)

    def cancelled(self,job_id):
        with self.lock: return self.jobs[job_id]['cancel_requested']

    def cancel(self,job_id):
        with self.lock:
            job = self.jobs[job_id]
            if job['status'] in ('SUCCEEDED','FAILED','CANCELLED'): return False
            job['cancel_requested'] = True
            job['stage'] = '正在取消，等待当前模型调用结束'
            return True

    def run(self,job_id,raw,points):
        path = self.output/(job_id+'.input.wav')
        started = time.perf_counter()
        try:
            path.write_bytes(raw)
            payload = read_wav(path)
            duration = payload['audio']['sample_count']/16000
            if self.cancelled(job_id): return
            if self.handlers is None:
                self.model_state = 'LOADING'
                self.update(job_id,status='RUNNING',stage='首次加载本地模型，通常约 1 分钟，请稍候',progress=8)
                begin = time.perf_counter()
                manifest,handlers,errors = self.loader(self.models)
                if errors or set(handlers)!={'M1','M2','M3','M4'}:
                    self.model_state = 'FAILED'
                    raise ProtocolError('MODEL_UNAVAILABLE','Model set unavailable')
                self.handlers,self.manifest = handlers,manifest
                self.load_ms = (time.perf_counter()-begin)*1000
                self.model_state = 'READY'
            outputs,timings = {},{}
            analysis_started = time.perf_counter()
            keypoints = [{'keypoint_id':f'k{i+1}','text':text} for i,text in enumerate(points)]
            for index,module in enumerate(STAGES):
                if self.cancelled(job_id): return
                self.update(job_id,status='RUNNING',stage=STAGES[module],progress=20+index*20)
                begin = time.perf_counter()
                value = self.handlers[module](payload)
                timings[module] = (time.perf_counter()-begin)*1000
                self.update(job_id,timings=dict(timings))
                outputs[module] = value
                payload = value | {'keypoints':keypoints} if module=='M2' else value
            if self.cancelled(job_id): return
            result = {'id':job_id,'condition':'SYNTHETIC_TTS_DESKTOP_DIAGNOSTIC' if self.jobs[job_id]['synthetic'] else 'DESKTOP_LOCAL_INPUT_NOT_HUMAN_REVIEWED',
                'formal_evaluation':False,'source_wav':self.jobs[job_id]['name'],'audio_sha256':hashlib.sha256(raw).hexdigest(),
                'audio_duration_s':duration,'model_version':self.manifest['model_version'],'config_version':self.manifest['config_version'],
                'reference_keypoints':keypoints,'model_load_ms':self.load_ms,'inference_ms':(time.perf_counter()-analysis_started)*1000,
                'total_ms':(time.perf_counter()-started)*1000,'module_ms':timings,
                'transcript':outputs['M2']['transcript'],'matches':outputs['M4']['matches']}
            text = '# 电脑语音回答分析\n\n来源：'+result['source_wav']+'\n\n数据标签：'+result['condition']+'\n\n'+result['transcript']['full_text']+'\n\n'
            for point,match in zip(keypoints,result['matches'],strict=True):
                text += '- '+point['text']+'：'+('已覆盖' if match['covered'] else '可能遗漏')+f'（{match["score"]:.3f}）\n  依据：'+match['evidence_text']+'\n'
            text += '\n覆盖判断需结合原文复核，当前阈值仍待真实数据校准。\n'
            with self.lock:
                if self.cancelled(job_id): return
                (self.output/(job_id+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),'utf-8')
                (self.output/(job_id+'.md')).write_text(text,'utf-8')
                self.jobs[job_id].update(status='SUCCEEDED',stage='分析完成',progress=100,result=result)
        except Exception as error:
            code = getattr(error,'code','INTERNAL_ERROR')
            self.update(job_id,status='FAILED',stage='分析未完成',error={'code':code,'message':ERRORS.get(code,'分析失败，请确认音频与模型文件，或重启界面后重试。')})
        finally:
            path.unlink(missing_ok=True)
            with self.lock:
                if self.jobs[job_id]['cancel_requested']:
                    self.jobs[job_id].update(status='CANCELLED',stage='已取消',result=None,progress=0)
                self.active = None

    def close(self):
        with self.lock:
            if self.active: self.jobs[self.active]['cancel_requested']=True
        self.pool.shutdown(wait=True,cancel_futures=True)


def create_app(models,output,sample=None,loader=load_registry):
    engine = DesktopEngine(models,output,sample,loader)
    @asynccontextmanager
    async def lifespan(app):
        yield
        await asyncio.to_thread(engine.close)
    app = FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.engine = engine
    key = secrets.token_urlsafe(32)

    @app.middleware('http')
    async def local_only(request,call_next):
        if request.client and request.client.host not in ('127.0.0.1','::1','testclient'):
            return JSONResponse({'message':'Local computer only'},403)
        host = request.headers.get('host','').split(':')[0]
        if host not in ('127.0.0.1','localhost','testserver'):
            return JSONResponse({'message':'Invalid host'},403)
        if request.url.path.startswith('/api/'):
            if not secrets.compare_digest(request.headers.get('x-desktop-key',''),key):
                return JSONResponse({'message':'请刷新页面后重试。'},401)
            origin = request.headers.get('origin')
            if origin and origin!=str(request.base_url).rstrip('/'):
                return JSONResponse({'message':'Origin rejected'},403)
        response = await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.get('/desktop/ping')
    def ping(): return {'application':'interview-feedback-desktop','version':'1.0'}

    @app.get('/')
    def index(): return HTMLResponse((STATIC/'index.html').read_text('utf-8').replace('__DESKTOP_KEY__',key))

    @app.get('/assets/{name}')
    def assets(name:str):
        if name not in ('app.js','app.css'): return Response(status_code=404)
        return FileResponse(STATIC/name)

    @app.get('/api/status')
    def status():
        with engine.lock:
            return {'model_state':engine.model_state,'active_job':engine.active,
                'sample_available':engine.sample is not None and engine.sample.is_file(),
                'jobs':[{'id':j['id'],'name':j['name'],'status':j['status'],'created_at':j['created_at']} for j in reversed(list(engine.jobs.values()))]}

    @app.get('/api/sample')
    def get_sample():
        if engine.sample is None or not engine.sample.is_file(): return JSONResponse({'message':'合成示例文件不可用，请选择自己的 WAV。'},404)
        return FileResponse(engine.sample,media_type='audio/wav',filename='synthetic-example.wav')

    @app.post('/api/jobs')
    async def submit(request:Request):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>MAX_REQUEST: return JSONResponse({'message':'文件过大，请选择不超过 60 秒的标准 WAV。'},413)
        try:
            data = json.loads(raw)
            points = data['keypoints']
            if not isinstance(points,list) or any(not isinstance(p,str) for p in points): raise ValueError('参考要点格式错误。')
            synthetic = data.get('use_sample') is True
            if synthetic:
                if engine.sample is None or not engine.sample.is_file(): raise ValueError('合成示例不可用。')
                audio = engine.sample.read_bytes()
                name = '合成语音示例（非真实采集）'
            else:
                audio = base64.b64decode(data['audio_base64'],validate=True)
                name = data.get('name','answer.wav')
            job_id = engine.submit(name,audio,points,synthetic)
            return JSONResponse({'id':job_id},202)
        except RuntimeError as error: return JSONResponse({'message':str(error)},409)
        except (ValueError,TypeError,KeyError,binascii.Error): return JSONResponse({'message':'请检查音频文件和参考要点，音频须为 16 kHz 单声道 PCM WAV。'},400)

    @app.get('/api/jobs/{job_id}')
    def job(job_id:str):
        try: return engine.view(job_id)
        except KeyError: return JSONResponse({'message':'任务不存在或已过期。'},404)

    @app.post('/api/jobs/{job_id}/cancel')
    def cancel(job_id:str):
        try: return {'requested':engine.cancel(job_id)}
        except KeyError: return JSONResponse({'message':'任务不存在。'},404)

    @app.get('/api/jobs/{job_id}/download/{kind}')
    def download(job_id:str,kind:str):
        if kind not in ('json','md'): return Response(status_code=404)
        try: job = engine.view(job_id)
        except KeyError: return Response(status_code=404)
        if job['status']!='SUCCEEDED': return JSONResponse({'message':'任务尚未完成。'},409)
        return FileResponse(engine.output/(job_id+'.'+kind),filename='语音分析结果.'+kind)

    return app
