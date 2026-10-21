"""Google Gemini: ovozni matnga aylantirish, rasm yaratish va bepul suhbat.

Asosiy miya - Claude (vositalar va agentlar bilan). Gemini'ning bepul API'si:
  - ommaviy Telegram botning bepul tarifi javoblari (FREE_PROVIDER=gemini);
  - Claude API ishlamasa (balans tugagan, kalit xato) - zaxira javob (GEMINI_FALLBACK=true).
"""
import logging

from .config import config

log = logging.getLogger("ali.providers")

_gemini = None
_openai = None


def _gemini_client():
    global _gemini
    if _gemini is None:
        from google import genai
        from google.genai import types
        # Google javob bermasa so'rov cheksiz osilib qolmasin (millisekund)
        _gemini = genai.Client(api_key=config.gemini_api_key, http_options=types.HttpOptions(timeout=90_000))
    return _gemini


def _openai_client():
    global _openai
    if _openai is None:
        from openai import OpenAI
        _openai = OpenAI(api_key=config.openai_api_key)
    return _openai


def available() -> dict[str, bool]:
    """Maslahatchi modellar (consult_experts uchun)."""
    return {"openai": bool(config.openai_api_key), "gemini": bool(config.gemini_api_key)}


def ask_openai(prompt: str) -> str:
    return _openai_client().responses.create(model=config.openai_model, input=prompt).output_text


def ask_gemini(prompt: str) -> str:
    return _gemini_client().models.generate_content(model=config.gemini_model, contents=prompt).text or ""


def ask_all(prompt: str) -> dict[str, str]:
    """Ulangan barcha maslahatchilarga (GPT, Gemini) parallel so'rov."""
    from concurrent.futures import ThreadPoolExecutor

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


def can_chat() -> bool:
    return bool(config.gemini_api_key)


def gemini_chat(system: str, history: list[dict], text: str, max_tokens: int = 1500, json_mode: bool = False,
                model: str | None = None) -> str:
    """Gemini bilan oddiy suhbat (vositalarsiz). history: [{"role": "user"|"assistant", "content": str}]."""
    if not config.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY yo'q")
    from google.genai import types

    contents = [
        types.Content(role="model" if m["role"] == "assistant" else "user", parts=[types.Part(text=str(m["content"]))])
        for m in history if str(m.get("content", "")).strip()
    ]
    contents.append(types.Content(role="user", parts=[types.Part(text=text)]))
    # Fikrlash tokenlari ham chegaraga kiradi - javob kesilmasligi uchun zaxira qo'shamiz
    cfg = types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens + 4096,
                                      response_mime_type="application/json" if json_mode else None)
    response = _gemini_client().models.generate_content(model=model or config.gemini_chat_model, contents=contents, config=cfg)
    return (response.text or "").strip()


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
