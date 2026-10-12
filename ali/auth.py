"""Kirish paroli va sessiya tokeni (veb-sayt va Telegram uchun umumiy)."""
import hashlib
import hmac
import secrets

from .config import config


def _load_secret(name: str, generate) -> str:
    path = config.data_dir / name
    if not path.exists():
        path.write_text(generate(), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


SECRET_KEY = _load_secret("secret.key", lambda: secrets.token_hex(32))
PASSWORD = config.access_password or _load_secret("password.txt", lambda: secrets.token_urlsafe(9))
TOKEN = hmac.new(SECRET_KEY.encode(), PASSWORD.encode(), hashlib.sha256).hexdigest()


def check_password(value: str) -> bool:
    return hmac.compare_digest(str(value), PASSWORD)


def check_token(value: str) -> bool:
    return hmac.compare_digest(str(value or ""), TOKEN)
