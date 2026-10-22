"""Google Gemini: ovozni matnga aylantirish, rasm yaratish va bepul suhbat.

Asosiy miya - Claude (vositalar va agentlar bilan). Gemini'ning bepul API'si:
  - ommaviy Telegram botning bepul tarifi javoblari (FREE_PROVIDER=gemini);
  - Claude API ishlamasa (balans tugagan, kalit xato) - zaxira javob (GEMINI_FALLBACK=true).
"""
import logging
import re

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
        _openai = OpenAI(api_key=config.openai_api_key, timeout=60, max_retries=1)
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
    return bool(config.gemini_api_key or config.openai_api_key or config.bedrock_api_key)


# --- Amazon Bedrock (Converse API, Bedrock API kaliti bilan) ---
def _bedrock_headers(key: str | None = None) -> dict:
    return {"Authorization": f"Bearer {key or config.bedrock_api_key}", "Content-Type": "application/json"}


def bedrock_models(key: str | None = None, region: str | None = None) -> list[str]:
    """Hisobda ishlatish mumkin bo'lgan Claude modellari (inference profile ID lari), eng yangisi birinchi."""
    import httpx
    region = region or config.bedrock_region
    found = []
    for path, field_name in (("inference-profiles?typeEquals=SYSTEM_DEFINED&maxResults=1000", "inferenceProfileSummaries"),
                             ("foundation-models?byProvider=anthropic", "modelSummaries")):
        try:
            r = httpx.get(f"https://bedrock.{region}.amazonaws.com/{path}", headers=_bedrock_headers(key), timeout=20)
            if r.status_code == 200:
                for m in r.json().get(field_name, []):
                    mid = m.get("inferenceProfileId") or m.get("modelId", "")
                    if "anthropic.claude" in mid:
                        found.append(mid)
        except httpx.HTTPError:
            continue
    # Opus > Sonnet > Haiku, versiya bo'yicha yangisi birinchi
    rank = lambda m: (0 if "opus" in m else 1 if "sonnet" in m else 2, [-int(x) for x in re.findall(r"\d+", m)[:3]])
    return sorted(dict.fromkeys(found), key=rank)


def bedrock_chat(system: str, history: list[dict], text: str, max_tokens: int = 1500, model: str | None = None,
                 key: str | None = None, region: str | None = None) -> str:
    """Bedrock orqali Claude bilan suhbat (vositalarsiz)."""
    import httpx
    key, region = key or config.bedrock_api_key, region or config.bedrock_region
    if not key:
        raise RuntimeError("Bedrock API kaliti yo'q")
    model = model or config.bedrock_model or next(iter(bedrock_models(key, region)), "")
    if not model:
        raise RuntimeError("Bedrock'da Claude modeli topilmadi - BEDROCK_MODEL ni kiriting")
    messages, last = [], None
    for m in history + [{"role": "user", "content": text}]:
        role = "assistant" if m["role"] == "assistant" else "user"
        content = str(m.get("content", "")).strip()
        if not content:
            continue
        if role == last:  # Bedrock ketma-ket bir xil rolni qabul qilmaydi
            messages[-1]["content"][0]["text"] += "\n\n" + content
        else:
            messages.append({"role": role, "content": [{"text": content}]})
            last = role
    if messages and messages[0]["role"] != "user":
        messages.pop(0)
    r = httpx.post(f"https://bedrock-runtime.{region}.amazonaws.com/model/{model}/converse", headers=_bedrock_headers(key),
                   json={"system": [{"text": system}], "messages": messages,
                         "inferenceConfig": {"maxTokens": max_tokens}}, timeout=180)
    if r.status_code != 200:
        raise RuntimeError(f"Bedrock xatosi {r.status_code}: {r.text[:300]}")
    parts = r.json().get("output", {}).get("message", {}).get("content", [])
    return "".join(p.get("text", "") for p in parts).strip()


def chat(system: str, history: list[dict], text: str, max_tokens: int = 1500,
         json_mode: bool = False) -> tuple[str, str]:
    """Try configured chat providers in order, without desktop tools or Claude billing."""
    order=['openai','gemini'] if config.chat_provider=='openai' else ['gemini','openai']
    order=['bedrock']+order  # Bedrock (pullik Claude) bo'lsa - birinchi, bepul Gemini zaxira
    for name in order:
        if not getattr(config,name+'_api_key'):continue
        try:
            if name=='bedrock':answer=bedrock_chat(system,history,text,max_tokens)
            elif name=='gemini':answer=gemini_chat(system,history,text,max_tokens,json_mode)
            else:
                options={'text':{'format':{'type':'json_object'}}} if json_mode else {}
                response=_openai_client().responses.create(model=config.openai_model,
                    instructions=system+('\nReturn valid JSON only.' if json_mode else ''),
                    input=history+[{'role':'user','content':text}],max_output_tokens=max_tokens+4096,
                    store=False,**options)
                answer=response.output_text.strip()
            if answer:return {'gemini':'Gemini','bedrock':'Bedrock'}.get(name,'GPT'),answer
        except Exception as error:
            log.warning('%s chat unavailable: %s',name,type(error).__name__)
    raise RuntimeError('AI xizmatlari hozir javob bermadi (Gemini bepul limiti tugagan bo‘lishi mumkin). '
                       'Kompyuterdagi Claude/ChatGPT ilovalari ulanganini yoki Bedrock kalitini tekshiring.')


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
