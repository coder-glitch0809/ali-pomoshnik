"""Ommaviy foydalanuvchilar (Telegram mehmonlari, telefon ilovasi) uchun vositalarsiz AI javobi.

Bepul tarif - Gemini (FREE_PROVIDER=gemini) yoki arzon Claude, Pro - asosiy Claude modeli.
Claude ishlamasa (balans tugagan va h.k.) - Gemini zaxira javob beradi.
"""
import asyncio
import logging

import anthropic

from . import providers
from .config import config

log = logging.getLogger("ali.public_ai")


async def ask_model(pro: bool, system: str, history: list[dict], text: str, max_tokens: int,
                    json_mode: bool = False) -> str:
    if config.chat_provider in {'gemini','openai','auto'} or (not pro and config.free_provider in {'gemini','openai'} and providers.can_chat()):
        return (await asyncio.to_thread(providers.chat, system, history, text, max_tokens, json_mode))[1]
    tier = ({"model": config.model, "max_tokens": max_tokens} if pro else
            {"model": config.free_model, "max_tokens": max_tokens, "output_config": {"effort": "low"}})
    try:
        async with anthropic.AsyncAnthropic(timeout=120 if pro else 60, max_retries=1) as client:
            response = await client.messages.create(**tier, system=system,
                                                    messages=history + [{"role": "user", "content": text}])
        return "".join(b.text for b in response.content if b.type == "text")
    except anthropic.APIError as e:
        if not (config.gemini_fallback and providers.can_chat()):
            raise
        log.warning("Claude javob bermadi (%s) - Gemini zaxirasi ishlatildi", type(e).__name__)
        return (await asyncio.to_thread(providers.chat, system, history, text, max_tokens, json_mode))[1]
