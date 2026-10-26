"""Mavzuga oid rasm yaratish (ChatGPT/Gemini, avval pro model) va uni Telegram kanalga joylash.

Claude (Ali miyasi) mavzu bo'yicha inglizcha tavsif (prompt) va o'zbekcha izoh yozadi, rasmni esa ulangan
eng kuchli model chizadi: pro tartibda ChatGPT (high) -> Gemini pro -> Gemini -> ChatGPT (medium).
Kanalga bot orqali joylanadi: botni kanalga administrator qilib qo'shing (post joylash ruxsati).
"""
import httpx

from .. import outbox, providers
from ..config import config
from . import skill

CAPTION_MAX = 1024  # Telegram rasm izohi chegarasi


def _chat_id(channel: str) -> str:
    channel = (channel or config.telegram_channel).strip()
    if not channel:
        raise RuntimeError("Kanal ko'rsatilmagan: @username yozing yoki .env ga TELEGRAM_CHANNEL qo'shing")
    if channel.startswith("https://t.me/"):
        channel = channel.removeprefix("https://t.me/").split("/")[0]
    return channel if channel.startswith("@") or channel.lstrip("-").isdigit() else "@" + channel


def _make(prompt: str, quality: str):
    data, source = providers.generate_image_best(prompt, quality)
    path = outbox.new_path("rasm", "png")
    path.write_bytes(data)
    outbox.register(path)
    return data, source, path


def send_photo(chat_id: str, data: bytes, caption: str = "") -> dict:
    if not config.telegram_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN yo'q")
    r = httpx.post(f"https://api.telegram.org/bot{config.telegram_token}/sendPhoto", timeout=120,
                   data={"chat_id": chat_id, "caption": caption[:CAPTION_MAX]},
                   files={"photo": ("rasm.png", data, "image/png")})
    body = r.json() if r.content else {}
    if not body.get("ok"):
        hint = " (botni kanalga administrator qilib qo'shing)" if r.status_code in (400, 403) else ""
        raise RuntimeError(f"Kanalga joylanmadi: {body.get('description') or r.status_code}{hint}")
    return body["result"]


QUALITY = {"type": "string", "enum": ["pro", "standard"],
           "description": "pro - avval eng kuchli modellar (standart), standard - tez/arzon modellar"}


@skill(
    description="Mavzuga oid rasm yaratadi: ulangan eng kuchli modelni tanlaydi (ChatGPT yoki Gemini, avval pro versiya, "
                "ishlamasa standartiga o'tadi). Rasm foydalanuvchiga avtomatik yuboriladi. Prompt'ni inglizcha, "
                "batafsil yoz (uslub, kompozitsiya, rang).",
    params={"prompt": {"type": "string", "description": "Rasm tavsifi (inglizcha, batafsil)"}, "quality": QUALITY},
    required=["prompt"],
)
def make_image(prompt: str, quality: str = "") -> str:
    _, source, path = _make(prompt, quality)
    return f"Rasm tayyor ({source}): {path.name}"


@skill(
    description="Mavzuga oid rasm yaratib, izoh bilan Telegram kanalga joylaydi. Rasm ChatGPT/Gemini (avval pro) bilan "
                "chiziladi; prompt'ni mavzuga mos inglizcha, izohni esa kanal tilida o'zing yoz. "
                "Kanal ko'rsatilmasa .env dagi TELEGRAM_CHANNEL ishlatiladi. Foydalanuvchi tasdiqlaydi.",
    params={
        "topic": {"type": "string", "description": "Post mavzusi"},
        "prompt": {"type": "string", "description": "Rasm tavsifi (inglizcha, batafsil)"},
        "caption": {"type": "string", "description": "Post matni (1024 belgigacha)"},
        "channel": {"type": "string", "description": "Kanal: @username, t.me havolasi yoki -100... ID"},
        "quality": QUALITY,
    },
    required=["topic", "prompt", "caption"],
    dangerous=True,
)
def post_image_to_channel(topic: str, prompt: str, caption: str, channel: str = "", quality: str = "") -> str:
    chat_id = _chat_id(channel)
    data, source, _ = _make(prompt, quality)
    msg = send_photo(chat_id, data, caption)
    return f"«{topic}» rasmli posti {chat_id} kanaliga joylandi (rasm: {source}, post #{msg.get('message_id')})."
