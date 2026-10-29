"""Telefondan kompyuterni masofadan boshqarish (Telegram /kompyuter).

Ekran rasmi katakchali to'r (A1..H6) bilan yuboriladi. Katak tugmasini bosish yoki "B3" deb yozish -
o'sha joyga sichqoncha bilan bosadi. 🔍 rejimida katak bosilsa - o'sha joy kattalashtiriladi (aniq bosish uchun).
Boshqa yozilgan matn faol oynaga teriladi, "+ctrl+s" kabi matn - tugmalar kombinatsiyasi.
Sichqoncha/klaviatura uchun ali/skills/desktop.py dagi funksiyalar qayta ishlatiladi.
"""
import io
import re
import time
from dataclasses import dataclass

COLS, ROWS = 8, 6
LETTERS = "ABCDEFGH"
MAX_SIDE = 1600
_CELL = re.compile(r"^\s*([a-hA-H])\s*([1-6])\s*$")


@dataclass
class Session:
    region: tuple[int, int, int, int] | None = None  # (x, y, w, h) haqiqiy ekranda; None - to'liq ekran
    screen: tuple[int, int] = (0, 0)
    button: str = "left"
    double: bool = False
    zoom: bool = False  # True bo'lsa keyingi katak bosilganda kattalashtiriladi
    used: float = 0.0  # oxirgi ishlatilgan vaqt


sessions: dict[int, Session] = {}
IDLE = 10 * 60  # 10 daqiqa ishlatilmasa - rejim o'zi yopiladi
_TYPE = re.compile(r"^\s*(yoz|ёз|йоз|type)\s*:\s*(.+)$", re.I | re.S)


def session(chat_id: int) -> Session:
    s = sessions.setdefault(chat_id, Session())
    s.used = time.time()
    return s


def active(chat_id: int) -> bool:
    s = sessions.get(chat_id)
    if s and time.time() - s.used > IDLE:
        stop(chat_id)
        return False
    return s is not None


def is_command(text: str) -> bool:
    """Kompyuterga tegishli xabarmi: katak (B3), tugmalar (+ctrl+s) yoki "yoz: matn". Qolgani - oddiy suhbat."""
    t = (text or "").strip()
    return bool(parse_cell(t) or (t.startswith("+") and len(t) > 1 and len(t) < 40) or _TYPE.match(t))


def stop(chat_id: int) -> None:
    sessions.pop(chat_id, None)


def parse_cell(text: str) -> tuple[int, int] | None:
    """'B3' -> (1, 2). Katak bo'lmasa None."""
    m = _CELL.match(text or "")
    return (LETTERS.index(m.group(1).upper()), int(m.group(2)) - 1) if m else None


def _area(s: Session) -> tuple[int, int, int, int]:
    return s.region or (0, 0, *s.screen)


def cell_center(s: Session, col: int, row: int) -> tuple[int, int]:
    x, y, w, h = _area(s)
    return round(x + (col + 0.5) * w / COLS), round(y + (row + 0.5) * h / ROWS)


def zoom_to(s: Session, col: int, row: int) -> None:
    """Katak atrofidagi 3x3 katakli joyni kattalashtiradi (ekran chegarasidan chiqmaydi)."""
    _, _, w, h = _area(s)
    nw, nh = max(round(w * 3 / COLS), 40), max(round(h * 3 / ROWS), 30)
    cx, cy = cell_center(s, col, row)
    nx = min(max(cx - nw // 2, 0), max(s.screen[0] - nw, 0))
    ny = min(max(cy - nh // 2, 0), max(s.screen[1] - nh, 0))
    s.region, s.zoom = (nx, ny, nw, nh), False


def draw_grid(image):
    """Rasm ustiga katak chiziqlari va nomlarini (A1..H6) chizadi."""
    from PIL import ImageDraw, ImageFont

    image = image.convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    w, h = image.size
    size = max(14, min(w // COLS, h // ROWS) // 5)
    try:
        font = ImageFont.truetype("arial.ttf", size)
    except OSError:
        font = ImageFont.load_default()
    for c in range(1, COLS):
        x = round(c * w / COLS)
        draw.line([(x, 0), (x, h)], fill=(255, 40, 40, 150), width=2)
    for r in range(1, ROWS):
        y = round(r * h / ROWS)
        draw.line([(0, y), (w, y)], fill=(255, 40, 40, 150), width=2)
    for c in range(COLS):
        for r in range(ROWS):
            x, y = round(c * w / COLS) + 3, round(r * h / ROWS) + 3
            label = f"{LETTERS[c]}{r + 1}"
            box = draw.textbbox((x, y), label, font=font)
            draw.rectangle([box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2], fill=(0, 0, 0, 150))
            draw.text((x, y), label, fill=(255, 255, 0, 255), font=font)
    return image


def capture(s: Session) -> bytes:
    """Ekran (yoki kattalashtirilgan joy) rasmini to'r bilan JPEG qilib qaytaradi."""
    from PIL import ImageGrab

    from .skills import desktop

    desktop.dpi_aware()
    full = ImageGrab.grab()
    s.screen = full.size
    x, y, w, h = _area(s)
    image = full.crop((x, y, x + w, y + h)) if s.region else full
    if image.width < 800:  # kattalashtirilgan kichik joy - ko'rinishi uchun kattalashtiramiz
        k = 800 / image.width
        image = image.resize((800, round(image.height * k)))
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    draw_grid(image).save(buf, format="JPEG", quality=75)
    return buf.getvalue()


def caption(s: Session) -> str:
    mode = "🔍 Katakni tanlang - kattalashtiriladi" if s.zoom else (
        f"🖱 {'O`ng' if s.button == 'right' else 'Chap'} tugma{' x2' if s.double else ''}")
    where = "kattalashtirilgan joy" if s.region else "to'liq ekran"
    return (f"💻 Kompyuter ({where}) | {mode}\n"
            "Katakni bosing yoki yozing (B3). Yozish: «yoz: matn», tugmalar: +ctrl+s. Boshqa xabarlar - oddiy suhbat.")


def click_cell(s: Session, col: int, row: int) -> str:
    if s.zoom:
        zoom_to(s, col, row)
        return f"🔍 {LETTERS[col]}{row + 1} kattalashtirildi"
    from .skills import desktop

    x, y = cell_center(s, col, row)
    desktop._gui().click(x, y, clicks=2 if s.double else 1, button=s.button)
    s.button, s.double = "left", False  # bir martalik - keyingi bosish yana oddiy
    time.sleep(0.6)
    return f"Bosildi: {LETTERS[col]}{row + 1}"


def scroll(amount: int) -> str:
    from .skills import desktop

    desktop._gui().scroll(amount * 120)
    time.sleep(0.4)
    return f"Aylantirildi: {amount}"


def keys(combo: str) -> str:
    from .skills import desktop

    result = desktop.press_keys(combo)
    time.sleep(0.5)
    return result


def type_text(text: str) -> str:
    from .skills import desktop

    result = desktop.type_text(text)
    time.sleep(0.5)
    return result


def handle_text(s: Session, text: str) -> str:
    """Telefondan yozilgan matn: katak -> bosish, '+...' -> tugmalar, boshqasi -> yozish."""
    cell = parse_cell(text)
    if cell:
        return click_cell(s, *cell)
    if text.startswith("+") and len(text) > 1:
        return keys(text[1:])
    m = _TYPE.match(text)
    if not m:
        return "Kompyuter buyrug'i emas"
    return type_text(m.group(2))


# --- Jonli boshqaruv (/remote sahifasi): ekran tez-tez yangilanadi, barmoq bilan bosish/sudrash/yozish ---
def frame(max_w: int = 1280, quality: int = 60) -> bytes:
    """Ekran rasmi (to'rsiz), sichqoncha joyi qizil nuqta bilan - telefonda jonli ko'rish uchun."""
    from PIL import ImageDraw, ImageGrab

    from .skills import desktop

    desktop.dpi_aware()
    image = ImageGrab.grab().convert("RGB")
    try:
        x, y = desktop._gui().position()
        ImageDraw.Draw(image).ellipse([x - 7, y - 7, x + 7, y + 7], outline=(255, 0, 0), width=3)
    except Exception:  # sichqoncha joyi olinmasa ham rasm yuboriladi
        pass
    max_w = max(480, min(int(max_w), 1920))
    if image.width > max_w:
        image = image.resize((max_w, round(image.height * max_w / image.width)))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=max(30, min(int(quality), 85)))
    return buf.getvalue()


def _point(a: dict) -> tuple[int, int]:
    """Telefondagi nisbiy nuqta (0..1) -> haqiqiy ekran koordinatasi."""
    from .skills import desktop

    w, h = desktop._gui().size()
    fx, fy = float(a.get("x", 0.5)), float(a.get("y", 0.5))
    return round(min(max(fx, 0.0), 1.0) * (w - 1)), round(min(max(fy, 0.0), 1.0) * (h - 1))


def act(a: dict) -> str:
    """Bitta amal: click / down / move / up / scroll / key / type."""
    from .skills import desktop

    gui, kind = desktop._gui(), str(a.get("type", ""))
    if kind == "click":
        x, y = _point(a)
        button = "right" if a.get("button") == "right" else "left"
        gui.click(x, y, clicks=2 if a.get("double") else 1, button=button)
        return f"bosildi {x},{y}"
    if kind == "down":
        gui.mouseDown(*_point(a))
        return "bosib turibdi"
    if kind == "move":
        gui.moveTo(*_point(a))
        return "siljidi"
    if kind == "up":
        gui.mouseUp(*_point(a))
        return "qo'yib yuborildi"
    if kind == "scroll":
        gui.scroll(int(max(-20, min(20, float(a.get("dy", 0))))) * 120)
        return "aylantirildi"
    if kind == "key":
        return desktop.press_keys(str(a.get("keys", ""))[:40])
    if kind == "type":
        return desktop.type_text(str(a.get("text", ""))[:2000])
    raise ValueError("Noma'lum amal")
