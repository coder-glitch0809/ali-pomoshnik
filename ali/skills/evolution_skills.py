"""Agentlarni rivojlantirish: sog'lik tekshiruvi, tajriba qo'shish, oldingi holatga qaytarish."""
import json

from . import REGISTRY, skill


def _brain():
    from ..service import brain  # kech import: service miyani yaratganda skills allaqachon yuklangan bo'ladi
    return brain


@skill(
    description=(
        "Agent sog'lig'ini tekshiradi (API'siz): mavjud bo'lmagan/taqiqlangan vositalar, so'nggi 7 kundagi ishlar va "
        "xatolar, o'rganish xatolari, bilimlar soni, tajriba saboqlari soni va 0-100 ball. key bo'sh bo'lsa - hamma agentlar."
    ),
    params={"key": {"type": "string", "description": "Agent kaliti (ixtiyoriy)"}},
    required=[],
)
def agent_health(key: str = "") -> str:
    from .. import agents, evolution
    team = agents.load()
    keys = [key.strip().lower()] if key.strip() else list(team)
    return json.dumps([evolution.health(REGISTRY, k, team) for k in keys], ensure_ascii=False, indent=1)


@skill(
    description=(
        "Agentni rivojlantiradi: 'Tajriba' bo'limiga o'rganilgan saboqlar (lessons, 1-3 ta), bilim bo'shlig'ini "
        "to'ldiradigan o'rganish mavzulari (learn, 0-2 ta) qo'shadi, vositalarni qo'shadi/olib tashlaydi (faqat tasdiqsiz "
        "ishlaydigan vositalar). Asosiy ko'rsatma o'zgarmaydi, eski nusxa saqlanadi."
    ),
    params={
        "key": {"type": "string", "description": "Agent kaliti"},
        "lessons": {"type": "array", "items": {"type": "string"}, "description": "Qisqa, amaliy saboqlar"},
        "learn": {"type": "array", "items": {"type": "string"}, "description": "Yangi o'rganish mavzulari"},
        "add_tools": {"type": "array", "items": {"type": "string"}, "description": "Qo'shiladigan vositalar"},
        "remove_tools": {"type": "array", "items": {"type": "string"}, "description": "Olib tashlanadigan vositalar"},
    },
    required=["key"],
)
def improve_agent(key: str, lessons: list | None = None, learn: list | None = None,
                  add_tools: list | None = None, remove_tools: list | None = None) -> str:
    from .. import evolution
    return evolution.improve(REGISTRY, key, lessons, learn, add_tools, remove_tools)


@skill(
    description="Agentni oxirgi avtomatik o'zgarishdan oldingi holatiga qaytaradi (rivojlantirish yoqmagan bo'lsa).",
    params={"key": {"type": "string", "description": "Agent kaliti"}},
)
def rollback_agent(key: str) -> str:
    from .. import evolution
    return evolution.rollback(key)


@skill(
    description=(
        "Hozir bitta agentni (yoki key bo'sh bo'lsa hammasini) tekshirib, xatosini tuzatib, Murabbiy orqali rivojlantiradi. "
        "Bir necha daqiqa davom etadi va API sarflaydi."
    ),
    params={"key": {"type": "string", "description": "Agent kaliti (ixtiyoriy)"}},
    required=[],
)
def improve_agents_now(key: str = "") -> str:
    from .. import evolution
    brain = _brain()
    keys = [key.strip().lower()] if key.strip() else list(brain.agents)
    results = {}
    for k in keys:
        try:
            results[k] = evolution.run_cycle_for(brain, k, {})
        except Exception as e:
            results[k] = {"status": "error", "issues": [str(e)[:200]]}
    return evolution.daily_report(results, brain.agents)
