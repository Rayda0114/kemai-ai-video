"""Package only runtime code/assets; never include jobs, logs, keys or Git data."""
import hashlib
import gzip
import io
import json
from pathlib import Path
import tarfile

root=Path(__file__).resolve().parent
paths=[root/name for name in ('server.py','render.py','requirements.txt')]
paths += sorted((root/'vendor').rglob('*.py'))
paths += [root/'vendor/moneyprinter/config.toml',root/'vendor/moneyprinter/LICENSE',root/'vendor/moneyprinter/UPSTREAM.md']
paths += [root/'assets/NotoSansTC-Medium.ttf',root/'assets/OFL.txt']
paths += sorted(p for p in (root/'static').iterdir() if p.is_file() and p.suffix in ('.html','.css','.js','.svg','.txt','.xml') and not p.name.startswith('_'))
out=root/'static/releases';out.mkdir(exist_ok=True)
buffer=io.BytesIO()
with gzip.GzipFile(fileobj=buffer,mode='wb',mtime=0) as compressed, tarfile.open(fileobj=compressed,mode='w') as package:
    for path in paths:
        info=package.gettarinfo(str(path),str(path.relative_to(root)))
        info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
        with path.open('rb') as handle:package.addfile(info,handle)
body=buffer.getvalue();digest=hashlib.sha256(body).hexdigest()
name=f'kemai-{digest[:12]}.tar.gz';(out/name).write_bytes(body)
bootstrap=(root/'bootstrap.py').read_bytes();bootsha=hashlib.sha256(bootstrap).hexdigest()
bootname=f'bootstrap-{bootsha[:12]}.py';(out/bootname).write_bytes(bootstrap)
manifest={'release_url':f'https://kemai-ai-video.pages.dev/releases/{name}','release_sha256':digest,
          'bootstrap_url':f'https://kemai-ai-video.pages.dev/releases/{bootname}','bootstrap_sha256':bootsha,'bytes':len(body)}
(out/'release.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest))
