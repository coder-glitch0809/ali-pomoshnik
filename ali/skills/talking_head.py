"""Personaj gapiradi: rasm (3D portret) -> fonsiz qahramon + og'iz harakati ovozga mos (lip-sync) + ko'z qisish.

Og'iz: pastki lab va jag' ovoz balandligiga qarab pastga tushadi, lablar orasi ochiladi (qorong'i og'iz, tepada tishlar).
Har rasm uchun «rig» - og'iz chizig'i, iyak va ko'zlar koordinatalari (rasm yonida personaj.json).
Rig bo'lmasa - personaj faqat tebranadi (og'iz harakatsiz).
"""
import base64
import io
import json
import logging
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

log = logging.getLogger("ali.talking_head")

LEVELS = (0, 4, 8, 12, 16, 20, 24, 28)  # og'iz ochilishi (asl rasm pikselida)


def rig(image: Path) -> dict | None:
    try:
        return json.loads(image.with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cutout(image: Path) -> Image.Image:
    """Fonsiz personaj (RGBA). rembg bo'lsa - fon olib tashlanadi (natija keshlanadi), bo'lmasa - asl rasm."""
    cache = image.with_name(image.stem + "_cut.png")
    if cache.exists() and cache.stat().st_mtime >= image.stat().st_mtime:
        return Image.open(cache).convert("RGBA")
    src = Image.open(image).convert("RGBA")
    try:
        from rembg import remove
        cut = remove(src)
    except Exception as e:
        log.info("Fon olib tashlanmadi (%s) - asl rasm", e)
        return src
    a = np.asarray(cut)[..., 3].astype(np.float32)
    # pastki chekka (kiyim) kadr chetiga yopishib tursin - yarim shaffof qolmasin
    a[-6:] = np.maximum(a[-6:], np.asarray(src)[-6:, :, 3] * (a[-7:-6].max(axis=0, keepdims=True) > 128))
    cut.putalpha(Image.fromarray(a.clip(0, 255).astype(np.uint8)))
    cut.save(cache)
    return cut


def _smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def _mouth(img: np.ndarray, r: dict, D: float) -> np.ndarray:
    """Og'iz D pikselga ochilgan holat (faqat rig «box» qismi qaytariladi, RGBA)."""
    x0, y0, x1, y1 = r["box"]
    cx, half, base, curve = r["mouth_cx"], r["mouth_half"], r["seam_y"], r["seam_curve"]
    jaw_half, chin, neck = r["jaw_half"], r["chin_y"], r["neck_y"]
    ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    u = (xs - cx) / half
    seam = base + curve * (1 - np.clip(u * u, 0, 1))  # tabassum chizig'i (lablar tutashgan joy)
    wm = np.clip(1 - u * u, 0, 1) ** 0.8  # og'iz shakli - burchaklarda yopiq
    wx = np.clip(1 - ((xs - cx) / jaw_half) ** 2, 0, 1)  # jag' kengligi
    t = _smooth((ys - seam) / max(1.0, (chin - 40) - base))
    shape = wm * (1 - t) + wx * t
    wy = 1 - _smooth((ys - chin) / max(1.0, neck - chin))
    d = np.where(ys > seam, D * shape * wy, 0.0)
    sy = ys - d
    hole = (ys >= seam) & (sy < seam)  # lablar orasi - og'iz ichi
    # bilinear namuna
    sy_c = np.clip(sy, 0, img.shape[0] - 1.001)
    yi = np.floor(sy_c).astype(int)
    fy = (sy_c - yi)[..., None]
    xi = xs.astype(int)
    out = img[yi, xi] * (1 - fy) + img[yi + 1, xi] * fy
    if D > 0:
        depth = np.clip((seam + D * wm - ys) / max(1.0, D * wm.max()), 0, 1)[..., None]  # 1 - tepada, 0 - pastda
        inner = np.array([38, 10, 12, 255], np.float32) * (1 - depth) + np.array([70, 18, 22, 255], np.float32) * depth
        top = hole & ((ys - seam) < np.minimum(D * wm * 0.3, 7))
        teeth = (top & (np.abs(u) < 0.7) & (D >= 8))[..., None]
        inner = np.where(teeth, np.array([218, 206, 196, 255], np.float32), inner)
        # og'iz chekkasi yumshoq (1 px) - qirrali ko'rinmasin
        soft = np.asarray(Image.fromarray((hole * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.9)),
                          np.float32)[..., None] / 255
        out = out * (1 - soft) + inner * soft
        out[..., 3] = img[ys.astype(int), xi, 3]
    return out.clip(0, 255).astype(np.uint8)


def _blink(img: np.ndarray, r: dict) -> np.ndarray:
    """Ko'z yumilgan holat (rig «eyes_box» qismi)."""
    x0, y0, x1, y1 = r["eyes_box"]
    part = Image.fromarray(img[y0:y1, x0:x1].copy())
    for ex, ey, ew, eh in r["eyes"]:
        lx, ly = ex - x0, ey - y0
        W, H = int(ew * 1.15), int(eh * 1.3)
        L, T = int(lx - W / 2), int(ly - H / 2)
        # yumuq qovoq: tepa qovoq terisi -> pastki qovoq terisi (vertikal o'tish), ko'z o'rni ustidan
        up = np.asarray(part.crop((L, T - 7, L + W, T - 1)), np.float32).mean(axis=0)
        lo = np.asarray(part.crop((L, T + H + 1, L + W, T + H + 6)), np.float32).mean(axis=0)
        k = np.linspace(0, 1, H)[:, None, None]
        lid = Image.fromarray((up[None] * (1 - k) + lo[None] * k).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2))
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).ellipse((3, 3, W - 4, H - 4), fill=255)
        part.paste(lid, (L, T), mask.filter(ImageFilter.GaussianBlur(3)))
        lash = Image.new("RGBA", part.size, (0, 0, 0, 0))
        ImageDraw.Draw(lash).arc((lx - ew / 2 + 3, ly - eh * 0.75, lx + ew / 2 - 3, ly + eh * 0.4), 12, 168,
                                 fill=(48, 30, 26, 230), width=3)
        part.alpha_composite(lash.filter(ImageFilter.GaussianBlur(0.6)))
    out = np.asarray(part).copy()
    out[..., 3] = img[y0:y1, x0:x1, 3]
    return out


def _uri(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=False, compress_level=3)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def build(image: Path, width: int) -> dict:
    """{base, w, h, mouths: [(uri, left, top, w, h)], blink: (uri, ...) | None} - displey o'lchamida."""
    cut = cutout(image)
    s = width / cut.width
    w, h = width, round(cut.height * s)
    res = {"base": _uri(cut.resize((w, h), Image.LANCZOS)), "w": w, "h": h, "mouths": [], "blink": None,
           "cut": cut.mode == "RGBA" and np.asarray(cut)[..., 3].min() < 10}
    r = rig(image)
    if not r:
        return res
    arr = np.asarray(cut, np.float32)

    def place(patch: np.ndarray, box):
        x0, y0, x1, y1 = box
        im = Image.fromarray(patch).resize((max(1, round((x1 - x0) * s)), max(1, round((y1 - y0) * s))), Image.LANCZOS)
        return _uri(im), x0 * s, y0 * s, (x1 - x0) * s, (y1 - y0) * s

    res["mouths"] = [place(_mouth(arr, r, D), r["box"]) for D in LEVELS[1:]]
    if r.get("eyes"):
        res["blink"] = place(_blink(np.asarray(cut), r), r["eyes_box"])
    return res


def levels(audio: Path, dur: float, fps: int) -> list[int]:
    """Har kadr uchun og'iz ochilishi (0..len(LEVELS)-1) - ovoz balandligidan."""
    from .video_edit import ffmpeg
    raw = subprocess.run([ffmpeg(), "-v", "error", "-i", str(audio), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, timeout=120).stdout
    pcm = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    n, hop = int(dur * fps), 16000 / fps
    rms = np.array([np.sqrt(np.mean(pcm[int(k * hop):int((k + 1) * hop)] ** 2)) if int(k * hop) < len(pcm) else 0.0
                    for k in range(n)])
    peak = np.percentile(rms[rms > 0], 95) if (rms > 0).any() else 1.0
    top = len(LEVELS) - 1
    out, cur = [], 0.0
    for v in rms / max(peak, 1e-6):
        want = 0.0 if v < 0.12 else min(1.0, v) ** 0.7 * top
        cur = want if want > cur else max(want, cur - 1.6)  # tez ochiladi, sekinroq yopiladi
        out.append(int(round(cur)))
    return out


def blinks(dur: float, fps: int) -> list[bool]:
    """Tabiiy ko'z qisish: har 2.8-4.6 s da 4 kadr."""
    out, t, k = [False] * int(dur * fps), 1.4, 0
    while t < dur:
        f = int(t * fps)
        for j in range(f, min(f + 4, len(out))):
            out[j] = True
        k += 1
        t += 2.8 + (k * 0.77) % 1.8
    return out


def html(face: dict, left: float, top: float, cls: str = "hero") -> str:
    """Personaj bloki: asos rasm + og'iz/ko'z qatlamlari (window.__face(og'iz, ko'z) bilan boshqariladi)."""
    parts = [f'<img src="{face["base"]}" style="position:absolute;left:0;top:0;width:{face["w"]}px;height:{face["h"]}px">']
    for k, (uri, x, y, w, h) in enumerate(face["mouths"]):
        parts.append(f'<img class="fm" src="{uri}" style="position:absolute;left:{x:.2f}px;top:{y:.2f}px;'
                     f'width:{w:.2f}px;height:{h:.2f}px;visibility:hidden">')
    if face["blink"]:
        uri, x, y, w, h = face["blink"]
        parts.append(f'<img id="fb" src="{uri}" style="position:absolute;left:{x:.2f}px;top:{y:.2f}px;'
                     f'width:{w:.2f}px;height:{h:.2f}px;visibility:hidden">')
    script = ("<script>window.__face=function(m,b){var e=document.querySelectorAll('.fm');"
              "for(var i=0;i<e.length;i++)e[i].style.visibility=(i===m-1)?'visible':'hidden';"
              "var k=document.getElementById('fb');if(k)k.style.visibility=b?'visible':'hidden';};</script>")
    return (f'<div class="{cls}" style="position:absolute;left:{left}px;top:{top}px;width:{face["w"]}px;'
            f'height:{face["h"]}px">{"".join(parts)}</div>{script}')
