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


sessions: dict[int, Session] = {}


def session(chat_id: int) -> Session:
    return sessions.setdefault(chat_id, Session())


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
            "Katakni bosing yoki yozing (B3). Matn - faol oynaga yoziladi, +ctrl+s - tugmalar.")


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
    return type_text(text)
