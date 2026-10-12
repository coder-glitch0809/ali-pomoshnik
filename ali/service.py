"""Yagona miya va so'rovlarni bajarish - veb-sayt ham, Telegram ham shu orqali ishlaydi.

Hamma kanallar bitta suhbatni bo'lishadi: telefonda boshlangan gapni kompyuterda yoki
Telegram'da davom ettirish mumkin, hammasi har bir ekranda jonli ko'rinadi.
"""
import asyncio
import logging
import secrets
from typing import Callable

import anthropic

from .brain import Brain
from .hub import hub

log = logging.getLogger("ali.service")

brain = Brain(confirm=hub.confirm)


class AskError(Exception):
    pass


def error_text(e: Exception) -> str:
    if isinstance(e, anthropic.AuthenticationError):
        return "Claude API kaliti noto'g'ri yoki yo'q (.env -> ANTHROPIC_API_KEY)."
    if isinstance(e, anthropic.RateLimitError):
        return "So'rovlar chegarasi. Biroz kuting."
    if isinstance(e, anthropic.APIConnectionError):
        return "Internetga ulanib bo'lmadi."
    if isinstance(e, anthropic.APIStatusError):
        return f"API xatosi {e.status_code}: {e.message}"
    return f"Xato: {e}"


async def run_ask(text: str, images: list[dict] | None = None, deep: bool = False, super_mode: bool = False,
                  source: str = "web", req_id: str | None = None,
                  on_event: Callable[[str, object], None] | None = None) -> str:
    """So'rovni bajaradi va jarayonni barcha ochiq ekranlarga uzatadi. Xatoda AskError."""
    if brain.lock.locked():
        raise AskError("Ali hozir boshqa vazifa ustida - biroz kuting.")
    req_id = req_id or secrets.token_hex(4)
    hub.broadcast({"type": "user", "id": req_id, "text": text, "from": source,
                   "images": [f"data:{i['media_type']};base64,{i['data']}" for i in images or []]})

    def emit(kind, data):
        hub.broadcast({"type": kind, "id": req_id, "data": data})
        if on_event:
            on_event(kind, data)

    try:
        answer = await asyncio.to_thread(brain.ask, text, emit, deep, super_mode, images)
    except Exception as e:
        if not isinstance(e, anthropic.APIError):
            log.exception("so'rov xatosi")
        message = error_text(e)
        hub.broadcast({"type": "error", "id": req_id, "text": message})
        raise AskError(message) from e
    hub.broadcast({"type": "done", "id": req_id, "text": answer, "speak_on": source})
    return answer
