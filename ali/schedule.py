"""Dars jadvali: aniq saqlash, ertalabki kun rejasi, har darsdan oldin ogohlantirish, so'ralganda yozma jadval.

data/schedule.json:
  {"teacher": "...", "subject": "Informatika", "periods": {"1": ["08:30", "09:20"], ...},
   "lessons": [{"day": 0, "period": 1, "class": "5-A"}, ...],   # day: 0 - Dushanba ... 4 - Juma
   "topics": {"5-A": ["o'tilgan mavzu", ...]}}
Jadvalni rasmdan ham o'qib oladi (parse_image - Pro ilova rasmni ko'radi).
"""
import json
import logging
import re
import threading
import time
from datetime import date, datetime, timedelta

from .config import config

log = logging.getLogger("ali.schedule")

PATH = config.data_dir / "schedule.json"
STATE = config.data_dir / "schedule_state.json"
DAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
WARN_MIN = 10           # darsdan necha daqiqa oldin ogohlantiradi
MORNING = "07:30"       # kun rejasi vaqti
QUERY_WORDS = ("dars jadval", "дарс жадвал", "jadvalim", "жадвалим", "расписани", "darslarim", "дарсларим",
               "qaysi sinf", "кайси синф", "қайси синф", "qaysi dars", "кайси дарс", "bugun dars", "бугун дарс",
               "ertaga dars", "эртага дарс", "kun rejam", "кун режам")
SCHEDULE_PHOTO_WORDS = ("jadval", "жадвал", "расписани", "dars", "дарс")


def load() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(data: dict) -> None:
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    try:  # Obsidian/xotirada ham ko'rinsin
        from .memory import memory
        memory.add_knowledge("[informatika] Dars jadvali", week_text(data))
        memory.set_fact("dars jadvali", "data/schedule.json da saqlangan - " + summary(data))
    except Exception:
        log.exception("Jadval xotiraga yozilmadi")


def summary(data: dict | None = None) -> str:
    data = data or load()
    n = len(data.get("lessons", []))
    classes = sorted({l["class"] for l in data.get("lessons", [])})
    return f"haftasiga {n} ta dars, sinflar: {', '.join(classes)}" if n else "bo'sh"


def lessons_on(day: int, data: dict | None = None) -> list[dict]:
    data = data or load()
    periods = data.get("periods", {})
    out = []
    for l in sorted((l for l in data.get("lessons", []) if l["day"] == day), key=lambda l: l["period"]):
        start, end = periods.get(str(l["period"]), ["?", "?"])
        out.append({**l, "start": start, "end": end, "subject": l.get("subject") or data.get("subject", "")})
    return out


def day_text(d: date, data: dict | None = None) -> str:
    data = data or load()
    items = lessons_on(d.weekday(), data)
    head = f"📅 {DAYS[d.weekday()]}, {d.strftime('%d.%m.%Y')}"
    if not items:
        return f"{head}: dars yo'q 🎉"
    return head + "\n" + "\n".join(f"{l['period']}-soat · {l['start']}-{l['end']} · {l['class']} sinf · {l['subject']}"
                                   for l in items)


def week_text(data: dict | None = None) -> str:
    data = data or load()
    if not data.get("lessons"):
        return "Dars jadvali hali kiritilmagan. Jadval rasmini «dars jadvalim» deb yuboring."
    lines = [f"📚 {data.get('teacher') or 'Dars'} jadvali ({data.get('subject', '')})"]
    for day in range(5):
        items = lessons_on(day, data)
        lines.append(f"\n{DAYS[day]}:" + ("" if items else " dars yo'q"))
        lines += [f"  {l['period']}) {l['start']}-{l['end']} — {l['class']}" for l in items]
    return "\n".join(lines)


def is_query(text: str) -> str | None:
    """'Dars jadvalim', 'bugun qaysi sinflar', 'ertaga darslar' - 'today' | 'tomorrow' | 'week' | None."""
    low = text.lower()
    if not any(w in low for w in QUERY_WORDS) or len(low) > 300:
        return None
    if any(w in low for w in ("ertaga", "эртага", "завтра")):
        return "tomorrow"
    if any(w in low for w in ("bugun", "бугун", "сегодня", "kun rejam", "кун режам")):
        return "today"
    return "week"


def answer(kind: str) -> str:
    today = date.today()
    if kind == "today":
        return day_text(today)
    if kind == "tomorrow":
        return day_text(today + timedelta(days=1))
    return week_text()


def next_lesson(now: datetime | None = None) -> dict | None:
    now = now or datetime.now()
    for l in lessons_on(now.weekday()):
        if l["start"] != "?" and datetime.combine(now.date(), datetime.strptime(l["start"], "%H:%M").time()) > now:
            return l
    return None


# --- rasmdan o'qish ---
PARSE_TASK = """Biriktirilgan rasmda o'qituvchining dars jadvali bor. Uni DIQQAT bilan o'qib, FAQAT JSON qaytar:
{"teacher": "o'qituvchi (sarlavhadan)", "subject": "fan nomi",
 "periods": {"1": ["08:30", "09:20"], "2": [...]},
 "lessons": [{"day": 0, "period": 1, "class": "5-A", "subject": "fan"}]}
day: 0 - Dushanba (Du), 1 - Seshanba (Se), 2 - Chorshanba (Ch), 3 - Payshanba (Pa), 4 - Juma (Ju), 5 - Shanba (Sh).
Bo'sh kataklarni yozma. Har bir to'ldirilgan katakni alohida lesson qil. Sinf nomini aynan yoz (5-A, 2-B...)."""


def parse_image(path: str) -> dict:
    from . import local_ai
    got = local_ai.ask_pro(PARSE_TASK, local_ai.TIMEOUT, None, [path]) if local_ai.access() is True else None
    if not got:
        raise RuntimeError("Rasmni ko'ra oladigan AI (Claude/ChatGPT ilovasi) hozir javob bermadi")
    raw = got[1]
    data = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    lessons = [{"day": int(l["day"]), "period": int(l["period"]), "class": str(l["class"]).strip(),
                **({"subject": l["subject"]} if l.get("subject") else {})}
               for l in data.get("lessons", []) if str(l.get("class", "")).strip() and 0 <= int(l["day"]) <= 6]
    if not lessons:
        raise RuntimeError("Rasmda dars topilmadi")
    old = load()
    new = {"teacher": data.get("teacher") or old.get("teacher", ""), "subject": data.get("subject") or old.get("subject", ""),
           "periods": {str(k): v for k, v in (data.get("periods") or old.get("periods", {})).items()},
           "lessons": lessons, "topics": old.get("topics", {})}
    save(new)
    return new


def is_schedule_photo(caption: str) -> bool:
    low = (caption or "").lower()
    return any(w in low for w in SCHEDULE_PHOTO_WORDS) and any(w in low for w in ("jadval", "жадвал", "расписани"))


# --- ogohlantirishlar ---
def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def due_notices(now: datetime | None = None) -> list[str]:
    """Hozir yuborilishi kerak bo'lgan xabarlar: ertalabki kun rejasi va darsdan oldingi ogohlantirish."""
    now = now or datetime.now()
    data = load()
    if not data.get("lessons") or now.weekday() > 5:
        return []
    today = now.date().isoformat()
    state = _state()
    sent = set(state.get(today, []))
    out = []
    lessons = lessons_on(now.weekday(), data)
    morning = datetime.combine(now.date(), datetime.strptime(MORNING, "%H:%M").time())
    if lessons and "morning" not in sent and morning <= now < morning + timedelta(hours=2):
        out.append("☀️ Bugungi kun rejasi:\n" + day_text(now.date(), data)
                   + "\n\nTaqdimot kerak bo'lsa: /dars SINF (masalan /dars 5-A)")
        sent.add("morning")
    for l in lessons:
        if l["start"] == "?":
            continue
        start = datetime.combine(now.date(), datetime.strptime(l["start"], "%H:%M").time())
        key = f"{l['period']}"
        if key not in sent and start - timedelta(minutes=WARN_MIN) <= now < start:
            mins = max(1, int((start - now).total_seconds() // 60))
            out.append(f"⏰ {mins} daqiqadan keyin dars: {l['class']} sinf · {l['subject']} · "
                       f"{l['start']}-{l['end']} ({l['period']}-soat).\nTaqdimot: /dars {l['class']}")
            sent.add(key)
    if out:
        state = {today: sorted(sent)}  # faqat bugungi holat saqlanadi
        STATE.write_text(json.dumps(state), encoding="utf-8")
    return out


def start(notify) -> None:
    if getattr(start, "_started", False):
        return
    start._started = True

    def loop():
        while True:
            try:
                for msg in due_notices():
                    notify(msg)
            except Exception:
                log.exception("Jadval ogohlantirishi xatosi")
            time.sleep(30)

    threading.Thread(target=loop, daemon=True, name="schedule").start()


def lesson_request(cls: str, topic: str = "") -> str:
    """/dars 5-A [mavzu] uchun Ali'ga beriladigan topshiriq (informatika agenti + API'siz taqdimot)."""
    data = load()
    done = data.get("topics", {}).get(cls, [])[-8:]
    subject = data.get("subject") or "Informatika"
    if topic:
        return (f"{cls} sinf uchun {subject} darsi: «{topic}» mavzusida 50 daqiqalik dars taqdimoti (slaydlar) tayyorla. "
                f"Sinf yoshiga mos, har bir slayd foni dars mavzusiga mos bo'lsin.")
    return (f"{cls} sinf uchun bugungi {subject} darsiga mos mavzuni O'zbekiston maktab dasturi (DTS) bo'yicha tanla "
            f"(bugun {date.today().strftime('%d.%m.%Y')}; avval o'tilgan mavzular: {', '.join(done) or 'noma`lum'}) "
            f"va shu mavzuda 50 daqiqalik dars taqdimoti (slaydlar) tayyorla. Sinf yoshiga mos, har bir slayd foni dars "
            f"mavzusiga mos bo'lsin.")


def remember_topic(cls: str, topic: str) -> None:
    data = load()
    if not data:
        return
    data.setdefault("topics", {}).setdefault(cls, []).append(topic[:120])
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def class_from(text: str) -> str | None:
    m = re.search(r"\b(\d{1,2})\s*[-–]?\s*([A-ZА-ЯЁa-zа-яё])\b", text)
    return f"{m.group(1)}-{m.group(2).upper()}" if m else None
