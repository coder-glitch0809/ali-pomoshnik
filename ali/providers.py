"""Google Gemini - faqat Claude qila olmaydigan ishlar uchun: ovozni matnga aylantirish va rasm yaratish.

Savollarga javob, tahlil va agentlar - hammasi Claude'da.
"""
import logging

from .config import config

log = logging.getLogger("ali.providers")

_gemini = None


def _gemini_client():
    global _gemini
    if _gemini is None:
        from google import genai
        _gemini = genai.Client(api_key=config.gemini_api_key)
    return _gemini


MIME = {"webm": "audio/webm", "ogg": "audio/ogg", "oga": "audio/ogg", "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4"}


def can_transcribe() -> bool:
    return bool(config.gemini_api_key)


def transcribe(audio: bytes, filename: str = "audio.webm") -> str:
    """Ovozni matnga aylantiradi (brauzer tanimasa va Telegram ovozli xabarlari uchun) - Gemini orqali."""
    if not config.gemini_api_key:
        raise RuntimeError("Ovozni tanish uchun GEMINI_API_KEY kerak")
    from google.genai import types

    mime = MIME.get(filename.rsplit(".", 1)[-1].lower(), "audio/ogg")
    response = _gemini_client().models.generate_content(
        model=config.gemini_fast_model,
        contents=[
            types.Part.from_bytes(data=audio, mime_type=mime),
            "Bu audioni so'zma-so'z matnga yoz (asosan o'zbek tilida). Faqat matnni qaytar, boshqa hech narsa yozma.",
        ],
    )
    return (response.text or "").strip()


def can_generate_image() -> bool:
    return bool(config.gemini_api_key)


def generate_image(prompt: str) -> bytes:
    """Matn bo'yicha rasm (PNG bayt) - Gemini orqali."""
    if not config.gemini_api_key:
        raise RuntimeError("Rasm uchun GEMINI_API_KEY kerak")
    response = _gemini_client().models.generate_content(model=config.gemini_image_model, contents=prompt[:4000])
    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            if getattr(part, "inline_data", None) and part.inline_data.data:
                return part.inline_data.data
    raise RuntimeError("Gemini rasm qaytarmadi")
