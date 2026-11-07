"""Boshlovchi personaj: bitta portretdan «rig» - bosh, gavda va ikki qo'l alohida harakatlanadi.

Personaj stol ortida turadi, sahna diagrammasi tomon qo'li bilan ko'rsatadi, kaftlarini ochib tushuntiradi, barmog'i bilan
sanaydi, oxirida bosh barmog'ini ko'taradi. Qo'llar (yeng + kaft + barmoqlar) SVG'da chiziladi, kadr sayin hisoblanadi.
Har kadr holati Python'da aniqlanadi - render takrorlanadigan va aniq.
"""
import base64
import io
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from . import talking_head as th

SCALE = 0.72  # asl rasm -> ekran
NECK_X, NECK_Y = 525, 765  # bosh aylanadigan nuqta (asl rasm)
TOP = 1010  # personaj rasmining ekrandagi tepasi
DESK_Y = 1690  # stol tepasi - shu chiziqdan pastda gavda va rasm cheti ko'rinmaydi
PAD = 260  # o'ng chekka davomi (asl rasm pikseli)
SIDES = (700, 380)  # bo'yin x: 0 - o'ngda (diagramma chapda), 1 - chapda (diagramma o'ngda)

# barmoqlar egilishi: bosh, ko'rsatkich, o'rta, nomsiz, jimjiloq (0 - to'g'ri, 1 - musht)
HANDS = {
    "relax": (.35, .25, .3, .35, .4),
    "open": (.0, .0, .0, .0, .0),
    "point": (.75, .0, 1, 1, 1),
    "one": (.8, .0, 1, 1, 1),
    "two": (.8, .0, .0, 1, 1),
    "three": (.8, .0, .0, .0, 1),
    "four": (.8, .0, .0, .0, .0),
    "thumb": (-.2, 1, 1, 1, 1),
}
COUNT = ("one", "two", "three", "four", "open")


def _png(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.save(buf, "PNG", compress_level=3)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _head_mask(size: tuple[int, int]) -> Image.Image:
    """Bosh + bo'yinning yuqori qismi (yoqa va yelka kirmaydi), pastki cheti yumshoq."""
    w, h = size
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    left = np.interp(ys, [0, 640, 720, 800], [0, 0, 400, 425])
    right = np.interp(ys, [0, 620, 690, 800], [w, w, 712, 690])
    inside = (xs > left) & (xs < right) & (ys < 790)
    mask = Image.fromarray((inside * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(7))
    return mask


def _pad_right(a: np.ndarray) -> np.ndarray:
    """Rasm o'ng chetda kesilgan yelkani davom ettiradi: chekka ustun cho'ziladi, qiyalik bilan pastga tushadi va qorayadi."""
    h = a.shape[0]
    edge = a[:, -1:, :3].astype(np.float32)
    start = int(np.argmax(a[:, -1, 3] > 128)) if (a[:, -1, 3] > 128).any() else h
    out = np.zeros((h, a.shape[1] + PAD, 4), np.uint8)
    out[:, :a.shape[1]] = a
    xs = np.arange(1, PAD + 1, dtype=np.float32)
    for y in range(start, h):
        shade = np.clip(1 - xs / (PAD * 1.3), .25, 1)[:, None]
        out[y, a.shape[1]:, :3] = (edge[y] * shade).astype(np.uint8)
        out[y, a.shape[1]:, 3] = (np.clip((y - (start + xs * .62)) / 3, 0, 1) * 255).astype(np.uint8)
    return out


def build(image: Path) -> dict | None:
    """Rig qatlamlari (ekran o'lchamida). Og'iz koordinatalari bo'lmasa - None (oddiy personaj ishlatiladi)."""
    r = th.rig(image)
    if not r:
        return None
    cut = th.cutout(image)
    if np.asarray(cut)[..., 3].min() > 10:  # fon olib tashlanmagan - rig chiroyli chiqmaydi
        return None
    w, h = round((cut.width + PAD) * SCALE), round(cut.height * SCALE)
    mask = _head_mask(cut.size)
    arr = np.asarray(cut, np.float32)

    def piece(a: np.ndarray, box) -> tuple[str, float, float, float, float]:
        x0, y0, x1, y1 = box
        im = Image.fromarray(a.astype(np.uint8), "RGBA")
        alpha = np.asarray(im, np.float32)[..., 3] * np.asarray(mask.crop(box), np.float32) / 255
        im.putalpha(Image.fromarray(alpha.astype(np.uint8)))
        im = im.resize((max(1, round((x1 - x0) * SCALE)), max(1, round((y1 - y0) * SCALE))), Image.LANCZOS)
        return _png(im), x0 * SCALE, y0 * SCALE, (x1 - x0) * SCALE, (y1 - y0) * SCALE

    # gavda: bosh tepasi olib tashlanadi (bosh qimirlaganda ikkinchi nusxasi ko'rinmasin), jag' osti esa qoladi
    torso = np.array(cut)
    ys = np.arange(cut.height, dtype=np.float32)[:, None]
    torso[..., 3] = (torso[..., 3] * np.clip((ys - 560) / 30, 0, 1)).astype(np.uint8)
    torso = _pad_right(torso)
    head = cut.copy()
    head.putalpha(Image.fromarray((np.asarray(cut, np.float32)[..., 3] * np.asarray(mask, np.float32) / 255).astype(np.uint8)))
    wide = Image.new("RGBA", (cut.width + PAD, cut.height), (0, 0, 0, 0))
    wide.paste(head, (0, 0))
    head = wide
    denim = cut.convert("RGB").crop((790, 1040, 950, 1200)).resize((128, 128), Image.LANCZOS)
    buf = io.BytesIO()
    denim.save(buf, "JPEG", quality=85)
    return {
        "w": w, "h": h,
        "torso": _png(Image.fromarray(torso, "RGBA").resize((w, h), Image.LANCZOS)),
        "head": _png(head.resize((w, h), Image.LANCZOS)),
        "mouths": [piece(th._mouth(arr, r, D), r["box"]) for D in th.LEVELS[1:]],
        "blink": piece(th._blink(np.asarray(cut), r).astype(np.float32), r["eyes_box"]) if r.get("eyes") else None,
        "denim": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
    }


def _svg(body: str, w: int, h: int) -> str:
    doc = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{body}</svg>'
    return "data:image/svg+xml;base64," + base64.b64encode(doc.encode("utf-8")).decode()


def vector_rig() -> dict:
    """Ali o'zi chizgan personaj (Planet Print boshlovchisi): haqiqiy odam rasmi ishlatilmaydi. Qatlamlari foto rig bilan bir xil."""
    w, h = round((1024 + PAD) * SCALE), round(1280 * SCALE)
    cx = round(NECK_X * SCALE)
    torso = (f'''<defs><linearGradient id="hd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2b4a8f"/><stop offset="1" stop-color="#14224a"/></linearGradient>
<linearGradient id="nk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#b9774a"/><stop offset=".5" stop-color="#d99a6c"/></linearGradient></defs>
<rect x="{cx - 62}" y="440" width="124" height="190" rx="40" fill="url(#nk)"/>
<path d="M{cx - 330} 922C{cx - 345} 730 {cx - 300} 640 {cx - 95} 575C{cx - 40} 625 {cx + 40} 625 {cx + 95} 575C{cx + 300} 640 {cx + 345} 730 {cx + 330} 922Z" fill="url(#hd)"/>
<path d="M{cx - 108} 566C{cx - 70} 660 {cx + 70} 660 {cx + 108} 566C{cx + 140} 590 {cx + 120} 690 {cx} 716C{cx - 120} 690 {cx - 140} 590 {cx - 108} 566Z" fill="#203a78"/>
<path d="M{cx - 34} 700V810M{cx + 34} 700V800" stroke="#ffb300" stroke-width="9" stroke-linecap="round"/>
<circle cx="{cx - 34}" cy="818" r="10" fill="#ffb300"/><circle cx="{cx + 34}" cy="808" r="10" fill="#ffb300"/>''')
    head = (f'''<defs><radialGradient id="fc" cx=".42" cy=".36" r=".75"><stop offset="0" stop-color="#f5c49a"/><stop offset=".75" stop-color="#e3a578"/><stop offset="1" stop-color="#c98757"/></radialGradient>
<radialGradient id="ir" cx=".5" cy=".42" r=".6"><stop offset="0" stop-color="#7a4a24"/><stop offset="1" stop-color="#2d1a0d"/></radialGradient>
<linearGradient id="hr" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#46362d"/><stop offset="1" stop-color="#1f1612"/></linearGradient></defs>
<ellipse cx="{cx - 168}" cy="318" rx="30" ry="44" fill="#d59463"/><ellipse cx="{cx + 168}" cy="318" rx="30" ry="44" fill="#d59463"/>
<path d="M{cx - 160} 240C{cx - 170} 400 {cx - 110} 500 {cx} 510C{cx + 110} 500 {cx + 170} 400 {cx + 160} 240C{cx + 150} 110 {cx - 150} 110 {cx - 160} 240Z" fill="url(#fc)"/>
<path d="M{cx - 172} 270C{cx - 196} 130 {cx - 90} 62 {cx + 10} 70C{cx + 130} 60 {cx + 200} 150 {cx + 172} 270C{cx + 158} 216 {cx + 130} 190 {cx + 88} 188C{cx + 20} 206 {cx - 70} 200 {cx - 112} 180C{cx - 140} 196 {cx - 160} 226 {cx - 172} 270Z" fill="url(#hr)"/>
<path d="M{cx - 96} 262Q{cx - 66} 244 {cx - 34} 262M{cx + 34} 262Q{cx + 66} 244 {cx + 96} 262" fill="none" stroke="#2a1c16" stroke-width="13" stroke-linecap="round"/>
<ellipse cx="{cx - 66}" cy="306" rx="33" ry="30" fill="#fff"/><ellipse cx="{cx + 66}" cy="306" rx="33" ry="30" fill="#fff"/>
<circle cx="{cx - 62}" cy="308" r="20" fill="url(#ir)"/><circle cx="{cx + 62}" cy="308" r="20" fill="url(#ir)"/>
<circle cx="{cx - 62}" cy="308" r="9" fill="#0d0705"/><circle cx="{cx + 62}" cy="308" r="9" fill="#0d0705"/>
<circle cx="{cx - 55}" cy="300" r="6" fill="#fff"/><circle cx="{cx + 69}" cy="300" r="6" fill="#fff"/>
<path d="M{cx - 14} 372Q{cx} 390 {cx + 14} 372" fill="none" stroke="#b97648" stroke-width="7" stroke-linecap="round"/>
<ellipse cx="{cx - 112}" cy="378" rx="28" ry="17" fill="#e8795a" opacity=".28"/><ellipse cx="{cx + 112}" cy="378" rx="28" ry="17" fill="#e8795a" opacity=".28"/>
<path d="M{cx - 46} 424Q{cx} 456 {cx + 46} 424" fill="none" stroke="#8a4a2c" stroke-width="8" stroke-linecap="round"/>''')
    mouths = []
    for k in range(1, len(th.LEVELS)):
        rx, ry = 42 + k * 1.6, 5 + k * 4.2
        my = 430 + k * 1.2
        teeth = f'<clipPath id="m{k}"><ellipse cx="{cx}" cy="{my}" rx="{rx}" ry="{ry}"/></clipPath><rect x="{cx - rx}" y="{my - ry}" width="{2 * rx}" height="{min(ry * .55, 15):.1f}" fill="#fff8ee" clip-path="url(#m{k})"/>'
        tongue = f'<ellipse cx="{cx}" cy="{my + ry * .75}" rx="{rx * .62}" ry="{ry * .42}" fill="#d9605d" clip-path="url(#m{k})"/>' if k > 2 else ""
        mouths.append((_svg(f'<ellipse cx="{cx}" cy="{my}" rx="{rx + 3}" ry="{ry + 3}" fill="#8a4a2c"/><ellipse cx="{cx}" cy="{my}" rx="{rx}" ry="{ry}" fill="#4a1414"/>{teeth}{tongue}', w, h), 0, 0, w, h))
    blink = _svg(f'<ellipse cx="{cx - 66}" cy="306" rx="36" ry="33" fill="#eab084"/><ellipse cx="{cx + 66}" cy="306" rx="36" ry="33" fill="#eab084"/>'
                 f'<path d="M{cx - 98} 310Q{cx - 66} 330 {cx - 34} 310M{cx + 34} 310Q{cx + 66} 330 {cx + 98} 310" fill="none" stroke="#2a1c16" stroke-width="7" stroke-linecap="round"/>', w, h)
    tex = Image.fromarray(np.clip(np.random.default_rng(7).normal(0, 7, (128, 128, 3)) + np.array([38, 62, 122]), 0, 255).astype(np.uint8))
    buf = io.BytesIO()
    tex.save(buf, "JPEG", quality=85)
    return {"w": w, "h": h, "torso": _svg(torso, w, h), "head": _svg(head, w, h), "mouths": mouths, "blink": (blink, 0, 0, w, h),
            "denim": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}


DEFS = """<defs>
<pattern id="denim" patternUnits="userSpaceOnUse" width="128" height="128"><image href="{denim}" width="128" height="128"/></pattern>
<filter id="skin" filterUnits="userSpaceOnUse" x="-200" y="-200" width="1480" height="2320"><feGaussianBlur in="SourceAlpha" stdDeviation="7" result="b"/>
<feDiffuseLighting in="b" surfaceScale="9" diffuseConstant="1.12" lighting-color="#fff" result="l"><feDistantLight azimuth="245" elevation="62"/></feDiffuseLighting>
<feComposite in="l" in2="SourceAlpha" operator="in" result="lit"/><feBlend in="SourceGraphic" in2="lit" mode="multiply"/></filter>
<filter id="armshade" filterUnits="userSpaceOnUse" x="-200" y="-200" width="1480" height="2320"><feDropShadow dx="0" dy="14" stdDeviation="14" flood-color="#000" flood-opacity=".5"/></filter>
</defs>"""


def _finger(kx: float, ky: float, ang: float, length: float, width: float, curl: float) -> tuple[str, bool]:
    """Bitta barmoq (3 bo'g'in). curl=1 - kaft ustiga bukilgan. (svg, kaft ustida chizilsinmi)."""
    pts = [(kx, ky)]
    a = math.radians(ang)
    for part, fold in ((.45, .55), (.3, 1.25), (.25, 1.5)):
        seg = length * part * (1 - .62 * max(0, curl))
        b = a + math.pi * fold * max(0, curl) * (1 if kx >= 0 else -1) * .22
        pts.append((pts[-1][0] + seg * math.sin(b), pts[-1][1] - seg * math.cos(b) + (seg * 1.5 * max(0, curl) * fold / 1.5)))
        a = b
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    style = 'fill="none" stroke-linecap="round" stroke-linejoin="round"'
    crease = ""
    for (x, y), (x2, y2) in zip(pts[1:3], pts[2:4]):  # bo'g'in chiziqlari
        dx, dy = x2 - x, y2 - y
        n = math.hypot(dx, dy) or 1
        px, py = -dy / n * width * .32, dx / n * width * .32
        crease += f'<path d="M{x - px:.1f} {y - py:.1f}L{x + px:.1f} {y + py:.1f}" stroke="#8a5230" stroke-width="1.8" stroke-linecap="round" opacity=".55"/>'
    svg = (f'<polyline points="{line}" {style} stroke="#7f4726" stroke-width="{width + 3:.1f}"/>'
           f'<polyline points="{line}" {style} stroke="url(#skinc)" stroke-width="{width:.1f}"/>{crease}')
    return svg, curl > .5


def hand(curls, mirror: int = 1) -> str:
    """Kaft va barmoqlar (mahalliy koordinata: bilak (0,0), barmoqlar yuqoriga). Bosh barmoq +x tomonda."""
    t, i, m, r, p = curls
    specs = ((-37, -108, -7 - 6 * (1 - p), 90, 23, p), (-13, -116, -2, 112, 25, r), (12, -118, 1, 122, 26, m), (37, -112, 6, 112, 26, i))
    under, over = [], []
    for kx, ky, a, ln, wd, c in specs:
        svg, top = _finger(kx, ky, a, ln, wd, c)
        (over if top else under).append(svg)
    thumb_a = 62 - 62 * max(0, t) * 1.3
    tx, ty = 50, -46
    if t < 0:  # 👍: bosh barmoq mushtning chetidan, tashqariga og'ib chiqadi
        tx, ty, thumb_a = 58, -96, 24
    thumb, _ = _finger(tx, ty, thumb_a, 98 if t >= 0 else 104, 33, max(0, t) * .4)
    palm = ('<path d="M-52 -2C-60 -44 -58 -92 -50 -118C-20 -128 26 -130 50 -120C60 -96 66 -54 54 -4C34 14 -32 14 -52 -2Z" '
            'fill="url(#skinc)" stroke="#7f4726" stroke-width="2"/>'
            '<path d="M-28 -84C-8 -70 18 -70 38 -88M-34 -34C-14 -48 -2 -74 -2 -94" fill="none" stroke="#8a5230" '
            'stroke-width="2.4" stroke-linecap="round" opacity=".45"/>'
            '<ellipse cx="40" cy="-38" rx="26" ry="36" fill="#c98657" opacity=".55"/>')
    return f'<g transform="scale({mirror},1)">{"".join(under)}{thumb if t >= .5 else ""}{palm}{thumb if t < .5 else ""}{"".join(over)}</g>'


def arm(ex: float, ey: float, wx: float, wy: float, ang: float, curls, mirror: int) -> str:
    """Yeng (tirsak -> bilak), yeng uchi va kaft. ang - kaftning og'ishi (daraja, 0 - tepaga)."""
    dx, dy = wx - ex, wy - ey
    n = math.hypot(dx, dy) or 1
    ux, uy = dx / n, dy / n
    px, py = -uy, ux
    cuffx, cuffy = wx - ux * 42, wy - uy * 42  # yeng tugaydigan joy (bilak ko'rinadi)

    def quad(x1, y1, w1, x2, y2, w2):
        return (f"M{x1 + px * w1:.1f} {y1 + py * w1:.1f}L{x2 + px * w2:.1f} {y2 + py * w2:.1f}"
                f"L{x2 - px * w2:.1f} {y2 - py * w2:.1f}L{x1 - px * w1:.1f} {y1 - py * w1:.1f}Z")
    grad = (f'<linearGradient id="sl{mirror + 1}" gradientUnits="userSpaceOnUse" x1="{ex + px * 90:.0f}" y1="{ey + py * 90:.0f}" '
            f'x2="{ex - px * 90:.0f}" y2="{ey - py * 90:.0f}"><stop offset="0" stop-color="#000" stop-opacity=".55"/>'
            '<stop offset=".42" stop-color="#9fb8e0" stop-opacity=".16"/><stop offset="1" stop-color="#000" stop-opacity=".62"/></linearGradient>')
    sleeve = quad(ex, ey, 92, cuffx, cuffy, 63)
    band = quad(cuffx - ux * 40, cuffy - uy * 40, 66, cuffx, cuffy, 64)
    bx, by = cuffx - ux * 20 + px * 42 * -mirror, cuffy - uy * 20 + py * 42 * -mirror
    wrist = (f'<path d="M{cuffx - ux * 6:.1f} {cuffy - uy * 6:.1f}L{wx:.1f} {wy:.1f}" stroke="url(#skinc)" stroke-width="88" '
             f'stroke-linecap="butt" fill="none"/>')
    palm = (f'<g filter="url(#skin)" transform="translate({wx + ux * 6:.1f} {wy + uy * 6:.1f}) rotate({ang:.2f}) scale(.98)">'
            f'{hand(curls, mirror)}</g>')
    return (f'<g filter="url(#armshade)">{grad}<g filter="url(#skin)">{wrist}</g>{palm}'
            f'<path d="{sleeve}" fill="url(#denim)"/><path d="{sleeve}" fill="url(#sl{mirror + 1})"/>'
            f'<path d="{band}" fill="#1a2b4e"/><path d="{band}" fill="url(#denim)" opacity=".55"/><path d="{band}" fill="url(#sl{mirror + 1})"/>'
            f'<path d="M{cuffx + px * 60 - ux * 34:.1f} {cuffy + py * 60 - uy * 34:.1f}L{cuffx - px * 60 - ux * 34:.1f} '
            f'{cuffy - py * 60 - uy * 34:.1f}" stroke="#c98d55" stroke-width="2" stroke-dasharray="7 5" opacity=".8"/>'
            f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="8" fill="#6d5338" stroke="#2c2015" stroke-width="2"/></g>')


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _keys(n_scenes: int, step: float, dur: float) -> tuple[list, list]:
    """Qo'l harakatlari jadvali. Har sahna: diagrammaga ko'rsatadi -> ikki kaft bilan tushuntiradi -> barmoq bilan sanaydi."""
    active, other = [(0.0, "rest")], [(0.0, "rest")]
    for k in range(n_scenes):
        s, last = k * step, k == n_scenes - 1
        if last:  # CTA: ikki qo'l ochiq, keyin bosh barmoq
            active += [(s + .2, "open"), (s + step * .55, "thumb")]
            other += [(s + .3, "open"), (s + step * .55, "rest")]
        elif k == 0:  # hook: ikki kaft ochiq - savol
            active += [(s + .9, "open"), (s + step * .55, "point")]
            other += [(s + 1.0, "open"), (s + step * .55, "rest")]
        else:
            active += [(s + .1, "point"), (s + step * .45, "open"), (s + step * .72, COUNT[min(k - 1, 4)]),
                       (s + step * .96, "point")]
            other += [(s + step * .45, "open"), (s + step * .72, "rest")]
    return active, other


def frames(n_scenes: int, step: float, dur: float, fps: int, mouth: list[int], blink: list[bool], denim: str = "") -> list[dict]:
    """Har kadr holati: {x, r, h, n, m, b, a} - gavda joyi/og'ishi, bosh burilishi/nod, og'iz, ko'z, qo'llar SVG'si."""
    active, other = _keys(n_scenes, step, dur)
    out = []
    n = int(dur * fps)

    def pose(keys, t):
        """(nomi, keyingi nomi, aralash) - o'tish .32 s."""
        cur = keys[0][1]
        for at, name in keys:
            if t >= at:
                prev, cur, since = cur, name, t - at
        return prev, cur, _ease(since / .32)

    def spot(name: str, d: int, nx: float, t: float, lvl: float) -> tuple:
        """Kaft joyi (bilak x, y, og'ish, barmoqlar) - d: -1 ekran chapi, +1 ekran o'ngi."""
        beat = lvl * 16 * math.sin(t * 7.3 + d)  # gap zarbiga yengil harakat
        if name == "rest":
            return nx + d * 235, DESK_Y + 150, d * 4.0, HANDS["relax"]
        if name == "point":
            return nx + d * 285, 1420 + beat * .4, d * 58.0, HANDS["point"]
        if name == "open":
            return nx + d * (285 + 18 * math.sin(t * 2.3)), 1500 + beat, d * (20 + 7 * math.sin(t * 3.1)), HANDS["open"]
        if name == "thumb":
            return nx + d * 265, 1480 + beat * .5, d * 6.0, HANDS["thumb"]
        return nx + d * 275, 1460 + beat * .5, d * 10.0, HANDS[name]  # sanash

    for f in range(n):
        t = f / fps
        k = min(int(t / step), n_scenes - 1)
        side = k % 2
        since = t - k * step
        a = SIDES[(k - 1) % 2] if k else SIDES[0]
        nx = a + (SIDES[side] - a) * _ease(since / .7)
        lvl = (mouth[f] if f < len(mouth) else 0) / (len(th.LEVELS) - 1)
        toward = -1 if side == 0 else 1  # diagramma tomoni
        rot = 1.7 * math.sin(t * 1.9) + 1.0 * math.sin(t * .67 + 1) + toward * 1.2
        nod = 3.2 * lvl * math.sin(t * 8.1) + 2 * math.sin(t * 1.3)
        arms = []
        for keys, d in ((active, toward), (other, -toward)):
            p0, p1, mix = pose(keys, t)
            x0, y0, a0, c0 = spot(p0, d, nx, t, lvl)
            x1, y1, a1, c1 = spot(p1, d, nx, t, lvl)
            wx, wy, ang = x0 + (x1 - x0) * mix, y0 + (y1 - y0) * mix, a0 + (a1 - a0) * mix
            curls = tuple(u + (v - u) * mix for u, v in zip(c0, c1))
            mirror = 1 if d < 0 else -1
            arms.append(arm(nx + d * 300, DESK_Y + 150, wx, wy, ang, curls, mirror))
        out.append({"x": round(nx - NECK_X * SCALE, 2), "tr": round(.5 * math.sin(t * 1.1) + toward * .5, 3),
                    "ty": round(4 * math.sin(t * 1.5), 2), "h": round(rot, 3), "n": round(nod, 2),
                    "m": mouth[f] if f < len(mouth) else 0, "b": bool(blink[f]) if f < len(blink) else False,
                    "a": "".join(arms)})
    return out


def html(rig: dict) -> str:
    """Personaj qatlamlari va har kadr holatini qo'yadigan __rig()."""
    def img(p, cls=""):
        uri, x, y, w, h = p
        return f'<img class="{cls}" src="{uri}" style="position:absolute;left:{x:.2f}px;top:{y:.2f}px;width:{w:.2f}px;height:{h:.2f}px;visibility:hidden">'
    mouths = "".join(img(p, "fm") for p in rig["mouths"])
    blink = img(rig["blink"], "fb") if rig["blink"] else ""
    px, py = NECK_X * SCALE, NECK_Y * SCALE
    base = f'style="position:absolute;left:0;top:0;width:{rig["w"]}px;height:{rig["h"]}px"'
    return f"""<div id="pr" style="position:absolute;left:0;top:{TOP}px;width:{rig['w']}px;height:{rig['h']}px;transform-origin:{px}px 100%">
<img src="{rig['torso']}" {base}>
<div id="hd" {base.replace('style="', f'style="transform-origin:{px}px {py}px;')}><img src="{rig['head']}" {base}>{mouths}{blink}</div></div>
<svg id="arms" width="1080" height="1920" style="position:absolute;left:0;top:0;overflow:visible">
<defs><linearGradient id="skinc" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ecb88f"/><stop offset="1" stop-color="#d4966a"/></linearGradient></defs>
{DEFS.format(denim=rig['denim'])}<g id="armg"></g></svg>
<script>window.__rig=function(s){{var p=document.getElementById('pr');
p.style.transform='translate('+s.x+'px,'+s.ty+'px) rotate('+s.tr+'deg)';
document.getElementById('hd').style.transform='rotate('+s.h+'deg) translateY('+s.n+'px)';
var e=document.querySelectorAll('.fm');for(var i=0;i<e.length;i++)e[i].style.visibility=(i===s.m-1)?'visible':'hidden';
var b=document.querySelector('.fb');if(b)b.style.visibility=s.b?'visible':'hidden';
document.getElementById('armg').innerHTML=s.a;}};</script>"""
