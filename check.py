"""Run with: python check.py. Uses a temporary DB, never production jobs."""
import os
from pathlib import Path
import tempfile
import secrets
import time

with tempfile.TemporaryDirectory(prefix="kemai-video-check-") as tmp:
    os.environ["KEMAI_DATA_DIR"] = tmp
    os.environ.pop("RENDER", None)
    os.environ.pop("KEMAI_PROXY_SECRET", None)
    from fastapi.testclient import TestClient
    import server
    with TestClient(server.app) as client:
        assert client.get('/api/status').json()['available'] is True
        assert client.get('/api/jobs/not-a-job').status_code == 404
        assert client.get('/api/jobs/'+secrets.token_hex(24)).status_code == 404
        assert client.post('/api/jobs',data={'title':'test','script':'too short'}).status_code == 422
        assert client.post('/api/jobs',data={'title':'測試','script':'這是一段合法長度的測試文字。'},headers={'Origin':'https://unrelated.example'}).status_code == 403
        assert client.post('/api/jobs',content=b'a',headers={'Content-Length':'22000000'}).status_code == 413
        assert client.post('/api/jobs',data={'title':'測試','script':'<script>這是一段測試文字</script>'}).status_code == 422
        assert client.post('/api/jobs',data={'title':'測試','script':'這是一段合法長度的測試文字。'},files={'images':('bad.svg',b'<svg/>','image/svg+xml')}).status_code == 422
        # Exercise complete, expired and unlisted-file access without a paid/external call.
        job = secrets.token_hex(24);folder=server.job_path(job);folder.mkdir()
        (folder/'video.mp4').write_bytes(b'test-output')
        (folder/'result.json').write_text('{"duration":1,"width":720,"height":1280,"bytes":11}')
        with server.connect() as db:
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)',(job,'test',time.time(),time.time()+100,'complete',''))
        assert client.get(f'/api/jobs/{job}/video.mp4').content == b'test-output'
        assert client.get(f'/api/jobs/{job}/input.json').status_code == 404
        with server.connect() as db: db.execute('UPDATE jobs SET expires=? WHERE id=?',(time.time()-1,job))
        assert client.get(f'/api/jobs/{job}/video.mp4').status_code == 404
        server.SECRET='test-gateway-secret'
        assert client.get('/api/status').status_code == 403
        assert client.get('/api/status',headers={'x-kemai-proxy':server.SECRET}).status_code == 200
        server.SECRET=''
    from render import native_subtitles
    source=Path(tmp)/'captions.srt';target=Path(tmp)/'captions.ass'
    source.write_text('1\n00:00:59,999 --> 00:01:01,011\n測試{文字}\\N，保留內容\n\n',encoding='utf-8')
    native_subtitles(source,target,(720,1280))
    ass=target.read_text()
    assert 'Style: Default,Noto Sans TC Thin,36,' in ass
    assert 'PlayResX: 720' in ass and 'PlayResY: 1280' in ass
    assert 'Dialogue: 0,0:01:00.00,0:01:01.01,' in ass
    assert '測試｛文字｝＼N，保留內容' in ass
    from render import readable_subtitles,voice
    original_writer=voice.create_subtitle
    try:
        voice.create_subtitle=lambda maker,text,path,**kw: Path(path).write_text('1\n00:00:00,000 --> 00:00:03,000\n'+'字'*28+'\n\n2\n00:00:03,000 --> 00:00:04,000\n最後一句\n\n',encoding='utf-8')
        readable_subtitles(None,'',source)
    finally:voice.create_subtitle=original_writer
    native_subtitles(source,target,(720,1280))
    assert target.read_text().count('Dialogue:')==2 and '最後一句' in target.read_text()
    assert '字'*16+r'\N'+'字'*12 in target.read_text()
    print('Passed: validation, upload limits, origin, expiry, file allowlist, gateway authentication, subtitle timing and literal text.')
