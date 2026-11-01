"""Fonda internetdan izlash (Ali'ning Chrome'i, alohida profil): ma'lumot, namuna va bepul fon musiqasi."""
from . import skill


def _ready() -> list[str]:
    from .. import local_ai
    return local_ai.connected() if local_ai.access() is True else []


@skill(
    description=(
        "Ali'ning Chrome'ida (fonda, alohida profil) Google orqali topshiriqni bajaradi: ma'lumot, trend, namuna "
        "video/kadr g'oyalari, narx va h.k. qidiradi, sahifalarni ochib o'qiydi va natijani qaytaradi. Xavfli tugmalar "
        "(to'lov, yuborish, o'chirish) faqat egasining tasdig'i bilan."
    ),
    params={"goal": {"type": "string", "description": "Nima topish kerak, aniq (masalan: «2026 Reels montaj trendlari»)"}},
)
def google_research(goal: str) -> str:
    from .. import browser
    from ..hub import hub
    return browser.agent(f"Google'da izla va natijani qisqa xulosa qil: {goal}", _ready(),
                         lambda name, args: hub.confirm(name, args, timeout=600), steps=10)


@skill(
    description=(
        "Video uchun BEPUL (reklamada ishlatish mumkin) fon musiqasini internetdan (Pixabay Music) topib kutubxonaga "
        "yuklaydi. mood: cinematic / energetic / calm. Keyin make_music yoki video_music shu trekni ishlatadi."
    ),
    params={"mood": {"type": "string", "enum": ["cinematic", "energetic", "calm"], "description": "Kayfiyat"}},
)
def music_find_online(mood: str = "cinematic") -> str:
    from ..hub import hub
    from .music import find_online
    return find_online(mood, _ready(), lambda name, args: hub.confirm(name, args, timeout=600))
