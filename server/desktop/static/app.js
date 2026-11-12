'use strict';
const $ = id => document.getElementById(id);
const key = document.querySelector('meta[name="desktop-key"]').content;
let chosenFile=null, useSample=false, currentJob=null, currentResult=null, polling=null, objectUrl=null, starting=false, active=false;
async function api(path,options={}) {
  const response=await fetch(path,{...options,headers:{'X-Desktop-Key':key,...options.headers}});
  if(!response.ok){ let message='请求未完成，请重试。'; try{message=(await response.json()).message||message;}catch{} throw Error(message); }
  return response;
}
function message(text){$('message').textContent=text;$('message').classList.toggle('success',text.startsWith('结果已')||text.startsWith('示例已'));}
function setBusy(value){active=value;$('startButton').disabled=value;$('audioFile').disabled=value;$('keypoints').disabled=value;$('sampleButton').disabled=value;$('cancelButton').hidden=!value;}
function choose(file){
  if(active)return;
  if(!file||!file.name.toLowerCase().endsWith('.wav')){message('请选择 WAV 文件。');return;}
  if(file.size>8*1024*1024){message('文件超过 8 MB，请选择不超过 60 秒的标准 WAV。');return;}
  chosenFile=file;useSample=false;$('sampleNote').hidden=true;$('fileLabel').textContent=file.name;
  $('fileInfo').textContent=(file.size/1024).toFixed(0)+' KB · 已选择，点击开始分析';
  if(objectUrl)URL.revokeObjectURL(objectUrl);objectUrl=URL.createObjectURL(file);$('audioPreview').src=objectUrl;$('audioPreview').hidden=false;message('');
}
$('audioFile').addEventListener('change',e=>choose(e.target.files[0]));
$('drop').addEventListener('dragover',e=>{e.preventDefault();if(!active)$('drop').classList.add('drag');});
$('drop').addEventListener('dragleave',()=>$('drop').classList.remove('drag'));
$('drop').addEventListener('drop',e=>{e.preventDefault();$('drop').classList.remove('drag');choose(e.dataTransfer.files[0]);});
function points(){return $('keypoints').value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);}
$('keypoints').addEventListener('input',()=>{$('pointCount').textContent=points().length+' 个要点';});
$('sampleButton').addEventListener('click',async()=>{
  try{
    const response=await api('/api/sample');const blob=await response.blob();
    if(objectUrl)URL.revokeObjectURL(objectUrl);objectUrl=URL.createObjectURL(blob);$('audioPreview').src=objectUrl;$('audioPreview').hidden=false;
    chosenFile=null;useSample=true;$('audioFile').value='';$('fileLabel').textContent='合成中文语音示例 · 社区反诈宣传';
    $('fileInfo').textContent='8.455 秒 · 标准 PCM WAV';$('sampleNote').hidden=false;
    $('keypoints').value='调查居民需求\n组织分层反诈宣传\n回访评估宣传效果';$('pointCount').textContent='3 个要点';message('示例已准备好，点击“开始分析”。');
  }catch(error){message(error.message);}
});
function toBase64(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('文件读取失败。'));reader.readAsDataURL(file);});}
$('startButton').addEventListener('click',async()=>{
  if(starting||active)return;
  if(!chosenFile&&!useSample){message('请先选择 WAV，或试试合成语音示例。');return;}
  const values=points();if(!values.length||values.length>100||values.some(x=>x.length>1000)){message('请填写 1–100 个参考要点，每个不超过 1000 字。');return;}
  starting=true;setBusy(true);$('cancelButton').disabled=true;message('');$('resultSection').hidden=true;$('emptyState').hidden=true;$('progressSection').hidden=false;
  $('progressText').textContent='正在准备输入';$('progressFill').style.width='2%';$('jobBadge').textContent='分析中';
  try{
    const body={keypoints:values,use_sample:useSample};if(!useSample){body.name=chosenFile.name;body.audio_base64=await toBase64(chosenFile);}
    const response=await api('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    currentJob=(await response.json()).id;currentResult=null;$('cancelButton').disabled=false;poll();
  }catch(error){setBusy(false);message(error.message);$('progressSection').hidden=true;$('emptyState').hidden=false;$('jobBadge').textContent='未开始';}
  finally{starting=false;}
});
$('cancelButton').addEventListener('click',async()=>{if(!currentJob)return;try{await api('/api/jobs/'+currentJob+'/cancel',{method:'POST'});$('cancelButton').disabled=true;message('已请求取消，当前模型调用结束后即可继续。');}catch(error){message(error.message);}});
async function poll(){
  clearTimeout(polling);
  if(!currentJob)return;
  try{
    const job=await (await api('/api/jobs/'+currentJob)).json();
    $('progressText').textContent=job.stage;$('progressFill').style.width=job.progress+'%';
    const seconds=Math.max(0,Math.floor(Date.now()/1000-job.created_at));$('elapsed').textContent=String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');
    document.querySelectorAll('[data-step]').forEach(x=>x.classList.toggle('done',x.dataset.step in job.timings));
    if(job.status==='SUCCEEDED'){setBusy(false);$('cancelButton').disabled=false;$('progressSection').hidden=true;render(job.result);await refreshStatus();return;}
    if(job.status==='FAILED'||job.status==='CANCELLED'){
      setBusy(false);$('cancelButton').disabled=false;$('jobBadge').textContent=job.status==='FAILED'?'未完成':'已取消';
      $('progressSection').hidden=true;$('emptyState').hidden=false;message(job.error?.message||'任务已取消，可以重新选择音频。');await refreshStatus();return;
    }
    await refreshStatus(false);polling=setTimeout(poll,750);
  }catch(error){message('连接中断：'+error.message+' 页面会继续尝试恢复。');polling=setTimeout(poll,2000);}
}
function render(result){
  currentResult=result;currentJob=result.id;$('emptyState').hidden=true;$('resultSection').hidden=false;$('jobBadge').textContent='分析完成';
  $('coveredCount').textContent=result.matches.filter(x=>x.covered).length+' / '+result.matches.length;
  $('audioDuration').textContent=result.audio_duration_s.toFixed(1)+' 秒';$('analysisTime').textContent=(result.inference_ms/1000).toFixed(2)+' 秒';
  $('resultNotice').textContent=result.condition==='SYNTHETIC_TTS_DESKTOP_DIAGNOSTIC'?'合成语音诊断示例 · 仅验证运行流程，不计入真实录音评价。':'本地模型辅助判断 · 请结合原文复核，阈值仍待真实数据校准。';
  $('transcript').textContent=result.transcript.full_text;$('matches').replaceChildren();
  result.matches.forEach((match,index)=>{
    const box=document.createElement('article');box.className='match';
    const head=document.createElement('div');head.className='matchhead';
    const title=document.createElement('strong');title.textContent=(index+1)+'. '+(result.reference_keypoints[index]?.text||match.keypoint_id);
    const tag=document.createElement('span');tag.className='tag'+(match.covered?'':' missing');tag.textContent=match.covered?'已覆盖':'可能遗漏';
    const score=document.createElement('span');score.className='score';score.textContent=match.score.toFixed(3);
    head.append(title,tag,score);const evidence=document.createElement('p');evidence.className='evidence';evidence.textContent='依据 · '+match.evidence_text;
    box.append(head,evidence);$('matches').append(box);
  });
  const table=document.createElement('table');Object.entries(result.module_ms).forEach(([module,ms])=>{const row=document.createElement('tr');[module+' · '+({M1:'语音检测',M2:'语音转写',M3:'语义编码',M4:'要点匹配'}[module]),ms.toFixed(1)+' ms'].forEach(value=>{const td=document.createElement('td');td.textContent=value;row.append(td);});table.append(row);});$('timings').replaceChildren(table);
  $('versions').textContent='模型 '+result.model_version+' · 配置 '+result.config_version+' · 加载 '+(result.model_load_ms/1000).toFixed(1)+' 秒 · 本次总耗时 '+(result.total_ms/1000).toFixed(2)+' 秒';
  message('结果已自动保存，可下载查看。');
}
async function refreshStatus(renderHistory=true){
  const data=await (await api('/api/status')).json();
  const labels={NOT_LOADED:'本地模型待加载',LOADING:'本地模型加载中',READY:'本地模型已就绪',FAILED:'模型加载失败'};
  $('modelStatus').textContent=labels[data.model_state]||'本地模型';$('modelDot').style.background=data.model_state==='READY'?'#087e85':'#d1a04c';
  $('modelHint').textContent=data.model_state==='READY'?'后续分析复用当前模型，无需再次加载':'首次分析会加载模型，请保留启动程序';
  $('sampleButton').hidden=!data.sample_available;
  if(renderHistory){
    $('historyList').replaceChildren();if(!data.jobs.length){const p=document.createElement('p');p.className='helper';p.textContent='还没有分析任务。';$('historyList').append(p);}
    data.jobs.forEach(job=>{const row=document.createElement('div');row.className='historyrow';const name=document.createElement('strong');name.textContent=job.name;const time=document.createElement('time');time.textContent=new Date(job.created_at*1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});const label=document.createElement('span');label.textContent=({SUCCEEDED:'已完成',FAILED:'未完成',CANCELLED:'已取消',RUNNING:'分析中',QUEUED:'等待中'}[job.status]);row.append(name,time,label);if(job.status==='SUCCEEDED'){const button=document.createElement('button');button.className='textbutton';button.textContent='查看结果 →';button.disabled=active;button.onclick=async()=>{try{const full=await(await api('/api/jobs/'+job.id)).json();render(full.result);}catch(error){message(error.message);}};row.append(button);}$('historyList').append(row);});
  }
  if(data.active_job&&!currentJob){currentJob=data.active_job;setBusy(true);$('emptyState').hidden=true;$('progressSection').hidden=false;$('jobBadge').textContent='分析中';poll();}
}
$('copyButton').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(currentResult.transcript.full_text);$('copyButton').textContent='已复制';setTimeout(()=>{$('copyButton').textContent='复制文字';},1500);}catch{message('复制未成功，可在转写区域选中文字复制。');}});
async function download(kind){if(!currentResult)return;try{const response=await api('/api/jobs/'+currentResult.id+'/download/'+kind);const blob=await response.blob();const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='语音分析结果.'+kind;link.click();setTimeout(()=>URL.revokeObjectURL(url),2000);}catch(error){message(error.message);}}
$('downloadMd').addEventListener('click',()=>download('md'));$('downloadJson').addEventListener('click',()=>download('json'));
refreshStatus().catch(error=>{message('本地服务连接失败，请重新双击“打开电脑界面”。');$('modelStatus').textContent='本地服务未连接';});
