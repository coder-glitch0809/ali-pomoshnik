"""Kontent reja: Instagram statistikasi tahlili -> har bir yo'nalish uchun alohida reja -> kunlik eslatmalar.

Yo'nalishlar (egasining 3 ta faoliyati): targetolog (shaxsiy brend), informatika o'qituvchisi, tashqi reklama agentligi.
data/content_plan.json:
  {"created": "...", "analysis": "...", "items": [{"id", "date", "time", "brand", "platform", "format", "topic",
   "hook", "script", "caption", "hashtags", "done"}]}
Har bir kontent vaqtida (va kun boshida 07:40) Telegram/saytga eslatma keladi. Vaqtlar dars jadvaliga to'qnashmaydi.
"""
import json
import logging
import threading
import time
from datetime import date, datetime, timedelta

from .config import config

log = logging.getLogger("ali.content_plan")

PATH = config.data_dir / "content_plan.json"
STATE = config.data_dir / "content_plan_state.json"
MORNING = "07:40"
BRANDS = {
    "target": "🎯 Targetolog (shaxsiy brend: xizmatlar, keyslar, natijalar, foydali maslahatlar)",
    "ustoz": "💻 Informatika o'qituvchisi (o'quvchilar, ota-onalar va o'qituvchilar uchun foydali kontent)",
    "agentlik": "🏢 Tashqi reklama agentligi (hajmli harflar, bannerlar, vizitkalar, lightbox: ishlar, jarayon, mijozlar)",
}
QUERY_WORDS = ("kontent reja", "kontent plan", "контент план", "контент режа", "content plan")
TODAY_WORDS = ("bugungi kontent", "бугунги контент", "bugun nima joylay", "bugun qanday kontent")

PLAN_TASK = """Sen tajribali SMM strateg va Kontent-meykersan. Egang 3 ta yo'nalishda ishlaydi va har biriga ALOHIDA e'tibor kerak:
{brands}

Instagram statistikasi (bo'lsa - shunga tayan, eng yaxshi ishlagan format, mavzu va vaqtni aniqlab ishlat):
{analytics}

Egang haqida faktlar:
{facts}

Band vaqtlari (dars jadvali - bu vaqtlarga kontent qo'yma, suratga olish ham bo'lmaydi):
{busy}

VAZIFA: {start} dan boshlab {days} kunlik kontent reja tuz. Har kuni 1-3 ta kontent, uchala yo'nalish muvozanatli
(haftasiga har biriga kamida 3 ta). Formatlar: Reels, karusel, post, stories. Joylash vaqti - auditoriya faol
vaqtida (statistikaga qarab; bo'lmasa 12:30-13:30 yoki 19:00-21:00) va band vaqtdan tashqarida.
Har kontent uchun aniq, tayyor ishlatiladigan narsa yoz: hook (birinchi 3 soniya), qisqa ssenariy yoki slaydlar,
caption va 5-10 hashtag.
FAQAT JSON qaytar:
{{"analysis": "statistika tahlili va strategiya (5-10 gap)",
  "items": [{{"date": "YYYY-MM-DD", "time": "HH:MM", "brand": "target|ustoz|agentlik", "platform": "Instagram",
             "format": "Reels|Karusel|Post|Stories", "topic": "...", "hook": "...", "script": "...",
             "caption": "...", "hashtags": "#... #..."}}]}}"""


def load() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _analytics() -> str:
    """Ulangan Instagram akkauntlari statistikasi (bo'lmasa - izoh)."""
    from .skills import instagram
    if not config.ig_accounts:
        return "(Instagram ulanmagan - umumiy eng yaxshi amaliyot va bilimlar asosida tuz)"
    parts = []
    for name in config.ig_accounts:
        try:
            parts.append(f"### @{name}\n{instagram.instagram_analytics(name, 15)[:6000]}\n"
                         f"Davr statistikasi:\n{instagram.instagram_insights(name, 30)[:2000]}")
        except Exception as e:
            parts.append(f"### @{name}: statistika olinmadi ({str(e)[:150]})")
    return "\n\n".join(parts)


def _busy() -> str:
    from . import schedule
    data = schedule.load()
    if not data.get("lessons"):
        return "(jadval yo'q)"
    return "\n".join(f"{schedule.DAYS[d]}: " + ", ".join(f"{l['start']}-{l['end']}" for l in schedule.lessons_on(d, data))
                     for d in range(5) if schedule.lessons_on(d, data))


def generate(days: int = 14) -> dict:
    """Statistikani tahlil qilib, yangi kontent reja tuzadi (avvalgi bajarilmaganlari almashtiriladi)."""
    from . import local_ai
    from .brain import _facts_text
    from .memory import memory
    from .service import _ask_json, brain, knowledge_block
    days = max(3, min(days, 31))
    start = date.today()
    kontent = brain.agents.get("kontent")
    prompt = ((kontent.prompt + "\n\n") if kontent else "") + PLAN_TASK.format(
        brands="\n".join(f"- {k}: {v}" for k, v in BRANDS.items()), analytics=_analytics(), facts=_facts_text(),
        busy=_busy(), start=start.isoformat(), days=days)
    prompt += knowledge_block("Instagram kontent reja Reels hook targetolog reklama agentligi o'qituvchi", "kontent")
    ready = local_ai.connected() if local_ai.access() is True else []
    data = _ask_json(prompt, ready)
    items = []
    for i, it in enumerate(data.get("items") or []):
        try:
            d = datetime.strptime(str(it.get("date")), "%Y-%m-%d").date()
            datetime.strptime(str(it.get("time", "19:00")), "%H:%M")
        except ValueError:
            continue
        if it.get("brand") not in BRANDS:
            it["brand"] = "target"
        items.append({"id": i + 1, "date": d.isoformat(), "time": str(it.get("time", "19:00")),
                      **{k: str(it.get(k, "")).strip() for k in ("brand", "platform", "format", "topic", "hook",
                                                                  "script", "caption", "hashtags")}, "done": False})
    if not items:
        raise RuntimeError("Reja tuzilmadi - AI javob bermadi yoki noto'g'ri format qaytardi")
    items.sort(key=lambda x: (x["date"], x["time"]))
    for n, it in enumerate(items, 1):
        it["id"] = n
    plan = {"created": time.strftime("%Y-%m-%d %H:%M"), "analysis": str(data.get("analysis", "")).strip(), "items": items}
    _save(plan)
    memory.add_knowledge(f"[kontent] Kontent reja {start.isoformat()} ({days} kun)",
                         plan["analysis"] + "\n\n" + "\n".join(f"- {i['date']} {i['time']} [{i['brand']}] {i['format']}: {i['topic']}"
                                                              for i in items))
    return plan


def day_items(d: date | None = None) -> list[dict]:
    d = (d or date.today()).isoformat()
    return [i for i in load().get("items", []) if i["date"] == d]


def item_text(i: dict, full: bool = False) -> str:
    head = f"{'✅' if i.get('done') else '🎬'} #{i['id']} {i['time']} · {BRANDS.get(i['brand'], i['brand']).split(' (')[0]} · {i['format']}: {i['topic']}"
    if not full:
        return head
    return head + "".join(f"\n{label}: {i[k]}" for k, label in (("hook", "🪝 Hook"), ("script", "🎥 Ssenariy"),
                                                                 ("caption", "✍️ Caption"), ("hashtags", "#️⃣")) if i.get(k))


def today_text(full: bool = True) -> str:
    items = day_items()
    if not items:
        return "Bugun kontent rejada narsa yo'q." + ("" if load().get("items") else " Reja tuzish: /kontent_reja")
    return f"📅 Bugungi kontent ({date.today().strftime('%d.%m')}):\n\n" + "\n\n".join(item_text(i, full) for i in items)


def plan_summary() -> str:
    plan = load()
    if not plan.get("items"):
        return "Kontent reja hali tuzilmagan: /kontent_reja"
    by = {}
    for i in plan["items"]:
        by.setdefault(i["date"], []).append(item_text(i))
    lines = [f"🗓 Kontent reja ({plan['created']}):", "", plan.get("analysis", "")[:1500], ""]
    for d, rows in by.items():
        lines.append(f"\n{d}:")
        lines += rows
    return "\n".join(lines)


def mark_done(item_id: int) -> str:
    plan = load()
    for i in plan.get("items", []):
        if i["id"] == item_id:
            i["done"] = True
            _save(plan)
            return f"✅ #{item_id} bajarildi: {i['topic']}"
    return f"#{item_id} topilmadi"


def excel(plan: dict | None = None) -> str:
    """Rejani Excel fayl qilib beradi (avtomatik yuboriladi)."""
    from .skills.documents import make_excel
    plan = plan or load()
    rows = [[i["date"], i["time"], BRANDS.get(i["brand"], i["brand"]).split(" (")[0], i["format"], i["topic"], i["hook"],
             i["script"], i["caption"], i["hashtags"], "ha" if i.get("done") else ""] for i in plan.get("items", [])]
    return make_excel("Kontent reja", [{"name": "Reja", "columns": ["Sana", "Vaqt", "Yo'nalish", "Format", "Mavzu", "Hook",
                                                                     "Ssenariy", "Caption", "Hashtaglar", "Bajarildi"],
                                        "rows": rows}])


def is_query(text: str) -> str | None:
    low = text.lower()
    if any(w in low for w in TODAY_WORDS):
        return "today"
    if any(w in low for w in QUERY_WORDS):
        return "make" if any(w in low for w in ("tuz", "туз", "qil", "кил", "yangi", "янги", "составь", "сделай")) else "show"
    return None


# --- eslatmalar ---
def due_notices(now: datetime | None = None) -> list[str]:
    now = now or datetime.now()
    items = day_items(now.date())
    if not items:
        return []
    today = now.date().isoformat()
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    sent = set(state.get(today, []))
    out = []
    morning = datetime.combine(now.date(), datetime.strptime(MORNING, "%H:%M").time())
    if "morning" not in sent and morning <= now < morning + timedelta(hours=3):
        out.append(today_text(full=False) + "\n\nBatafsil (hook, ssenariy, caption): /kontent")
        sent.add("morning")
    for i in items:
        at = datetime.combine(now.date(), datetime.strptime(i["time"], "%H:%M").time())
        key = f"i{i['id']}"
        if not i.get("done") and key not in sent and at - timedelta(minutes=15) <= now < at + timedelta(minutes=30):
            out.append("📣 Kontent vaqti!\n\n" + item_text(i, full=True) + f"\n\nJoylagach: /tayyor {i['id']}")
            sent.add(key)
    if out:
        STATE.write_text(json.dumps({today: sorted(sent)}), encoding="utf-8")
    return out


def start(notify) -> None:
    if getattr(start, "_started", False):
        return
    start._started = True

    def loop():
        checked = 0.0
        while True:
            try:
                for msg in due_notices():
                    notify(msg)
            except Exception:
                log.exception("Kontent eslatmasi xatosi")
            if time.time() - checked > 6 * 3600:  # Instagram tokeni muddati tugab qolmasin
                checked = time.time()
                try:
                    from .skills import instagram
                    if instagram.refresh_if_needed() == "refreshed":
                        log.info("Instagram tokeni yangilandi")
                except Exception as e:
                    log.warning("Instagram tokenini yangilab bo'lmadi: %s", e)
            time.sleep(30)

    threading.Thread(target=loop, daemon=True, name="content-plan").start()
