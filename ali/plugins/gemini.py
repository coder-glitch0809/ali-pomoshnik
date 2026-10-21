"""Gemini plagini: Google Gemini'dan savol so'rash va rasm yaratish."""
from .. import outbox, providers
from ..config import config
from ..skills import skill
from . import Plugin


def _start() -> tuple[bool, str]:
    if not config.gemini_api_key:
        return False, "GEMINI_API_KEY kiritilmagan"
    return True, f"Ulangan ({config.gemini_chat_model})"


PLUGIN = Plugin(key="gemini", name="Gemini", icon="✦", start=_start,
                description="Google Gemini: ikkinchi fikr, tez javob va rasm yaratish")


@skill(
    description="Savolni Google Gemini'ga beradi va uning javobini qaytaradi. Foydalanuvchi 'Gemini'dan so'ra' desa "
                "yoki ikkinchi fikr kerak bo'lsa ishlat.",
    params={"question": {"type": "string", "description": "Gemini'ga beriladigan to'liq savol"}},
)
def ask_gemini(question: str) -> str:
    answer = providers.gemini_chat("Qisqa, aniq va oddiy tilda javob ber. Savol qaysi tilda bo'lsa, o'sha tilda.",
                                   [], question)
    return answer or "(Gemini bo'sh javob qaytardi)"


@skill(
    description="Gemini bilan matn bo'yicha rasm yaratadi (PNG). Rasm foydalanuvchiga avtomatik yuboriladi.",
    params={"prompt": {"type": "string", "description": "Rasm tavsifi (inglizcha yozilsa sifatliroq)"}},
)
def gemini_image(prompt: str) -> str:
    data = providers.generate_image(prompt)
    path = outbox.new_path("gemini_rasm", "png")
    path.write_bytes(data)
    outbox.register(path)
    return f"Rasm tayyor: {path.name}"
