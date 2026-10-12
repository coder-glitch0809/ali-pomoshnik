"""Qo'shimcha AI modellari: OpenAI (GPT) va Google Gemini.

Claude - asosiy miya (vositalar bilan ishlaydi). GPT va Gemini - maslahatchilar:
Claude ularning fikrini so'raydi, solishtiradi va yakuniy javobni beradi.
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from .config import config

log = logging.getLogger("ali.providers")

_openai = None
_gemini = None


def _openai_client():
    global _openai
    if _openai is None:
        from openai import OpenAI
        _openai = OpenAI(api_key=config.openai_api_key)
    return _openai


def _gemini_client():
    global _gemini
    if _gemini is None:
        from google import genai
        _gemini = genai.Client(api_key=config.gemini_api_key)
    return _gemini


def available() -> dict[str, bool]:
    return {"openai": bool(config.openai_api_key), "gemini": bool(config.gemini_api_key)}


def ask_openai(prompt: str) -> str:
    response = _openai_client().responses.create(model=config.openai_model, input=prompt)
    return response.output_text


def ask_gemini(prompt: str) -> str:
    response = _gemini_client().models.generate_content(model=config.gemini_model, contents=prompt)
    return response.text or ""


def ask_all(prompt: str) -> dict[str, str]:
    """Mavjud barcha maslahatchilarga parallel so'rov yuboradi."""
    jobs = {}
    if config.openai_api_key:
        jobs[f"GPT ({config.openai_model})"] = ask_openai
    if config.gemini_api_key:
        jobs[f"Gemini ({config.gemini_model})"] = ask_gemini
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(jobs) or 1) as pool:
        futures = {name: pool.submit(fn, prompt) for name, fn in jobs.items()}
        for name, future in futures.items():
            try:
                results[name] = future.result(timeout=180)
            except Exception as e:
                log.exception("%s xatosi", name)
                results[name] = f"[xato: {e}]"
    return results


MIME = {"webm": "audio/webm", "ogg": "audio/ogg", "oga": "audio/ogg", "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4"}


def can_transcribe() -> bool:
    return bool(config.openai_api_key or config.gemini_api_key)


def transcribe(audio: bytes, filename: str = "audio.webm") -> str:
    """Ovozni matnga aylantiradi (brauzer tanimasa va Telegram ovozli xabarlari uchun).
    Avval OpenAI, bo'lmasa Gemini ishlatiladi."""
    if config.openai_api_key:
        result = _openai_client().audio.transcriptions.create(
            model=config.openai_transcribe_model, file=(filename, audio), language="uz"
        )
        return result.text
    if config.gemini_api_key:
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
    raise RuntimeError("Ovozni tanish uchun OPENAI_API_KEY yoki GEMINI_API_KEY kerak")
