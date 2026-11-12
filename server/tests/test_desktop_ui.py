import base64
import io
import json
from pathlib import Path
import re
import tempfile
import threading
import time
import unittest
import wave
import httpx
from server.desktop.app import create_app


def wav_bytes():
    stream=io.BytesIO()
    with wave.open(stream,'wb') as audio:
        audio.setparams((1,2,16000,0,'NONE','not compressed'))
        audio.writeframes(b'\x01\x00'*1600)
    return stream.getvalue()

def loader(root):
    return {'model_version':'fixture-model','config_version':'fixture-rules'}, {
        'M1':lambda p:{'segments':[{'segment_id':'seg1','start_sample':0,'end_sample':1600,'pcm_b64':p['audio']['pcm_b64']}]},
        'M2':lambda p:{'transcript':{'full_text':'测试转写','segments':[{'segment_id':'seg1','text':'测试转写'}]}},
        'M3':lambda p:{'embeddings':{}},
        'M4':lambda p:{'matches':[{'keypoint_id':'k1','score':.9,'covered':True,'evidence_sentence_id':'s1','evidence_text':'测试转写'}]},
    },{}

class DesktopUITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.folder=Path(self.temp.name)
        self.sample=self.folder/'synthetic.wav'; self.sample.write_bytes(wav_bytes())
        self.app=create_app(self.folder,self.folder/'results',self.sample,loader=loader)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://testserver')
        response=await self.client.get('/')
        self.assertEqual(response.status_code,200)
        key=response.text.split('name="desktop-key" content="',1)[1].split('"',1)[0]
        self.headers={'X-Desktop-Key':key}

    async def asyncTearDown(self):
        self.app.state.engine.close()
        await self.client.aclose()
        self.temp.cleanup()

    async def wait_job(self,job_id):
        import asyncio
        for _ in range(300):
            row=(await self.client.get('/api/jobs/'+job_id,headers=self.headers)).json()
            if row['status'] in ('SUCCEEDED','FAILED','CANCELLED'): return row
            await asyncio.sleep(.01)
        self.fail('Job did not terminate')

    async def test_index_assets_auth_origin_and_limits(self):
        self.assertEqual((await self.client.get('/assets/app.js')).status_code,200)
        self.assertEqual((await self.client.get('/assets/private.py')).status_code,404)
        self.assertEqual((await self.client.get('/api/status')).status_code,401)
        response=await self.client.get('/api/status',headers=self.headers|{'Origin':'https://unrelated.test'})
        self.assertEqual(response.status_code,403)
        response=await self.client.get('/',headers={'Host':'unrelated.test'})
        self.assertEqual(response.status_code,403)
        response=await self.client.post('/api/jobs',headers=self.headers,json={'keypoints':[],'use_sample':True})
        self.assertEqual(response.status_code,400)
        response=await self.client.post('/api/jobs',headers=self.headers,json={'keypoints':['要点'],'audio_base64':'%%%','name':'bad.wav'})
        self.assertEqual(response.status_code,400)

    async def test_real_pipeline_contract_progress_download_and_reuse(self):
        calls=[]
        self.app.state.engine.loader=lambda root:(calls.append(1) or loader(root))
        for _ in range(2):
            response=await self.client.post('/api/jobs',headers=self.headers,json={'keypoints':['测试要点'],'use_sample':True})
            self.assertEqual(response.status_code,202)
            job=await self.wait_job(response.json()['id'])
            self.assertEqual(job['status'],'SUCCEEDED',job)
            self.assertEqual(job['result']['condition'],'SYNTHETIC_TTS_DESKTOP_DIAGNOSTIC')
            self.assertEqual(set(job['timings']),{'M1','M2','M3','M4'})
            for kind in ('json','md'):
                response=await self.client.get('/api/jobs/'+job['id']+'/download/'+kind,headers=self.headers)
                self.assertEqual(response.status_code,200)
            response=await self.client.get('/api/jobs/'+job['id']+'/download/exe',headers=self.headers)
            self.assertEqual(response.status_code,404)
        self.assertEqual(len(calls),1)
        self.assertFalse(list((self.folder/'results').glob('*.input.wav')))
        status=(await self.client.get('/api/status',headers=self.headers)).json()
        self.assertEqual(status['model_state'],'READY')
        self.assertEqual(len(status['jobs']),2)

    async def test_invalid_wav_fails_without_loading(self):
        self.app.state.engine.loader=lambda root:self.fail('Must validate WAV before model load')
        response=await self.client.post('/api/jobs',headers=self.headers,json={
            'keypoints':['要点'],'audio_base64':base64.b64encode(b'not wav').decode(),'name':'bad.wav'})
        job=await self.wait_job(response.json()['id'])
        self.assertEqual(job['status'],'FAILED')
        self.assertEqual(job['error']['code'],'INVALID_PAYLOAD')

    async def test_cancel_keeps_single_flight_and_discards_late_result(self):
        import asyncio
        started,release=threading.Event(),threading.Event()
        def blocked(root):
            started.set(); release.wait(5)
            return loader(root)
        self.app.state.engine.loader=blocked
        response=await self.client.post('/api/jobs',headers=self.headers,json={'keypoints':['要点'],'use_sample':True})
        job_id=response.json()['id']
        try:
            self.assertTrue(await asyncio.to_thread(started.wait,2))
            self.assertEqual((await self.client.post('/api/jobs/'+job_id+'/cancel',headers=self.headers)).status_code,200)
            response=await self.client.post('/api/jobs',headers=self.headers,json={'keypoints':['要点'],'use_sample':True})
            self.assertEqual(response.status_code,409)
        finally: release.set()
        job=await self.wait_job(job_id)
        self.assertEqual(job['status'],'CANCELLED')
        self.assertIsNone(job['result'])
        self.assertFalse((self.folder/'results'/(job_id+'.json')).exists())

    async def test_missing_model_set_clear_error(self):
        self.app.state.engine.loader=lambda root:(None,{}, {'M2':'FileNotFoundError'})
        response=await self.client.post('/api/jobs',headers=self.headers,json={'keypoints':['要点'],'use_sample':True})
        job=await self.wait_job(response.json()['id'])
        self.assertEqual(job['status'],'FAILED')
        self.assertEqual(job['error']['code'],'MODEL_UNAVAILABLE')
