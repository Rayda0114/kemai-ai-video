'use strict';
const $ = id => document.getElementById(id);
let theme = 'violet', aspect = '9:16', images = [], busy = false, pollTimer, statusTimer;
const fields = $('editor-fields');
const example = {title:'把每天，留一點給自己',script:'忙碌的生活裡，也別忘了照顧自己。每天留十分鐘，泡一杯喜歡的茶，讀幾頁書，或只是看看窗外。不用做得完美，從今天開始，把一點時間留給自己。'};

async function api(path, options = {}, timeout = 90000) {
  const response = await fetch(path, {...options, signal:AbortSignal.timeout(timeout), cache:'no-store'});
  const content = response.headers.get('content-type') || '';
  if (!content.includes('application/json')) throw new Error('免費主機正在啟動或暫時離線，請約 1 分鐘後再試。');
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(typeof result.detail === 'string' ? result.detail : '無法完成請求，請稍後重試。');
    error.status = response.status; throw error;
  }
  return result;
}

function showMessage(message, error = false) {
  $('job-panel').hidden = false;
  $('job-panel').classList.toggle('error', error);
  $('job-message').textContent = message;
}

function updatePreview() {
  $('char-count').textContent = `${Array.from($('script').value).length} / 220 字`;
  $('preview-title').textContent = $('title').value || '把每天，\n留一點給自己。';
  const sentence = $('script').value.split(/[。！？\n]/).find(s => s.trim());
  $('preview-subtitle').textContent = sentence || '你的故事，值得被聽見。';
  $('preview-frame').dataset.theme = theme;
  $('preview-frame').dataset.aspect = aspect;
  $('visual-preview').style.backgroundImage = images.length ? `linear-gradient(#14101d44,#14101d44), url("${images[0].url}")` : '';
  $('preview-title').hidden = images.length > 0;
}

function showImages() {
  $('image-list').replaceChildren();
  images.forEach((item, i) => {
    const box = document.createElement('div'); box.className = 'image-item';
    const img = document.createElement('img'); img.src = item.url; img.alt = `第 ${i+1} 張：${item.file.name}`;
    const actions = document.createElement('div'); actions.className = 'image-actions';
    [['←','向前移',i===0,()=>{[images[i-1],images[i]]=[images[i],images[i-1]];}],
     ['×','移除',false,()=>{URL.revokeObjectURL(item.url);images.splice(i,1);}],
     ['→','向後移',i===images.length-1,()=>{[images[i+1],images[i]]=[images[i],images[i+1]];}]].forEach(([text,label,disabled,action])=>{
       const button = document.createElement('button'); button.type='button';button.textContent=text;button.disabled=disabled;
       button.setAttribute('aria-label',`${label}第 ${i+1} 張圖片`);
       button.addEventListener('click',()=>{action();showImages();updatePreview();});actions.append(button);
     });
    box.append(img,actions);$('image-list').append(box);
  });
}

async function addFiles(files) {
  if (busy) return;
  if (images.length + files.length > 5) return showMessage('最多使用 5 張圖片，請先移除不需要的圖片。',true);
  const prepared = [];
  try {
    for (const file of files) {
      if (!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size > 4000000 || !file.size)
        throw new Error('請使用每張 4 MB 以內的 JPG、PNG 或 WebP 圖片。');
      const url = URL.createObjectURL(file); prepared.push({file,url});
      const image = new Image(); image.src=url; await image.decode();
      if (image.naturalWidth*image.naturalHeight > 12000000 || Math.max(image.naturalWidth,image.naturalHeight) > 8000)
        throw new Error('圖片上限為 1,200 萬像素，最長邊 8,000 px。');
    }
    images.push(...prepared);showImages();updatePreview();
  } catch(error) {
    prepared.forEach(x=>URL.revokeObjectURL(x.url));showMessage(error.message || '圖片無法讀取，請更換圖片。',true);
  }
  $('images').value='';
}

function setBusy(value) {
  busy=value;fields.disabled=value;$('generate').disabled=value;
  $('processing-cover').hidden=!value;
}

async function checkStatus() {
  try {
    const status = await api('/api/status',{},75000);
    $('status-dot').classList.toggle('ready',status.available);
    $('service-status').textContent = status.available ? (status.busy ? `主機運作中 · 目前有 ${status.busy} 支影片處理中` : '影片主機已就緒 · 可以開始製作') : '免費主機目前排隊已滿或額度已用完，請稍後再試。';
  } catch(error) {
    $('status-dot').classList.remove('ready');
    $('service-status').textContent='免費主機可能正在休眠或暫時離線；按「免費製作影片」可重新連線。';
  }
}

async function poll(id) {
  try {
    const job = await api(`/api/jobs/${id}`,{},75000);
    showMessage(job.message);$('job-progress').value=job.progress;
    $('processing-title').textContent=job.state==='queued'?'已排入影片隊列':'正在製作你的影片';
    if (job.state==='complete') {
      setBusy(false);fields.disabled=true;$('generate').disabled=true;
      $('visual-preview').hidden=true;$('result-video').hidden=false;
      $('result-video').src=`/api/jobs/${id}/video.mp4`;
      $('preview-badge').textContent='已完成';$('preview-caption').textContent=`${job.width} × ${job.height} · ${job.duration} 秒 · ${(job.bytes/1e6).toFixed(1)} MB`;
      $('downloads').hidden=false;$('download-video').href=`/api/jobs/${id}/video.mp4`;
      $('download-subtitles').href=`/api/jobs/${id}/subtitles.srt`;
      $('job-detail').textContent=`請於 ${new Date(job.expires*1000).toLocaleTimeString('zh-TW',{hour:'2-digit',minute:'2-digit'})} 前下載；主機休眠或重啟可能提早清除。`;
      $('new-video').hidden=false;checkStatus();return;
    }
    if (job.state==='failed') throw Object.assign(new Error(job.message),{status:422});
    $('job-detail').textContent='免費主機製作影片需要數分鐘，較長文案會更久；請保持此頁開啟，不必重複提交。';
    pollTimer=setTimeout(()=>poll(id),4000);
  } catch(error) {
    if ([404,422,403].includes(error.status)) {
      showMessage(error.message,true);setBusy(false);$('new-video').hidden=false;
      $('job-detail').textContent='這次沒有可下載的影片。可以調整內容後重新製作。';
      localStorage.removeItem('kemai-video-job');
    } else {
      showMessage('連線暫時中斷，正在重新查詢原本的影片，請不要重複提交。');
      pollTimer=setTimeout(()=>poll(id),12000);
    }
  }
}

$('video-form').addEventListener('submit', async event => {
  event.preventDefault();if(busy)return;
  const title=$('title').value.trim(), script=$('script').value.trim();
  if(!title || Array.from(title).length>28 || Array.from(script).length<10 || Array.from(script).length>220)
    return showMessage('請填寫標題，並提供 10–220 字旁白文案。',true);
  const form = new FormData();
  for(const [key,value] of Object.entries({title,script,theme,aspect,voice:$('voice').value,rate:$('rate').value})) form.append(key,value);
  images.forEach(item=>form.append('images',item.file));
  $('downloads').hidden=true;$('new-video').hidden=true;$('job-progress').value=0;
  setBusy(true);showMessage('正在連線並提交影片，首次使用可能需要約 1 分鐘。');
  $('job-panel').focus({preventScroll:true});
  try {
    const job = await api('/api/jobs',{method:'POST',body:form},120000);
    localStorage.setItem('kemai-video-job',JSON.stringify({id:job.id,time:Date.now()}));
    checkStatus();
    await poll(job.id);
  } catch(error) {
    setBusy(false);showMessage(error.message||'提交暫時無法完成，請稍後再試。',true);
  }
});

$('new-video').addEventListener('click',()=>{
  clearTimeout(pollTimer);localStorage.removeItem('kemai-video-job');
  $('result-video').pause();$('result-video').removeAttribute('src');$('result-video').load();
  $('result-video').hidden=true;$('visual-preview').hidden=false;$('job-panel').hidden=true;
  $('preview-badge').textContent='版面示意';$('preview-caption').textContent='畫面為排版示意；製作完成後可播放真正的影片。';
  setBusy(false);updatePreview();checkStatus();
});
$('example').addEventListener('click',()=>{$('title').value=example.title;$('script').value=example.script;updatePreview();});
for (const id of ['title','script']) $(id).addEventListener('input',updatePreview);
document.querySelectorAll('[data-theme].theme').forEach(button=>button.addEventListener('click',()=>{
  theme=button.dataset.theme;document.querySelectorAll('.theme').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));updatePreview();
}));
document.querySelectorAll('button[data-aspect]').forEach(button=>button.addEventListener('click',()=>{
  aspect=button.dataset.aspect;document.querySelectorAll('button[data-aspect]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));updatePreview();
}));
$('images').addEventListener('change',event=>addFiles([...event.target.files]));
for(const name of ['dragover','dragenter']) $('dropzone').addEventListener(name,event=>{event.preventDefault();if(!busy)$('dropzone').classList.add('dragging');});
for(const name of ['dragleave','drop']) $('dropzone').addEventListener(name,event=>{event.preventDefault();$('dropzone').classList.remove('dragging');});
$('dropzone').addEventListener('drop',event=>addFiles([...event.dataTransfer.files]));
updatePreview();checkStatus();
try {
  const saved=JSON.parse(localStorage.getItem('kemai-video-job')||'null');
  if(saved && /^[a-f0-9]{48}$/.test(saved.id) && Date.now()-saved.time<3600000){setBusy(true);poll(saved.id);}
} catch { localStorage.removeItem('kemai-video-job'); }
