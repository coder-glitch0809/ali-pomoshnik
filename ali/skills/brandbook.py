"""Brendbuk: brendning to'liq qo'llanmasi - ko'p sahifali PDF va logotip fayllari.

Sahifalar: muqova, brend mohiyati (missiya, qadriyatlar, auditoriya, ovoz ohangi), logotip (asosiy, oq/qora fonda,
monoxrom, belgi), logotip qoidalari (xavfsiz zona, minimal o'lcham, taqiqlar), rang palitrasi (HEX, RGB, CMYK),
tipografiya, qo'llanilishi (vizitka, Instagram post, peshlavha) va xulosa.
Logotip alohida: .svg (vektor, Illustrator/CorelDRAW ochadi) va shaffof fonli .png.
"""
from __future__ import annotations

from pathlib import Path

from .. import outbox
from . import skill

W, H = 1754, 1240  # A4 albom, 150 dpi
LOGO_STYLES = ["monogram", "circle", "wordmark"]

TEXT = {
    "uz": {
        "book": "BRENDBUK", "guide": "Brendni qo'llash bo'yicha qo'llanma", "essence": "Brend mohiyati",
        "mission": "Missiya", "values": "Qadriyatlar", "audience": "Auditoriya", "tone": "Ovoz ohangi",
        "logo": "Logotip", "main": "Asosiy versiya", "dark": "Qora fonda", "mono": "Monoxrom", "mark": "Belgi",
        "rules": "Logotip qoidalari", "clear": "Xavfsiz zona", "clear_t": "Logotip atrofida kamida x (belgi balandligining yarmi) bo'sh joy qoldiring.",
        "min": "Minimal o'lcham", "min_t": "Bosmada 25 mm, ekranda 120 px dan kichik qilmang.",
        "dont": "Taqiqlanadi", "donts": ["Cho'zish", "Burish", "Boshqa rang", "Ola-bula fon"],
        "colors": "Rang palitrasi", "type": "Tipografiya", "heading": "Sarlavha shrifti", "body": "Matn shrifti",
        "scale": "O'lchamlar shkalasi", "apps": "Qo'llanilishi", "card": "Vizitka 90×50 mm", "post": "Instagram post",
        "sign": "Peshlavha", "do": "Shunday qiling", "dos": ["Faqat tasdiqlangan ranglar", "Logotipga yetarli joy",
                                                        "Bir xil shriftlar", "Yuqori sifatli fayllar (SVG, PDF)"],
        "contact": "Savollar bo'yicha: brend menejeri", "sample": "Sifat, ishonch va zamonaviy uslub",
        "text_role": "Matn", "bg_role": "Fon", "person": "Ism Familiya", "position": "Lavozim", "city": "Toshkent",
        "cmyk_note": "CMYK - taxminiy; bosmadan oldin Pantone/bosmaxona namunasi bilan solishtiring.",
        "fonts_note": "Shriftlar: Google Fonts - {}, {}. Kompyuterda yo'q bo'lsa - o'rnating.",
    },
    "ru": {
        "book": "БРЕНДБУК", "guide": "Руководство по использованию бренда", "essence": "Суть бренда",
        "mission": "Миссия", "values": "Ценности", "audience": "Аудитория", "tone": "Тон коммуникации",
        "logo": "Логотип", "main": "Основная версия", "dark": "На тёмном фоне", "mono": "Монохром", "mark": "Знак",
        "rules": "Правила логотипа", "clear": "Охранное поле", "clear_t": "Оставляйте вокруг логотипа не меньше x (половина высоты знака).",
        "min": "Минимальный размер", "min_t": "В печати не меньше 25 мм, на экране не меньше 120 px.",
        "dont": "Запрещено", "donts": ["Растягивать", "Поворачивать", "Менять цвет", "Пёстрый фон"],
        "colors": "Цветовая палитра", "type": "Типографика", "heading": "Шрифт заголовков", "body": "Шрифт текста",
        "scale": "Шкала размеров", "apps": "Применение", "card": "Визитка 90×50 мм", "post": "Пост Instagram",
        "sign": "Вывеска", "do": "Так правильно", "dos": ["Только утверждённые цвета", "Достаточно места вокруг логотипа",
                                                       "Единые шрифты", "Качественные файлы (SVG, PDF)"],
        "contact": "По вопросам: бренд-менеджер", "sample": "Качество, доверие и современный стиль",
        "text_role": "Текст", "bg_role": "Фон", "person": "Имя Фамилия", "position": "Должность", "city": "Ташкент",
        "cmyk_note": "CMYK приблизительный; перед печатью сверьте с Pantone/образцом типографии.",
        "fonts_note": "Шрифты: Google Fonts - {}, {}. Если их нет на компьютере - установите.",
    },
}


# ------------------------------------------------------------------ yordamchilar
def _font(size: int, bold: bool = False):
    """Kirill va lotinni qo'llaydigan shrift (Linux DejaVu yoki Windows Segoe UI / Arial)."""
    from PIL import ImageFont
    names = (["DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/segoeuib.ttf",
              "C:/Windows/Fonts/arialbd.ttf"] if bold else
             ["DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/segoeui.ttf",
              "C:/Windows/Fonts/arial.ttf"])
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _clean(value, limit=300) -> str:
    return " ".join(str(value or "").split())[:limit]


def _hex(value, default: str) -> str:
    v = str(value or "").strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    try:
        int(v, 16)
        return "#" + v.upper() if len(v) == 6 else default
    except ValueError:
        return default


def _rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _cmyk(h: str) -> str:
    r, g, b = (c / 255 for c in _rgb(h))
    k = 1 - max(r, g, b)
    if k >= 1:
        return "0 / 0 / 0 / 100"
    c, m, y = ((1 - x - k) / (1 - k) for x in (r, g, b))
    return " / ".join(str(round(v * 100)) for v in (c, m, y, k))


def _light(h: str) -> bool:
    r, g, b = _rgb(h)
    return 0.299 * r + 0.587 * g + 0.114 * b > 160


def _mix(h: str, other: str, k: float) -> str:
    a, b = _rgb(h), _rgb(other)
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * k) for x, y in zip(a, b))


def _initials(name: str) -> str:
    words = [w for w in name.replace("-", " ").split() if w[:1].isalnum()]
    return ("".join(w[0] for w in words[:2]) if len(words) > 1 else name[:2]).upper() or "B"


def _wrap(draw, text: str, font, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        test = f"{line} {word}".strip()
        if draw.textlength(test, font=font) <= width or not line:
            line = test
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def _paragraph(draw, xy, text, font, width, fill, gap=1.45) -> int:
    x, y = xy
    for line in _wrap(draw, text, font, width):
        draw.text((x, y), line, font=font, fill=fill)
        y += int(font.size * gap)
    return y


# ------------------------------------------------------------------ logotip
def _draw_logo(img, x: int, y: int, height: int, name: str, style: str, mark_color: str, text_color: str,
               mark_text: str = "#FFFFFF", logo_img=None) -> tuple[int, int]:
    """Logotipni (belgi + nom) chizadi, (eni, bo'yi) qaytaradi. logo_img - foydalanuvchining tayyor logotipi."""
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    if logo_img is not None:
        logo = logo_img.copy()
        logo.thumbnail((height * 4, height))
        img.paste(logo, (x, y), logo if logo.mode == "RGBA" else None)
        return logo.width, logo.height
    gap = int(height * .28)
    mark_w = 0
    if style != "wordmark":
        box = (x, y, x + height, y + height)
        if style == "circle":
            d.ellipse(box, fill=mark_color)
        else:
            d.rounded_rectangle(box, radius=int(height * .24), fill=mark_color)
        f = _font(int(height * .44), True)
        d.text((x + height / 2, y + height / 2), _initials(name), font=f, fill=mark_text, anchor="mm")
        mark_w = height + gap
    f = _font(int(height * (.5 if style != "wordmark" else .78)), True)
    d.text((x + mark_w, y + height / 2), name, font=f, fill=text_color, anchor="lm")
    return mark_w + int(d.textlength(name, font=f)), height


def _logo_svg(name: str, style: str, primary: str, text_color: str, heading: str) -> str:
    h = 120
    est = int(len(name) * h * .5 * .62)
    mark = ""
    tx = 0
    if style != "wordmark":
        shape = (f'<circle cx="{h / 2}" cy="{h / 2}" r="{h / 2}" fill="{primary}"/>' if style == "circle" else
                 f'<rect width="{h}" height="{h}" rx="{int(h * .24)}" fill="{primary}"/>')
        mark = (f'{shape}<text x="{h / 2}" y="{h / 2}" dy=".35em" text-anchor="middle" font-size="{int(h * .44)}" '
                f'font-weight="700" fill="#FFFFFF">{_esc(_initials(name))}</text>')
        tx = int(h * 1.28)
    size = int(h * (.5 if style != "wordmark" else .78))
    width = tx + (est if style != "wordmark" else int(len(name) * size * .62)) + 20
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {h}" width="{width}" height="{h}" '
            f'font-family="{_esc(heading)}, Montserrat, Arial, sans-serif">{mark}'
            f'<text x="{tx}" y="{h / 2}" dy=".35em" font-size="{size}" font-weight="700" fill="{text_color}">{_esc(name)}</text>'
            f'<!-- Bosmaga topshirishdan oldin matnni egri chiziqqa o\'tkazing (Create Outlines / Ctrl+Q) --></svg>')


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ------------------------------------------------------------------ sahifalar
class Book:
    def __init__(self, name, primary, dark, light, t):
        self.name, self.primary, self.dark, self.light, self.t = name, primary, dark, light, t
        self.pages = []

    def page(self, title: str | None, bg: str | None = None):
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (W, H), bg or "#FFFFFF")
        d = ImageDraw.Draw(img)
        if title:
            n = len(self.pages) + 1
            d.text((110, 100), f"{n:02d}", font=_font(30, True), fill=self.primary)
            d.text((180, 100), title.upper(), font=_font(30, True), fill=self.dark)
            d.line([(110, 160), (W - 110, 160)], fill=_mix(self.dark, "#FFFFFF", .85), width=2)
            d.text((W - 110, H - 70), f"{self.name} · {self.t['book']}", font=_font(22), fill=_mix(self.dark, "#FFFFFF", .5), anchor="rs")
        self.pages.append(img)
        return img, d


@skill(
    description=(
        "BRENDBUK yaratadi: brendning to'liq qo'llanmasi ko'p sahifali PDF ko'rinishida - muqova, brend mohiyati "
        "(missiya, qadriyatlar, auditoriya, ovoz ohangi), logotip versiyalari (asosiy, qora fonda, monoxrom, belgi), "
        "logotip qoidalari (xavfsiz zona, minimal o'lcham, taqiqlar), rang palitrasi (HEX/RGB/CMYK), tipografiya, "
        "qo'llanilishi (vizitka, Instagram post, peshlavha). Logotip alohida .svg va shaffof .png. Fayllar avtomatik yuboriladi."
    ),
    params={
        "brand_name": {"type": "string", "description": "Brend nomi"},
        "tagline": {"type": "string", "description": "Shior (qisqa)"},
        "mission": {"type": "string", "description": "Missiya / brend haqida 2-4 gap"},
        "values": {"type": "array", "items": {"type": "string"}, "description": "3-5 qadriyat"},
        "audience": {"type": "string", "description": "Maqsadli auditoriya tavsifi"},
        "tone": {"type": "array", "items": {"type": "string"}, "description": "Ovoz ohangi: 3-4 sifat (do'stona, ishonchli...)"},
        "colors": {"type": "array", "items": {"type": "object"},
                   "description": "Palitra: [{name, hex, role}] - birinchisi asosiy rang. 3-6 ta rang"},
        "heading_font": {"type": "string", "description": "Sarlavha shrifti nomi (masalan Montserrat)"},
        "body_font": {"type": "string", "description": "Matn shrifti nomi (masalan Inter)"},
        "logo_style": {"type": "string", "enum": LOGO_STYLES, "description": "Logotip turi: monogram (standart), circle, wordmark"},
        "logo_path": {"type": "string", "description": "Tayyor logotip fayli (PNG) bo'lsa - uning yo'li (ixtiyoriy)"},
        "language": {"type": "string", "enum": ["uz", "ru"], "description": "Brendbuk tili (standart uz)"},
    },
    required=["brand_name"],
)
def make_brandbook(brand_name: str, tagline: str = "", mission: str = "", values: list | None = None,
                   audience: str = "", tone: list | None = None, colors: list | None = None,
                   heading_font: str = "Montserrat", body_font: str = "Inter", logo_style: str = "monogram",
                   logo_path: str = "", language: str = "uz") -> str:
    from PIL import Image, ImageDraw
    t = TEXT.get(language, TEXT["uz"])
    name = _clean(brand_name, 40) or "Brand"
    tagline, mission, audience = _clean(tagline, 120), _clean(mission, 700), _clean(audience, 400)
    values = [_clean(v, 60) for v in (values or []) if _clean(v)][:5]
    tone = [_clean(v, 40) for v in (tone or []) if _clean(v)][:4]
    style = logo_style if logo_style in LOGO_STYLES else "monogram"
    heading_font, body_font = _clean(heading_font, 40) or "Montserrat", _clean(body_font, 40) or "Inter"

    palette = []
    for c in colors or []:
        if isinstance(c, dict) and (h := _hex(c.get("hex"), "")):
            palette.append({"name": _clean(c.get("name"), 30) or h, "hex": h, "role": _clean(c.get("role"), 50)})
    if not palette:
        palette = [{"name": "Primary", "hex": "#1E3A8A", "role": ""}]
    primary = palette[0]["hex"]
    if len(palette) < 3:  # palitrani to'ldiramiz: to'q va och neytral
        palette += [{"name": "Dark", "hex": _mix(primary, "#000000", .78), "role": t["text_role"]},
                    {"name": "Light", "hex": _mix(primary, "#FFFFFF", .92), "role": t["bg_role"]}][:3 - len(palette)]
    palette = palette[:6]
    dark = next((c["hex"] for c in palette if not _light(c["hex"]) and c["hex"] != primary), _mix(primary, "#000000", .78))
    light = next((c["hex"] for c in palette if _light(c["hex"])), _mix(primary, "#FFFFFF", .92))
    on_primary = "#111111" if _light(primary) else "#FFFFFF"

    logo_img = None
    if logo_path:
        p = Path(logo_path).expanduser()
        if p.is_file():
            logo_img = Image.open(p).convert("RGBA")

    book = Book(name, primary, dark, light, t)

    # 1. Muqova
    img, d = book.page(None, primary)
    for i in range(6):  # bezak: shaffof doiralar
        r = 260 + i * 120
        d.ellipse([W - r // 2 - 200, H - r // 2 - 100, W + r // 2 - 200, H + r // 2 - 100],
                  outline=_mix(primary, on_primary, .12 + i * .02), width=3)
    _draw_logo(img, 130, 140, 110, name, style, on_primary, on_primary, primary, logo_img)
    d.text((130, 560), t["book"], font=_font(150, True), fill=on_primary)
    d.text((136, 740), tagline or t["guide"], font=_font(44), fill=_mix(on_primary, primary, .25))
    d.text((136, H - 120), t["guide"], font=_font(26), fill=_mix(on_primary, primary, .35))

    # 2. Brend mohiyati
    img, d = book.page(t["essence"])
    col = (W - 330) // 2
    y = _paragraph(d, (110, 220), t["mission"].upper(), _font(26, True), col, primary)
    y = _paragraph(d, (110, y + 10), mission or tagline or name, _font(40, True), col, dark, 1.35)
    if audience:
        y = _paragraph(d, (110, y + 50), t["audience"].upper(), _font(26, True), col, primary)
        _paragraph(d, (110, y + 10), audience, _font(30), col, _mix(dark, "#FFFFFF", .2))
    x2 = 110 + col + 110
    d.text((x2, 220), t["values"].upper(), font=_font(26, True), fill=primary)
    for i, v in enumerate(values or [name]):
        yy = 280 + i * 120
        d.rounded_rectangle([x2, yy, W - 110, yy + 96], radius=18, fill=_mix(primary, "#FFFFFF", .9))
        d.text((x2 + 30, yy + 48), f"{i + 1:02d}", font=_font(30, True), fill=primary, anchor="lm")
        d.text((x2 + 110, yy + 48), v, font=_font(32, True), fill=dark, anchor="lm")
    if tone:
        yy = 280 + max(1, len(values)) * 120 + 40
        d.text((x2, yy), t["tone"].upper(), font=_font(26, True), fill=primary)
        xx = x2
        for v in tone:
            f = _font(28, True)
            tw = d.textlength(v, font=f) + 60
            if xx + tw > W - 110:
                xx, yy = x2, yy + 80
            d.rounded_rectangle([xx, yy + 50, xx + tw, yy + 110], radius=30, outline=primary, width=3)
            d.text((xx + tw / 2, yy + 80), v, font=f, fill=primary, anchor="mm")
            xx += tw + 20

    # 3. Logotip versiyalari
    img, d = book.page(t["logo"])
    cells = [(t["main"], "#FFFFFF", primary, dark, "#FFFFFF"), (t["dark"], dark, primary, "#FFFFFF", "#FFFFFF"),
             (t["mono"], "#FFFFFF", "#111111", "#111111", "#FFFFFF"), (t["mark"], primary, on_primary, on_primary, primary)]
    cw, ch = (W - 220 - 40) // 2, (H - 360 - 40) // 2
    for i, (label, bg, mark, text_c, mark_t) in enumerate(cells):
        x, y = 110 + (i % 2) * (cw + 40), 210 + (i // 2) * (ch + 40)
        d.rounded_rectangle([x, y, x + cw, y + ch], radius=24, fill=bg, outline=_mix(dark, "#FFFFFF", .85), width=2)
        if i == 3 and style != "wordmark" and logo_img is None:
            s = int(ch * .5)
            mx, my = x + cw // 2 - s // 2, y + ch // 2 - s // 2 - 20
            (d.ellipse if style == "circle" else lambda b, fill: d.rounded_rectangle(b, radius=int(s * .24), fill=fill))(
                [mx, my, mx + s, my + s], fill=mark)
            d.text((mx + s / 2, my + s / 2), _initials(name), font=_font(int(s * .44), True), fill=mark_t, anchor="mm")
        else:
            layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            lw, lh = _draw_logo(layer, 0, 0, int(ch * .3), name, style, mark, text_c, mark_t, logo_img)
            scale = min(1, (cw - 120) / max(1, lw))
            if scale < 1:
                layer = layer.resize((int(cw * scale), int(ch * scale)))
                lw, lh = int(lw * scale), int(lh * scale)
            img.paste(layer, (x + (cw - lw) // 2, y + (ch - lh) // 2 - 20), layer)
        d.text((x + 30, y + ch - 40), label, font=_font(24, True), fill=_mix(text_c, bg, .4))

    # 4. Logotip qoidalari
    img, d = book.page(t["rules"])
    layer = Image.new("RGBA", (900, 200), (0, 0, 0, 0))
    lw, lh = _draw_logo(layer, 0, 0, 120, name, style, primary, dark, "#FFFFFF", logo_img)
    x0, y0, pad = 170, 360, 60
    d.rectangle([x0 - pad, y0 - pad, x0 + lw + pad, y0 + lh + pad], outline=primary, width=2)
    d.rectangle([x0, y0, x0 + lw, y0 + lh], outline=_mix(primary, "#FFFFFF", .5), width=1)
    img.paste(layer, (x0, y0), layer)
    for (ax, ay) in ((x0 - pad / 2, y0 + lh / 2), (x0 + lw + pad / 2, y0 + lh / 2), (x0 + lw / 2, y0 - pad / 2)):
        d.text((ax, ay), "x", font=_font(28, True), fill=primary, anchor="mm")
    d.text((110, 220), t["clear"], font=_font(30, True), fill=dark)
    _paragraph(d, (110, y0 + lh + pad + 30), t["clear_t"], _font(26), 800, _mix(dark, "#FFFFFF", .25))
    d.text((1060, 220), t["min"], font=_font(30, True), fill=dark)
    small = Image.new("RGBA", (900, 200), (0, 0, 0, 0))
    sw, sh = _draw_logo(small, 0, 0, 44, name, style, primary, dark, "#FFFFFF", logo_img)
    img.paste(small, (1060, 300), small)
    _paragraph(d, (1060, 380), t["min_t"], _font(26), 580, _mix(dark, "#FFFFFF", .25))
    d.text((110, 700), t["dont"].upper(), font=_font(26, True), fill="#DC2626")
    bw = (W - 220 - 3 * 30) // 4
    for i, label in enumerate(t["donts"]):
        x = 110 + i * (bw + 30)
        d.rounded_rectangle([x, 760, x + bw, 1040], radius=18, fill="#FFFFFF", outline="#E5E7EB", width=2)
        if i == 3:  # ola-bula fon: chiziqlar faqat kartochka ichida
            busy = Image.new("RGB", (bw, 280), "#F59E0B")
            bd = ImageDraw.Draw(busy)
            for k in range(-280, bw, 40):
                bd.line([(k, 0), (k + 280, 280)], fill="#10B981", width=14)
            mask = Image.new("L", (bw, 280), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, bw - 1, 279], radius=18, fill=255)
            img.paste(busy, (x, 760), mask)
        lay = Image.new("RGBA", (900, 200), (0, 0, 0, 0))
        mark = "#E11D48" if i == 2 else primary
        lw2, lh2 = _draw_logo(lay, 0, 0, 60, name, style, mark, "#E11D48" if i == 2 else dark, "#FFFFFF", logo_img)
        lay = lay.crop((0, 0, lw2, lh2))
        if i == 0:
            lay = lay.resize((int(lw2 * 1.35), int(lh2 * .6)))
        if i == 1:
            lay = lay.rotate(18, expand=True)
        lay.thumbnail((bw - 40, 200))
        img.paste(lay, (x + (bw - lay.width) // 2, 900 - lay.height // 2), lay)
        d.line([(x + bw - 70, 780), (x + bw - 30, 820)], fill="#DC2626", width=6)
        d.line([(x + bw - 30, 780), (x + bw - 70, 820)], fill="#DC2626", width=6)
        d.text((x + bw / 2, 1075), label, font=_font(24, True), fill=dark, anchor="mm")

    # 5. Ranglar
    img, d = book.page(t["colors"])
    n = len(palette)
    sw_w = (W - 220 - (n - 1) * 24) // n
    for i, c in enumerate(palette):
        x = 110 + i * (sw_w + 24)
        d.rounded_rectangle([x, 220, x + sw_w, 760], radius=22, fill=c["hex"],
                            outline="#E5E7EB" if _light(c["hex"]) else None, width=2)
        ink = "#111111" if _light(c["hex"]) else "#FFFFFF"
        d.text((x + 30, 270), c["name"], font=_font(34, True), fill=ink)
        if c["role"]:
            _paragraph(d, (x + 30, 320), c["role"], _font(22), sw_w - 60, ink)
        y = 800
        for label, value in (("HEX", c["hex"]), ("RGB", " / ".join(map(str, _rgb(c["hex"])))), ("CMYK", _cmyk(c["hex"]))):
            d.text((x, y), label, font=_font(20, True), fill=_mix(dark, "#FFFFFF", .45))
            d.text((x, y + 28), value, font=_font(26, True), fill=dark)
            y += 85
    d.text((110, H - 110), t["cmyk_note"],
           font=_font(20), fill=_mix(dark, "#FFFFFF", .45))

    # 6. Tipografiya
    img, d = book.page(t["type"])
    d.text((110, 220), t["heading"].upper(), font=_font(24, True), fill=primary)
    d.text((110, 260), heading_font, font=_font(96, True), fill=dark)
    d.text((110, 390), "Aa Bb Cc Dd Ee Ff Gg 0123456789", font=_font(40, True), fill=_mix(dark, "#FFFFFF", .2))
    d.text((110, 470), "Аа Бб Вв Гг Дд Ўў Ққ Ғғ Ҳҳ", font=_font(40, True), fill=_mix(dark, "#FFFFFF", .2))
    d.text((110, 590), t["body"].upper(), font=_font(24, True), fill=primary)
    d.text((110, 630), body_font, font=_font(72), fill=dark)
    _paragraph(d, (110, 740), (mission or t["sample"]) , _font(28), 760, _mix(dark, "#FFFFFF", .2))
    d.text((1000, 220), t["scale"].upper(), font=_font(24, True), fill=primary)
    y = 270
    for label, size, bold in (("H1", 72, True), ("H2", 52, True), ("H3", 38, True), ("Body", 26, False), ("Caption", 20, False)):
        d.text((1000, y), label, font=_font(20, True), fill=_mix(dark, "#FFFFFF", .5))
        d.text((1150, y - 6), t["sample"][:22], font=_font(size, bold), fill=dark)
        y += size + 70
    d.text((110, H - 110), t["fonts_note"].format(heading_font, body_font),
           font=_font(20), fill=_mix(dark, "#FFFFFF", .45))

    # 7. Qo'llanilishi
    img, d = book.page(t["apps"])
    # vizitka: old va orqa
    cx, cy, cw2, ch2 = 110, 230, 630, 350
    d.rounded_rectangle([cx + 10, cy + 12, cx + cw2 + 10, cy + ch2 + 12], radius=16, fill="#E5E7EB")
    d.rounded_rectangle([cx, cy, cx + cw2, cy + ch2], radius=16, fill=primary)
    lay = Image.new("RGBA", (900, 200), (0, 0, 0, 0))
    lw, lh = _draw_logo(lay, 0, 0, 70, name, style, on_primary, on_primary, primary, logo_img)
    lay = lay.crop((0, 0, lw, lh)); lay.thumbnail((cw2 - 80, 120))
    img.paste(lay, (cx + (cw2 - lay.width) // 2, cy + (ch2 - lay.height) // 2), lay)
    by = cy + ch2 + 50
    d.rounded_rectangle([cx + 10, by + 12, cx + cw2 + 10, by + ch2 + 12], radius=16, fill="#E5E7EB")
    d.rounded_rectangle([cx, by, cx + cw2, by + ch2], radius=16, fill="#FFFFFF", outline="#E5E7EB", width=2)
    d.text((cx + 50, by + 70), t["person"], font=_font(34, True), fill=dark)
    d.text((cx + 50, by + 120), t["position"], font=_font(22), fill=primary)
    for i, line in enumerate(("+998 90 000 00 00", "info@" + "".join(ch for ch in name.lower() if ch.isalnum())[:16] + ".uz", t["city"])):
        d.text((cx + 50, by + 200 + i * 38), line, font=_font(22), fill=_mix(dark, "#FFFFFF", .25))
    d.rectangle([cx + cw2 - 20, by, cx + cw2, by + ch2], fill=primary)
    d.text((cx, by + ch2 + 40), t["card"], font=_font(24, True), fill=dark)
    # Instagram post
    px, py, ps = 820, 230, 420
    d.rounded_rectangle([px, py, px + ps, py + ps], radius=20, fill=light)
    d.rectangle([px, py + ps * .62, px + ps, py + ps], fill=primary)
    lay = Image.new("RGBA", (900, 200), (0, 0, 0, 0))
    lw, lh = _draw_logo(lay, 0, 0, 50, name, style, primary, dark, "#FFFFFF", logo_img)
    lay = lay.crop((0, 0, lw, lh)); lay.thumbnail((ps - 60, 60))
    img.paste(lay, (px + 30, py + 30), lay)
    _paragraph(d, (px + 30, py + 130), tagline or t["sample"], _font(34, True), ps - 60, dark, 1.25)
    d.text((px + 30, py + ps * .62 + 50), "@" + "".join(ch for ch in name.lower() if ch.isalnum())[:20], font=_font(26, True), fill=on_primary)
    d.text((px, py + ps + 40), t["post"], font=_font(24, True), fill=dark)
    # peshlavha
    sx, sy, sw2, sh2 = 1320, 230, 324, 600
    d.rectangle([sx, sy, sx + sw2, sy + sh2], fill="#C8B8A6")
    d.rectangle([sx + 20, sy + 40, sx + sw2 - 20, sy + 150], fill=dark)
    lay = Image.new("RGBA", (900, 200), (0, 0, 0, 0))
    lw, lh = _draw_logo(lay, 0, 0, 60, name, style, primary, "#FFFFFF", "#FFFFFF", logo_img)
    lay = lay.crop((0, 0, lw, lh)); lay.thumbnail((sw2 - 70, 80))
    img.paste(lay, (sx + (sw2 - lay.width) // 2, sy + 95 - lay.height // 2), lay)
    d.rectangle([sx + 30, sy + 220, sx + sw2 - 30, sy + 560], fill="#93B4CC", outline=dark, width=6)
    d.rectangle([sx + sw2 // 2 - 50, sy + 380, sx + sw2 // 2 + 50, sy + 560], fill=_mix(dark, "#FFFFFF", .2))
    d.text((sx, sy + sh2 + 40), t["sign"], font=_font(24, True), fill=dark)

    # 8. Xulosa
    img, d = book.page(t["do"], light)
    for i, v in enumerate(t["dos"]):
        y = 240 + i * 130
        d.ellipse([110, y, 180, y + 70], fill=primary)
        d.line([(128, y + 36), (141, y + 50), (164, y + 22)], fill=on_primary, width=7, joint="curve")
        d.text((220, y + 35), v, font=_font(40, True), fill=dark, anchor="lm")
    _draw_logo(img, 110, H - 260, 90, name, style, primary, dark, "#FFFFFF", logo_img)
    d.text((W - 110, H - 215), t["contact"], font=_font(24), fill=_mix(dark, "#FFFFFF", .35), anchor="rm")

    # Saqlash
    pdf = outbox.new_path(f"{name} brendbuk", "pdf")
    book.pages[0].save(pdf, save_all=True, append_images=book.pages[1:], resolution=150)
    made = [pdf]
    if logo_img is None:
        svg = pdf.with_name(pdf.stem + "_logo.svg")
        svg.write_text(_logo_svg(name, style, primary, dark, heading_font), encoding="utf-8")
        made.append(svg)
        for suffix, mark, text_c in (("_logo.png", primary, dark), ("_logo_oq.png", "#FFFFFF", "#FFFFFF")):
            lay = Image.new("RGBA", (3000, 400), (0, 0, 0, 0))
            lw, lh = _draw_logo(lay, 40, 40, 320, name, style, mark, text_c, primary if mark == "#FFFFFF" else "#FFFFFF")
            path = pdf.with_name(pdf.stem + suffix)
            lay.crop((0, 0, lw + 80, lh + 80)).save(path)
            made.append(path)
    for p in made:
        outbox.register(p)
    return (f"✅ Brendbuk tayyor: {len(book.pages)} sahifali PDF"
            + (", logotip .svg (vektor) va .png (shaffof, rangli va oq)" if logo_img is None else "")
            + " - avtomatik yuboriladi.\nPalitra: " + ", ".join(f"{c['name']} {c['hex']}" for c in palette)
            + f"\nShriftlar: {heading_font} / {body_font}")
