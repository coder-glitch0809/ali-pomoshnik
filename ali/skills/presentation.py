"""PowerPoint dvigateli: mavzuga mos dizayn (informatika motivlari) va 50 daqiqalik dars taqdimoti.

- make_presentation: istalgan taqdimot.
- make_lesson_presentation: dars ishlanmasi bo'yicha 5 bosqichli 50 daqiqalik dars (Tashkiliy qism 5, Uy vazifasini
  so'rash 10, Yangi mavzu 15, Mustahkamlash 15, Yakuniy qism 5) + uy vazifasi + Word dars ishlanmasi.
Rasmlar PowerPoint'ning o'zida chiziladi (lupa, ikkilik kod, tarmoq, monitor, ma'lumotlar bazasi, qulf, sxema) va rangli
emoji-ikonkalar ishlatiladi - internet kerak emas, hammasi tahrirlanadi.
"""
from __future__ import annotations

import hashlib
import random
import re

from .. import outbox
from . import skill

W, H = 13.333, 7.5
FONT, MONO, EMOJI = "Calibri", "Consolas", "Segoe UI Emoji"
INK, MUTED, PAPER, CARD = "0F172A", "64748B", "F8FAFC", "FFFFFF"

# motif: (dark, primary, accent, second accent)
MOTIFS = {
    "search": ("0B1F3A", "2563EB", "F59E0B", "14B8A6"),
    "binary": ("0B1A14", "10B981", "22D3EE", "A3E635"),
    "network": ("1E1B4B", "6366F1", "EC4899", "22D3EE"),
    "hardware": ("1F2937", "F97316", "38BDF8", "A78BFA"),
    "data": ("0C4A6E", "0EA5E9", "FACC15", "34D399"),
    "security": ("111827", "EF4444", "FBBF24", "60A5FA"),
    "algorithm": ("2E1065", "8B5CF6", "34D399", "F472B6"),
    "code": ("0F172A", "3B82F6", "F472B6", "FACC15"),
    "office": ("14321F", "16A34A", "F59E0B", "3B82F6"),
}
MOTIF_WORDS = {
    "search": ("поиск", "qidiruv", "izlash", "search", "поисков", "браузер", "brauzer"),
    "binary": ("кодиров", "kodlash", "двоич", "ikkilik", "binary", "бит", "bit", "байт", "bayt", "ascii", "unicode",
               "систем счисл", "sanoq sistema", "информаци", "axborot", "ma'lumot"),
    "network": ("сет", "tarmoq", "интернет", "internet", "network", "протокол", "protokol", "wi-fi", "лвс"),
    "hardware": ("устройств", "qurilma", "процессор", "protsessor", "компьютер", "kompyuter", "аппарат", "hardware",
                 "память", "xotira", "клавиатур", "monitor"),
    "data": ("база данных", "baza", "database", "sql", "таблиц", "excel", "электронн"),
    "security": ("безопасн", "xavfsiz", "вирус", "virus", "пароль", "parol", "шифр", "shifr", "security"),
    "algorithm": ("алгоритм", "algoritm", "блок-схем", "blok-sxema", "цикл", "sikl", "ветвлен", "логик", "mantiq"),
    "code": ("python", "программ", "dastur", "код", "kod", "html", "css", "pascal", "c++", "java", "переменн", "o'zgaruvchi"),
    "office": ("word", "powerpoint", "презентац", "taqdimot", "текстов", "matn muharrir"),
}
ICONS = {
    "search": "🔍", "code": "💻", "binary": "🔢", "internet": "🌐", "data": "🗄️", "lock": "🔒", "idea": "💡",
    "book": "📚", "question": "❓", "task": "✍️", "home": "🏠", "clock": "⏰", "target": "🎯", "star": "⭐",
    "check": "✅", "people": "👥", "chart": "📊", "gear": "⚙️", "cloud": "☁️", "keyboard": "⌨️", "robot": "🤖",
    "image": "🖼️", "music": "🎵", "video": "🎬", "phone": "📱", "mail": "✉️", "key": "🔑", "warning": "⚠️",
    "trophy": "🏆", "brain": "🧠", "puzzle": "🧩", "rocket": "🚀", "folder": "📁", "link": "🔗", "pencil": "✏️",
    "eye": "👀", "hello": "👋", "calendar": "📅", "school": "🏫", "computer": "🖥️", "text": "🔤", "sound": "🔊",
}
STAGES = [  # (key, minutes, uz, ru, icon)
    ("organizational", 5, "Tashkiliy qism", "Организационный момент", "👋"),
    ("homework_check", 10, "Uy vazifasini so'rash", "Проверка домашнего задания", "📝"),
    ("new_topic", 15, "Yangi mavzu bayoni", "Объяснение новой темы", "💡"),
    ("reinforcement", 15, "Yangi mavzuni mustahkamlash", "Закрепление новой темы", "🧩"),
    ("conclusion", 5, "Yakuniy qism", "Итог урока", "🏁"),
]
DEFAULT_ACTIVITY = {
    "uz": ["Salomlashish, davomatni aniqlash, darsga tayyorgarlikni tekshirish, ma'naviy daqiqa.",
           "O'tilgan mavzu va uy vazifasi bo'yicha savol-javob, test, tarqatma materiallar; ishtirokni baholash.",
           "Yangi mavzuni slaydlar, sxemalar va hayotiy misollar orqali tushuntirish, oldingi mavzularga bog'lash.",
           "Savol-javob, test, amaliy topshiriq va interaktiv metodlar orqali bilimni mustahkamlash va baholash.",
           "Darsga yakun, baholarni e'lon qilish, uy vazifasini berish va qanday bajarishni tushuntirish."],
    "ru": ["Приветствие, отметка отсутствующих, проверка готовности к уроку, воспитательная минутка.",
           "Опрос по прошлой теме и домашнему заданию: вопросы, тест, раздаточный материал; оценивание.",
           "Объяснение новой темы через слайды, схемы и жизненные примеры, связь с прошлыми темами.",
           "Закрепление: вопросы, тест, практическое задание и интерактивные методы; оценивание.",
           "Подведение итогов, выставление оценок, домашнее задание и объяснение, как его выполнить."],
}
L10N = {
    "uz": {"min": "daqiqa", "plan": "Dars rejasi", "goals": "Dars maqsadlari", "edu": "Ta'limiy", "up": "Tarbiyaviy",
           "dev": "Rivojlantiruvchi", "hw": "Uy vazifasi", "fact": "Bilasizmi?", "task": "Amaliy topshiriq",
           "quiz": "Savol", "answer": "To'g'ri javob", "thanks": "E'tiboringiz uchun rahmat!", "stage": "bosqich",
           "grade": "sinf", "total": "Jami: 50 daqiqa", "lesson": "Dars", "teacher": "O'qituvchi"},
    "ru": {"min": "мин", "plan": "План урока", "goals": "Цели урока", "edu": "Образовательная", "up": "Воспитательная",
           "dev": "Развивающая", "hw": "Домашнее задание", "fact": "Знаете ли вы?", "task": "Практическое задание",
           "quiz": "Вопрос", "answer": "Правильный ответ", "thanks": "Спасибо за внимание!", "stage": "этап",
           "grade": "класс", "total": "Итого: 50 минут", "lesson": "Урок", "teacher": "Учитель"},
}


def _clean(value, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit]


def _list(value, limit: int = 40) -> list[str]:
    if isinstance(value, str):
        value = [v for v in re.split(r"\n+", value) if v.strip()]
    if not isinstance(value, list):
        return []
    return [_clean(v, 400) for v in value if _clean(v)][:limit]


def _icon(value: str, default: str = "") -> str:
    value = str(value or "").strip()
    return ICONS.get(value.lower(), value[:4] if value and not value.isascii() else default)


def choose_motif(text: str) -> str:
    low = text.lower()
    scores = {m: sum(low.count(w) for w in words) for m, words in MOTIF_WORDS.items()}
    best = max(scores, key=lambda m: scores[m])
    return best if scores[best] else "code"


def _rgb(hex_color: str):
    from pptx.dml.color import RGBColor
    return RGBColor.from_string(hex_color)


def _on(color: str) -> str:
    """Fon rangiga o'qiladigan matn rangi."""
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return INK if 0.299 * r + 0.587 * g + 0.114 * b > 165 else "FFFFFF"


def _mix(a: str, b: str, t: float) -> str:
    """a va b ranglar orasidagi rang (t=0 -> a)."""
    pa, pb = [int(a[i:i + 2], 16) for i in (0, 2, 4)], [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(pa, pb))


class Deck:
    def __init__(self, title: str, motif: str, secondary: str = "", footer: str = ""):
        from pptx import Presentation
        from pptx.util import Inches
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(W), Inches(H)
        self.motif = motif if motif in MOTIFS else "code"
        self.secondary = secondary if secondary in MOTIFS and secondary != self.motif else ""
        self.dark, self.primary, self.accent, self.accent2 = MOTIFS[self.motif]
        self.title, self.footer = title, footer or title
        self.blank = self.prs.slide_layouts[6]
        self.rand = random.Random(int(hashlib.md5(title.encode()).hexdigest()[:8], 16))
        self.chip = ""  # joriy dars bosqichi belgisi

    # ------------------------------------------------------------ primitives
    def slide(self, background: str = PAPER):
        s = self.prs.slides.add_slide(self.blank)
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = _rgb(background)
        return s

    def shape(self, s, kind, x, y, w, h, fill: str | None, line: str | None = None, width: float = 0, rotation=0):
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Inches, Pt
        sh = s.shapes.add_shape(getattr(MSO_SHAPE, kind), Inches(x), Inches(y), Inches(w), Inches(h))
        if fill:
            sh.fill.solid()
            sh.fill.fore_color.rgb = _rgb(fill)
        else:
            sh.fill.background()
        if line:
            sh.line.color.rgb, sh.line.width = _rgb(line), Pt(width or 1)
        else:
            sh.line.fill.background()
        sh.shadow.inherit = False
        sh.rotation = rotation
        if kind == "ROUNDED_RECTANGLE" and min(w, h) > 0:
            sh.adjustments[0] = min(0.5, 0.14 / min(w, h))  # burchak radiusi ~0.14" (katta kartada ham)
        if sh.has_text_frame:
            sh.text_frame.text = ""
        return sh

    def text(self, s, x, y, w, h, text: str, size: float, color: str = INK, bold=False, align="left", anchor="top",
             font: str = FONT, italic=False, spacing: float = 0):
        from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
        from pptx.util import Inches, Pt
        tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.05)
        tf.vertical_anchor = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}[anchor]
        for i, line in enumerate(str(text).split("\n")):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[align]
            if spacing:
                p.space_after = Pt(spacing)
            r = p.add_run()
            r.text = line
            r.font.size, r.font.bold, r.font.italic, r.font.name = Pt(size), bold, italic, font
            r.font.color.rgb = _rgb(color)
        return tb

    def badge(self, s, x, y, d, icon: str, fill: str, size: float | None = None):
        """Doira ichida emoji-ikonka."""
        self.shape(s, "OVAL", x, y, d, d, fill)
        self.text(s, x, y, d, d, icon, size or d * 30, INK, align="center", anchor="middle", font=EMOJI)

    def notes(self, s, text: str):
        if text:
            s.notes_slide.notes_text_frame.text = text

    def fit(self, items: list[str], base: float) -> float:
        chars = sum(len(i) for i in items) + 25 * len(items)
        return base + 2 if chars < 220 else base if chars < 380 else base - 3 if chars < 560 else base - 5

    # ------------------------------------------------------------ motif illustrations
    def binary_rain(self, s, x, y, w, h, color: str, size: float = 12):
        rows = int(h / (size / 52))
        cols = int(w / (size / 95))
        lines = ["".join(self.rand.choice("01 ") if self.rand.random() > 0.15 else " " for _ in range(cols))
                 for _ in range(rows)]
        self.text(s, x, y, w, h, "\n".join(lines), size, color, font=MONO)

    def magnifier(self, s, cx, cy, r, ring: str, glass: str, handle: str):
        import math
        self.shape(s, "OVAL", cx - r, cy - r, 2 * r, 2 * r, glass, ring, width=r * 14)
        length = r * 1.25
        hx, hy = cx + r * 0.95 * math.cos(math.radians(45)), cy + r * 0.95 * math.sin(math.radians(45))
        mx, my = hx + length / 2 * 0.707, hy + length / 2 * 0.707
        self.shape(s, "ROUNDED_RECTANGLE", mx - length / 2, my - r * 0.14, length, r * 0.28, handle, rotation=45)
        self.shape(s, "ARC", cx - r * 0.62, cy - r * 0.62, r * 1.0, r * 1.0, None, "FFFFFF", width=r * 5)

    def network(self, s, x, y, w, h, node: str, line: str, count: int = 9):
        from pptx.enum.shapes import MSO_CONNECTOR
        from pptx.util import Inches, Pt
        pts = [(x + self.rand.random() * w, y + self.rand.random() * h) for _ in range(count)]
        for i, (px, py) in enumerate(pts):
            for qx, qy in sorted(pts, key=lambda q: (q[0] - px) ** 2 + (q[1] - py) ** 2)[1:3]:
                c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(px), Inches(py), Inches(qx), Inches(qy))
                c.line.color.rgb, c.line.width = _rgb(line), Pt(1.5)
        for i, (px, py) in enumerate(pts):
            d = 0.22 if i % 3 else 0.34
            self.shape(s, "OVAL", px - d / 2, py - d / 2, d, d, node if i % 3 else self.accent)

    def monitor(self, s, x, y, w, frame: str, screen: str, glyph: str = "</>", glyph_color: str = "FFFFFF"):
        h = w * 0.62
        self.shape(s, "ROUNDED_RECTANGLE", x, y, w, h, frame)
        self.shape(s, "RECTANGLE", x + w * 0.05, y + w * 0.05, w * 0.9, h - w * 0.1, screen)
        self.shape(s, "TRAPEZOID", x + w * 0.38, y + h, w * 0.24, w * 0.14, frame)
        self.shape(s, "ROUNDED_RECTANGLE", x + w * 0.28, y + h + w * 0.13, w * 0.44, w * 0.05, frame)
        self.text(s, x, y, w, h, glyph, w * 22, glyph_color, bold=True, align="center", anchor="middle", font=MONO)

    def database(self, s, x, y, w, color: str, top: str):
        for i in range(3):
            self.shape(s, "CAN", x, y + i * w * 0.42, w, w * 0.55, color if i % 2 == 0 else top)

    def lock(self, s, x, y, w, body: str, shackle: str):
        self.shape(s, "BLOCK_ARC", x + w * 0.18, y, w * 0.64, w * 0.7, shackle)
        self.shape(s, "ROUNDED_RECTANGLE", x, y + w * 0.38, w, w * 0.8, body)
        self.shape(s, "OVAL", x + w * 0.42, y + w * 0.62, w * 0.16, w * 0.16, self.dark)

    def flow(self, s, x, y, w, color: str, accent: str):
        self.shape(s, "FLOWCHART_TERMINATOR", x + w * 0.25, y, w * 0.5, w * 0.18, accent)
        self.shape(s, "FLOWCHART_PROCESS", x + w * 0.2, y + w * 0.32, w * 0.6, w * 0.22, color)
        self.shape(s, "FLOWCHART_DECISION", x + w * 0.22, y + w * 0.68, w * 0.56, w * 0.32, accent)
        self.shape(s, "DOWN_ARROW", x + w * 0.46, y + w * 0.19, w * 0.08, w * 0.12, "CBD5E1")
        self.shape(s, "DOWN_ARROW", x + w * 0.46, y + w * 0.55, w * 0.08, w * 0.12, "CBD5E1")

    def illustration(self, s, motif: str, x, y, size, on_dark=True):
        """Mavzu rasmi (x, y - chap yuqori burchak, size - taxminiy kenglik)."""
        dark, primary, accent, accent2 = MOTIFS.get(motif, MOTIFS["code"])
        glass = _mix(dark, primary, 0.25) if on_dark else "E0ECFF"
        if motif == "search":
            r = size * 0.32
            self.magnifier(s, x + size * 0.4, y + size * 0.4, r, primary, glass, accent)
        elif motif == "binary":
            self.shape(s, "ROUNDED_RECTANGLE", x, y, size, size * 0.8, _mix(dark, primary, 0.18) if on_dark else "ECFDF5")
            bits = "\n".join(" ".join(self.rand.choice("01") for _ in range(6)) for _ in range(5))
            self.text(s, x, y, size, size * 0.8, bits, size * 9.5, primary, bold=True, align="center",
                      anchor="middle", font=MONO)
        elif motif == "network":
            self.network(s, x, y, size, size * 0.8, primary, _mix(primary, "FFFFFF", 0.4) if on_dark else "A5B4FC")
        elif motif == "hardware":
            self.monitor(s, x, y + size * 0.05, size, primary, dark if on_dark else "1F2937", "⚙", accent)
        elif motif == "data":
            self.database(s, x + size * 0.15, y, size * 0.7, primary, accent2)
        elif motif == "security":
            self.lock(s, x + size * 0.15, y, size * 0.7, primary, accent)
        elif motif == "algorithm":
            self.flow(s, x, y, size, primary, accent)
        else:
            self.monitor(s, x, y + size * 0.05, size, primary, dark if on_dark else INK, "</>", accent)

    # ------------------------------------------------------------ frame
    def header(self, s, title: str, icon: str = ""):
        self.shape(s, "RECTANGLE", 0, 0, W, 0.09, self.primary)
        self.shape(s, "RECTANGLE", 0, 0.09, 2.2, 0.05, self.accent)
        x = 0.6
        if icon:
            self.badge(s, 0.55, 0.38, 0.8, icon, _mix(self.primary, "FFFFFF", 0.82))
            x = 1.55
        size = 30 if len(title) < 42 else 25 if len(title) < 65 else 21
        width = W - x - (3.6 if self.chip else 0.6)
        self.text(s, x, 0.3, width, 1.0, title, size, INK, bold=True, anchor="middle")
        if self.chip:
            self.shape(s, "ROUNDED_RECTANGLE", W - 3.55, 0.47, 3.1, 0.55, _mix(self.primary, "FFFFFF", 0.85))
            self.text(s, W - 3.5, 0.47, 3.0, 0.55, self.chip, 15, _mix(self.primary, INK, 0.3), bold=True, align="center",
                      anchor="middle")
        number = len(self.prs.slides)
        self.text(s, 0.6, 7.0, 9, 0.35, self.footer, 10.5, MUTED)
        self.shape(s, "OVAL", W - 1.05, 6.93, 0.45, 0.45, self.primary)
        self.text(s, W - 1.05, 6.93, 0.45, 0.45, str(number), 11, "FFFFFF", bold=True, align="center", anchor="middle")
        # kichik motif belgisi o'ng pastda
        self.binary_rain(s, W - 3.3, 6.95, 2.1, 0.4, "E2E8F0", 9) if self.motif == "binary" else None

    # ------------------------------------------------------------ slide types
    def cover(self, title: str, subtitle: str, meta: str):
        s = self.slide(self.dark)
        self.binary_rain(s, 0.2, 0.1, W - 0.4, H - 0.2, _mix(self.dark, self.primary, 0.22), 13)
        self.shape(s, "OVAL", 7.7, -1.2, 7.4, 7.4, _mix(self.dark, self.primary, 0.35))
        self.shape(s, "OVAL", 8.4, -0.5, 6.0, 6.0, _mix(self.dark, self.primary, 0.55))
        self.illustration(s, self.motif, 9.0, 1.0, 3.2)
        if self.secondary:
            self.illustration(s, self.secondary, 10.6, 4.4, 1.9)
        self.shape(s, "RECTANGLE", 0.75, 2.0, 0.14, 2.4, self.accent)
        size = 46 if len(title) < 32 else 38 if len(title) < 55 else 30
        self.text(s, 1.1, 1.4, 7.4, 3.0, title, size, "FFFFFF", bold=True, anchor="bottom")
        if subtitle:
            self.text(s, 1.1, 4.5, 7.2, 1.0, subtitle, 21, _mix("FFFFFF", self.accent, 0.35))
        if meta:
            self.shape(s, "ROUNDED_RECTANGLE", 1.1, 5.85, min(7.2, 0.6 + len(meta) * 0.11), 0.55,
                       _mix(self.dark, self.primary, 0.45))
            self.text(s, 1.2, 5.85, 7.0, 0.55, meta, 14, "FFFFFF", anchor="middle")
        return s

    def section(self, number: int, title: str, subtitle: str = "", icon: str = "", minutes: str = ""):
        s = self.slide(self.dark)
        self.binary_rain(s, 0.2, 0.1, W - 0.4, H - 0.2, _mix(self.dark, self.primary, 0.16), 13)
        self.shape(s, "RECTANGLE", 0, 0, 4.4, H, self.primary)
        self.text(s, 0.4, 1.9, 3.6, 2.0, f"{number:02d}", 96, "FFFFFF", bold=True, align="center", anchor="middle")
        if icon:
            self.badge(s, 1.6, 4.1, 1.2, icon, _mix(self.primary, "FFFFFF", 0.85))
        self.text(s, 5.0, 2.2, 7.6, 1.6, title, 40 if len(title) < 30 else 32, "FFFFFF", bold=True, anchor="bottom")
        if subtitle:
            self.text(s, 5.0, 3.9, 7.6, 1.2, subtitle, 19, _mix("FFFFFF", self.primary, 0.3))
        if minutes:
            self.shape(s, "ROUNDED_RECTANGLE", 5.0, 5.3, 2.4, 0.65, self.accent)
            self.text(s, 5.0, 5.3, 2.4, 0.65, "⏱ " + minutes, 18, INK, bold=True, align="center", anchor="middle")
        return s

    def bullets(self, title: str, items: list[str], icon: str = "", side: str = ""):
        s = self.slide()
        self.header(s, title, icon)
        width = W - 1.2
        if side:
            width = 7.6
            self.shape(s, "ROUNDED_RECTANGLE", 8.55, 1.6, 4.2, 5.1, _mix(self.dark, self.primary, 0.05))
            self.illustration(s, side, 9.05, 2.2, 3.2)
        iconic = all(not i[:1].isascii() and not i[:1].isalnum() for i in items)
        size = self.fit(items, 22 if side else 24)
        row_h = min(1.2, 5.1 / max(1, len(items)))
        for k, item in enumerate(items):
            y = 1.6 + k * row_h
            self.shape(s, "ROUNDED_RECTANGLE", 0.6, y + 0.06, width, row_h - 0.12, CARD, "E2E8F0", 0.75)
            self.shape(s, "RECTANGLE", 0.6, y + 0.06, 0.09, row_h - 0.12, self.primary if k % 2 == 0 else self.accent)
            x = 0.9
            if iconic:
                glyph, _, item = item.partition(" ")
                d = min(0.7, row_h - 0.3)
                self.badge(s, 0.9, y + (row_h - d) / 2, d, glyph, _mix(self.primary, "FFFFFF", 0.86))
                x = 0.9 + d + 0.2
            head, sep, rest = item.partition(": ")
            text = s.shapes  # noqa: F841
            tb = self.text(s, x, y + 0.06, width - (x - 0.6) - 0.2, row_h - 0.12, "", size, INK, anchor="middle")
            p = tb.text_frame.paragraphs[0]
            from pptx.util import Pt
            if sep and len(head) <= 45:
                r = p.add_run()
                r.text, r.font.bold, r.font.size, r.font.name = head + ": ", True, Pt(size), FONT
                r.font.color.rgb = _rgb(self.primary)
                item = rest
            r = p.add_run()
            r.text, r.font.size, r.font.name = item, Pt(size), FONT
            r.font.color.rgb = _rgb(INK)
        return s

    def cards(self, title: str, cards: list[dict], icon: str = ""):
        s = self.slide()
        self.header(s, title, icon)
        cards = cards[:4]
        n = max(1, len(cards))
        gap = 0.3
        w = (W - 1.2 - gap * (n - 1)) / n
        colors = [self.primary, self.accent, self.accent2, _mix(self.primary, self.dark, 0.4)]
        for k, c in enumerate(cards):
            x = 0.6 + k * (w + gap)
            self.shape(s, "ROUNDED_RECTANGLE", x, 1.65, w, 5.05, CARD, "E2E8F0", 0.75)
            self.shape(s, "RECTANGLE", x, 1.65, w, 0.12, colors[k % 4])
            self.badge(s, x + w / 2 - 0.65, 2.15, 1.3, _icon(c.get("icon"), "💡"), _mix(colors[k % 4], "FFFFFF", 0.8))
            self.text(s, x + 0.2, 3.6, w - 0.4, 0.8, _clean(c.get("title"), 60), 24 if n < 4 else 20,
                      _mix(colors[k % 4], INK, 0.25), bold=True, align="center", anchor="middle")
            body = _clean(c.get("text"), 300)
            size = (20 if len(body) < 90 else 17 if len(body) < 160 else 15) - (2 if n == 4 else 0)
            self.text(s, x + 0.3, 4.5, w - 0.6, 2.1, body, size, INK, align="center")
        return s

    def steps(self, title: str, steps: list[dict], icon: str = ""):
        s = self.slide()
        self.header(s, title, icon)
        steps = steps[:5]
        n = max(1, len(steps))
        gap = 0.35
        w = (W - 1.2 - gap * (n - 1)) / n
        for k, st in enumerate(steps):
            x = 0.6 + k * (w + gap)
            color = self.primary if k % 2 == 0 else self.accent2
            self.shape(s, "CHEVRON" if 0 < k else "PENTAGON", x, 1.75, w + 0.2, 1.05, color)
            self.text(s, x + (0.6 if k else 0.3), 1.75, w - (0.75 if k else 0.45), 1.05,
                      f"{k + 1}. " + _clean(st.get("title"), 40), 18, _on(color),
                      bold=True, anchor="middle")
            self.shape(s, "ROUNDED_RECTANGLE", x, 3.05, w, 3.65, CARD, "E2E8F0", 0.75)
            self.badge(s, x + w / 2 - 0.45, 3.25, 0.9, _icon(st.get("icon"), "➡️"), _mix(color, "FFFFFF", 0.82))
            body = _clean(st.get("text"), 220)
            self.text(s, x + 0.2, 4.35, w - 0.4, 2.2, body, 18 if len(body) < 70 else 15 if len(body) < 130 else 13,
                      INK, align="center")
        return s

    def two_column(self, title: str, left: dict, right: dict, icon: str = ""):
        s = self.slide()
        self.header(s, title, icon)
        for k, col in enumerate((left, right)):
            x = 0.6 + k * 6.2
            color = self.primary if k == 0 else self.accent
            self.shape(s, "ROUNDED_RECTANGLE", x, 1.6, 5.9, 5.1, CARD, "E2E8F0", 0.75)
            self.shape(s, "ROUNDED_RECTANGLE", x, 1.6, 5.9, 0.85, color)
            self.text(s, x + 0.3, 1.6, 5.3, 0.85, (_icon(col.get("icon")) + "  " if col.get("icon") else "")
                      + _clean(col.get("title"), 60), 22, _on(color), bold=True, anchor="middle")
            items = _list(col.get("bullets"), 7)
            self.text(s, x + 0.35, 2.75, 5.2, 3.85, "\n".join("• " + i for i in items), self.fit(items, 22), INK,
                      spacing=14)
        return s

    def table(self, title: str, rows: list[list], icon: str = ""):
        from pptx.util import Inches, Pt
        s = self.slide()
        self.header(s, title, icon)
        rows = [[_clean(c, 120) for c in r[:7]] for r in rows[:12]]
        cols = max(len(r) for r in rows)
        rows = [r + [""] * (cols - len(r)) for r in rows]
        size = 20 if len(rows) <= 5 and cols <= 3 else 16 if len(rows) <= 8 else 13
        row_h = min(0.75, 5.0 / len(rows))
        frame = s.shapes.add_table(len(rows), cols, Inches(0.6), Inches(1.7), Inches(W - 1.2), Inches(row_h * len(rows)))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                cell = frame.table.cell(r, c)
                cell.fill.solid()
                cell.fill.fore_color.rgb = _rgb(self.primary if r == 0 else (CARD if r % 2 else _mix(self.primary, "FFFFFF", 0.92)))
                cell.text = value
                for p in cell.text_frame.paragraphs:
                    for run in p.runs:
                        run.font.size, run.font.bold, run.font.name = Pt(size), r == 0 or c == 0, FONT
                        run.font.color.rgb = _rgb("FFFFFF" if r == 0 else INK)
        return s

    def code(self, title: str, code: str, caption: str = "", icon: str = "💻"):
        s = self.slide()
        self.header(s, title, icon)
        width = 7.9 if caption else W - 1.2
        self.shape(s, "ROUNDED_RECTANGLE", 0.6, 1.6, width, 5.1, "0F172A")
        for k, c in enumerate(("EF4444", "F59E0B", "22C55E")):
            self.shape(s, "OVAL", 0.85 + k * 0.3, 1.8, 0.17, 0.17, c)
        lines = str(code or "").splitlines()[:16]
        self.text(s, 0.85, 2.15, width - 0.5, 4.5, "\n".join(lines), 17 if len(lines) <= 10 else 14, "E2E8F0", font=MONO)
        if caption:
            self.shape(s, "ROUNDED_RECTANGLE", 8.8, 1.6, 3.95, 5.1, _mix(self.primary, "FFFFFF", 0.9))
            self.text(s, 9.05, 1.85, 3.5, 4.6, caption, 17, INK)
        return s

    def chart(self, title: str, spec: dict, icon: str = ""):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
        from pptx.util import Inches, Pt
        s = self.slide()
        self.header(s, title, icon)
        kinds = {"bar": XL_CHART_TYPE.BAR_CLUSTERED, "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
                 "line": XL_CHART_TYPE.LINE_MARKERS, "pie": XL_CHART_TYPE.PIE, "doughnut": XL_CHART_TYPE.DOUGHNUT}
        kind = spec.get("type") if spec.get("type") in kinds else "column"
        data = CategoryChartData()
        data.categories = [_clean(c, 40) for c in spec.get("categories", [])][:20]
        series = (spec.get("series") or [])[:1 if kind in ("pie", "doughnut") else 6]
        for se in series:
            values = [float(v) if isinstance(v, (int, float)) else 0.0 for v in se.get("values", [])]
            data.add_series(_clean(se.get("name"), 40) or "—", values[:len(data.categories)])
        width = 7.8 if spec.get("caption") else W - 1.2
        self.shape(s, "ROUNDED_RECTANGLE", 0.6, 1.6, width, 5.1, CARD, "E2E8F0", 0.75)
        chart = s.shapes.add_chart(kinds[kind], Inches(0.8), Inches(1.8), Inches(width - 0.4), Inches(4.7), data).chart
        chart.has_title = False
        chart.font.size, chart.font.name = Pt(13), FONT
        chart.has_legend = len(series) > 1 or kind in ("pie", "doughnut")
        if chart.has_legend:
            chart.legend.position, chart.legend.include_in_layout = XL_LEGEND_POSITION.BOTTOM, False
        palette = [self.primary, self.accent, self.accent2, "E76F51", "94A3B8", "6366F1"]
        if kind in ("pie", "doughnut"):
            for i, point in enumerate(chart.plots[0].series[0].points):
                point.format.fill.solid()
                point.format.fill.fore_color.rgb = _rgb(palette[i % len(palette)])
        else:
            for i, se in enumerate(chart.plots[0].series):
                if kind == "line":
                    se.format.line.color.rgb, se.format.line.width = _rgb(palette[i % 6]), Pt(3)
                else:
                    se.format.fill.solid()
                    se.format.fill.fore_color.rgb = _rgb(palette[i % 6])
        if spec.get("caption"):
            self.shape(s, "ROUNDED_RECTANGLE", 8.7, 1.6, 4.05, 5.1, _mix(self.primary, "FFFFFF", 0.9))
            self.text(s, 8.95, 1.85, 3.6, 4.6, _clean(spec["caption"], 400), 17, INK)
        return s

    def stats(self, title: str, items: list[dict], icon: str = ""):
        s = self.slide()
        self.header(s, title, icon)
        items = items[:4]
        n = max(1, len(items))
        w = (W - 1.2 - 0.3 * (n - 1)) / n
        for k, it in enumerate(items):
            x = 0.6 + k * (w + 0.3)
            color = [self.primary, self.accent, self.accent2, self.primary][k]
            self.shape(s, "ROUNDED_RECTANGLE", x, 1.9, w, 4.4, CARD, "E2E8F0", 0.75)
            self.shape(s, "OVAL", x + w / 2 - 1.15, 2.25, 2.3, 2.3, _mix(color, "FFFFFF", 0.85))
            self.text(s, x, 2.25, w, 2.3, _clean(it.get("value"), 10), 48, color, bold=True, align="center", anchor="middle")
            self.text(s, x + 0.2, 4.75, w - 0.4, 1.4, _clean(it.get("label"), 120), 17, INK, align="center")
        return s

    def quiz(self, title: str, question: str, options: list[str], answer, label: str, answer_label: str):
        s = self.slide()
        self.header(s, title or label, "❓")
        self.shape(s, "ROUNDED_RECTANGLE", 0.6, 1.6, W - 1.2, 1.5, self.dark)
        self.text(s, 0.95, 1.6, W - 1.9, 1.5, question, 27 if len(question) < 70 else 23 if len(question) < 120 else 19,
                  "FFFFFF", bold=True, anchor="middle")
        colors = [self.primary, self.accent, self.accent2, _mix(self.primary, "EC4899", 0.6)]
        letters = "ABCD"
        options = options[:4]
        for k, opt in enumerate(options):
            x, y = 0.6 + (k % 2) * 6.2, 3.35 + (k // 2) * 1.7
            self.shape(s, "ROUNDED_RECTANGLE", x, y, 5.9, 1.45, CARD, colors[k], 2.5)
            self.shape(s, "OVAL", x + 0.25, y + 0.3, 0.85, 0.85, colors[k])
            self.text(s, x + 0.25, y + 0.3, 0.85, 0.85, letters[k], 26, "FFFFFF", bold=True, align="center", anchor="middle")
            self.text(s, x + 1.3, y, 4.45, 1.45, opt, 24 if len(opt) < 30 else 20 if len(opt) < 60 else 16, INK,
                      anchor="middle")
        if isinstance(answer, int) and 0 <= answer < len(options):
            answer = letters[answer]
        if answer:
            self.notes(s, f"{answer_label}: {str(answer)[:120]}")
        return s

    def callout(self, title: str, text: str, icon: str, kind: str = "fact"):
        s = self.slide(self.dark)
        self.binary_rain(s, 0.2, 0.1, W - 0.4, H - 0.2, _mix(self.dark, self.primary, 0.14), 13)
        self.shape(s, "ROUNDED_RECTANGLE", 0.9, 1.0, W - 1.8, 5.5, _mix(self.dark, self.primary, 0.22))
        self.badge(s, 1.5, 2.95, 1.9, icon, self.accent)
        self.text(s, 3.9, 1.3, 8.3, 0.9, title, 32, self.accent, bold=True, anchor="middle")
        self.text(s, 3.9, 2.25, 8.3, 3.9, text, 28 if len(text) < 170 else 23 if len(text) < 280 else 19, "FFFFFF",
                  anchor="middle")
        return s

    def task(self, title: str, steps: list[str], icon: str, note: str = "", minutes: str = ""):
        s = self.slide()
        self.header(s, title, icon)
        self.shape(s, "ROUNDED_RECTANGLE", 0.6, 1.6, 8.3, 5.1, CARD, "E2E8F0", 0.75)
        size = self.fit(steps, 21)
        for k, st in enumerate(steps[:7]):
            y = 1.85 + k * min(0.7, 4.7 / max(1, len(steps)))
            self.shape(s, "OVAL", 0.85, y + 0.05, 0.5, 0.5, self.primary)
            self.text(s, 0.85, y + 0.05, 0.5, 0.5, str(k + 1), 15, "FFFFFF", bold=True, align="center", anchor="middle")
            self.text(s, 1.55, y, 7.2, 0.65, st, size, INK, anchor="middle")
        self.shape(s, "ROUNDED_RECTANGLE", 9.2, 1.6, 3.55, 5.1, _mix(self.primary, "FFFFFF", 0.88))
        self.badge(s, 10.3, 1.95, 1.35, icon, CARD)
        if minutes:
            self.text(s, 9.3, 3.45, 3.35, 0.6, "⏱ " + minutes, 20, self.primary, bold=True, align="center")
        if note:
            self.text(s, 9.4, 4.1, 3.15, 2.5, note, 15, INK, align="center")
        return s

    def quote(self, text: str, author: str):
        s = self.slide(self.dark)
        self.text(s, 0.9, 0.5, 2, 2, "“", 150, self.accent, bold=True)
        self.text(s, 1.6, 1.9, 10.2, 3.3, text, 32 if len(text) < 140 else 25, "FFFFFF", anchor="middle")
        if author:
            self.text(s, 1.6, 5.4, 10.2, 0.6, "— " + author, 18, self.accent)
        return s

    def timeline(self, title: str, stages: list[tuple], total: str):
        s = self.slide()
        self.header(s, title, "📅")
        y = 2.0
        total_min = sum(m for _, m, _, _ in stages) or 1
        x = 0.6
        colors = [self.primary, self.accent2, self.accent, _mix(self.primary, self.dark, 0.35), _mix(self.accent, "EF4444", 0.4)]
        for k, (name, minutes, icon, unit) in enumerate(stages):
            w = (W - 1.2) * minutes / total_min
            self.shape(s, "RECTANGLE", x, y, w - 0.06, 0.55, colors[k % 5])
            self.text(s, x, y, w - 0.06, 0.55, f"{minutes} {unit}", 15, _on(colors[k % 5]), bold=True, align="center",
                      anchor="middle")
            cy = 2.85 + k * 0.78
            self.badge(s, 0.6, cy, 0.62, icon, _mix(colors[k % 5], "FFFFFF", 0.82))
            self.text(s, 1.4, cy, 8.5, 0.62, f"{k + 1}. {name}", 20, INK, bold=True, anchor="middle")
            self.text(s, 10.0, cy, 2.75, 0.62, f"{minutes} {unit}", 20, colors[k % 5], bold=True, align="right", anchor="middle")
            x += w
        self.text(s, 0.6, 6.55, W - 1.2, 0.4, total, 16, MUTED, bold=True, align="right")
        return s

    def ending(self, text: str, subtitle: str = ""):
        s = self.slide(self.dark)
        self.binary_rain(s, 0.2, 0.1, W - 0.4, H - 0.2, _mix(self.dark, self.primary, 0.2), 13)
        self.shape(s, "OVAL", -1.5, 4.2, 5.0, 5.0, _mix(self.dark, self.primary, 0.5))
        self.illustration(s, self.motif, 10.0, 0.7, 2.4)
        self.text(s, 1.0, 2.5, W - 2, 1.5, text, 46, "FFFFFF", bold=True, align="center", anchor="middle")
        if subtitle:
            self.text(s, 1.0, 4.0, W - 2, 0.7, subtitle, 20, _mix("FFFFFF", self.accent, 0.4), align="center")
        return s

    # ------------------------------------------------------------ dispatcher
    def render(self, raw: dict, lang: str = "uz"):
        t = L10N.get(lang, L10N["uz"])
        kind = raw.get("type") or ("table" if raw.get("rows") else "chart" if raw.get("chart") else
                                   "quiz" if raw.get("question") else "cards" if raw.get("cards") else
                                   "steps" if raw.get("steps") else "code" if raw.get("code") else "bullets")
        title, icon = _clean(raw.get("title"), 120), _icon(raw.get("icon"))
        side = raw.get("illustration") if raw.get("illustration") in MOTIFS else ""
        s = None
        if kind == "section":
            s = self.section(int(raw.get("number") or 1), title, _clean(raw.get("subtitle"), 200), icon)
        elif kind == "cards" and isinstance(raw.get("cards"), list):
            s = self.cards(title, [c for c in raw["cards"] if isinstance(c, dict)], icon)
        elif kind == "steps" and isinstance(raw.get("steps"), list):
            s = self.steps(title, [c for c in raw["steps"] if isinstance(c, dict)], icon)
        elif kind == "two_column":
            s = self.two_column(title, raw.get("left") or {}, raw.get("right") or {}, icon)
        elif kind == "table" and isinstance(raw.get("rows"), list) and raw["rows"] and all(isinstance(r, list) for r in raw["rows"]):
            s = self.table(title, raw["rows"], icon)
        elif kind == "chart" and isinstance(raw.get("chart"), dict) and raw["chart"].get("categories"):
            s = self.chart(title, raw["chart"], icon)
        elif kind == "stats" and isinstance(raw.get("stats"), list):
            s = self.stats(title, [x for x in raw["stats"] if isinstance(x, dict)], icon)
        elif kind == "code" and raw.get("code"):
            s = self.code(title, str(raw["code"])[:1500], _clean(raw.get("caption"), 400), icon or "💻")
        elif kind == "quiz" and raw.get("question") and isinstance(raw.get("options"), list):
            s = self.quiz(title, _clean(raw["question"], 260), _list(raw["options"], 4), raw.get("answer"),
                          t["quiz"], t["answer"])
        elif kind in ("fact", "callout"):
            s = self.callout(title or t["fact"], _clean(raw.get("text"), 500), icon or "💡")
        elif kind == "task":
            s = self.task(title or t["task"], _list(raw.get("steps") or raw.get("bullets"), 7), icon or "✍️",
                          _clean(raw.get("note"), 300), _clean(raw.get("minutes"), 20))
        elif kind == "quote":
            s = self.quote(_clean(raw.get("text") or title, 400), _clean(raw.get("author"), 80))
        else:
            items = _list(raw.get("bullets") or raw.get("text"), 14)
            if not items:
                return []
            made = []
            for part in range(0, len(items), 6):
                made.append(self.bullets(title + (" (2)" if part else ""), items[part:part + 6], icon, side))
                self.notes(made[-1], _clean(raw.get("notes"), 3000))
            return made
        self.notes(s, _clean(raw.get("notes"), 3000))
        return [s]

    def save(self, title: str) -> tuple:
        from pptx import Presentation
        path = outbox.new_path(title, "pptx")
        self.prs.save(path)
        count = len(Presentation(path).slides)
        outbox.register(path)
        return path, count


SLIDE_DOC = (
    "Slayd turlari (type): bullets {title, icon, bullets: [\"🔍 Termin: izoh\" ...], illustration: motif} - punkt "
    "boshidagi emoji ikonka bo'ladi; cards {title, cards: [{icon, title, text}] 2-4}; steps {title, steps: [{icon, "
    "title, text}] 3-5} - jarayon; two_column {title, left: {icon, title, bullets}, right: {...}}; table {title, rows}; "
    "chart {title, chart: {type: column|bar|line|pie|doughnut, categories, series: [{name, values}], caption}}; stats "
    "{title, stats: [{value, label}]}; code {title, code, caption}; quiz {title, question, options: [4 ta], answer: "
    "\"B\"}; fact {title, text, icon} - \"Bilasizmi?\"; task {title, steps, note, minutes} - amaliy ish; quote {text, "
    "author}; section {title, subtitle}. Har slaydga notes: o'qituvchi nima deydi va qiladi. icon - emoji yoki nom: "
    + ", ".join(ICONS) + ". Motivlar: " + ", ".join(MOTIFS) + "."
)


@skill(
    description=(
        "Professional dizayndagi PowerPoint (.pptx) taqdimot: mavzuga mos rang va chizilgan rasm-motivlar (lupa, ikkilik "
        "kod, tarmoq, monitor, ma'lumotlar bazasi, qulf, blok-sxema), ikonkali kartalar, jarayon, test, jadval, diagramma, "
        "kod bloki, izohlar. Fayl foydalanuvchiga AVTOMATIK yuboriladi. DARS taqdimoti uchun make_lesson_presentation "
        "ishlat. " + SLIDE_DOC
    ),
    params={
        "title": {"type": "string", "description": "Taqdimot nomi"},
        "subtitle": {"type": "string", "description": "Kichik sarlavha"},
        "author": {"type": "string", "description": "Muallif / sana"},
        "motif": {"type": "string", "enum": list(MOTIFS), "description": "Dizayn motivi (bo'sh - mavzudan avtomatik)"},
        "slides": {"type": "array", "items": {"type": "object"}, "description": "Slaydlar"},
        "ending": {"type": "string", "description": "Yakuniy slayd matni"},
    },
    required=["title", "slides"],
)
def make_presentation(title: str, slides: list, subtitle: str = "", author: str = "", motif: str = "",
                      ending: str = "", theme: str = "") -> str:
    title = _clean(title, 120) or "Taqdimot"
    if not isinstance(slides, list) or not slides:
        return "slides bo'sh: kamida bitta slayd kerak."
    motif = motif if motif in MOTIFS else choose_motif(title + " " + subtitle)
    deck = Deck(title, motif)
    deck.cover(title, _clean(subtitle, 200), _clean(author, 120))
    sections = 0
    for raw in slides[:45]:
        if isinstance(raw, dict):
            if raw.get("type") == "section":
                sections += 1
                raw = {**raw, "number": sections}
            deck.render(raw)
    if ending:
        deck.ending(_clean(ending, 80), title)
    path, count = deck.save(title)
    return (f"✅ PowerPoint tayyor: {path.name} ({count} slayd, dizayn motivi: {motif}). Fayl javob bilan birga "
            "avtomatik yuboriladi - havola to'qima, faqat nima tayyorlanganini qisqa ayt.")


def _lesson_doc(topic: str, grade: str, lang: str, teacher: str, goals: dict, rows: list, homework: list, path_title: str):
    """Dars ishlanmasi (Word): sizning jadvalingiz ko'rinishida - T/r, bosqich, ishlar, vaqt."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    t = L10N[lang]
    head = {"uz": ("T/r", "Dars bosqichlari", "Qanday ishlar amalga oshiriladi", "Ajratilgan vaqt"),
            "ru": ("№", "Этапы урока", "Что делается на этапе", "Время")}[lang]
    doc = Document()
    doc.styles["Normal"].font.name, doc.styles["Normal"].font.size = "Times New Roman", Pt(12)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"{t['lesson']}: {topic}")
    r.bold, r.font.size = True, Pt(16)
    info = doc.add_paragraph(" | ".join(x for x in (f"{grade} {t['grade']}" if grade else "", t["total"],
                                                      f"{t['teacher']}: {teacher}" if teacher else "") if x))
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if any(goals.values()):
        doc.add_paragraph(t["goals"], style="Heading 2")
        for key, label in (("educational", t["edu"]), ("upbringing", t["up"]), ("developmental", t["dev"])):
            if goals.get(key):
                q = doc.add_paragraph(style="List Bullet")
                q.add_run(label + ": ").bold = True
                q.add_run(goals[key])
    table = doc.add_table(rows=1 + len(rows), cols=4)
    table.style = "Table Grid"
    for c, text in enumerate(head):
        cell = table.cell(0, c)
        cell.text = text
        cell.paragraphs[0].runs[0].bold = True
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        shade = OxmlElement("w:shd")
        shade.set(qn("w:val"), "clear")
        shade.set(qn("w:fill"), "FFF2CC")
        cell._tc.get_or_add_tcPr().append(shade)
    for i, (name, activity, minutes) in enumerate(rows, 1):
        for c, text in enumerate((str(i), name, activity, f"{minutes} {t['min']}")):
            table.cell(i, c).text = text
            if c != 2:
                table.cell(i, c).paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    widths = (0.45, 1.5, 3.75, 0.8)  # jami 6.5" - A4 ning ish kengligi
    from docx.shared import Inches
    table.autofit = False
    for c, (col, w) in enumerate(zip(table._tbl.tblGrid.findall(qn("w:gridCol")), widths)):
        col.set(qn("w:w"), str(int(w * 1440)))  # LibreOffice va Word ikkalasi ham gridCol ga qaraydi
        table.columns[c].width = Inches(w)
    for row in table.rows:
        for c, w in enumerate(widths):
            row.cells[c].width = Inches(w)
    if homework:
        doc.add_paragraph(t["hw"], style="Heading 2")
        for task in homework:
            doc.add_paragraph(task, style="List Number")
    for style in ("Heading 2",):
        doc.styles[style].font.color.rgb = RGBColor.from_string("1F4E99")
    path = outbox.new_path(path_title, "docx")
    doc.save(path)
    Document(path)
    outbox.register(path)
    return path


@skill(
    description=(
        "50 daqiqalik DARS uchun professional PowerPoint taqdimot (va xohlasa Word dars ishlanmasi). Dars ishlanmasi "
        "jadvali bo'yicha 5 bosqich: organizational (Tashkiliy qism, 5 daq: salomlashish, davomat, ma'naviy daqiqa), "
        "homework_check (Uy vazifasini so'rash, 10 daq: savol-javob, test), new_topic (Yangi mavzu bayoni, 15 daq: "
        "tushunchalar, misollar, sxemalar, 'Bilasizmi?'), reinforcement (Mustahkamlash, 15 daq: test, amaliy topshiriq, "
        "interaktiv metod), conclusion (Yakuniy qism, 5 daq: xulosa, baholash). Avtomatik qo'shiladi: muqova, dars rejasi "
        "(vaqt chizig'i), maqsadlar, har bosqich bo'limi va vaqti, uy vazifasi slaydi, yakun. Har bosqichga slides "
        "ro'yxatini ber; tavsiya: organizational 2, homework_check 3-4 (2-3 quiz), new_topic 6-9 (cards, steps, table, "
        "code, fact, bullets bilan), reinforcement 4-6 (quiz, task), conclusion 2. Har slaydga notes yoz. Dizayn motivi "
        "mavzudan tanlanadi. " + SLIDE_DOC
    ),
    params={
        "topic": {"type": "string", "description": "Dars mavzusi"},
        "grade": {"type": "string", "description": "Sinf, masalan '7' yoki '7-A'"},
        "language": {"type": "string", "enum": ["uz", "ru"], "description": "Taqdimot tili (standart uz)"},
        "teacher": {"type": "string", "description": "O'qituvchi F.I.Sh. (ixtiyoriy)"},
        "motif": {"type": "string", "enum": list(MOTIFS), "description": "Asosiy dizayn motivi (bo'sh - avtomatik)"},
        "secondary_motif": {"type": "string", "enum": list(MOTIFS), "description": "Ikkinchi motiv (masalan qidiruv+kodlash)"},
        "goals": {"type": "object", "description": "{educational, upbringing, developmental} - maqsadlar matni"},
        "stages": {"type": "object", "description": "{organizational|homework_check|new_topic|reinforcement|conclusion: "
                                                    "{activity: 'bosqichda nima qilinadi (dars ishlanmasi uchun)', slides: [...]}}"},
        "homework": {"type": "object", "description": "{tasks: ['Darslik 45-bet, 1-3 savollar', ...], note: 'qanday bajarish'}"},
        "with_lesson_plan": {"type": "boolean", "description": "Word dars ishlanmasi ham yaratilsin (standart true)"},
    },
    required=["topic", "stages"],
)
def make_lesson_presentation(topic: str, stages: dict, grade: str = "", language: str = "uz", teacher: str = "",
                             motif: str = "", secondary_motif: str = "", goals: dict | None = None,
                             homework: dict | None = None, with_lesson_plan: bool = True) -> str:
    lang = language if language in L10N else "uz"
    t = L10N[lang]
    topic = _clean(topic, 140) or "Dars"
    stages = stages if isinstance(stages, dict) else {}
    goals = {k: _clean(v, 400) for k, v in (goals or {}).items() if k in ("educational", "upbringing", "developmental")}
    homework = homework if isinstance(homework, dict) else {}
    hw_tasks = _list(homework.get("tasks"), 8)
    auto = choose_motif(topic)
    motif = motif if motif in MOTIFS else auto
    if not secondary_motif:
        low = topic.lower()
        others = [m for m, words in MOTIF_WORDS.items() if m != motif and any(w in low for w in words)]
        secondary_motif = others[0] if others else ""
    deck = Deck(topic, motif, secondary_motif, footer=f"{topic} · {grade} {t['grade']}" if grade else topic)
    meta = " · ".join(x for x in (f"{grade} {t['grade']}" if grade else "", f"50 {t['min']}", teacher) if x)
    deck.cover(topic, f"{t['lesson']} · " + ("Информатика" if lang == "ru" else "Informatika"), meta)
    names = [(st[3] if lang == "ru" else st[2]) for st in STAGES]
    deck.timeline(t["plan"], [(names[i], STAGES[i][1], STAGES[i][4], t["min"]) for i in range(5)], t["total"])
    if goals:
        deck.cards(t["goals"], [{"icon": ic, "title": label, "text": goals.get(key, "")} for key, label, ic in
                                (("educational", t["edu"], "🎯"), ("upbringing", t["up"], "🤝"),
                                 ("developmental", t["dev"], "🧠")) if goals.get(key)], "🎯")
    counts, rows = {}, []
    for i, (key, minutes, uz, ru, icon) in enumerate(STAGES):
        stage = stages.get(key) if isinstance(stages.get(key), dict) else {}
        deck.chip = ""
        deck.section(i + 1, names[i], _clean(stage.get("subtitle"), 160), icon, f"{minutes} {t['min']}")
        deck.chip = f"{i + 1}-{t['stage']} · {minutes} {t['min']}" if lang == "uz" else f"Этап {i + 1} · {minutes} {t['min']}"
        made = 0
        for raw in (stage.get("slides") or [])[:14]:
            if isinstance(raw, dict) and raw.get("type") != "section":
                made += len(deck.render(raw, lang))
        if key == "conclusion" and hw_tasks:
            deck.task(t["hw"], hw_tasks, "🏠", _clean(homework.get("note"), 300), "")
            made += 1
        counts[key] = made
        rows.append((names[i], _clean(stage.get("activity"), 900) or DEFAULT_ACTIVITY[lang][i], minutes))
    deck.chip = ""
    deck.ending(t["thanks"], topic)
    path, count = deck.save(topic)
    plan = ""
    if with_lesson_plan:
        doc = _lesson_doc(topic, _clean(grade, 20), lang, _clean(teacher, 80), goals, rows, hw_tasks,
                          f"{topic} dars ishlanmasi" if lang == "uz" else f"{topic} конспект урока")
        plan = f" + Word dars ishlanmasi {doc.name}"
    advice = {"homework_check": 2, "new_topic": 5, "reinforcement": 3}
    weak = [f"{names[STAGES.index(next(s for s in STAGES if s[0] == k))]}: {counts.get(k, 0)} slayd (tavsiya {n}+)"
            for k, n in advice.items() if counts.get(k, 0) < n]
    note = (" Diqqat - 50 daqiqaga mazmun kam: " + "; ".join(weak) + ". Kerak bo'lsa ko'proq slayd bilan qayta yarat."
            ) if weak else ""
    if not hw_tasks:
        note += " Uy vazifasi berilmadi (homework.tasks)."
    return (f"✅ Dars taqdimoti tayyor: {path.name} ({count} slayd, motiv {motif}"
            f"{'+' + secondary_motif if secondary_motif else ''}){plan}. Fayllar avtomatik yuboriladi.{note}")
