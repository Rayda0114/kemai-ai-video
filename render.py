"""KEMAI public workflow using the pinned MoneyPrinterTurbo voice/video engine."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import textwrap

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor/moneyprinter"))
from imageio_ffmpeg import get_ffmpeg_exe
FFMPEG = get_ffmpeg_exe()  # Bundled FFmpeg includes libass on macOS and Linux.
from loguru import logger
logger.remove()  # Public jobs must not copy narration or user filenames into logs.
from PIL import Image, ImageDraw, ImageFont, ImageOps
from app.models.schema import VideoAspect
from app.services import voice
from moviepy.video.tools.subtitles import file_to_subtitles
logger.remove()

Image.MAX_IMAGE_PIXELS = 12_000_000
FONT = str(ROOT / "assets/NotoSansTC-Medium.ttf")
PALETTES = {"violet": ((28, 20, 51), (100, 68, 169)),
            "forest": ((12, 39, 37), (40, 111, 95)),
            "sunset": ((56, 27, 32), (158, 83, 69))}


def command(args, timeout=150):
    if args[0] == "ffmpeg": args = [FFMPEG, *args[1:]]
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError("影片編碼失敗，請稍後重試或換一張圖片。")
    return result.stdout


def probe(path):
    return json.loads(command(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                               "-of", "json", str(path)], 15))


def progress(folder, percent, message):
    temp = folder / "progress.tmp"
    temp.write_text(json.dumps({"progress": percent, "message": message}, ensure_ascii=False))
    temp.replace(folder / "progress.json")


def readable_subtitles(maker, text, target):
    """Group upstream word timings into captions that fit the smallest layout."""
    voice.create_subtitle(maker, text, str(target), word_level=True)
    if not target.is_file():
        return
    words = file_to_subtitles(str(target), encoding="utf-8")
    groups, current, start, end = [], "", 0., 0.
    for (a, b), word in words:
        # Long indivisible tokens keep bounded lines; interpolate only within that token.
        pieces = [word[i:i+28] for i in range(0,len(word),28)]
        for i, piece in enumerate(pieces):
            left = a+(b-a)*i/len(pieces); right=a+(b-a)*(i+1)/len(pieces)
            separator = " " if current and current[-1:].isascii() and piece[:1].isascii() else ""
            if current and len(current+separator+piece)>28:
                groups.append(((start,end),current));current="";separator=""
            if not current: start=left
            current+=separator+piece;end=right
    if current: groups.append(((start,end),current))
    def timestamp(t):
        ms=round(t*1000);s,ms=divmod(ms,1000);m,s=divmod(s,60);h,m=divmod(m,60)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    target.write_text("\n\n".join(f"{i+1}\n{timestamp(a)} --> {timestamp(b)}\n{line}" for i,((a,b),line) in enumerate(groups))+"\n\n",encoding="utf-8")


def prepare_image(source, output, size, theme, title):
    w, h = size
    if source:
        with Image.open(source) as image:
            if image.format not in ("JPEG", "PNG", "WEBP") or getattr(image, "n_frames", 1) != 1:
                raise ValueError("請使用靜態 JPG、PNG 或 WebP 圖片。")
            if image.width * image.height > 12_000_000 or max(image.size) > 8000:
                raise ValueError("圖片上限為 1,200 萬像素，最長邊 8,000 px。")
            image.load()
            oriented = ImageOps.fit(ImageOps.exif_transpose(image), size, Image.Resampling.LANCZOS).convert("RGBA")
            canvas = Image.new("RGBA", size, "white")
            canvas.alpha_composite(oriented)
            canvas = canvas.convert("RGB")
        shade = Image.new("RGBA", size)
        draw = ImageDraw.Draw(shade)
        draw.rectangle((0, 0, w, h), fill=(10, 10, 20, 55))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), shade).convert("RGB")
    else:
        top, bottom = PALETTES[theme]
        canvas = Image.new("RGB", size)
        draw = ImageDraw.Draw(canvas)
        for y in range(h):
            a = y / h
            draw.line((0, y, w, y), fill=tuple(round(top[k]*(1-a)+bottom[k]*a) for k in range(3)))
        draw.ellipse((w*.28, h*.12, w*1.12, h*.12+w*.84), outline=tuple(min(255,c+35) for c in bottom), width=2)
        draw.ellipse((-w*.5, h*.5, w*.5, h*.5+w), outline=bottom, width=2)
        draw.line((w*.1, h*.25, w*.22, h*.25), fill=(224, 207, 255), width=5)
        font = ImageFont.truetype(FONT, 46 if w < h else 48)
        # Title is user text, rendered as pixels; never interpreted as markup or a command.
        lines, line = [], ""
        for c in title:
            if font.getlength(line+c) > w*.76:
                lines.append(line); line = c
            else:
                line += c
        if line:
            lines.append(line)
        draw.multiline_text((w*.1, h*.30), "\n".join(lines), font=font,
                            fill=(250, 247, 255), spacing=16)
    canvas.save(output, "PNG")


def native_subtitles(source, target, size):
    """Render the upstream subtitle timings with FFmpeg instead of Python frames."""
    w,h=size
    # Linux font matching needs the bundled face's legacy family name.
    font_name="Noto Sans TC Thin"  # Name ID 1; the bundled outlines use weight 500.
    def timestamp(t):
        seconds,cs=divmod(round(t*100),100);minutes,seconds=divmod(seconds,60);hours,minutes=divmod(minutes,60)
        return f"{hours}:{minutes:02}:{seconds:02}.{cs:02}"
    header=f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{font_name},36,&H00FFFFFF,&H00FFFFFF,&H402B2016,&H402B2016,0,0,0,0,100,100,0,0,3,8,0,2,{round(w*.08)},{round(w*.08)},{round(h*.20)},1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines=[]
    for (start,end),text in file_to_subtitles(str(source),encoding="utf-8"):
        text=textwrap.fill(text,width=max(12,int(w*.8/36)))
        # User text stays text, including ASS control characters.
        text=text.replace("\\","＼").replace("{","｛").replace("}","｝").replace("\n",r"\N")
        lines.append(f"Dialogue: 0,{timestamp(start)},{timestamp(end)},Default,,0,0,0,,{text}")
    target.write_text(header+"\n".join(lines)+"\n",encoding="utf-8")


def render(folder):
    data = json.loads((folder / "input.json").read_text())
    audio = folder / "voice.mp3"
    subtitles = folder / "subtitles.srt"
    progress(folder, 8, "正在製作中文配音")
    maker = voice.tts(data["script"], data["voice"], data["rate"], str(audio))
    if maker is None or not audio.is_file() or audio.stat().st_size == 0:
        raise RuntimeError("免費配音服務暫時無法連線，請稍後重試。")
    duration = float(probe(audio)["format"]["duration"])
    if not 1 <= duration <= 60:
        raise ValueError("配音超過 60 秒，請縮短文案後重新製作。")
    progress(folder, 25, "正在對齊旁白與字幕")
    readable_subtitles(maker, data["script"], subtitles)
    if not subtitles.is_file() or subtitles.stat().st_size == 0:
        raise RuntimeError("字幕時間無法對齊，請加入標點符號後重試。")
    size = VideoAspect(data["aspect"]).to_resolution()
    photos = [folder / f"upload-{i}" for i in range(data["image_count"])] or [None]
    clips = []
    clip_duration = (duration + .15) / len(photos)
    for i, photo in enumerate(photos):
        progress(folder, 30+int(i/len(photos)*25), f"正在處理第 {i+1} 個畫面")
        frame = folder / f"frame-{i}.png"
        prepare_image(photo, frame, size, data["theme"], data["title"])
        clip = folder / f"clip-{i}.mp4"
        # One FFmpeg process per image bounds RAM independently of upload count.
        command(["ffmpeg", "-y", "-v", "error", "-threads", "1", "-loop", "1", "-i", str(frame),
                 "-t", str(clip_duration), "-vf",
                 f"zoompan=z='min(zoom+0.00035,1.08)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={size[0]}x{size[1]}:fps=24",
                 "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "25",
                 "-pix_fmt", "yuv420p", "-threads", "1", str(clip)])
        clips.append(clip)
    manifest = folder / "clips.txt"
    manifest.write_text("\n".join(f"file '{p.name}'" for p in clips))
    background = folder / "background.mp4"
    command(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "1", "-i", str(manifest),
             "-c", "copy", str(background)])
    progress(folder, 65, "正在合成 720p 影片，請保持頁面開啟")
    ass=folder/"subtitles.ass"
    native_subtitles(subtitles,ass,size)
    command(["ffmpeg", "-y", "-v", "error", "-threads", "1", "-i", str(background), "-i", str(audio),
             "-vf", f"ass=filename='{ass}':fontsdir='{ROOT/'assets'}'", "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-threads", "1",
             "-c:a", "aac", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
             "-movflags", "+faststart", "-t", str(duration), str(folder / "video.mp4")],300)
    output = probe(folder / "video.mp4")
    if not any(s["codec_type"] == "audio" for s in output["streams"]):
        raise RuntimeError("輸出音軌驗證失敗，請重試。")
    progress(folder, 100, "影片已完成，可以預覽與下載")
    (folder / "result.json").write_text(json.dumps({"duration": round(duration, 1),
        "width": size[0], "height": size[1], "bytes": (folder/"video.mp4").stat().st_size}))


if __name__ == "__main__":
    job_dir = Path(sys.argv[1]).resolve()
    try:
        render(job_dir)
    except Exception as error:
        message = str(error) if isinstance(error, (ValueError, RuntimeError)) else "影片製作失敗，請確認圖片格式後重試。"
        (job_dir/"error.json").write_text(json.dumps({"message": message}, ensure_ascii=False))
        sys.exit(1)
