"""Super miya: GPT va Gemini fikrini so'rash (Claude solishtiradi va yakuniy javobni beradi)."""
from .. import providers
from . import skill


@skill(
    description=(
        "Murakkab yoki muhim savolda boshqa AI modellar (OpenAI GPT va Google Gemini) fikrini parallel so'raydi. "
        "Ularning javoblarini tanqidiy solishtir, xatolarini top va eng yaxshi yakuniy javobni yarat. "
        "Savolni to'liq kontekst bilan yoz - ular suhbat tarixini ko'rmaydi."
    ),
    params={"question": {"type": "string", "description": "To'liq savol va kerakli kontekst"}},
)
def consult_experts(question: str) -> str:
    if not any(providers.available().values()):
        return "Maslahatchi modellar ulanmagan (.env da OPENAI_API_KEY / GEMINI_API_KEY yo'q)."
    answers = providers.ask_all(question)
    return "\n\n".join(f"=== {name} ===\n{text}" for name, text in answers.items())
