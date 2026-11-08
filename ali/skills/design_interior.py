"""Interer / stend 3D vizualizatsiyasi: xona (do'kon, ofis, stend) perspektivada - mebel, devordagi yozuv,
oyna (vitrina) va shiftdagi hajmli harflar ranglari bilan. Natija: .png (kunduzgi va tungi)."""
from __future__ import annotations

from .. import outbox
from . import skill
from .design_floorplan import _font
from .design_media import _clean, _hex, _rgb

FURNITURE = {"counter", "shelf", "sofa", "table", "stand"}
# (nomi, eni, balandligi, chuqurligi) - metrda
SIZES = {"counter": (2.2, 1.0, .7), "shelf": (1.6, 2.0, .4), "sofa": (2.0, .8, .9), "table": (1.4, .75, .8),
         "stand": (1.2, 2.2, .5)}


def _shade(c: str, k: float) -> tuple:
    return tuple(max(0, min(255, int(v * k))) for v in _rgb(c))


@skill(
    description=(
        "INTERER 3D VIZUALIZATSIYA (render): xona perspektivada - devordagi yozuv/stend, qaysi mebel qayerda turishi, "
        "oynalardagi yozuv va shiftdagi hajmli harflar, hammasi aniq ranglarda. Kunduzgi va tungi .png avtomatik yuboriladi."
    ),
    params={
        "title": {"type": "string", "description": "Loyiha nomi"},
        "brand": {"type": "string", "description": "Devor va shiftdagi yozuv (brend nomi)"},
        "width_m": {"type": "number", "description": "Xona eni, m"},
        "depth_m": {"type": "number", "description": "Xona chuqurligi, m"},
        "height_m": {"type": "number", "description": "Shift balandligi, m"},
        "wall_color": {"type": "string", "description": "Devor rangi #RRGGBB"},
        "floor_color": {"type": "string", "description": "Pol rangi #RRGGBB"},
        "letter_color": {"type": "string", "description": "Hajmli harflar rangi #RRGGBB"},
        "furniture": {"type": "array", "items": {"type": "object"},
                      "description": "Mebel: [{kind: counter|shelf|sofa|table|stand, x (0..1 chapdan), color}]; "
                                     "shelf/stand orqa devor oldida, qolganlari zal ichida"},
        "wall_text": {"type": "string", "description": "Orqa devorga yoziladigan kichik matn (shior)"},
        "window_text": {"type": "string", "description": "Oynaga (vitrinaga) yopishtiriladigan yozuv"},
    },
    required=["title"],
)
def design_interior_render(title: str, brand: str = "", width_m: float = 6, depth_m: float = 5, height_m: float = 3,
                           wall_color: str = "#F3EEE6", floor_color: str = "#B08968", letter_color: str = "#FFC21A",
                           furniture: list | None = None, wall_text: str = "", window_text: str = "") -> str:
    from PIL import Image, ImageDraw
    title, brand = _clean(title, 60) or "Interer", _clean(brand, 30)
    wall_text, window_text = _clean(wall_text, 60), _clean(window_text, 30)
    w_m, d_m, h_m = (max(2.0, min(float(v or dflt), 40.0)) for v, dflt in ((width_m, 6), (depth_m, 5), (height_m, 3)))
    wall, floor, letters_hex = _hex(wall_color, "#F3EEE6"), _hex(floor_color, "#B08968"), _hex(letter_color, "#FFC21A")
    letters = tuple(_rgb(letters_hex))
    items = [f for f in (furniture or []) if isinstance(f, dict) and f.get("kind") in FURNITURE][:10]
    W, H = 1600, 1000
    paths = []
    for night in (False, True):
        img = Image.new("RGB", (W, H), "#101418" if night else "#FFFFFF")
        d = ImageDraw.Draw(img, "RGBA")
        k = .55 if night else 1.0
        # orqa devor to'rtburchagi (ichki), tashqi - kadr chetlari: bir nuqtali perspektiva
        bx0, bx1, by0, by1 = int(W * .27), int(W * .73), int(H * .2), int(H * .62)
        d.polygon([(0, 0), (W, 0), (bx1, by0), (bx0, by0)], fill=_shade("#FFFFFF", .95 * k))  # shift
        d.polygon([(0, 0), (bx0, by0), (bx0, by1), (0, H)], fill=_shade(wall, .82 * k))  # chap devor
        d.polygon([(W, 0), (bx1, by0), (bx1, by1), (W, H)], fill=_shade(wall, .78 * k))  # o'ng devor
        d.rectangle([bx0, by0, bx1, by1], fill=_shade(wall, k))  # orqa devor
        d.polygon([(0, H), (bx0, by1), (bx1, by1), (W, H)], fill=_shade(floor, k))  # pol
        for i in range(1, 8):  # pol chiziqlari
            t = i / 8
            d.line([(int(bx0 * (1 - t)), by1 + int((H - by1) * t)),
                    (bx1 + int((W - bx1) * t), by1 + int((H - by1) * t))], fill=(0, 0, 0, 40), width=2)
        sx = (bx1 - bx0) / w_m  # orqa devordagi 1 m ning piksel o'lchami
        if brand:  # orqa devorda hajmli harflar (yon soya bilan)
            f = _font(int(sx * h_m * .22), True)
            cx, cy = (bx0 + bx1) // 2, by0 + int((by1 - by0) * .3)
            if night:
                d.text((cx, cy), brand, font=f, fill=letters + (70,), anchor="mm", stroke_width=14, stroke_fill=letters + (40,))
            d.text((cx + 5, cy + 6), brand, font=f, fill=tuple(int(v * .45) for v in letters) + (255,), anchor="mm")
            d.text((cx, cy), brand, font=f, fill=letters + (255,), anchor="mm")
            if wall_text:
                d.text((cx, cy + int(f.size * .9)), wall_text, font=_font(int(f.size * .33)), fill=_shade("#222222", k) + (255,), anchor="mm")
        # oyna: chap devorda; yozuv oynaga yopishtirilgan
        wy0, wy1 = by0 + int((by1 - by0) * .18), by1 - int((by1 - by0) * .08)
        d.polygon([(int(bx0 * .35), wy0 - 60), (int(bx0 * .8), wy0), (int(bx0 * .8), wy1), (int(bx0 * .35), wy1 + 110)],
                  fill=(150, 200, 235, 90 if not night else 40), outline=(60, 60, 60, 255))
        if window_text:
            win = Image.new("RGBA", (360, 80), (0, 0, 0, 0))
            ImageDraw.Draw(win).text((180, 40), window_text, font=_font(46, True), fill=(255, 255, 255, 235), anchor="mm")
            win = win.transform(win.size, Image.AFFINE, (1, 0, 0, -.18, 1, 20), Image.BICUBIC)
            img.paste(win, (int(bx0 * .22), wy0 + 60), win)
        # shiftdagi hajmli harflar (kichik yorug' blok)
        if brand:
            d.rounded_rectangle([bx0 + 40, by0 - 8, bx1 - 40, by0 + 6], radius=4, fill=letters + (255 if night else 160,))
        # mebel
        for i, it in enumerate(sorted(items, key=lambda x: x["kind"] in ("shelf", "stand"), reverse=True)):
            kind, col = it["kind"], _hex(it.get("color"), "#7A5C3E")
            mw, mh, md = SIZES[kind]
            back = kind in ("shelf", "stand")
            depth_k = 1.0 if back else .55 + .18 * (i % 3)  # 1 - orqa devor oldida, kichikroq - yaqinroq
            scale = sx * (1 if back else 1.6 + (1 - depth_k) * 1.3)
            fx = _float(it.get("x"), .5)
            x0 = int(bx0 + (bx1 - bx0 - mw * scale) * fx) if back else int(W * (.12 + .5 * fx))
            y1 = by1 - 4 if back else int(by1 + (H - by1) * (1 - depth_k) * 1.4 + 40)
            y0 = y1 - int(mh * scale)
            d.rectangle([x0, y0, x0 + int(mw * scale), y1], fill=_shade(col, k))
            d.rectangle([x0, y0, x0 + int(mw * scale), y0 + max(6, int(mh * scale * .08))], fill=_shade(col, 1.25 * k))
            d.text((x0 + mw * scale / 2, y0 + mh * scale / 2), kind, font=_font(22, True), fill=(255, 255, 255, 210), anchor="mm")
        label = f"{title} · {w_m:g}×{d_m:g}×{h_m:g} m · " + ("TUN" if night else "KUN")
        d.rounded_rectangle([24, H - 64, 24 + int(d.textlength(label, font=_font(26, True))) + 30, H - 20], radius=12, fill=(0, 0, 0, 255))
        d.text((39, H - 42), label, font=_font(26, True), fill="#FFFFFF", anchor="lm")
        path = outbox.new_path(f"{title} 3D {'tun' if night else 'kun'}", "png")
        img.save(path, optimize=True)
        paths.append(path)
    for p in paths:
        outbox.register(p)
    spec = [f"Devor {wall}, pol {floor}, harflar {letters_hex}"]
    spec += [f"{it['kind']} ({_hex(it.get('color'), '#7A5C3E')}) - {SIZES[it['kind']][0]}×{SIZES[it['kind']][2]} m" for it in items]
    return ("✅ 3D vizualizatsiya tayyor: kunduzgi va tungi .png - avtomatik yuboriladi. Bu sxematik ko'rinish "
            "(aniq fotorealistik render uchun .obj ni 3ds Max'da render qiling).\n- " + "\n- ".join(spec))


def _float(v, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return default
