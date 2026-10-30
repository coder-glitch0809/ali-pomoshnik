"""Telegram akkauntga kirish - Ali sahifasidagi forma orqali (terminal o'rniga): telefon -> kod -> (bo'lsa) parol.

Raqam, kod va parolni egasi O'ZI kiritadi; hech biri faylga yoki logga yozilmaydi. Sessiya data/telegram_user.session
da saqlanadi (tg_account bilan bir xil). Telethon mijozi bosqichlar orasida alohida oqimdagi event loop'da yashaydi.
"""
import asyncio
import threading
import time

from . import tg_account

_loop: asyncio.AbstractEventLoop | None = None
_state: dict = {}  # client, phone, hash, at
TTL = 10 * 60


def _run(coro):
    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
        threading.Thread(target=_loop.run_forever, daemon=True, name="tg-login").start()
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(120)


def _error(e: Exception) -> str:
    name = type(e).__name__
    return {
        "PhoneNumberInvalidError": "Telefon raqami noto‘g‘ri. Masalan: +998901234567",
        "PhoneCodeInvalidError": "Kod noto‘g‘ri. Telegram ilovasidagi oxirgi kodni yozing.",
        "PhoneCodeExpiredError": "Kod eskirgan. «Kod yuborish» ni qayta bosing va yangi kodni darhol yozing.",
        "PasswordHashInvalidError": "Parol noto‘g‘ri (Telegram «Ikki bosqichli tekshiruv» paroli). 👁 bilan tekshirib yozing.",
        "FloodWaitError": f"Telegram ko‘p urinish sabab vaqtincha blokladi: {getattr(e, 'seconds', '?')} soniyadan keyin urining.",
    }.get(name, f"{name}: {e}")


async def _close():
    c = _state.pop("client", None)
    if c:
        await c.disconnect()


def start(phone: str) -> dict:
    """Kod yuboradi. Natija: {"step": "code"} yoki {"error": ...}."""
    from telethon import TelegramClient
    creds = tg_account.credentials()
    if not creds:
        return {"error": "Avval api_id va api_hash ni kiriting (Ruxsatlar -> Telegram akkaunt)"}
    phone = phone.strip().replace(" ", "")

    async def go():
        await _close()
        client = TelegramClient(str(tg_account.SESSION), *creds)
        await client.connect()
        sent = await client.send_code_request(phone)
        _state.update(client=client, phone=phone, hash=sent.phone_code_hash, at=time.time())
    try:
        _run(go())
    except Exception as e:
        return {"error": _error(e)}
    return {"step": "code"}


def code(value: str) -> dict:
    """Kodni tekshiradi: {"step": "done"} | {"step": "password"} | {"error": ...}."""
    if not _state.get("client") or time.time() - _state.get("at", 0) > TTL:
        return {"error": "Kirish boshlanmagan yoki eskirgan - «Kod yuborish» ni qayta bosing"}
    from telethon.errors import SessionPasswordNeededError

    async def go():
        try:
            await _state["client"].sign_in(_state["phone"], value.strip().replace(" ", ""), phone_code_hash=_state["hash"])
        except SessionPasswordNeededError:
            return "password"
        return "done"
    try:
        step = _run(go())
    except Exception as e:
        return {"error": _error(e)}
    return _finish() if step == "done" else {"step": "password"}


def password(value: str) -> dict:
    if not _state.get("client"):
        return {"error": "Kirish boshlanmagan - «Kod yuborish» dan boshlang"}
    try:
        _run(_state["client"].sign_in(password=value))
    except Exception as e:
        return {"error": _error(e)}
    return _finish()


def _finish() -> dict:
    async def go():
        me = await _state["client"].get_me()
        await _close()
        return me
    me = _run(go())
    tg_account._authorized = True
    tg_account._auth_cache.update(at=time.time(), ok=True)
    _state.clear()
    return {"step": "done", "name": f"{me.first_name or ''} (@{me.username or '-'})"}
