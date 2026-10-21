"""ChatGPT plagini: OpenAI API orqali savol so'rash va rasm yaratish."""
import base64

import httpx

from .. import outbox
from ..config import config
from ..skills import skill
from . import Plugin

API = "https://api.openai.com/v1"


def _headers() -> dict:
    if not config.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY kiritilmagan")
    return {"Authorization": f"Bearer {config.openai_api_key}"}


def _start() -> tuple[bool, str]:
    if not config.openai_api_key:
        return False, "OPENAI_API_KEY kiritilmagan"
    try:
        r = httpx.get(f"{API}/models", headers=_headers(), timeout=15)
    except httpx.HTTPError:
        return True, "Kalit bor, OpenAI'ga hozir ulanib bo'lmadi"
    if r.status_code == 401:
        return False, "OpenAI kalitni qabul qilmadi"
    return True, f"Ulangan ({config.openai_model})"


PLUGIN = Plugin(key="chatgpt", name="ChatGPT", icon="◎", start=_start,
                description="OpenAI ChatGPT: savollarga javob va rasm yaratish")


def _error(r: httpx.Response) -> str:
    try:
        return r.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return f"HTTP {r.status_code}"


@skill(
    description="Savolni ChatGPT'ga (OpenAI) beradi va javobini qaytaradi. Foydalanuvchi 'ChatGPT'dan so'ra' desa "
                "yoki boshqa AI fikri kerak bo'lsa ishlat.",
    params={"question": {"type": "string", "description": "ChatGPT'ga beriladigan to'liq savol"}},
)
def ask_chatgpt(question: str) -> str:
    r = httpx.post(f"{API}/chat/completions", headers=_headers(), timeout=120, json={
        "model": config.openai_model,
        "messages": [
            {"role": "system", "content": "Qisqa, aniq va oddiy tilda javob ber. Savol qaysi tilda bo'lsa, o'sha tilda."},
            {"role": "user", "content": question},
        ],
    })
    if r.status_code != 200:
        raise RuntimeError(f"ChatGPT xatosi: {_error(r)}")
    return (r.json()["choices"][0]["message"]["content"] or "").strip() or "(ChatGPT bo'sh javob qaytardi)"


@skill(
    description="ChatGPT (OpenAI) bilan matn bo'yicha rasm yaratadi (PNG). Rasm foydalanuvchiga avtomatik yuboriladi.",
    params={
        "prompt": {"type": "string", "description": "Rasm tavsifi"},
        "size": {"type": "string", "enum": ["1024x1024", "1536x1024", "1024x1536"], "description": "O'lcham"},
    },
    required=["prompt"],
)
def chatgpt_image(prompt: str, size: str = "1024x1024") -> str:
    r = httpx.post(f"{API}/images/generations", headers=_headers(), timeout=300, json={
        "model": config.openai_image_model, "prompt": prompt[:4000], "size": size, "n": 1,
    })
    if r.status_code != 200:
        raise RuntimeError(f"ChatGPT rasm xatosi: {_error(r)}")
    item = r.json()["data"][0]
    if item.get("b64_json"):
        data = base64.b64decode(item["b64_json"])
    else:
        data = httpx.get(item["url"], timeout=120).content
    path = outbox.new_path("chatgpt_rasm", "png")
    path.write_bytes(data)
    outbox.register(path)
    return f"Rasm tayyor: {path.name}"
