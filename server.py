"""Small, bounded public API. Never expose MoneyPrinterTurbo's admin/file API."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import sqlite3
import sys
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Literal

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("KEMAI_DATA_DIR", ROOT / "runtime")).resolve()
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / "jobs.sqlite3"
SALT = secrets.token_bytes(32)
SECRET = os.environ.get("KEMAI_PROXY_SECRET", "")
ORIGIN = os.environ.get("PUBLIC_ORIGIN", "https://kemai-ai-video.pages.dev")
MAX_BODY = 21_000_000
TTL = 1800
JOB_TIMEOUT = 600
IP_LIMIT = int(os.environ.get("DAILY_IP_LIMIT", "3"))
GLOBAL_LIMIT = int(os.environ.get("DAILY_GLOBAL_LIMIT", "30"))
ID = re.compile(r"^[a-f0-9]{48}$")
upload_lock = asyncio.Semaphore(1)


def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    return db


class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=28)
    script: str = Field(min_length=10, max_length=220)
    voice: Literal["zh-TW-HsiaoChenNeural", "zh-TW-YunJheNeural", "zh-TW-HsiaoYuNeural"] = "zh-TW-HsiaoChenNeural"
    aspect: Literal["9:16", "16:9", "1:1"] = "9:16"
    rate: Literal[0.9, 1.0, 1.1] = 1.0
    theme: Literal["violet", "forest", "sunset"] = "violet"


def clean_parameters(fields):
    try:
        fields["rate"] = float(fields.get("rate", "1"))
        result = Parameters.model_validate(fields)
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, "請填寫 1–28 字標題、10–220 字文案，並選擇有效的影片設定。")
    if re.search(r"[\x00-\x08\x0b-\x1f\x7f]", result.title+result.script):
        raise HTTPException(422, "文字包含無法處理的控制字元。")
    if any(c in result.script for c in "<>{}"):
        raise HTTPException(422, "文案請使用純文字，移除標籤與大括號。")
    return result


def job_path(job_id):
    if not ID.fullmatch(job_id):
        raise HTTPException(404, "找不到這支影片，或影片已到期。")
    return DATA / job_id


def job_row(job_id):
    job_path(job_id)
    with connect() as db:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None or row["expires"] < time.time():
        raise HTTPException(404, "影片已到期或主機曾重啟，請重新製作。")
    return dict(row)


def purge_expired():
    # Only our server-created, randomly named runtime directories are disposable.
    with connect() as db:
        expired = db.execute("SELECT id FROM jobs WHERE expires < ? AND state NOT IN ('queued','running')", (time.time(),)).fetchall()
        for row in expired:
            shutil.rmtree(job_path(row["id"]), ignore_errors=True)
        db.execute("DELETE FROM jobs WHERE created < ? AND state NOT IN ('queued','running')", (time.time()-86400,))


async def consumer():
    # ponytail: one renderer per instance; use a durable queue before adding instances.
    while True:
        purge_expired()
        with connect() as db:
            row = db.execute("SELECT id FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET state='running' WHERE id=?", (row["id"],))
        if row is None:
            await asyncio.sleep(2)
            continue
        folder = job_path(row["id"])
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(ROOT/"render.py"), str(folder),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True)
            code = await asyncio.wait_for(process.wait(), JOB_TIMEOUT)
            state = "complete" if code == 0 and (folder/"video.mp4").is_file() else "failed"
            if state == "failed":
                error = "影片製作失敗，請稍後重試。"
                if (folder/"error.json").is_file():
                    error = json.loads((folder/"error.json").read_text())["message"]
            else:
                error = ""
        except (TimeoutError, asyncio.CancelledError):
            if process and process.returncode is None:
                os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
            with connect() as db:
                db.execute("UPDATE jobs SET state='failed',error=?,expires=? WHERE id=?",
                           ("本次處理逾時或服務重新啟動，請重試。", time.time()+TTL, row["id"]))
            if asyncio.current_task().cancelling():
                raise
            continue
        except Exception:
            state, error = "failed", "影片主機暫時無法處理，請稍後再試。"
        with connect() as db:
            db.execute("UPDATE jobs SET state=?,error=?,expires=? WHERE id=?",
                       (state, error, time.time()+TTL, row["id"]))


@asynccontextmanager
async def lifespan(app):
    if os.environ.get("RENDER") and not SECRET:
        raise RuntimeError("KEMAI_PROXY_SECRET must be configured before public deployment")
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, client TEXT, created REAL, expires REAL, state TEXT, error TEXT DEFAULT '')")
        db.execute("UPDATE jobs SET state='failed',error='主機曾重啟，請重新製作。',expires=? WHERE state IN ('running','queued')", (time.time()+TTL,))
    worker = asyncio.create_task(consumer())
    yield
    worker.cancel()
    try:
        await worker
    except asyncio.CancelledError:
        pass


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def headers_and_gateway(request, call_next):
    if request.url.path.startswith("/api/"):
        if SECRET and not hmac.compare_digest(request.headers.get("x-kemai-proxy", ""), SECRET):
            return JSONResponse({"detail":"請從客脈影片工坊使用此服務。"}, 403)
        if request.method == "POST":
            origin = request.headers.get("origin", "")
            allowed = {ORIGIN, "http://localhost:4181", "http://127.0.0.1:4181"}
            if origin and origin not in allowed:
                return JSONResponse({"detail":"此網頁無法提交影片。"}, 403)
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                length = -1
            if not 0 < length <= MAX_BODY:
                return JSONResponse({"detail":"上傳總量上限為 20 MB。"}, 413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.exception_handler(HTTPException)
async def http_error(request, error):
    return JSONResponse({"detail": error.detail}, error.status_code, headers=error.headers)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/status")
def status():
    with connect() as db:
        count = db.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]
        used = db.execute("SELECT COUNT(*) FROM jobs WHERE created >= ? AND state != 'failed'", (time.time()-86400,)).fetchone()[0]
    return {"available": count < 4 and used < GLOBAL_LIMIT, "busy": count, "daily_ip_limit": IP_LIMIT,
            "remaining_today": max(0, GLOBAL_LIMIT-used), "max_seconds":60, "retention_minutes":30}


@app.post("/api/jobs", status_code=202)
async def create_job(request: Request):
    async with upload_lock:
        client_ip = request.headers.get("x-kemai-ip", "") if SECRET else request.client.host
        client = hmac.new(SALT, client_ip.encode(), hashlib.sha256).hexdigest()
        with connect() as db:
            active = db.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]
            recent = db.execute("SELECT client,state FROM jobs WHERE created >= ? AND state != 'failed'", (time.time()-86400,)).fetchall()
        if active >= 4:
            raise HTTPException(429, "目前排隊已滿，請稍後再試。")
        if len(recent) >= GLOBAL_LIMIT:
            raise HTTPException(429, "今天的免費生成名額已用完，請明天再來。")
        if sum(r["client"] == client for r in recent) >= IP_LIMIT:
            raise HTTPException(429, f"每個網路來源 24 小時可免費製作 {IP_LIMIT} 支影片，請稍後再來。")
        if sum(p.stat().st_size for p in DATA.rglob('*') if p.is_file()) > 450_000_000:
            raise HTTPException(503, "暫存空間使用中，請稍後再試。")
        async with request.form(max_files=5, max_fields=6, max_part_size=4096) as form:
            allowed_fields = {"title", "script", "voice", "aspect", "rate", "theme", "images"}
            if any(key not in allowed_fields for key in form.keys()):
                raise HTTPException(422, "無法辨識的影片設定。")
            fields = {k:v for k,v in form.items() if isinstance(v,str)}
            params = clean_parameters(fields)
            images = form.getlist("images")
            if any(isinstance(i,str) or not i.filename for i in images):
                raise HTTPException(422, "請重新選擇圖片。")
            job_id = secrets.token_hex(24)
            folder = job_path(job_id)
            folder.mkdir(mode=0o700)
            try:
                total = 0
                for i, image in enumerate(images):
                    if Path(image.filename).suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                        raise HTTPException(422, "只接受 JPG、PNG、WebP 圖片。")
                    size = 0
                    with (folder/f"upload-{i}").open("wb") as output:
                        while chunk := await image.read(65536):
                            size += len(chunk); total += len(chunk)
                            if size > 4_000_000 or total > 20_000_000:
                                raise HTTPException(413, "每張圖片上限 4 MB、全部上限 20 MB。")
                            output.write(chunk)
                (folder/"input.json").write_text(json.dumps({**params.model_dump(),"image_count":len(images)},ensure_ascii=False))
                with connect() as db:
                    db.execute("INSERT INTO jobs(id,client,created,expires,state) VALUES(?,?,?,?,?)",
                               (job_id, client, time.time(), time.time()+JOB_TIMEOUT*4+TTL, "queued"))
            except BaseException:
                shutil.rmtree(folder, ignore_errors=True)
                raise
    return {"id":job_id, "state":"queued"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    row = job_row(job_id)
    folder = job_path(job_id)
    result = {"id":job_id,"state":row["state"],"expires":row["expires"],"progress":0,
              "message":"已排入隊列，輪到你時會自動開始。"}
    if row["state"] == "failed":
        result.update(message=row["error"], progress=0)
    elif row["state"] in ("running", "complete"):
        try:
            result.update(json.loads((folder/"progress.json").read_text()))
        except (FileNotFoundError, json.JSONDecodeError):
            result.update(progress=3, message="正在啟動影片引擎")
        if row["state"] == "complete":
            result.update(json.loads((folder/"result.json").read_text()))
    return result


@app.get("/api/jobs/{job_id}/{filename}")
def download(job_id: str, filename: str):
    row = job_row(job_id)
    if row["state"] != "complete" or filename not in ("video.mp4", "subtitles.srt"):
        raise HTTPException(404, "檔案尚未完成或不存在。")
    return FileResponse(job_path(job_id)/filename,
                        media_type="video/mp4" if filename.endswith("mp4") else "text/plain; charset=utf-8",
                        filename="kemai-video.mp4" if filename.endswith("mp4") else "kemai-subtitles.srt")


app.mount("/", StaticFiles(directory=ROOT/"static", html=True), name="website")


class BodyLimit:
    """Count actual streamed bytes, including a falsely declared Content-Length."""
    def __init__(self, inner): self.inner = inner
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.inner(scope, receive, send)
        size = 0
        async def limited_receive():
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > MAX_BODY:
                raise HTTPException(413, "上傳總量上限為 20 MB。")
            return message
        await self.inner(scope, limited_receive, send)


app = BodyLimit(app)
