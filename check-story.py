"""Offline preview -> edit -> confirm check: python check-story.py."""
import asyncio
import copy
import io
import json
import os
from pathlib import Path
import tempfile

with tempfile.TemporaryDirectory(prefix='kemai-story-check-') as tmp:
    os.environ['KEMAI_DATA_DIR']=tmp
    os.environ.pop('RENDER',None)
    os.environ.pop('KEMAI_PROXY_SECRET',None)
    from fastapi.testclient import TestClient
    from PIL import Image
    import server
    import render
    from story import validate_plan
    async def no_external_work():await asyncio.Event().wait()
    server.consumer=no_external_work
    server.IP_LIMIT=1
    sources=[{'provider':'pexels','kind':'photo','id':str(i),'url':f'https://images.pexels.com/photos/{i}/test.jpg','page':f'https://www.pexels.com/photo/{i}/','author':'Creator','license':'https://www.pexels.com/license/'} for i in (1,2,3)]
    original='清晨泡一杯熱茶，慢慢享受。翻開書本，留一點時間給自己。'
    plan=validate_plan({'title':'慢下來','scenes':[{'text':s,'query':'tea books','candidates':copy.deepcopy(sources)} for s in ['清晨泡一杯熱茶，慢慢享受。','翻開書本，留一點時間給自己。']]},{'mode':'script','visuals':'auto','script':original})
    plan_calls=[]
    render.plan_story=lambda data: (plan_calls.append(data),copy.deepcopy(plan))[1]
    def no_voice(*args):raise AssertionError('Preview must not generate speech')
    render.voice.tts=no_voice
    with TestClient(server.app) as client:
        fields={'title':'慢下來','script':original,'mode':'script','visuals':'auto','preview':'1'}
        response=client.post('/api/jobs',data=fields)
        assert response.status_code==202,response.text
        job=response.json()['id'];folder=server.job_path(job)
        assert client.post('/api/jobs',data=fields).status_code==429
        assert client.post(f'/api/jobs/{job}/confirm',data={'edits':'{}'}).status_code==409
        render.render(folder)
        assert len(plan_calls)==1 and (folder/'draft.json').is_file() and not (folder/'video.mp4').exists()
        with server.connect() as db:db.execute("UPDATE jobs SET state='ready' WHERE id=?",(job,))
        preview=client.get(f'/api/jobs/{job}').json()
        assert preview['state']=='ready' and len(preview['draft']['scenes'][0]['candidates'])==3
        edited={'title':'我確認的標題','scenes':[{'text':'這是我修改過的第一段旁白。','candidate':1},{'text':'第二段使用我自己的圖片。','candidate':None}]}
        image=io.BytesIO();Image.new('RGB',(32,32),'green').save(image,format='PNG')
        def submit(value,content=image.getvalue()):
            return client.post(f'/api/jobs/{job}/confirm',data={'edits':json.dumps(value)},files={'scene-1':('mine.png',content,'image/png')})
        bad=copy.deepcopy(edited);bad['scenes'][0]['candidate']=9
        assert submit(bad).status_code==422
        bad=copy.deepcopy(edited);bad['scenes'][0]['url']='https://example.com/asset.mp4'
        assert submit(bad).status_code==422
        bad=copy.deepcopy(edited);bad['scenes'][0]['text']='<b>不要接受標記</b>'
        assert submit(bad).status_code==422
        assert submit(edited,b'not an image').status_code==422
        assert client.get(f'/api/jobs/{job}').json()['state']=='ready'
        assert not (folder/'confirmed.json').exists()
        accepted=submit(edited)
        assert accepted.status_code==202,accepted.text
        confirmed=json.loads((folder/'confirmed.json').read_text())
        assert confirmed['script']==''.join(s['text'] for s in edited['scenes'])
        assert confirmed['scenes'][0]['candidates']==[plan['scenes'][0]['candidates'][1]]
        assert confirmed['scenes'][1]['uploaded'] and not confirmed['scenes'][1]['candidates']
        assert (folder/'scene-1').read_bytes()==image.getvalue()
        assert submit(edited).status_code==202 # Retry the same request, never a second job.
        with server.connect() as db:assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==1
        class SpeechReached(Exception):pass
        def selected_voice(script,*args):
            assert script==confirmed['script']
            raise SpeechReached()
        render.voice.tts=selected_voice
        render.plan_story=lambda data: (_ for _ in ()).throw(AssertionError('Confirmed scenes must not call AI again'))
        try:render.render(folder)
        except SpeechReached:pass
        else:raise AssertionError('Confirmed render did not start the selected narration')
        assert client.get(f'/api/jobs/{job}/confirmed.json').status_code==404
        assert client.get(f'/api/jobs/{job}/scene-1').status_code==404
print('Passed: preview without TTS, quota counted once, draft recovery, exact edits and selected sources, validated uploads, idempotent confirmation, no second AI call.')
