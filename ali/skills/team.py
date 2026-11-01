"""Ali jamoasi: maslahat kengashi, jamoa nazorati va Telegram guruhlarini tekshirish (faqat o'qish)."""
from . import skill


@skill(
    description=(
        "Maslahat kengashi: murakkab yoki muhim masalada mos 2-3 agent navbat bilan fikr bildiradi (bir-birining "
        "fikrini ko'radi), keyin yakuniy qaror chiqariladi. Hammasi Telegramdagi «Ali jamoasi» guruhiga yoziladi."
    ),
    params={"question": {"type": "string", "description": "Masala to'liq kontekst bilan"},
            "agents": {"type": "array", "items": {"type": "string"},
                       "description": "Ixtiyoriy: qatnashadigan agent kalitlari (bo'lmasa o'zim tanlayman)"}},
    required=["question"],
)
def team_council(question: str, agents: list[str] | None = None) -> str:
    from .. import team_hub
    from ..service import brain
    return team_hub.council(question, brain.agents, agents or None, team_hub_ready_apps())


def team_hub_ready_apps() -> list[str]:
    from .. import local_ai
    return local_ai.connected() if local_ai.access() is True else []


@skill(description="Jamoa nazorati: har agent qancha ishladi, oxirgi ishi qachon, kim maslahatda qatnashmadi, kim bekorchi.")
def team_report() -> str:
    from .. import team_hub
    from ..service import brain
    return team_hub.watch_report(brain.agents)


@skill(
    description=(
        "Telegram guruhini to'liq ko'rib chiqadi (xabarlar, rasm va video kadrlari): asosiy mavzular, egasiga "
        "tegishli topshiriqlar, muammolar, foydali ma'lumot. Foydali narsalar bilimlar bazasiga qo'shiladi."
    ),
    params={"name": {"type": "string", "description": "Guruh nomi (bir qismi ham bo'ladi)"},
            "hours": {"type": "integer", "description": "Necha soatlik xabarlar (standart 72)"}},
    required=["name"],
)
def tg_check_group(name: str, hours: int = 72) -> str:
    from .. import tg_watch
    return tg_watch.check_group(name, max(1, min(hours, 24 * 14)))


@skill(description="Sinf rahbari uchun: guruhlardagi sinfga oid yangi xabarlar, muammolar va dars jadvali (hozir tekshirish).")
def tg_class_review() -> str:
    from .. import tg_watch
    from ..hub import hub
    r = tg_watch.review_class(24, hub.notify)
    if not r["issues"] and not r["schedules"]:
        return "Sinfga oid yangi muammo yoki dars jadvali yo'q." + (f"\n{r['summary']}" if r["summary"] else "")
    return "\n".join([*(f"⚠️ {i.get('group', '')}: {i['what']}" for i in r["issues"]),
                      *(f"📅 Dars jadvali: {s}" for s in r["schedules"])])
