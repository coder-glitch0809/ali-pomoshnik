"""Kirish paroli va sessiya tokeni (veb-sayt va Telegram uchun umumiy)."""
import hashlib
import hmac
import secrets
import threading
import time

from .config import config


def _load_secret(name: str, generate) -> str:
    path = config.data_dir / name
    if not path.exists():
        path.write_text(generate(), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


SECRET_KEY = _load_secret("secret.key", lambda: secrets.token_hex(32))
PASSWORD = config.access_password or _load_secret("password.txt", lambda: secrets.token_urlsafe(9))
TOKEN = hmac.new(SECRET_KEY.encode(), PASSWORD.encode(), hashlib.sha256).hexdigest()


# Parol terishdan himoya: MAX_FAILS marta xato bo'lsa, LOCK_SECONDS davomida hamma urinishlar rad etiladi
MAX_FAILS = 5
LOCK_SECONDS = 15 * 60
_fails: list[float] = []
_locked_until = 0.0
_guard = threading.Lock()


def locked_for() -> int:
    """Kirish bloklangan bo'lsa, qolgan soniyalar; aks holda 0."""
    return max(0, int(_locked_until - time.time()))


def check_password(value: str) -> bool:
    global _locked_until
    with _guard:
        now = time.time()
        if now < _locked_until:
            return False
        if hmac.compare_digest(str(value), PASSWORD):
            _fails.clear()
            return True
        _fails[:] = [t for t in _fails if now - t < LOCK_SECONDS] + [now]
        if len(_fails) >= MAX_FAILS:
            _locked_until = now + LOCK_SECONDS
            _fails.clear()
        return False


def check_token(value: str) -> bool:
    return hmac.compare_digest(str(value or ""), TOKEN)
