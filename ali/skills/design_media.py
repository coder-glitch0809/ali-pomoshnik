"""Tashqi reklama (hajmli harflar, lightbox, banner) va reklama videosi.

- design_signage: .svg (haqiqiy o'lcham mm, Illustrator/CorelDraw ochadi), kunduzgi va tungi maket .png,
  texnik topshiriq (harf balandligi, ko'rinish masofasi, materiallar, LED va quvvat hisobi).
- make_promo_video: .mp4 (9:16 / 16:9 / 1:1) va After Effects uchun .jsx skript (File > Scripts > Run Script File)
  - xuddi shu kompozitsiyani qatlamlar va animatsiya kalitlari bilan AE ichida yaratadi.
"""
from __future__ import annotations

import json
import math
import random

from .. import outbox
from . import skill
from .design_floorplan import _font

SIGN_KINDS = ["volumetric_letters", "lightbox", "banner", "neon"]


def _clean(value, limit=200):
    return " ".join(str(value or "").split())[:limit]


def _hex(value: str, default: str) -> str:
    value = str(value or "").strip()
    if value.startswith("#") and len(value) == 7:
        try:
            int(value[1:], 16)
            return value.upper()
        except ValueError:
            pass
    return default


def _rgb(h: str):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _fit_font(draw, text, max_w, max_h, bold=True):
    size = int(max_h)
    while size > 8:
        f = _font(size, bold)
        box = draw.textbbox((0, 0), text, font=f, anchor="ls")
        if box[2] - box[0] <= max_w and -box[1] <= max_h:
            return f, box
        size = int(size * .92)
    f = _font(8, bold)
    return f, draw.textbbox((0, 0), text, font=f, anchor="ls")


def _facade(w, h, night: bool, wall: str):
    """Bino fasadi: devor, vitrina, eshik, trotuar."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (w, h), "#0B1020" if night else "#BFD7EA")
    d = ImageDraw.Draw(img)
    for i in range(int(h * .25)):  # osmon
        k = i / (h * .25)
        c = (int(11 + 20 * k), int(16 + 22 * k), int(32 + 40 * k)) if night else (int(150 + 60 * k), int(195 + 30 * k), int(235 + 10 * k))
        d.line([(0, i), (w, i)], fill=c)
    base = _rgb(wall)
    wall_c = tuple(int(v * (.35 if night else 1)) for v in base)
    d.rectangle([0, int(h * .12), w, int(h * .86)], fill=wall_c)
    for y in range(int(h * .12), int(h * .86), 26):  # panel chiziqlari
        d.line([(0, y), (w, y)], fill=tuple(max(0, v - 14) for v in wall_c))
    gx0, gx1, gy0, gy1 = int(w * .08), int(w * .92), int(h * .5), int(h * .86)
    glass = (24, 40, 64) if night else (120, 160, 190)
    d.rectangle([gx0, gy0, gx1, gy1], fill=glass, outline=(40, 40, 40), width=8)
    for x in range(gx0, gx1, int((gx1 - gx0) / 4)):
        d.line([(x, gy0), (x, gy1)], fill=(40, 40, 40), width=6)
    door = (int(w * .44), int(h * .56), int(w * .56), gy1)
    d.rectangle(door, fill=(30, 30, 30) if night else (70, 80, 90), outline=(20, 20, 20), width=6)
    if night:  # vitrina ichki yorug'i
        d.rectangle([gx0 + 10, gy0 + 10, gx1 - 10, gy1 - 10], outline=(255, 214, 140), width=3)
    d.rectangle([0, int(h * .86), w, h], fill=(40, 40, 46) if night else (165, 165, 170))
    return img


def _render_sign(img, box, text, sub, kind, face, side, panel, night, depth_px):
    """Hajmli harf / lightbox / banner / neon ni fasad rasmiga chizadi."""
    from PIL import Image, ImageDraw, ImageFilter
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(img)
    if kind in ("lightbox", "banner"):
        pc = _rgb(panel)
        if kind == "lightbox":
            d.rounded_rectangle([x0 - 6, y0 - 6, x1 + 6 + depth_px // 2, y1 + 6 + depth_px // 2], radius=10, fill=(30, 30, 30))
        d.rectangle([x0, y0, x1, y1], fill=pc if not night or kind == "lightbox" else tuple(int(v * .4) for v in pc))
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    sub_h = (y1 - y0) * (.24 if sub else 0)
    f, tb = _fit_font(ld, text, (x1 - x0) * .92, (y1 - y0 - sub_h) * .78)
    tw = tb[2] - tb[0]
    tx = (x0 + x1) / 2 - tw / 2 - tb[0]
    ty = y0 + (y1 - y0 - sub_h) * .5 + (-tb[1]) * .45
    fc, sc = _rgb(face), _rgb(side)
    if kind == "volumetric_letters":
        for k in range(depth_px, 0, -1):  # yon devorlar (ekstruziya)
            shade = tuple(int(v * (.55 + .35 * k / depth_px)) for v in sc)
            if night:
                shade = tuple(int(v * .5) for v in shade)
            ld.text((tx + k * .6, ty + k * .8), text, font=f, fill=shade + (255,), anchor="ls")
    face_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    fd = ImageDraw.Draw(face_layer)
    if kind == "neon":
        fd.text((tx, ty), text, font=f, fill=(0, 0, 0, 0), anchor="ls", stroke_width=max(2, int(f.size * .05)),
                stroke_fill=fc + (255,))
    else:
        fd.text((tx, ty), text, font=f, fill=fc + (255,), anchor="ls")
    if sub:
        fs, sb = _fit_font(fd, sub, (x1 - x0) * .8, sub_h * .7, False)
        fd.text(((x0 + x1) / 2, y1 - sub_h * .25), sub, font=fs, fill=fc + (255,), anchor="ms")
    if not night and kind == "volumetric_letters":  # soya
        shadow = face_layer.split()[3].point(lambda a: int(a * .35))
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sh.putalpha(shadow.filter(ImageFilter.GaussianBlur(6)))
        img.paste(sh, (depth_px + 6, depth_px + 10), sh)
    img.paste(layer, (0, 0), layer)
    if night and kind != "banner":  # LED yorug'ligi
        glow = Image.new("RGBA", img.size, fc + (0,))
        glow.putalpha(face_layer.split()[3].filter(ImageFilter.GaussianBlur(18 if kind == "neon" else 12)))
        img.paste(glow, (0, 0), glow)
        img.paste(glow, (0, 0), glow)
    img.paste(face_layer, (0, 0), face_layer)


def _svg(text, sub, kind, width_mm, height_mm, face, side, panel, letter_mm, depth_mm):
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_mm}mm" height="{height_mm}mm" '
             f'viewBox="0 0 {width_mm} {height_mm}">',
             f'<title>{esc(text)} - {kind}, {width_mm}x{height_mm} mm</title>',
             '<g id="ORLCHAM_RAMKA"><rect x="0" y="0" width="%d" height="%d" fill="none" stroke="#999" stroke-width="2" '
             'stroke-dasharray="20 10"/></g>' % (width_mm, height_mm)]
    if kind in ("lightbox", "banner"):
        parts.append(f'<g id="PANEL"><rect x="0" y="0" width="{width_mm}" height="{height_mm}" fill="{panel}"/></g>')
    main_y = height_mm * (.62 if sub else .7)
    style = f'font-family="Arial Black, Arial, sans-serif" font-weight="900" text-anchor="middle"'
    if kind == "volumetric_letters":
        parts.append(f'<g id="YON_DEVOR_{depth_mm}mm" opacity="0.9"><text x="{width_mm / 2 + depth_mm * .3}" y="{main_y + depth_mm * .4}" '
                     f'font-size="{letter_mm * 1.35:.0f}" {style} fill="{side}">{esc(text)}</text></g>')
    fill = "none" if kind == "neon" else face
    stroke = f' stroke="{face}" stroke-width="{max(6, letter_mm * .05):.0f}"' if kind == "neon" else ""
    parts.append(f'<g id="YUZ_AKRIL"><text x="{width_mm / 2}" y="{main_y}" font-size="{letter_mm * 1.35:.0f}" {style} '
                 f'fill="{fill}"{stroke}>{esc(text)}</text>')
    if sub:
        parts.append(f'<text x="{width_mm / 2}" y="{height_mm * .9}" font-size="{letter_mm * .5:.0f}" '
                     f'font-family="Arial, sans-serif" text-anchor="middle" fill="{face}">{esc(sub)}</text>')
    parts.append('</g>')
    parts.append(f'<!-- Ishlab chiqarishdan oldin: Illustrator - Type > Create Outlines, CorelDraw - Ctrl+Q (egri chiziqqa). '
                 f'Harf balandligi {letter_mm} mm, chuqurligi {depth_mm} mm. -->')
    parts.append('</svg>')
    return "\n".join(parts)


@skill(
    description=(
        "TASHQI REKLAMA dizayni: hajmli (bortma) harflar, lightbox, banner yoki neon yozuv. Natija avtomatik yuboriladi: "
        "haqiqiy o'lchamdagi vektor .svg (Illustrator/CorelDraw ochadi, ishlab chiqarishga tayyorlash uchun), binoga "
        "o'rnatilgan holatdagi KUNDUZGI va TUNGI maket .png, texnik topshiriq: harf balandligi, ko'rinish masofasi, "
        "materiallar (akril, PVX, kompozit, alyuminiy profil), LED modullar soni va quvvat bloki hisobi."
    ),
    params={
        "text": {"type": "string", "description": "Asosiy yozuv (do'kon nomi)"},
        "subtitle": {"type": "string", "description": "Kichik yozuv (ixtiyoriy: 'Oziq-ovqat 24/7')"},
        "kind": {"type": "string", "enum": SIGN_KINDS, "description": "Turi (standart volumetric_letters)"},
        "width_m": {"type": "number", "description": "Reklama joyining eni, m"},
        "height_m": {"type": "number", "description": "Balandligi, m"},
        "face_color": {"type": "string", "description": "Harf yuzi rangi #RRGGBB"},
        "side_color": {"type": "string", "description": "Harf yon devori rangi #RRGGBB"},
        "panel_color": {"type": "string", "description": "Lightbox/banner foni #RRGGBB"},
        "facade_color": {"type": "string", "description": "Bino devori rangi #RRGGBB"},
        "viewing_distance_m": {"type": "number", "description": "Qaysi masofadan o'qilishi kerak, m"},
    },
    required=["text"],
)
def design_signage(text: str, subtitle: str = "", kind: str = "volumetric_letters", width_m: float = 4.0,
                   height_m: float = 0.9, face_color: str = "", side_color: str = "", panel_color: str = "",
                   facade_color: str = "", viewing_distance_m: float = 0) -> str:
    from PIL import ImageDraw
    text, subtitle = _clean(text, 40) or "SHOP", _clean(subtitle, 60)
    kind = kind if kind in SIGN_KINDS else "volumetric_letters"
    width_m = max(.6, min(float(width_m or 4), 30.0))
    height_m = max(.3, min(float(height_m or .9), 6.0))
    face = _hex(face_color, "#FFFFFF" if kind != "neon" else "#FF3EA5")
    side = _hex(side_color, "#1F2937")
    panel = _hex(panel_color, "#1D4ED8")
    wall = _hex(facade_color, "#C8B8A6")
    letter_mm = int(height_m * 1000 * (.55 if subtitle else .72))
    depth_mm = {"volumetric_letters": 100, "lightbox": 120, "banner": 0, "neon": 30}[kind]
    # Sanoat qoidasi (USSC): 1 sm harf ~1.2 m gacha o'qiladi; eng kuchli ta'sir shu masofaning ~40% ida
    readable, impact = letter_mm / 10 * 1.2, letter_mm / 10 * .5
    need = float(viewing_distance_m or 0)
    face_area = width_m * .85 * letter_mm / 1000 * .45  # harflar yuzi taxminan
    modules = math.ceil(face_area / 0.012) if kind == "volumetric_letters" else math.ceil(width_m * height_m / 0.03)
    watts = modules * (0.72 if kind == "volumetric_letters" else 1.2) if kind not in ("banner", "neon") else \
        (width_m * 9 if kind == "neon" else 0)
    psu = math.ceil(watts * 1.25 / 50) * 50 if watts else 0
    materials = {
        "volumetric_letters": [f"Yuz: opal yoki rangli akril 3 mm ({face})", f"Yon devor: PVX 10 mm yoki alyuminiy profil, chuqurlik {depth_mm} mm ({side})",
                               "Orqa: PVX 8-10 mm", "Yoritish: 12V LED modullar (ichki yoritish), IP65 quvvat bloki",
                               "Mahkamlash: kompozit podlojka yoki distansion shpilka, metall karkas"],
        "lightbox": [f"Karkas: alyuminiy profil, chuqurlik {depth_mm} mm", f"Yuz: akril 3-4 mm yoki tentli material, chop etilgan ({panel})",
                     "Yoritish: LED lineykalar 12V, IP65 quvvat bloki", "Orqa va yon: kompozit 3 mm"],
        "banner": ["Material: frontlit banner 440-510 g/m², UV bo'yoq bilan chop", "Karkas: metall profil 20x20/40x20",
                   "Mahkamlash: lyuverslar har 30-50 sm, tortish arqoni"],
        "neon": ["Egiluvchan neon (LED flex neon) 12V, kesimi 6x12 mm", "Asos: tiniq akril 8-10 mm, lazer bilan kesilgan",
                 "Quvvat bloki IP65, taymer bilan"],
    }[kind]
    base = outbox.new_path(f"{text} reklama", "svg")
    stem = base.with_suffix("")
    base.write_text(_svg(text, subtitle, kind, int(width_m * 1000), int(height_m * 1000), face, side, panel, letter_mm,
                         depth_mm), encoding="utf-8")
    shots = []
    for night in (False, True):
        W, H = 1800, 1100
        img = _facade(W, H, night, wall)
        sx0, sx1 = int(W * .12), int(W * .88)
        sy0 = int(H * .18)
        sy1 = sy0 + int((sx1 - sx0) * height_m / width_m)
        sy1 = min(sy1, int(H * .46))
        _render_sign(img, (sx0, sy0, sx1, sy1), text, subtitle, kind, face, side, panel, night, 10 if kind == "volumetric_letters" else 6)
        d = ImageDraw.Draw(img)
        label = ("TUNGI KO'RINISH (LED yoqilgan)" if night else "KUNDUZGI KO'RINISH") + f" · {width_m:.1f} × {height_m:.2f} m"
        d.rounded_rectangle([30, H - 70, 30 + d.textlength(label, font=_font(26, True)) + 30, H - 22], radius=12,
                            fill=(0, 0, 0))
        d.text((45, H - 46), label, font=_font(26, True), fill=(255, 255, 255), anchor="lm")
        path = stem.parent / (stem.name + ("_tun.png" if night else "_kun.png"))
        img.save(path, optimize=True)
        shots.append(path)
    for p in shots + [base]:
        outbox.register(p)
    spec = [f"Turi: {kind}, joy {width_m:.2f} × {height_m:.2f} m", f"Asosiy harf balandligi: {letter_mm} mm"
            + (f", chuqurligi {depth_mm} mm" if depth_mm else ""),
            f"Ko'rinish: o'qiladi ~{readable:.0f} m gacha, eng yaxshi ta'sir ~{impact:.0f} m"
            + (f" - talab {need:.0f} m: {'yetarli' if need <= readable else 'harfni kamida ' + str(math.ceil(need / 1.2 * 10)) + ' mm qiling'}" if need else "")]
    if watts:
        spec.append(f"LED: ~{modules} modul, ~{watts:.0f} Vt, quvvat bloki {psu} Vt (25% zaxira bilan), IP65")
    spec += materials
    spec.append("Ruxsat: tashqi reklama uchun tuman/shahar hokimiyatidan ruxsatnoma oling; elektr ulanishini usta bajarsin.")
    return ("✅ Reklama dizayni tayyor: vektor .svg (haqiqiy o'lcham, mm), kunduzgi va tungi maket .png - avtomatik "
            "yuboriladi.\nTexnik topshiriq:\n- " + "\n- ".join(spec))


# ------------------------------------------------------------------ video
FORMATS = {"9:16": (720, 1280), "16:9": (1280, 720), "1:1": (1080, 1080)}


def _ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _frame(w, h, scene, t_local, dur, t_global, colors, particles, index):
    from PIL import Image, ImageDraw
    c1, c2, accent = (_rgb(c) for c in colors)
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    shift = (math.sin(t_global * .6) + 1) / 2
    for y in range(0, h, 4):  # silliq harakatlanuvchi gradient (uzilishsiz)
        k = min(1.0, max(0.0, y / h * .8 + shift * .2))
        col = tuple(int(a + (b - a) * k) for a, b in zip(c1, c2))
        d.rectangle([0, y, w, y + 4], fill=col)
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))  # sekin suzuvchi yorug' doiralar
    gd = ImageDraw.Draw(glow)
    for k, (cx, cy, rr) in enumerate(((.2, .25, .45), (.85, .7, .55), (.5, 1.0, .5))):
        x = (cx + .08 * math.sin(t_global * .4 + k * 2)) * w
        y = (cy + .05 * math.cos(t_global * .3 + k)) * h
        r = rr * min(w, h)
        gd.ellipse([x - r, y - r, x + r, y + r], fill=accent + (26,) if k != 1 else tuple(min(255, v + 40) for v in c2) + (34,))
    from PIL import ImageFilter
    soft = glow.filter(ImageFilter.GaussianBlur(60))
    img.paste(soft, (0, 0), soft)
    for (px, py, r, sp) in particles:  # suzuvchi zarralar
        yy = (py - t_global * sp) % 1.2 - .1
        d.ellipse([px * w - r, yy * h - r, px * w + r, yy * h + r], fill=tuple(min(255, v + 60) for v in accent))
    a_in, a_out = _ease(t_local / .6), _ease((dur - t_local) / .5)
    alpha = min(a_in, a_out)
    big = int(min(w, h) * (.11 if len(scene["title"]) < 14 else .075))
    title_f = _font(big, True)
    text_f = _font(int(big * .42))
    cy = h * .45 + (1 - a_in) * h * .06
    bar_w = int(w * .5 * a_in)
    d.rounded_rectangle([w / 2 - bar_w / 2, cy + big * .75, w / 2 + bar_w / 2, cy + big * .75 + 8], radius=4, fill=accent)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    lines = _wrap(od, scene["title"], title_f, w * .86)
    for k, line in enumerate(lines):
        od.text((w / 2, cy - (len(lines) - 1 - k) * big * 1.1), line, font=title_f, fill=(255, 255, 255, int(255 * alpha)), anchor="ms")
    if scene.get("text"):
        sub = _wrap(od, scene["text"], text_f, w * .8)
        for k, line in enumerate(sub[:4]):
            od.text((w / 2, cy + big * 1.6 + k * big * .58), line, font=text_f, fill=(235, 240, 255, int(235 * min(alpha, _ease((t_local - .25) / .6)))), anchor="ms")
    img.paste(overlay, (0, 0), overlay)
    prog = (index + t_local / dur)
    return img, prog


def _wrap(draw, text, font, width):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        test = (cur + " " + wd).strip()
        if draw.textlength(test, font=font) <= width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def _ae_script(title, scenes, size, fps, colors):
    data = json.dumps({"title": title, "scenes": scenes, "w": size[0], "h": size[1], "fps": fps, "colors": colors},
                      ensure_ascii=False)
    return """// Ali dizayn studiyasi -> After Effects. File > Scripts > Run Script File... bilan ishga tushiring.
// Har bir sahna: gradient fon, sarlavha va matn qatlamlari, kirish/chiqish animatsiyasi (Opacity, Position, Scale kalitlari).
(function () {
  var D = %s;
  function rgb(h) { return [parseInt(h.substr(1,2),16)/255, parseInt(h.substr(3,2),16)/255, parseInt(h.substr(5,2),16)/255]; }
  app.beginUndoGroup("Ali promo");
  var total = 0; for (var i = 0; i < D.scenes.length; i++) total += D.scenes[i].duration;
  var comp = app.project.items.addComp(D.title, D.w, D.h, 1, total, D.fps);
  var bg = comp.layers.addSolid(rgb(D.colors[0]), "Fon", D.w, D.h, 1, total);
  var ramp = bg.property("Effects").addProperty("ADBE Ramp");
  ramp.property("Start Color").setValue(rgb(D.colors[0])); ramp.property("End Color").setValue(rgb(D.colors[1]));
  var t = 0;
  for (var i = 0; i < D.scenes.length; i++) {
    var s = D.scenes[i];
    var layer = comp.layers.addText(s.title);
    var doc = layer.property("Source Text").value; doc.fontSize = Math.round(Math.min(D.w, D.h) * 0.09);
    doc.fillColor = [1,1,1]; doc.justification = ParagraphJustification.CENTER_JUSTIFY; doc.applyStroke = false;
    layer.property("Source Text").setValue(doc);
    layer.inPoint = t; layer.outPoint = t + s.duration;
    var pos = layer.property("Transform").property("Position");
    pos.setValueAtTime(t, [D.w/2, D.h*0.5]); pos.setValueAtTime(t + 0.6, [D.w/2, D.h*0.45]);
    var op = layer.property("Transform").property("Opacity");
    op.setValueAtTime(t, 0); op.setValueAtTime(t + 0.6, 100); op.setValueAtTime(t + s.duration - 0.5, 100); op.setValueAtTime(t + s.duration, 0);
    var sc = layer.property("Transform").property("Scale");
    sc.setValueAtTime(t, [90,90]); sc.setValueAtTime(t + 0.6, [100,100]);
    if (s.text) {
      var sub = comp.layers.addText(s.text);
      var d2 = sub.property("Source Text").value; d2.fontSize = Math.round(Math.min(D.w, D.h) * 0.038); d2.fillColor = [0.92,0.94,1];
      d2.justification = ParagraphJustification.CENTER_JUSTIFY; sub.property("Source Text").setValue(d2);
      sub.inPoint = t + 0.25; sub.outPoint = t + s.duration;
      sub.property("Transform").property("Position").setValue([D.w/2, D.h*0.58]);
      var o2 = sub.property("Transform").property("Opacity");
      o2.setValueAtTime(t + 0.25, 0); o2.setValueAtTime(t + 0.85, 100); o2.setValueAtTime(t + s.duration - 0.5, 100); o2.setValueAtTime(t + s.duration, 0);
    }
    t += s.duration;
  }
  comp.openInViewer();
  app.endUndoGroup();
})();
""" % data


@skill(
    description=(
        "Reklama / taqdimot VIDEOSI: sahnalar (sarlavha + matn), animatsiyali gradient fon, suzuvchi zarralar, silliq "
        "kirish-chiqish. Natija avtomatik yuboriladi: .mp4 (Instagram/Telegram uchun 9:16, YouTube 16:9 yoki 1:1) va "
        "After Effects .jsx skripti - AE'da xuddi shu kompozitsiyani tahrirlanadigan qatlamlar va animatsiya kalitlari "
        "bilan yaratadi. scenes: [{title, text, duration (2-6 s)}], 3-8 sahna, oxirgisi - nom va aloqa."
    ),
    params={
        "title": {"type": "string", "description": "Video nomi"},
        "scenes": {"type": "array", "items": {"type": "object"}, "description": "Sahnalar"},
        "format": {"type": "string", "enum": list(FORMATS), "description": "Kadr nisbati (standart 9:16)"},
        "colors": {"type": "array", "items": {"type": "string"}, "description": "[fon1, fon2, aksent] #RRGGBB"},
    },
    required=["title", "scenes"],
)
def make_promo_video(title: str, scenes: list, format: str = "9:16", colors: list | None = None) -> str:
    import imageio_ffmpeg
    title = _clean(title, 80) or "Promo"
    clean = []
    for s in (scenes or [])[:10]:
        if isinstance(s, dict) and _clean(s.get("title")):
            dur = float(s.get("duration") or 3)
            clean.append({"title": _clean(s["title"], 60), "text": _clean(s.get("text"), 160), "duration": max(1.5, min(dur, 8.0))})
    if not clean:
        return "scenes bo'sh: kamida bitta sahna (title) kerak."
    cols = [_hex(c, d) for c, d in zip((colors or []) + [None] * 3, ("#0F172A", "#1D4ED8", "#F59E0B"))][:3]
    w, h = FORMATS.get(format, FORMATS["9:16"])
    fps = 25
    rnd = random.Random(title)
    particles = [(rnd.random(), rnd.random(), rnd.uniform(1.5, 4.5), rnd.uniform(.03, .09)) for _ in range(40)]
    path = outbox.new_path(title, "mp4")
    writer = imageio_ffmpeg.write_frames(str(path), (w, h), fps=fps, codec="libx264", pix_fmt_out="yuv420p",
                                         macro_block_size=8, ffmpeg_log_level="error", output_params=["-crf", "23"])
    writer.send(None)
    t_global = 0.0
    try:
        for i, scene in enumerate(clean):
            frames = int(scene["duration"] * fps)
            for f in range(frames):
                img, _ = _frame(w, h, scene, f / fps, scene["duration"], t_global, cols, particles, i)
                writer.send(img.tobytes())
                t_global += 1 / fps
    finally:
        writer.close()
    jsx = path.with_suffix(".jsx")
    jsx.write_text(_ae_script(title, clean, (w, h), fps, cols), encoding="utf-8")
    outbox.register(path)
    outbox.register(jsx)
    total = sum(s["duration"] for s in clean)
    return (f"✅ Video tayyor: {path.name} ({format}, {w}x{h}, {total:.0f} s, {len(clean)} sahna) va After Effects skripti "
            f"{jsx.name} (AE: File > Scripts > Run Script File). Fayllar avtomatik yuboriladi.")
