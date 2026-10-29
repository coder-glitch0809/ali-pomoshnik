"""Video montaj (FFmpeg 7.1 - imageio-ffmpeg ichida, alohida o'rnatish shart emas).

Reels/Shorts uchun: 9:16 ga moslash (xira fon bilan), kesish, birlashtirish (o'tishlar bilan), matn va sarlavha,
avtomatik subtitr (Gemini ovozni matnga aylantiradi), musiqa, ovozli matn (TTS), tezlik, rasmlardan video
(Ken Burns), muqova. Manba: fayl yo'li yoki "oxirgi" - Telegram/saytga eng oxirgi yuborilgan video.
Natija avtomatik yuboriladi (outbox).
"""
import asyncio
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .. import outbox
from ..config import config
from . import skill

W, H, FPS = 1080, 1920, 30
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
FONT = "C\\:/Windows/Fonts/arialbd.ttf"  # drawtext uchun (":" qochiriladi)
INBOX = config.data_dir / "inbox"


def ffmpeg() -> str:
    import imageio_ffmpeg
    return shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()


def _run(args: list[str], cwd: Path | None = None, timeout: int = 1800) -> str:
    r = subprocess.run([ffmpeg(), "-hide_banner", "-y", *args], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise RuntimeError("FFmpeg xatosi: " + r.stderr.strip()[-600:])
    return r.stderr


def info(path: Path) -> dict:
    """Davomiylik, o'lcham, fps, ovoz bormi (ffprobe'siz - ffmpeg -i chiqishidan)."""
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out = r.stderr
    d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    v = re.search(r"Video: .*?(\d{2,5})x(\d{2,5})", out)
    f = re.search(r"([\d.]+) fps", out)
    return {"duration": int(d[1]) * 3600 + int(d[2]) * 60 + float(d[3]) if d else 0.0,
            "width": int(v[1]) if v else 0, "height": int(v[2]) if v else 0,
            "fps": float(f[1]) if f else 0.0, "audio": "Audio:" in out}


def _src(path: str) -> Path:
    """Fayl yo'li yoki "oxirgi" -> eng oxirgi yuborilgan video."""
    path = (path or "").strip().strip('"')
    if not path or path.lower() in ("oxirgi", "last", "latest", "охирги"):
        videos = sorted((p for p in INBOX.glob("*") if p.suffix.lower() in VIDEO_EXT), key=lambda p: p.stat().st_mtime)
        if not videos:
            raise RuntimeError("Video topilmadi: avval videoni Telegram yoki saytga yuboring yoki fayl yo'lini yozing")
        return videos[-1]
    p = Path(path)
    if not p.is_file():
        raise RuntimeError(f"Fayl topilmadi: {path}")
    return p


def _out(title: str, ext: str = "mp4") -> Path:
    return outbox.new_path(title, ext)


def _done(path: Path, note: str = "") -> str:
    outbox.register(path)
    i = info(path) if path.suffix == ".mp4" else {}
    extra = f" ({i['width']}x{i['height']}, {i['duration']:.1f} s)" if i.get("duration") else ""
    return f"Tayyor: {path.name}{extra}. {note}".strip()


def _fit(mode: str) -> str:
    """Har qanday videoni 1080x1920 ga: blur - kadr to'liq, atrofi xira fon; crop - markazdan kesiladi."""
    if mode == "crop":
        return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"
    return (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=25:2[bg];"
            f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={FPS}")


def _text_file(text: str, folder: Path, name: str) -> str:
    """drawtext matni faylda (qochirish muammolarisiz); ffmpeg cwd=folder bilan nisbiy nom beriladi."""
    # emoji shriftda yo'q (bo'sh kvadrat bo'lib chiqadi) - olib tashlanadi
    text = re.sub("[𐀀-􏿿☀-➿️‍]", "", text).strip()
    (folder / name).write_text(text, encoding="utf-8")
    return name


@skill(
    description="Video haqida: davomiyligi, o'lchami (eni x bo'yi), fps, ovozi bormi. path - fayl yo'li yoki 'oxirgi'.",
    params={"path": {"type": "string", "description": "Video fayl yo'li yoki 'oxirgi' (eng oxirgi yuborilgan)"}},
    required=[],
)
def video_info(path: str = "oxirgi") -> str:
    p = _src(path)
    i = info(p)
    return (f"{p.name}: {i['duration']:.1f} s, {i['width']}x{i['height']}, {i['fps']:.0f} fps, "
            f"ovoz: {'bor' if i['audio'] else 'yo‘q'}")


@skill(
    description=(
        "Videoni Reels/Shorts/TikTok formatiga (9:16, 1080x1920) keltiradi va kerak bo'lsa kesadi. fit='blur' - kadr to'liq "
        "ko'rinadi, atrofi xira fon (gorizontal video uchun eng yaxshisi); fit='crop' - markazdan kesib to'ldiradi."
    ),
    params={"path": {"type": "string", "description": "Video yo'li yoki 'oxirgi'"},
            "start": {"type": "number", "description": "Boshlanish soniyasi (ixtiyoriy)"},
            "end": {"type": "number", "description": "Tugash soniyasi (0 - oxirigacha)"},
            "fit": {"type": "string", "enum": ["blur", "crop"], "description": "Moslash usuli (standart blur)"}},
    required=[],
)
def video_reels(path: str = "oxirgi", start: float = 0, end: float = 0, fit: str = "blur") -> str:
    p, out = _src(path), _out("reels 9x16")
    trim = (["-ss", str(start)] if start else []) + (["-to", str(end)] if end else [])
    _run([*trim, "-i", str(p), "-filter_complex", _fit(fit), "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
          "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
    return _done(out, "9:16 Reels formatida.")


@skill(
    description=(
        "Bir nechta videoni bitta Reels'ga birlashtiradi (hammasi 9:16 ga keltiriladi), orasida silliq o'tish (fade, "
        "slideleft, circleopen, dissolve...). paths - ketma-ket fayl yo'llari."
    ),
    params={"paths": {"type": "array", "items": {"type": "string"}, "description": "Videolar ketma-ketligi (2-10 ta)"},
            "transition": {"type": "string", "description": "O'tish: fade, dissolve, slideleft, slideup, circleopen, none"},
            "seconds": {"type": "number", "description": "O'tish davomiyligi (standart 0.5)"}},
    required=["paths"],
)
def video_join(paths: list[str], transition: str = "fade", seconds: float = 0.5) -> str:
    files = [_src(x) for x in paths][:10]
    if len(files) < 2:
        raise RuntimeError("Kamida 2 ta video kerak")
    out = _out("birlashtirilgan reels")
    with tempfile.TemporaryDirectory() as tmp:
        parts, durs = [], []
        for n, f in enumerate(files):  # bir xil o'lcham/fps/ovoz - o'tishlar uchun shart
            part = Path(tmp) / f"p{n}.mp4"
            audio = [] if info(f)["audio"] else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
            _run(["-i", str(f), *audio, "-filter_complex", _fit("blur") + "[v]", "-map", "[v]", "-map", "0:a" if not audio else "1:a",
                  "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-ar", "44100",
                  "-ac", "2", str(part)])
            parts.append(part)
            durs.append(info(part)["duration"])
        if transition == "none":
            (Path(tmp) / "list.txt").write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
            _run(["-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", str(out)], cwd=Path(tmp))
        else:
            inputs = [a for p in parts for a in ("-i", str(p))]
            v, a, chain, offset = "[0:v]", "[0:a]", [], 0.0
            for n in range(1, len(parts)):
                offset += durs[n - 1] - seconds
                chain.append(f"{v}[{n}:v]xfade=transition={transition}:duration={seconds}:offset={offset:.3f}[v{n}]")
                chain.append(f"{a}[{n}:a]acrossfade=d={seconds}[a{n}]")
                v, a = f"[v{n}]", f"[a{n}]"
            _run([*inputs, "-filter_complex", ";".join(chain), "-map", v, "-map", a, "-c:v", "libx264", "-preset",
                  "veryfast", "-crf", "21", "-c:a", "aac", "-movflags", "+faststart", str(out)])
    return _done(out, f"{len(files)} ta video birlashtirildi.")


@skill(
    description=(
        "Videoga matn/sarlavha qo'yadi (hook, narx, aksiya, CTA): yarim shaffof fonli katta yozuv. position: top / center "
        "/ bottom. start/end - qaysi soniyalarda ko'rinadi (0 - butun video). Bir nechta yozuv uchun qayta chaqir."
    ),
    params={"path": {"type": "string", "description": "Video yo'li yoki 'oxirgi'"},
            "text": {"type": "string", "description": "Yozuv (\\n - yangi qator)"},
            "position": {"type": "string", "enum": ["top", "center", "bottom"]},
            "start": {"type": "number"}, "end": {"type": "number"},
            "size": {"type": "integer", "description": "Shrift o'lchami (standart 64)"}},
    required=["text"],
)
def video_text(path: str = "oxirgi", text: str = "", position: str = "top", start: float = 0, end: float = 0,
               size: int = 64) -> str:
    p, out = _src(path), _out("matnli video")
    y = {"top": "h*0.12", "center": "(h-text_h)/2", "bottom": "h*0.78"}.get(position, "h*0.12")
    enable = f":enable='between(t,{start},{end})'" if end else (f":enable='gte(t,{start})'" if start else "")
    with tempfile.TemporaryDirectory() as tmp:
        name = _text_file(text.replace("\\n", "\n"), Path(tmp), "t.txt")
        draw = (f"drawtext=fontfile='{FONT}':textfile={name}:fontsize={size}:fontcolor=white:line_spacing=12:expansion=none:"
                f"box=1:boxcolor=black@0.55:boxborderw=24:x=(w-text_w)/2:y={y}{enable}")
        _run(["-i", str(p), "-vf", draw, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "copy",
              str(out)], cwd=Path(tmp))
    return _done(out)


def _srt(video: Path, tmp: Path) -> str:
    """Ovoz -> SRT subtitr (Gemini): vaqt belgilari bilan, qisqa qatorlar."""
    from .. import providers
    from google.genai import types
    audio = tmp / "a.mp3"
    _run(["-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(audio)])
    response = providers._gemini_generate(config.gemini_fast_model, [
        types.Part.from_bytes(data=audio.read_bytes(), mime_type="audio/mpeg"),
        "Bu audioni SRT subtitr formatida yoz: aniq vaqt belgilari (00:00:01,200 --> 00:00:03,000), har bir blokda "
        "ko'pi bilan 6-7 so'z, asl tilda (asosan o'zbek). Faqat SRT matnini qaytar, boshqa hech narsa yozma."])
    text = (response.text or "").strip().strip("`")
    text = re.sub(r"^srt\s*", "", text, flags=re.I)
    if "-->" not in text:
        raise RuntimeError("Subtitr yaratilmadi (videoda nutq topilmadi)")
    return text


@skill(
    description=(
        "Videoga AVTOMATIK SUBTITR qo'shadi: nutqni matnga aylantiradi (vaqt belgilari bilan) va katta, o'qiladigan "
        "yozuv qilib videoga yopishtiradi (Reels uchun - ovozsiz ko'radiganlar ko'p). .srt fayl ham yuboriladi."
    ),
    params={"path": {"type": "string", "description": "Video yo'li yoki 'oxirgi'"}},
    required=[],
)
def video_subtitles(path: str = "oxirgi") -> str:
    p, out = _src(path), _out("subtitrli video")
    with tempfile.TemporaryDirectory() as tmp:
        srt = _srt(p, Path(tmp))
        (Path(tmp) / "s.srt").write_text(srt, encoding="utf-8")
        style = ("FontName=Arial,FontSize=13,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,"
                 "Outline=2,Shadow=0,Alignment=2,MarginV=60")
        _run(["-i", str(p), "-vf", f"subtitles=s.srt:force_style='{style}'", "-c:v", "libx264", "-preset", "veryfast",
              "-crf", "21", "-c:a", "copy", str(out)], cwd=Path(tmp))
        srt_out = out.with_suffix(".srt")
        srt_out.write_text(srt, encoding="utf-8")
        outbox.register(srt_out)
    return _done(out, "Subtitr qo'shildi (.srt ham yuborildi).")


@skill(
    description="Videoga fon musiqasi qo'shadi (asl ovoz saqlanadi, musiqa past): music - audio fayl yo'li.",
    params={"path": {"type": "string", "description": "Video yo'li yoki 'oxirgi'"},
            "music": {"type": "string", "description": "Musiqa fayli (.mp3/.m4a/.wav)"},
            "volume": {"type": "number", "description": "Musiqa balandligi 0.05-1 (standart 0.15)"}},
    required=["music"],
)
def video_music(path: str = "oxirgi", music: str = "", volume: float = 0.15) -> str:
    p, m, out = _src(path), Path(music), _out("musiqali video")
    if not m.is_file():
        raise RuntimeError(f"Musiqa fayli topilmadi: {music}")
    vol = min(max(float(volume), 0.02), 1.0)
    if info(p)["audio"]:
        mix = f"[1:a]volume={vol}[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2,loudnorm[a]"
    else:
        mix = f"[1:a]volume={vol},loudnorm[a]"
    _run(["-i", str(p), "-stream_loop", "-1", "-i", str(m), "-filter_complex", mix, "-map", "0:v", "-map", "[a]",
          "-c:v", "copy", "-c:a", "aac", "-shortest", str(out)])
    return _done(out, "Musiqa qo'shildi.")


@skill(
    description=(
        "Videoga OVOZLI MATN (diktor) qo'shadi: matnni Ali ovozida o'qiydi, asl ovozni pasaytiradi. Ssenariy matnini ber."
    ),
    params={"path": {"type": "string", "description": "Video yo'li yoki 'oxirgi'"},
            "text": {"type": "string", "description": "O'qiladigan matn"},
            "original_volume": {"type": "number", "description": "Asl ovoz balandligi 0-1 (standart 0.2)"}},
    required=["text"],
)
def video_voiceover(path: str = "oxirgi", text: str = "", original_volume: float = 0.2) -> str:
    from .. import tts
    p, out = _src(path), _out("ovozli video")
    with tempfile.TemporaryDirectory() as tmp:
        voice = Path(tmp) / "v.mp3"
        voice.write_bytes(asyncio.run(tts.synthesize(text)))
        i = info(p)
        if i["audio"]:
            mix = f"[0:a]volume={min(max(float(original_volume), 0), 1)}[o];[o][1:a]amix=inputs=2:duration=first[a]"
        else:  # apad cheksiz - video uzunligiga qirqiladi (aks holda -shortest bilan ffmpeg to'xtamaydi)
            mix = f"[1:a]apad,atrim=0:{i['duration']:.3f}[a]"
        _run(["-i", str(p), "-i", str(voice), "-filter_complex", mix, "-map", "0:v", "-map", "[a]", "-c:v", "copy",
              "-c:a", "aac", "-shortest", str(out)])
    return _done(out, "Ovozli matn qo'shildi.")


@skill(
    description="Video tezligini o'zgartiradi: 1.5 - tezroq (dinamik Reels), 0.5 - sekin (slow-motion).",
    params={"path": {"type": "string", "description": "Video yo'li yoki 'oxirgi'"},
            "factor": {"type": "number", "description": "0.25-4 (masalan 1.25, 1.5, 2, 0.5)"}},
    required=["factor"],
)
def video_speed(path: str = "oxirgi", factor: float = 1.5) -> str:
    p, out = _src(path), _out(f"tezlik {factor}x")
    k = min(max(float(factor), 0.25), 4.0)
    atempo, rest = [], k
    while rest > 2.0:
        atempo.append("atempo=2.0"); rest /= 2.0
    while rest < 0.5:
        atempo.append("atempo=0.5"); rest /= 0.5
    atempo.append(f"atempo={rest:.4f}")
    audio = ["-filter:a", ",".join(atempo)] if info(p)["audio"] else ["-an"]
    _run(["-i", str(p), "-filter:v", f"setpts=PTS/{k}", *audio, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
          str(out)])
    return _done(out, f"Tezlik {k}x.")


@skill(
    description=(
        "RASMLARDAN video (Reels kreativi): har bir rasm 9:16 da sekin kattalashadi (Ken Burns), orasida silliq o'tish, "
        "ixtiyoriy yozuvlar. Portfolio, oldin/keyin, mahsulotlar, tashqi reklama ishlari uchun."
    ),
    params={"images": {"type": "array", "items": {"type": "string"}, "description": "Rasm fayllari (2-15 ta)"},
            "seconds": {"type": "number", "description": "Har bir rasm necha soniya (standart 3)"},
            "texts": {"type": "array", "items": {"type": "string"}, "description": "Har bir rasm ustidagi yozuv (ixtiyoriy)"}},
    required=["images"],
)
def video_from_images(images: list[str], seconds: float = 3, texts: list[str] | None = None) -> str:
    files = [Path(x) for x in images if Path(x).is_file()][:15]
    if len(files) < 1:
        raise RuntimeError("Rasm topilmadi")
    out, secs, texts = _out("rasmlardan reels"), min(max(float(seconds), 1.5), 8), texts or []
    frames = round(secs * FPS)
    with tempfile.TemporaryDirectory() as tmp:
        clips = []
        for n, img in enumerate(files):
            clip = Path(tmp) / f"c{n}.mp4"
            vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
                  f"zoompan=z='min(zoom+0.0012,1.15)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}")
            if n < len(texts) and texts[n].strip():
                name = _text_file(texts[n], Path(tmp), f"t{n}.txt")
                vf += (f",drawtext=fontfile='{FONT}':textfile={name}:fontsize=68:fontcolor=white:expansion=none:box=1:"
                       f"boxcolor=black@0.55:boxborderw=24:x=(w-text_w)/2:y=h*0.12")
            _run(["-loop", "1", "-i", str(img), "-vf", vf, "-t", f"{secs}", "-c:v", "libx264", "-preset", "veryfast",
                  "-pix_fmt", "yuv420p", clip.name], cwd=Path(tmp))
            clips.append(clip)
        if len(clips) == 1:
            shutil.copy(clips[0], out)
        else:
            inputs = [a for c in clips for a in ("-i", c.name)]
            v, chain, offset = "[0:v]", [], 0.0
            for n in range(1, len(clips)):
                offset += secs - 0.5
                chain.append(f"{v}[{n}:v]xfade=transition=fade:duration=0.5:offset={offset:.3f}[v{n}]")
                v = f"[v{n}]"
            _run([*inputs, "-filter_complex", ";".join(chain), "-map", v, "-c:v", "libx264", "-preset", "veryfast",
                  "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)], cwd=Path(tmp))
    return _done(out, f"{len(files)} ta rasmdan video. Musiqa uchun video_music, ovoz uchun video_voiceover.")


@skill(
    description="Videodan MUQOVA (cover) rasm: tanlangan soniyadagi kadr + katta sarlavha. Reels muqovasi uchun.",
    params={"path": {"type": "string", "description": "Video yo'li yoki 'oxirgi'"},
            "at": {"type": "number", "description": "Qaysi soniyadagi kadr (standart 1)"},
            "title": {"type": "string", "description": "Muqovadagi sarlavha (ixtiyoriy)"}},
    required=[],
)
def video_cover(path: str = "oxirgi", at: float = 1, title: str = "") -> str:
    p, out = _src(path), _out("muqova", "jpg")
    vf = _fit("crop")
    with tempfile.TemporaryDirectory() as tmp:
        if title:
            name = _text_file(title, Path(tmp), "t.txt")
            vf += (f",drawtext=fontfile='{FONT}':textfile={name}:fontsize=84:fontcolor=white:expansion=none:box=1:boxcolor=black@0.5:"
                   f"boxborderw=30:x=(w-text_w)/2:y=(h-text_h)/2")
        _run(["-ss", str(at), "-i", str(p), "-frames:v", "1", "-vf", vf, "-q:v", "2", str(out)], cwd=Path(tmp))
    return _done(out, "Muqova tayyor.")
