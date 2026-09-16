'use strict';
const $ = id => document.getElementById(id);
let theme = 'violet', aspect = '9:16', images = [], busy = false, pollTimer, statusTimer;
let draft=null, sceneChoices=[], preparingImages=0;
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
  const topic=$('mode').value==='topic', automatic=$('visuals').value==='auto';
  $('script-label').textContent=topic?'影片主題':'旁白文案';
  $('script').minLength=topic?2:10;
  $('script').placeholder=topic?'例：教咖啡新手如何在家享受手沖咖啡，語氣輕鬆溫暖。':'貼上完整旁白文案，加入逗號與句號，配音會更自然。';
  $('script-help').textContent=topic?'2–220 字，說清楚主題與重點。AI 會寫成短篇旁白並安排分鏡。':'10–220 字，保留你的原文配音；建議 60–150 字，最長 60 秒。';
  $('manual-visuals').hidden=automatic;$('auto-help').hidden=!automatic;
  $('generate').textContent=automatic?'免費安排分鏡 →':'免費製作影片 ↗';
  $('char-count').textContent = `${Array.from($('script').value).length} / 220 字`;
  $('preview-title').textContent = $('title').value || '把每天，\n留一點給自己。';
  const sentence = $('script').value.split(/[。！？\n]/).find(s => s.trim());
  $('preview-subtitle').textContent = sentence || '你的故事，值得被聽見。';
  $('preview-frame').dataset.theme = theme;
  $('preview-frame').dataset.aspect = aspect;
  $('visual-preview').style.backgroundImage = !automatic && images.length ? `linear-gradient(#14101d44,#14101d44), url("${images[0].url}")` : '';
  $('preview-title').hidden = !automatic && images.length > 0;
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
      prepared.push(await readImage(file));
    }
    images.push(...prepared);showImages();updatePreview();
  } catch(error) {
    prepared.forEach(x=>URL.revokeObjectURL(x.url));showMessage(error.message || '圖片無法讀取，請更換圖片。',true);
  }
  $('images').value='';
}

async function readImage(file) {
  if (!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size>4000000 || !file.size)
    throw new Error('請使用每張 4 MB 以內的 JPG、PNG 或 WebP 圖片。');
  const url=URL.createObjectURL(file);
  try {
    const image=new Image();image.src=url;await image.decode();
    if(image.naturalWidth*image.naturalHeight>12000000 || Math.max(image.naturalWidth,image.naturalHeight)>8000)
      throw new Error('圖片上限為 1,200 萬像素，最長邊 8,000 px。');
    return {file,url};
  } catch(error) {URL.revokeObjectURL(url);throw error;}
}

function clearDraft() {
  sceneChoices.forEach(s=>{if(s.upload)URL.revokeObjectURL(s.upload.url);});
  sceneChoices=[];draft=null;$('scene-list').replaceChildren();
  $('story-fields').hidden=true;$('editor-fields').hidden=false;$('initial-submit').hidden=false;
}

function showDraft(job) {
  clearDraft();draft={...job.draft,id:job.id,aspect:job.aspect};
  $('draft-title').value=draft.title;
  $('story-fields').hidden=false;$('editor-fields').hidden=true;$('initial-submit').hidden=true;
  const count=()=>$('draft-count').textContent=`${sceneChoices.reduce((n,s)=>n+Array.from(s.text.value.trim()).length,0)} / 220 字`;
  draft.scenes.forEach((scene,i)=>{
    const card=document.createElement('article');card.className='scene-card';
    const heading=document.createElement('h3');heading.textContent=`分鏡 ${i+1}`;
    const media=document.createElement('div');media.className='scene-media';media.style.aspectRatio=draft.aspect.replace(':','/');media.style.maxWidth={'9:16':'169px','1:1':'300px','16:9':'533px'}[draft.aspect];
    const credit=document.createElement('p');credit.className='helper';
    const note=document.createElement('p');note.className='helper';note.setAttribute('role','status');
    const text=document.createElement('textarea');text.id=`scene-text-${i}`;text.maxLength=220;text.value=scene.text;text.rows=3;
    text.addEventListener('input',count);
    const label=document.createElement('label');label.htmlFor=text.id;label.textContent=`第 ${i+1} 段旁白`;
    const actions=document.createElement('div');actions.className='scene-actions';
    const swap=document.createElement('button');swap.type='button';swap.className='button';
    const upload=document.createElement('input');upload.type='file';upload.accept='image/jpeg,image/png,image/webp';upload.id=`scene-upload-${i}`;upload.className='scene-upload';
    const uploadLabel=document.createElement('label');uploadLabel.htmlFor=upload.id;uploadLabel.textContent='換成自己的圖片（每張 4 MB）';
    const choice={candidate:0,upload:null,text};sceneChoices.push(choice);
    function display() {
      media.replaceChildren();credit.replaceChildren();
      const source=scene.candidates[choice.candidate];
      const player=document.createElement(!choice.upload && source.kind==='video'?'video':'img');
      player.src=choice.upload?.url || source.url;
      if(!choice.upload && source.kind==='video') {
        player.controls=true;player.muted=true;player.playsInline=true;player.preload='metadata';
        if(source.poster)player.poster=source.poster;
        player.setAttribute('aria-label',`第 ${i+1} 段素材預覽，原音不會用於成片`);
      } else player.alt=`第 ${i+1} 段圖片預覽`;
      player.addEventListener('error',()=>{note.textContent='這個素材暫時無法預覽，請換一個素材或上傳圖片。';});
      media.append(player);
      if(choice.upload){credit.textContent=choice.upload.file.name;note.textContent='將使用這張圖片，並配上本段旁白。';}
      else {
        const link=document.createElement('a');link.href=source.page;link.target='_blank';link.rel='noopener';
        link.textContent=`${source.author} / ${source.provider==='pixabay'?'Pixabay':'Pexels'} ↗`;credit.append(link);
        note.textContent=`候選 ${choice.candidate+1} / ${scene.candidates.length} · ${source.kind==='video'?'影片可點播放預覽':'圖片'}`;
      }
      swap.textContent=choice.upload?'改回素材庫':'換一個素材 ↻';swap.disabled=!choice.upload && scene.candidates.length<2;
    }
    swap.addEventListener('click',()=>{
      if(busy)return;
      if(choice.upload){URL.revokeObjectURL(choice.upload.url);choice.upload=null;upload.value='';}
      else choice.candidate=(choice.candidate+1)%scene.candidates.length;
      display();
    });
    upload.addEventListener('change',async()=>{
      if(busy || !upload.files[0])return;
      preparingImages++;$('confirm-story').disabled=true;
      try {
        const image=await readImage(upload.files[0]);
        if(busy || !sceneChoices.includes(choice)){URL.revokeObjectURL(image.url);return;}
        if(choice.upload)URL.revokeObjectURL(choice.upload.url);
        choice.upload=image;display();
      } catch(error){showMessage(error.message||'圖片無法讀取，請更換圖片。',true);upload.value='';}
      finally {preparingImages--;$('confirm-story').disabled=busy || preparingImages>0;}
    });
    actions.append(swap);card.append(heading,media,credit,note,actions,uploadLabel,upload,label,text);$('scene-list').append(card);display();
  });
  count();setBusy(false);
  $('draft-expiry').textContent=`請於 ${new Date(job.expires*1000).toLocaleTimeString('zh-TW',{hour:'2-digit',minute:'2-digit'})} 前確認。修改暫存在此頁；重新整理會恢復初始分鏡。`;
  $('job-detail').textContent='尚未配音或剪輯；請逐段檢查內容，再按「確認分鏡並製作影片」。';
  $('story-fields').scrollIntoView({behavior:'smooth',block:'start'});
}

function setBusy(value) {
  busy=value;fields.disabled=value;$('generate').disabled=value;
  $('story-fields').disabled=value;$('confirm-story').disabled=value || preparingImages>0;
  if(value)document.querySelectorAll('.scene-media video').forEach(video=>video.pause());
  $('processing-cover').hidden=!value;
  if(value)$('music-preview').pause();
}

function updateMusic() {
  const track=$('music').value, player=$('music-preview');
  player.pause();player.removeAttribute('src');
  $('music-controls').hidden=track==='none';
  if(['warm','bright','calm'].includes(track))player.src=`/music/${track}.mp3`;
  player.load();
}

async function checkStatus() {
  try {
    const status = await api('/api/status',{},75000);
    $('status-dot').classList.toggle('ready',status.available);
    $('service-status').textContent = status.available ? (status.busy ? `主機運作中 · 目前有 ${status.busy} 支影片處理中` : '影片主機已就緒 · 可以開始製作') : '免費主機目前排隊已滿或額度已用完，請稍後再試。';
  } catch(error) {
    $('status-dot').classList.remove('ready');
    $('service-status').textContent='免費主機可能正在休眠或暫時離線；稍後按製作按鈕可重新連線。';
  }
}

async function poll(id) {
  try {
    const job = await api(`/api/jobs/${id}`,{},75000);
    showMessage(job.message);$('job-progress').value=job.progress;
    $('processing-title').textContent=job.state==='queued'?'已排入影片隊列':'正在製作你的影片';
    if(job.state==='ready'){showDraft(job);return;}
    if (job.state==='complete') {
      clearDraft();
      setBusy(false);
      $('visual-preview').hidden=true;$('result-video').hidden=false;
      $('preview-frame').dataset.aspect=job.width===job.height?'1:1':job.width>job.height?'16:9':'9:16';
      $('result-video').src=`/api/jobs/${id}/video.mp4`;
      $('preview-badge').textContent='已完成';$('preview-caption').textContent=`${job.width} × ${job.height} · ${job.duration} 秒 · ${(job.bytes/1e6).toFixed(1)} MB`;
      $('downloads').hidden=false;$('download-video').href=`/api/jobs/${id}/video.mp4`;
      $('download-subtitles').href=`/api/jobs/${id}/subtitles.srt`;
      $('download-sources').href=`/api/jobs/${id}/sources.txt`;
      $('result-info').hidden=false;$('result-script').textContent=job.script||'';
      $('source-list').replaceChildren();
      (job.sources||[]).forEach((source,i)=>{
        const li=document.createElement('li'), link=document.createElement('a');
        const pixabay=source.provider==='pixabay', provider=pixabay?'Pixabay':'Pexels';
        link.textContent=`畫面 ${source.scene||i+1}：${source.author} / ${provider}（${source.kind==='video'?'影片':'圖片'}）`;
        try {const url=new URL(source.page);if(url.protocol==='https:' && !url.username && !url.password && (!url.port || url.port==='443') && (pixabay?['pixabay.com','www.pixabay.com']:['www.pexels.com','pexels.com']).includes(url.hostname))link.href=url.href;}catch{}
        link.target='_blank';link.rel='noopener';li.append(link);$('source-list').append(li);
      });
      (job.uploaded_scenes||[]).forEach(i=>{const li=document.createElement('li');li.textContent=`畫面 ${i}：你上傳的圖片`;$('source-list').append(li);});
      if(job.music_name){const li=document.createElement('li');li.textContent=`配樂：${job.music_name}`;$('source-list').append(li);}
      $('job-detail').textContent=`請於 ${new Date(job.expires*1000).toLocaleTimeString('zh-TW',{hour:'2-digit',minute:'2-digit'})} 前下載；主機休眠或重啟可能提早清除。`;
      $('new-video').hidden=false;checkStatus();return;
    }
    if (job.state==='failed') throw Object.assign(new Error(job.message),{status:422});
    $('job-detail').textContent='免費主機製作影片需要數分鐘，較長文案會更久；請保持此頁開啟，不必重複提交。';
    pollTimer=setTimeout(()=>poll(id),4000);
  } catch(error) {
    if ([404,422,403].includes(error.status)) {
      clearDraft();showMessage(error.message,true);setBusy(false);$('new-video').hidden=false;
      $('job-detail').textContent='這次沒有可下載的影片。可以調整內容後重新製作。';
      localStorage.removeItem('kemai-video-job');
    } else {
      showMessage('連線暫時中斷，正在重新查詢原本的影片，請不要重複提交。');
      pollTimer=setTimeout(()=>poll(id),12000);
    }
  }
}

$('video-form').addEventListener('submit', async event => {
  event.preventDefault();if(busy || draft)return;
  const title=$('title').value.trim(), script=$('script').value.trim();
  const mode=$('mode').value,visuals=$('visuals').value;
  if(Array.from(title).length>28 || Array.from(script).length<(mode==='topic'?2:10) || Array.from(script).length>220)
    return showMessage('請提供 2–220 字主題或 10–220 字旁白文案，標題最多 28 字。',true);
  const form = new FormData();
  for(const [key,value] of Object.entries({title,script,mode,visuals,theme,aspect,voice:$('voice').value,rate:$('rate').value,music:$('music').value,music_volume:Number($('music-volume').value)/100})) form.append(key,value);
  if(visuals==='upload')images.forEach(item=>form.append('images',item.file));
  else form.append('preview','1');
  $('result-info').hidden=true;
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

$('confirm-story').addEventListener('click',async()=>{
  if(busy || preparingImages || !draft)return;
  const scenes=sceneChoices.map(s=>({text:s.text.value.trim(),candidate:s.upload?null:s.candidate}));
  const script=scenes.map(s=>s.text).join(''),title=$('draft-title').value.trim();
  if(scenes.some(s=>!s.text) || Array.from(script).length<10 || Array.from(script).length>220 || /[<>{}]/.test(script) || Array.from(title).length>28)
    return showMessage('每段旁白都要有文字，合計 10–220 字，請移除標籤與大括號；標題最多 28 字。',true);
  const form=new FormData();form.append('edits',JSON.stringify({title,scenes}));
  sceneChoices.forEach((s,i)=>{if(s.upload)form.append(`scene-${i}`,s.upload.file);});
  setBusy(true);showMessage('正在提交已確認的分鏡，接著開始配音與剪輯。');
  try {
    const job=await api(`/api/jobs/${draft.id}/confirm`,{method:'POST',body:form},120000);
    localStorage.setItem('kemai-video-job',JSON.stringify({id:job.id,time:Date.now()}));
    await poll(job.id);
  } catch(error){setBusy(false);showMessage(error.message||'提交未完成，可再按確認查詢同一支影片。',true);}
});
$('restart-story').addEventListener('click',()=>{
  if(busy)return;clearDraft();localStorage.removeItem('kemai-video-job');showMessage('已返回設定。重新安排分鏡會使用另一次免費名額。');updatePreview();
});

$('new-video').addEventListener('click',()=>{
  clearTimeout(pollTimer);localStorage.removeItem('kemai-video-job');
  clearDraft();
  $('result-video').pause();$('result-video').removeAttribute('src');$('result-video').load();
  $('result-video').hidden=true;$('visual-preview').hidden=false;$('job-panel').hidden=true;
  $('result-info').hidden=true;$('downloads').hidden=true;$('new-video').hidden=true;
  $('preview-badge').textContent='版面示意';$('preview-caption').textContent='畫面為排版示意；製作完成後可播放真正的影片。';
  setBusy(false);updatePreview();checkStatus();
});
$('example').addEventListener('click',()=>{$('title').value=example.title;$('script').value=$('mode').value==='topic'?'忙碌上班族每天留一點時間給自己，泡茶、閱讀、欣賞窗外風景，語氣溫暖。':example.script;updatePreview();});
for(const id of ['mode','visuals'])$(id).addEventListener('change',updatePreview);
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
$('music').addEventListener('change',updateMusic);
$('music-volume').addEventListener('input',()=>{$('music-volume-value').textContent=`${$('music-volume').value}%`;});
$('music-preview').addEventListener('play',()=>{if(busy)$('music-preview').pause();else $('result-video').pause();});
$('result-video').addEventListener('play',()=>$('music-preview').pause());
updatePreview();updateMusic();checkStatus();
try {
  const saved=JSON.parse(localStorage.getItem('kemai-video-job')||'null');
  if(saved && /^[a-f0-9]{48}$/.test(saved.id) && Date.now()-saved.time<3600000){setBusy(true);poll(saved.id);}
} catch { localStorage.removeItem('kemai-video-job'); }
