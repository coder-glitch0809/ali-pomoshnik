"""Kirish paroli va sessiya tokeni (veb-sayt va Telegram uchun umumiy)."""
import hashlib
import hmac
import secrets
import json
import threading
import time
from urllib.parse import parse_qsl

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
        if hmac.compare_digest(str(value).encode(), PASSWORD.encode()):
            _fails.clear()
            return True
        _fails[:] = [t for t in _fails if now - t < LOCK_SECONDS] + [now]
        if len(_fails) >= MAX_FAILS:
            _locked_until = now + LOCK_SECONDS
            _fails.clear()
        return False


def check_token(value: str) -> bool:
    value=str(value or '')
    if hmac.compare_digest(value.encode(), TOKEN.encode()):return True
    try:
        prefix,uid,expires,signature=value.split('.')
        payload=f'{prefix}.{uid}.{expires}'
        expected=hmac.new(SECRET_KEY.encode(),payload.encode(),hashlib.sha256).hexdigest()
        return (prefix=='tg' and config.telegram_owner_id>0 and int(uid)==config.telegram_owner_id
                and time.time()<int(expires) and hmac.compare_digest(signature.encode(),expected.encode()))
    except (ValueError,TypeError):return False


def telegram_owner(init_data):
    """Validate Telegram HMAC, freshness and server-configured owner; never trust raw ID."""
    if not config.telegram_token or not config.telegram_owner_id:return False
    if not isinstance(init_data,str) or len(init_data)>16000:return False
    try:
        pairs=parse_qsl(init_data,keep_blank_values=True,strict_parsing=True)
        fields=dict(pairs)
        if len(fields)!=len(pairs):return False
        signature=fields.pop('hash','')
        secret=hmac.new(b'WebAppData',config.telegram_token.encode(),hashlib.sha256).digest()
        payload='\n'.join(f'{k}={v}' for k,v in sorted(fields.items()))
        expected=hmac.new(secret,payload.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature.encode(),expected.encode()):return False
        age=time.time()-int(fields['auth_date'])
        user=json.loads(fields['user'])
        return -30<=age<=300 and type(user.get('id')) is int and user['id']==config.telegram_owner_id
    except (ValueError,KeyError,TypeError,AttributeError):return False


def telegram_session():
    payload=f'tg.{config.telegram_owner_id}.{int(time.time())+8*3600}'
    return payload+'.'+hmac.new(SECRET_KEY.encode(),payload.encode(),hashlib.sha256).hexdigest()
