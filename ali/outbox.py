"""Chiquvchi fayllar: agentlar yaratgan .pptx/.docx/.xlsx shu yerda saqlanadi va so'rov tugagach
foydalanuvchiga (Telegram'da hujjat, saytda yuklab olish havolasi) avtomatik yuboriladi."""
import re
import threading
import time
from pathlib import Path

from .config import config

DIR = config.data_dir / "outbox"
KEEP_DAYS = 14
_lock = threading.Lock()
_created: list[Path] = []


def new_path(title: str, ext: str) -> Path:
    """Xavfsiz, takrorlanmaydigan fayl nomi (kirill harflari saqlanadi)."""
    DIR.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w\- ]+", "", title, flags=re.UNICODE).strip().replace(" ", "_")[:60] or "hujjat"
    path = DIR / f"{stem}_{time.strftime('%Y%m%d_%H%M%S')}.{ext}"
    n = 2
    while path.exists():
        path = DIR / f"{stem}_{time.strftime('%Y%m%d_%H%M%S')}_{n}.{ext}"
        n += 1
    return path


def register(path: Path) -> None:
    with _lock:
        _created.append(path)
    _cleanup()


def mark() -> int:
    with _lock:
        return len(_created)


def since(position: int) -> list[Path]:
    with _lock:
        return [p for p in _created[position:] if p.exists()]


def resolve(name: str) -> Path | None:
    """Yuklab olish uchun: faqat outbox ichidagi mavjud fayl."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    path = DIR / name
    return path if path.is_file() and path.resolve().parent == DIR.resolve() else None


def _cleanup() -> None:
    limit = time.time() - KEEP_DAYS * 86400
    for old in DIR.glob("*.*"):
        try:
            if old.stat().st_mtime < limit:
                old.unlink()
        except OSError:
            pass
