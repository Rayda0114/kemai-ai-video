"""Bounded scene planning and stock downloads for the public video workflow."""
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

import requests


def split_scenes(script):
    sentences=re.findall(r'.+?(?:[。！？!?]\s*|$)',script,re.S)
    parts=[];current=''
    for sentence in sentences:
        current+=sentence
        if len(current)>=len(script)/3 and len(parts)<2:
            parts.append(current);current=''
    if current:parts.append(current)
    return parts or [script]


def allowed_url(value,kind):
    try:
        u=urlsplit(value)
        host={'video':'videos.pexels.com','photo':'images.pexels.com'}[kind]
        return u.scheme=='https' and u.hostname==host and u.port in (None,443) and not u.username and not u.password
    except (ValueError,TypeError,KeyError):return False


def validate_plan(plan,data):
    if not isinstance(plan,dict):raise ValueError('分鏡格式無法使用。')
    scenes=plan.get('scenes')
    if not isinstance(scenes,list) or not 1<=len(scenes)<=3:raise ValueError('分鏡格式無法使用，請重試。')
    if any(not isinstance(s,dict) or not isinstance(s.get('text'),str) or not s['text'].strip() for s in scenes):raise ValueError('分鏡文字無法使用。')
    script=''.join(s.get('text','') for s in scenes)
    if not 10<=len(script)<=220 or re.search(r'[<>{}\x00-\x08\x0b-\x1f\x7f]',script):raise ValueError('自動文案長度或格式無法使用，請重試。')
    if data.get('mode','script')=='script' and script!=data['script']:raise ValueError('分鏡文案與原文不一致，請重試。')
    for scene in scenes:
        if not isinstance(scene.get('query'),str) or len(scene['query'])>80:raise ValueError('素材關鍵字無法使用。')
        candidates=scene.get('candidates',[])
        if not isinstance(candidates,list) or len(candidates)>2:raise ValueError('素材清單無法使用。')
        if data.get('visuals')=='auto' and not candidates:raise ValueError('找不到合適素材，請改寫主題後重試。')
        for source in candidates:
            if not isinstance(source,dict):raise ValueError('素材清單無法使用。')
            if not allowed_url(source.get('url'),source.get('kind')):raise ValueError('素材來源不在支援範圍。')
            page=urlsplit(source.get('page',''))
            if page.scheme!='https' or page.hostname not in ('www.pexels.com','pexels.com') or page.port not in (None,443) or page.username or page.password:raise ValueError('素材來源連結無法使用。')
            source['author']=re.sub(r'[\x00-\x1f\x7f]','',str(source.get('author') or 'Pexels creator'))[:100]
            source['license']='https://www.pexels.com/license/'
    title=plan.get('title') or data.get('title') or '我的影片'
    if not isinstance(title,str) or len(title)>28 or re.search(r'[\x00-\x1f\x7f]',title):raise ValueError('自動標題格式無法使用。')
    return {'title':title,'script':script,'scenes':scenes}


def plan_story(data):
    origin=os.environ.get('PUBLIC_ORIGIN','https://kemai-ai-video.pages.dev')
    if origin!='https://kemai-ai-video.pages.dev':raise RuntimeError('自動素材服務網址尚未設定。')
    secret=os.environ.get('KEMAI_PROXY_SECRET','')
    if not secret:raise RuntimeError('自動素材服務尚未設定。')
    body={k:data.get(k,default) for k,default in (('title',''),('script',''),('mode','script'),('visuals','upload'),('aspect','9:16'))}
    if body['mode']=='script':body['parts']=split_scenes(body['script'])
    try:
        with requests.post(origin+'/api/internal/plan',json=body,headers={'X-Kemai-Proxy':secret},timeout=(10,100),allow_redirects=False,stream=True) as response:
            content=b''
            for chunk in response.iter_content(8192):
                content+=chunk
                if len(content)>65536:raise ValueError('分鏡回應過大。')
            result=json.loads(content)
            if response.status_code!=200:raise RuntimeError(result.get('detail','自動素材服務暫時無法使用。'))
    except (requests.RequestException,json.JSONDecodeError):raise RuntimeError('自動素材服務暫時無法連線，請稍後再試。') from None
    return validate_plan(result,data)


def download_stock(source,destination):
    kind=source['kind'];url=source['url']
    if not allowed_url(url,kind):raise ValueError('不支援的素材網址。')
    limit=12_000_000 if kind=='video' else 4_000_000
    started=time.monotonic();size=0
    try:
        with requests.get(url,stream=True,timeout=(10,30),allow_redirects=False,headers={'User-Agent':'KemaiVideoStudio/1.0 (+https://kemai-ai.com)'}) as response:
            expected='video/' if kind=='video' else 'image/'
            if response.status_code!=200 or not response.headers.get('content-type','').startswith(expected):raise ValueError('素材暫時無法下載。')
            if int(response.headers.get('content-length','0'))>limit:raise ValueError('素材檔案超過免費主機處理上限。')
            with Path(destination).open('wb') as output:
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>limit or time.monotonic()-started>45:raise ValueError('素材下載超過處理上限。')
                    output.write(chunk)
    except requests.RequestException:raise ValueError('素材下載暫時中斷。') from None
    if not size:raise ValueError('素材檔案沒有內容。')
    if kind=='video':
        with Path(destination).open('rb') as source_file:
            if source_file.read(12)[4:8]!=b'ftyp':raise ValueError('素材不是支援的 MP4 影片。')


def scene_durations(scenes,words,duration):
    """Use narration word timings so scene changes follow their spoken text."""
    count=lambda text:sum(c.isalnum() for c in text)
    total=sum(count(text) for _,text in words)
    original=sum(count(s['text']) for s in scenes)
    targets=[];position=0
    for scene in scenes[:-1]:position+=count(scene['text']);targets.append(position)
    ends=[]
    for target in targets:
        # ponytail: number expansion changes character counts; distribute across spoken words.
        target=target*total/max(original,1)
        passed=0;end=None
        for (a,b),word in words:
            n=count(word)
            if n and passed+n>=target:
                end=a+(b-a)*(target-passed)/n;break
            passed+=n
        # ponytail: TTS may expand numbers; proportion is the fallback without alignment.
        ends.append(end if end is not None else duration*target/max(total,1))
    frames=round(duration*24);last=0;lengths=[]
    for i,end in enumerate([*ends,duration]):
        boundary=frames if i==len(ends) else min(frames-(len(ends)-i),max(last+1,round(end*24)))
        lengths.append((boundary-last)/24);last=boundary
    return lengths
