"""Video studiya plagini: Ali o'zi kontent yozadi va o'zi tayyor video yasaydi.

Zanjir (bitta so'rov bilan): mavzu -> AI ssenariy (hook, sahnalar, diktor matni, caption, hashtaglar)
-> har sahnaga ovoz (Edge TTS bepul yoki ElevenLabs shaxsiy ovoz) -> AI fon rasmlari (Gemini/ChatGPT,
bo'lmasa animatsiyali gradient) -> pastda subtitrlar -> ovozli .mp4 + .srt subtitr + caption .txt.
Kerakli plaginlar: ffmpeg (imageio-ffmpeg), Pillow, edge-tts - requirements.txt da bor.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import re
import subprocess
import threading
from pathlib import Path

from .. import outbox, providers, tts
from ..config import config
from ..skills import skill
from ..skills.design_media import _clean, _ease, _font, _frame, _hex, _rgb, _wrap
from . import Plugin

log = logging.getLogger("ali.video_studio")

FORMATS = {"9:16": (720, 1280), "16:9": (1280, 720), "1:1": (1080, 1080)}
PLATFORMS = ["reels", "tiktok", "shorts", "youtube", "telegram"]
FPS = 25
BRAND_COLORS = ("#FFFFFF", "#1F9D55", "#FFC21A")
DEFAULT_TOPIC = "Targetologlik yoki tashqi reklama bo'yicha bitta foydali video g'oyasini o'zing tanla"


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _start() -> tuple[bool, str]:
    try:
        _ffmpeg()
        import PIL  # noqa: F401
    except Exception as e:
        return False, f"ffmpeg/Pillow topilmadi: {e} (pip install imageio-ffmpeg pillow)"
    parts = ["video (ffmpeg)"]
    try:
        import edge_tts  # noqa: F401
        parts.append("ovoz (" + ("ElevenLabs" if tts.current_voice().get("provider") == "elevenlabs" else "Edge") + ")")
    except ImportError:
        parts.append("ovozsiz (edge-tts yo'q)")
    parts.append("AI rasm" if providers.image_sources("standard") else "gradient fon")
    return True, "Ulangan: " + ", ".join(parts)


PLUGIN = Plugin(key="video_studio", name="Video studiya", icon="🎬", start=_start,
                description="O'zi ssenariy yozadi va ovozli, subtitrli tayyor video (.mp4) yasaydi")


# ------------------------------------------------------------------ ssenariy
_SCRIPT_SYSTEM = (
    "Sen tajribali SMM ssenariy muallifisan. Faqat JSON qaytar, boshqa hech narsa yozma. Sxema: "
    '{"title": str, "hooks": [3 ta qisqa hook], "scenes": [{"title": "ekrandagi qisqa sarlavha (2-5 so\'z)", '
    '"text": "ekrandagi qo\'shimcha 1 qator (ixtiyoriy)", "narration": "diktor aytadigan gap (1-2 jumla)", '
    '"image_prompt": "fon rasm tavsifi inglizcha, matnsiz, vertikal kompozitsiya", "duration": soniya}], '
    '"caption": "post matni, birinchi qator - ilmoq, oxirida CTA", "hashtags": ["#..."]}. '
    "Birinchi sahna - kuchli hook (0-3 s), o'rtada qiymat yoki hikoya, oxirgi sahna - aniq CTA. "
    "Soxta raqam, soxta sharh va aldovchi va'da yozma. "
    "Egasi Abbos, Beshariq. Kontent yo'nalishlari: targetolog sifatida shaxsiy brend "
    "(@m_abbosbek1) va Planet Print tashqi reklama agentligi (@planet_print_beshariq): "
    "hajmli harflar, bannerlar, vizitkalar. Mavzuni shu yo'nalishlardan mos bittasiga bog'la; "
    "informatika o'qituvchiligini kontentga qo'shma. CTA tanlangan yo'nalishga mos bo'lsin."
)


def _parse_script(raw: str) -> dict:
    """AI javobidan JSON ssenariyni ajratadi (```json ... ``` bo'lsa ham)."""
    raw = (raw or "").strip()
    m = re.search(r"\{.*\}", raw, flags=re.S)
    if not m:
        raise ValueError("Ssenariy JSON topilmadi")
    data = json.loads(m.group(0))
    if not isinstance(data, dict) or not isinstance(data.get("scenes"), list):
        raise ValueError("Ssenariyda scenes yo'q")
    return data


def _write_script(topic: str, platform: str, duration_s: int, audience: str, goal: str, language: str) -> dict:
    prompt = (f"Mavzu: {_clean(topic, 500) or DEFAULT_TOPIC}\nPlatforma: {platform}\nDavomiylik: ~{duration_s} soniya\n"
              f"Auditoriya: {audience or 'aniqlanmagan, mavzudan kelib chiq'}\nMaqsad: {goal or 'qamrov va obunachi'}\n"
              f"Til: {language} (jonli, tabiiy). Sahnalar soni: {max(3, min(8, duration_s // 5))}.")
    from .. import local_ai
    ready = local_ai.connected() if local_ai.access() is True else []
    for key in sorted(ready, key=lambda k: k != "codex"):  # ChatGPT ssenariyda birinchi, keyin Claude/Gemini
        try:
            script = _parse_script(local_ai.ask_one(key, local_ai.app_exe(key) or "api",
                                                    f"{_SCRIPT_SYSTEM}\n\n{prompt}\n\nFAQAT JSON qaytar.", 300))
            if script.get("scenes"):
                return script
        except Exception as e:
            log.warning("%s ssenariy yozmadi: %s", key, e)
    _, answer = providers.chat(_SCRIPT_SYSTEM, [], prompt, max_tokens=2500, json_mode=True)
    return _parse_script(answer)


def _script_text(s: dict) -> str:
    lines = [f"🎬 {s.get('title', '')}"]
    if s.get("hooks"):
        lines.append("Hook variantlari:\n" + "\n".join(f"{i}. {h}" for i, h in enumerate(s["hooks"], 1)))
    lines.append("Sahnalar (# | vaqt | ekranda | diktor):")
    t = 0.0
    for i, sc in enumerate(s.get("scenes", []), 1):
        d = float(sc.get("duration") or 4)
        lines.append(f"{i} | {t:.0f}-{t + d:.0f} s | {sc.get('title', '')} {('- ' + sc['text']) if sc.get('text') else ''} | "
                     f"{sc.get('narration', '')}")
        t += d
    if s.get("caption"):
        lines.append("Caption:\n" + str(s["caption"]))
    if s.get("hashtags"):
        lines.append(" ".join(map(str, s["hashtags"])))
    return "\n".join(lines)


@skill(
    description=(
        "Mavzu bo'yicha Reels/TikTok/Shorts/YouTube VIDEO SSENARIYSINI o'zi yozadi: 3 ta hook, kadr-kadr sahnalar "
        "(ekrandagi matn + diktor gapi + fon rasm tavsifi), caption va hashtaglar. Video kerak bo'lmasa yoki avval "
        "ssenariyni ko'rsatish kerak bo'lsa ishlat; tayyor videoni make_content_video yasaydi."
    ),
    params={
        "topic": {"type": "string", "description": "Video mavzusi / g'oya"},
        "platform": {"type": "string", "enum": PLATFORMS, "description": "Platforma (standart reels)"},
        "duration_s": {"type": "integer", "description": "Davomiyligi, soniya (standart 30)"},
        "audience": {"type": "string", "description": "Maqsadli auditoriya"},
        "goal": {"type": "string", "description": "Maqsad: obunachi, sotuv, brend..."},
        "language": {"type": "string", "description": "Til (standart o'zbek lotin)"},
    },
    required=["topic"],
)
def write_video_script(topic: str, platform: str = "reels", duration_s: int = 30, audience: str = "", goal: str = "",
                       language: str = "o'zbek (lotin)") -> str:
    s = _write_script(_clean(topic, 500), platform, max(10, min(int(duration_s or 30), 600)), audience, goal, language)
    return _script_text(s) + "\n\n(JSON - make_content_video ga scenes sifatida berish mumkin)\n" + \
        json.dumps(s.get("scenes", []), ensure_ascii=False)


# ------------------------------------------------------------------ ovoz
def _tts(text: str) -> bytes:
    """Sinxron vositadan async TTS: alohida oqimda (ishlayotgan event loop bilan to'qnashmaydi)."""
    out: dict = {}

    def run():
        try:
            out["data"] = asyncio.run(tts.synthesize(text))
        except Exception as e:
            out["error"] = e
    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(120)
    if "error" in out:
        raise out["error"]
    return out.get("data") or b""


def _audio_seconds(path: Path) -> float:
    r = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def _mux(video: Path, audios: list[tuple[Path, float]], out: Path, total: float) -> None:
    """Ovozsiz videoga sahna ovozlarini o'z vaqtida qo'yadi (adelay + amix)."""
    cmd = [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(video)]
    chains, labels = [], []
    for k, (a, start) in enumerate(audios, 1):
        cmd += ["-i", str(a)]
        chains.append(f"[{k}:a]adelay=delays={int(start * 1000)}:all=1[a{k}]")
        labels.append(f"[a{k}]")
    graph = ";".join(chains) + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest[aout]"
    cmd += ["-filter_complex", graph, "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
            "-t", f"{total:.2f}", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"ffmpeg ovozni qo'sha olmadi: {r.stderr[-300:]}")


# ------------------------------------------------------------------ kadrlar
def _chunks(text: str, words: int = 6) -> list[str]:
    w = text.split()
    return [" ".join(w[i:i + words]) for i in range(0, len(w), words)]


def _subtitle_at(scene: dict, t_local: float) -> str:
    parts, speak = scene.get("subs") or [], scene.get("speak") or scene["duration"]
    if not parts or t_local > speak + .3:
        return ""
    return parts[min(len(parts) - 1, int(t_local / speak * len(parts)))]


def _draw_subtitle(img, text: str):
    from PIL import Image, ImageDraw
    w, h = img.size
    f = _font(max(14, int(min(w, h) * .045)), True)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    lines = _wrap(d, text, f, w * .84)[:2]
    lh = f.size * 1.25
    y0 = h * .86 - lh * len(lines)
    width = max(d.textlength(line, font=f) for line in lines)
    d.rounded_rectangle([w / 2 - width / 2 - 18, y0 - 12, w / 2 + width / 2 + 18, y0 + lh * len(lines) + 4],
                        radius=14, fill=(0, 0, 0, 150))
    for k, line in enumerate(lines):
        d.text((w / 2, y0 + lh * (k + .8)), line, font=f, fill=(255, 255, 255, 255), anchor="ms",
               stroke_width=2, stroke_fill=(0, 0, 0, 255))
    img.paste(layer, (0, 0), layer)


def _cover(data: bytes, w: int, h: int):
    """AI rasmni kadrga to'liq yoyadi (Ken Burns zoom uchun 12% zaxira bilan)."""
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    W, H = int(w * 1.12), int(h * 1.12)
    k = max(W / im.width, H / im.height)
    im = im.resize((max(W, int(im.width * k)), max(H, int(im.height * k))))
    x, y = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))


def _shade(w: int, h: int):
    from PIL import Image, ImageDraw
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for y in range(0, h, 4):  # tepada va pastda qorong'ilik - matn o'qilsin
        k = abs(y / h - .5) * 2
        d.rectangle([0, y, w, y + 4], fill=(0, 0, 0, int(40 + 150 * k ** 2)))
    return layer


def _photo_frame(w, h, bg, shade, scene, t_local, accent):
    from PIL import Image, ImageDraw
    dur = scene["duration"]
    zoom = 1 - .1 * (t_local / dur)  # sekin yaqinlashish
    cw, ch = bg.width * zoom, bg.height * zoom
    x, y = (bg.width - cw) / 2, (bg.height - ch) / 2
    img = bg.crop((int(x), int(y), int(x + cw), int(y + ch))).resize((w, h))
    img.paste(shade, (0, 0), shade)
    alpha = min(_ease(t_local / .5), _ease((dur - t_local) / .4))
    big = int(min(w, h) * (.09 if len(scene["title"]) < 16 else .065))
    f = _font(big, True)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    lines = _wrap(d, scene["title"], f, w * .86)[:3]
    top = h * .14 + (1 - _ease(t_local / .5)) * h * .04
    for k, line in enumerate(lines):
        d.text((w / 2, top + k * big * 1.15), line, font=f, fill=(255, 255, 255, int(255 * alpha)), anchor="ms",
               stroke_width=3, stroke_fill=(0, 0, 0, int(200 * alpha)))
    bar = int(w * .3 * _ease(t_local / .6))
    yb = top + len(lines) * big * 1.15 - big * .6
    d.rounded_rectangle([w / 2 - bar / 2, yb, w / 2 + bar / 2, yb + 7], radius=4, fill=accent + (int(255 * alpha),))
    img.paste(layer, (0, 0), layer)
    return img


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _srt(scenes: list[dict]) -> str:
    out, n, t = [], 1, 0.0
    for sc in scenes:
        parts = sc.get("subs") or []
        step = (sc.get("speak") or sc["duration"]) / max(1, len(parts))
        for k, p in enumerate(parts):
            out.append(f"{n}\n{_srt_time(t + k * step)} --> {_srt_time(t + (k + 1) * step)}\n{p}\n")
            n += 1
        t += sc["duration"]
    return "\n".join(out)


@skill(
    description=(
        "TAYYOR KONTENT VIDEO (.mp4) ni O'ZI yasaydi: scenes berilmasa mavzudan o'zi ssenariy yozadi, har sahnaga "
        "diktor OVOZI (Ali ovozi/TTS), AI fon RASMLARI (ulangan bo'lsa, aks holda animatsiyali gradient), pastda "
        "SUBTITRLAR. Natija avtomatik yuboriladi: ovozli .mp4, .srt subtitr va caption+hashtag .txt. "
        "Reels/TikTok/Shorts - 9:16, YouTube - 16:9, post - 1:1. "
        "scenes: [{title, text, narration, image_prompt, duration}] (3-8 sahna)."
    ),
    params={
        "topic": {"type": "string", "description": "Video mavzusi (ixtiyoriy, berilmasa egasining yo'nalishidan tanlanadi)"},
        "scenes": {"type": "array", "items": {"type": "object"}, "description": "Tayyor sahnalar (ixtiyoriy)"},
        "format": {"type": "string", "enum": list(FORMATS), "description": "Kadr nisbati (standart 9:16)"},
        "platform": {"type": "string", "enum": PLATFORMS, "description": "Platforma (standart reels)"},
        "duration_s": {"type": "integer", "description": "Taxminiy davomiylik, soniya (standart 30)"},
        "voice": {"type": "boolean", "description": "Diktor ovozi qo'shilsinmi (standart ha)"},
        "ai_images": {"type": "boolean", "description": "Sahnalarga AI fon rasm yaratilsinmi (standart ha)"},
        "images": {"type": "array", "items": {"type": "string"},
                   "description": "Tayyor rasm fayllari - har sahnaga bittadan fon (egasi ChatGPT/Gemini ilovasida yaratgan)"},
        "colors": {"type": "array", "items": {"type": "string"}, "description": "[fon1, fon2, aksent] #RRGGBB"},
        "audience": {"type": "string", "description": "Maqsadli auditoriya"},
        "goal": {"type": "string", "description": "Maqsad: obunachi, sotuv, brend..."},
    },
    required=[],
)
def make_content_video(topic: str = "", scenes: list | None = None, format: str = "9:16", platform: str = "reels",
                       duration_s: int = 30, voice: bool = True, ai_images: bool = True, colors: list | None = None,
                       audience: str = "", goal: str = "", images: list | None = None) -> str:
    import imageio_ffmpeg
    topic = _clean(topic, 500) or DEFAULT_TOPIC
    script = {"title": topic, "scenes": scenes or []}
    if not scenes:
        script = _write_script(topic, platform, max(10, min(int(duration_s or 30), 600)), audience, goal, "o'zbek (lotin)")
    clean = []
    for s in script.get("scenes", [])[:10]:
        if isinstance(s, dict) and _clean(s.get("title") or s.get("narration")):
            clean.append({"title": _clean(s.get("title") or s.get("narration"), 70), "text": _clean(s.get("text"), 160),
                          "narration": _clean(s.get("narration"), 400), "image_prompt": _clean(s.get("image_prompt"), 600),
                          "duration": max(2.0, min(float(s.get("duration") or 4), 15.0))})
    if not clean:
        return "Ssenariyda sahna yo'q: scenes ga kamida bitta {title, narration} bering."
    title = _clean(script.get("title"), 80) or topic[:60]
    cols = [_hex(c, d) for c, d in zip((colors or []) + [None] * 3, BRAND_COLORS)][:3]
    w, h = FORMATS.get(format, FORMATS["9:16"])
    path = outbox.new_path(title, "mp4")
    stem = path.with_suffix("")
    notes = []

    # 1) Ovoz: har sahna diktor matni -> audio; sahna davomiyligi ovozga moslanadi
    audios = []
    if voice:
        start = 0.0
        for i, sc in enumerate(clean):
            if sc["narration"]:
                try:
                    data = _tts(sc["narration"])
                    if data:
                        a = stem.parent / f"{stem.name}_ovoz{i}.{'wav' if data[:4] == b'RIFF' else 'mp3'}"
                        a.write_bytes(data)
                        sc["speak"] = _audio_seconds(a) or sc["duration"]
                        sc["duration"] = max(sc["duration"], min(sc["speak"] + .6, 20.0))
                        audios.append((a, start))
                except Exception as e:
                    log.warning("Ovoz yaratilmadi: %s", e)
                    if not notes:
                        notes.append(f"ovoz qo'shilmadi ({e})")
            start += sc["duration"]
    for sc in clean:  # emoji shriftda yo'q (bo'sh kvadrat) - subtitrdan olib tashlanadi, ovozda qoladi
        bare = re.sub("[𐀀-􏿿☀-➿️‍]", "", sc["narration"] or "").strip()
        sc["subs"] = _chunks(bare) if bare else []

    # 2) Fon rasmlari: egasi bergan tayyor rasmlar -> AI rasmlar -> gradient
    backgrounds = {}
    for i, img in enumerate((images or [])[:len(clean)]):
        try:
            backgrounds[i] = _cover(Path(img).read_bytes(), w, h)
        except Exception as e:
            log.warning("Rasm o'qilmadi %s: %s", img, e)
    if ai_images and len(backgrounds) < len(clean) and providers.image_sources("standard"):
        for i, sc in enumerate(clean):
            if i in backgrounds:
                continue
            prompt = sc["image_prompt"] or f"{sc['title']}, {topic}"
            try:
                data, _ = providers.generate_image_best(prompt + ", cinematic, no text, vertical social media background",
                                                        "standard")
                backgrounds[i] = _cover(data, w, h)
            except Exception as e:
                log.warning("Fon rasm yaratilmadi: %s", e)
        if len(backgrounds) < len(clean):
            notes.append(f"{len(clean) - len(backgrounds)} sahnada AI rasm o'rniga gradient")

    # 3) Kadrlar -> ovozsiz video
    accent = _rgb(cols[2])
    shade = _shade(w, h)
    rnd = random.Random(title)
    particles = [(rnd.random(), rnd.random(), rnd.uniform(1.5, 4.5), rnd.uniform(.03, .09)) for _ in range(40)]
    silent = stem.parent / f"{stem.name}_ovozsiz.mp4" if audios else path
    writer = imageio_ffmpeg.write_frames(str(silent), (w, h), fps=FPS, codec="libx264", pix_fmt_out="yuv420p",
                                         macro_block_size=8, ffmpeg_log_level="error", output_params=["-crf", "23"])
    writer.send(None)
    t_global = 0.0
    try:
        for i, sc in enumerate(clean):
            for f in range(int(math.ceil(sc["duration"] * FPS))):
                t = f / FPS
                if i in backgrounds:
                    img = _photo_frame(w, h, backgrounds[i], shade, sc, t, accent)
                else:
                    img, _ = _frame(w, h, sc, t, sc["duration"], t_global, cols, particles, i)
                sub = _subtitle_at(sc, t)
                if sub:
                    _draw_subtitle(img, sub)
                writer.send(img.tobytes())
                t_global += 1 / FPS
    finally:
        writer.close()
    total = sum(sc["duration"] for sc in clean)

    # 4) Ovozni qo'shish
    voiced = False
    if audios:
        try:
            _mux(silent, audios, path, total)
            voiced = True
        except Exception as e:
            log.warning("%s", e)
            silent.replace(path)
            notes.append("ovoz videoga qo'shilmadi")
        silent.unlink(missing_ok=True)
        for a, _ in audios:
            a.unlink(missing_ok=True)

    srt = stem.parent / f"{stem.name}.srt"
    srt.write_text(_srt(clean), encoding="utf-8")
    caption = stem.parent / f"{stem.name}_caption.txt"
    caption.write_text(_script_text({**script, "scenes": clean}), encoding="utf-8")
    for p in (path, srt, caption):
        outbox.register(p)
    tags = " ".join(map(str, script.get("hashtags") or []))
    return (f"✅ Video tayyor: {path.name} ({format}, {w}x{h}, {total:.0f} s, {len(clean)} sahna, "
            f"{'ovozli' if voiced else 'ovozsiz'}, subtitrli"
            f"{', AI rasmlar: ' + str(len(backgrounds)) if backgrounds else ''}). Subtitr: {srt.name}, caption: {caption.name}."
            + (f"\nCaption: {_clean(script.get('caption'), 600)}" if script.get("caption") else "")
            + (f"\n{tags}" if tags else "")
            + (f"\nEslatma: {'; '.join(notes)}" if notes else ""))
