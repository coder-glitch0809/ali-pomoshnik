"""Bitta kompyuterda bitta Ali: ikkinchi nusxa Telegram botini "o'g'irlamasligi" uchun (Conflict - tugmalar yo'qoladi).

data/ali.lock fayli OS darajasida qulflanadi; jarayon tugasa (hatto qulab tushsa ham) qulf o'zi ochiladi.
"""
import os

from .config import config

_handle = None


def acquire() -> bool:
    """Qulfni oladi. Boshqa jarayon ushlab turgan bo'lsa - False. Shu jarayonda qayta chaqirish xavfsiz."""
    global _handle
    if _handle is not None:
        return True
    config.data_dir.mkdir(parents=True, exist_ok=True)
    f = open(config.data_dir / "ali.lock", "a+")
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
    _handle = f
    return True


def release() -> None:
    global _handle
    if _handle is None:
        return
    try:
        if os.name == "nt":
            import msvcrt
            _handle.seek(0)
            msvcrt.locking(_handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(_handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    _handle.close()
    _handle = None
