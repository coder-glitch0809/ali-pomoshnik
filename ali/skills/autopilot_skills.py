"""Avtopilotni qo'lda ishga tushirish: agentni hozir o'qitish, treyding loyihalarini hozir tekshirish."""
from . import skill


def _brain():
    from ..service import brain  # kech import: service miyani yaratganda skills allaqachon yuklangan bo'ladi
    return brain


@skill(
    description=(
        "Agentni hozir o'z-o'zini o'qitishga yuboradi: u o'z 'o'rganish' mavzulari bo'yicha internetdan yangiliklarni "
        "o'rganib, bilimlar bazasiga yozadi. Bir necha daqiqa davom etadi."
    ),
    params={"agent": {"type": "string", "description": "Agent kaliti (masalan treyder)"}},
)
def learn_now(agent: str) -> str:
    from ..autopilot import learn
    return learn(_brain(), agent.strip().lower())


@skill(
    description=(
        "Treyding loyihalarini hozir tekshiradi (kompyuter, GitHub, Vercel): git holati, CI va deploy xatolari. "
        "Faqat tekshiradi, hech narsani o'zgartirmaydi."
    ),
)
def check_trading_projects() -> str:
    from ..autopilot import watch
    return watch(_brain())
