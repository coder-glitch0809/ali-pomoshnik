"""Bitta kompyuterda bitta Ali: ikkinchi nusxa Telegram botini "o'g'irlamasligi" uchun (Conflict - tugmalar yo'qoladi).

data/ali.lock - shu ma'lumotlar papkasi uchun bitta server; bot_lock() - bitta bot tokeni uchun bitta so'rovchi
(boshqa papkadan, masalan kuchaytirish nusxasidan ishga tushsa ham). Jarayon tugasa (hatto qulasa) qulf o'zi ochiladi.
"""
import hashlib
import os
import tempfile
from pathlib import Path

from .config import config

_handles: dict[str, object] = {}


def acquire(path: Path | None = None) -> bool:
    """Qulfni oladi. Boshqa jarayon ushlab turgan bo'lsa - False. Shu jarayonda qayta chaqirish xavfsiz."""
    path = Path(path or config.data_dir / "ali.lock")
    key = str(path)
    if key in _handles:
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return False
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    _handles[key] = f
    return True


def bot_lock(token: str) -> Path:
    """Bot tokeniga bog'langan umumiy qulf fayli (token o'zi yozilmaydi - faqat xeshi)."""
    return Path(tempfile.gettempdir()) / f"ali-bot-{hashlib.sha256(token.encode()).hexdigest()[:16]}.lock"


def release(path: Path | None = None) -> None:
    f = _handles.pop(str(Path(path or config.data_dir / "ali.lock")), None)
    if f is None:
        return
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    f.close()
