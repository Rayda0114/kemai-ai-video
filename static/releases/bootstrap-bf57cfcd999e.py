"""Load one checksum-pinned KEMAI release into the official MPT container."""
import hashlib
import io
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import urllib.request

url = os.environ["KEMAI_RELEASE_URL"]
expected = os.environ["KEMAI_RELEASE_SHA256"]
if not url.startswith("https://kemai-ai-video.pages.dev/releases/"):
    raise RuntimeError("Unexpected release origin")
request = urllib.request.Request(url, headers={"User-Agent":"KemaiVideoDeployment/1.0 (+https://kemai-ai.com)"})
with urllib.request.urlopen(request, timeout=60) as response:
    archive = response.read(20_000_001)
if len(archive)>20_000_000 or hashlib.sha256(archive).hexdigest()!=expected:
    raise RuntimeError("Release checksum verification failed")
target = Path(tempfile.mkdtemp(prefix="kemai-video-"))
with tarfile.open(fileobj=io.BytesIO(archive),mode="r:gz") as package:
    # A second boundary check complements the pinned digest.
    for member in package.getmembers():
        path=Path(member.name)
        if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
            raise RuntimeError("Unexpected release archive entry")
    package.extractall(target, filter="data")
os.environ.update(PYTHONPATH=str(target),KEMAI_DATA_DIR=str(target/"runtime"),
                  IMAGEIO_FFMPEG_EXE="/usr/bin/ffmpeg",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1")
if os.geteuid()==0:
    for path in [target,*target.rglob("*")]:
        os.chown(path,65534,65534)
    os.setgroups([]);os.setgid(65534);os.setuid(65534)
os.chdir(target)
os.execv(sys.executable,[sys.executable,"-m","uvicorn","server:app","--host","0.0.0.0",
                        "--port",os.environ.get("PORT","10000"),"--workers","1","--no-access-log"])
