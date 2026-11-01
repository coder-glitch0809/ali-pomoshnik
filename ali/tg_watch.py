"""Telegram nazoratchisi (Ulug'bek): guruhlar, botlar va kelgan rasm/videolarni doim kuzatadi (faqat o'qish).

- 5-D sinf: sinf guruhi va maktab guruhlaridagi sinfga oid xabar, rasm va muammolar - egasiga xabar va
  «🏫 5-D sinf» mavzusiga; dars jadvali (расписание) kelsa - sinf guruhiga tashlashni eslatadi.
- Talab bo'yicha: «X guruhini tekshir» / /tekshir X - guruh to'liq ko'rib chiqiladi, foydali bilimlar bazaga.
- Botlar: botlardan kelgan foydali ma'lumot bilimga qo'shiladi.
- Shaxsiy yozishmalarda kelgan rasm va videolar (video - kadri) ko'rib chiqiladi va o'rganiladi.
Hech narsa yuborilmaydi, o'chirilmaydi, a'zo bo'linmaydi. Xabarlar va topilmalar faqat egasiga.
"""
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import config

log = logging.getLogger("ali.tg_watch")

STATE = config.data_dir / "tg_watch.json"
MEDIA = config.data_dir / "inbox" / "tg_watch"
CLASS_NAME = os.getenv("CLASS_NAME", "5-D").strip() or "5-D"
_num, _, _letter = CLASS_NAME.replace("«", "-").replace("»", "").replace(" ", "-").partition("-")
_letters = {"d": "dд", "д": "dд", "a": "aа", "а": "aа", "b": "bб", "б": "bб", "v": "vв", "в": "vв", "g": "gг",
            "г": "gг", "e": "eе", "е": "eе"}.get(_letter.lower(), _letter.lower() or "dд")
# 5-D, 5Д, 5 «Д», 5"D", 5-d sinf... ("5 dan" kabi so'zlar mos kelmaydi)
CLASS_RE = re.compile(rf"(?<!\d){re.escape(_num or '5')}\s*[-«\"'“ʻ‘`]?\s*[{_letters}](?![a-zа-яёўқғҳ])", re.I)
TEACHER_WORDS = ("sinf rahbar", "синф раҳбар", "синф рахбар", "классный руковод", "классн. рук", "кл. рук")
SCHEDULE_WORDS = ("расписани", "dars jadval", "дарс жадвал", "jadval", "жадвал", "raspisaniye", "raspisanie")
CLASS_HOURS = 1     # sinf guruhlari tekshiruvi
OTHER_HOURS = 3     # botlar va kelgan rasm/videolar
MAX_PHOTOS = 6

CLASS_TASK = """Egam ({owner}) maktabda {cls} sinf rahbari. Quyida Telegram guruhlaridan {cls} sinfga oid xabarlar
(rasmlar tavsifi [rasm: ...] ko'rinishida). Sinf rahbari bilishi va harakat qilishi kerak bo'lgan narsalarni ajrat.
FAQAT JSON qaytar:
{{"issues": [{{"group": "guruh", "who": "kim yozgan", "what": "muammo yoki talab (aniq)", "action": "egam nima qilishi kerak"}}],
  "summary": "2-5 gapda nima bo'lyapti"}}
Muammo: o'quvchi kelmagan/kech qolgan, to'lov qilmagan, xulq, telefon olib qo'yilgan, ota-ona chaqirilgan,
hujjat/hisobot so'ralgan, davomat, direktor topshirig'i, tadbir. Bo'sh gap va tabriklarni yozma. Taxmin qilma.

Xabarlar:
{messages}"""

GROUP_TASK = """Egam ({owner}) so'radi: «{group}» guruhini to'liq ko'rib chiq (oxirgi {hours} soat).
Quyida guruh xabarlari (rasmlar tavsifi [rasm: ...]). Qisqa va aniq hisobot ber (o'zbek tilida):
1) Asosiy mavzular va qarorlar; 2) Egamga tegishli topshiriq, muddat va savollar; 3) Muammolar;
4) Foydali ma'lumot (havola, fayl, qoida). Bo'sh gaplarni tashla. Taxmin qilma.

Xabarlar:
{messages}"""


def _state() -> dict:
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    STATE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def is_class(text: str) -> bool:
    low = (text or "").lower()
    return bool(CLASS_RE.search(text or "")) or any(w in low for w in TEACHER_WORDS)


def is_schedule(text: str) -> bool:
    low = (text or "").lower()
    return any(w in low for w in SCHEDULE_WORDS)


def _who(m) -> str:
    s = getattr(m, "sender", None)
    if s is None:
        return "?"
    name = " ".join(x for x in (getattr(s, "first_name", None), getattr(s, "last_name", None)) if x)
    return name or getattr(s, "title", None) or "?"


def describe_image(path: str, hint: str = "") -> str:
    """Rasmni qisqa tavsiflaydi (jadval, ro'yxat, hujjat bo'lsa - matnini ham o'qiydi)."""
    from . import local_ai, providers
    prompt = ("Rasmni o'zbek tilida 1-4 gapda tavsifla. Unda jadval, ro'yxat, hujjat yoki e'lon bo'lsa - asosiy "
              "matnini (sinf, fan, ism, sana, raqam) aniq yoz. Dars jadvali bo'lsa «DARS JADVALI» deb boshla."
              + (f" Kontekst: {hint[:300]}" if hint else ""))
    try:
        if config.gemini_api_key:
            return providers.gemini_ask(prompt, [path])
        if local_ai.access() is True and local_ai.connected():
            got = local_ai.ask_pro(prompt, local_ai.TIMEOUT, None, [path])
            return got[1] if got else ""
    except Exception as e:
        log.info("Rasm tavsiflanmadi: %s", e)
    return ""


# ---------- Telegram'dan yig'ish ----------
def collect_groups(hours: float = 24, only: int | None = None, everything: bool = False,
                   per_dialog: int = 200, photos: int = MAX_PHOTOS) -> list[dict]:
    """Guruh xabarlari. only - bitta guruh id si (to'liq tekshirish). Aks holda sinfga oid va jadval xabarlari.
    everything=True - guruhdagi barcha matnlar (talab bo'yicha tekshirish)."""
    from . import team_hub, tg_account
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    team = team_hub.chat_id()
    MEDIA.mkdir(parents=True, exist_ok=True)

    async def go(client):
        out, left = [], photos
        async for d in client.iter_dialogs():
            if not d.is_group or d.date is None or d.date < since:
                continue
            if only is not None and d.id != only:
                continue
            if team and d.id == team:  # o'zimizning jamoa guruhi
                continue
            class_group = is_class(d.name)
            rows = []
            async for m in client.iter_messages(d.id, limit=per_dialog):
                if m.date < since:
                    break
                text = m.text or ""
                relevant = everything or class_group or is_class(text) or is_schedule(text)
                if not relevant:
                    continue
                photo = None
                media = m.photo or m.video or getattr(m, "video_note", None)
                if media and left > 0 and (everything or class_group or is_class(text) or is_schedule(text)):
                    path = MEDIA / f"{abs(d.id)}_{m.id}.jpg"
                    try:  # video - faqat kadri (thumb), rasm - o'zi
                        got = await client.download_media(m, file=str(path), thumb=-1 if not m.photo else None)
                        photo = str(got) if got else None
                        left -= 1 if photo else 0
                    except Exception as e:
                        log.info("Media yuklanmadi: %s", e)
                if text or photo:
                    rows.append({"id": m.id, "who": _who(m), "when": m.date.astimezone().strftime("%m-%d %H:%M"),
                                 "text": text[:1500], "photo": photo, "video": bool(m.video)})
            if rows:
                out.append({"group": d.name, "id": d.id, "class": class_group, "messages": list(reversed(rows))})
        return out
    return tg_account._run(go, 900)


def _render(groups: list[dict], describe=None) -> tuple[str, list[str]]:
    """Xabarlar matni (rasmlar tavsifi bilan) va topilgan dars jadvallari."""
    describe = describe or describe_image
    parts, schedules = [], []
    for g in groups:
        lines = []
        for m in g["messages"]:
            note = ""
            if m.get("photo"):
                desc = describe(m["photo"], m["text"])
                note = f" [{'video kadri' if m.get('video') else 'rasm'}: {desc or 'tavsiflanmadi'}]"
                if desc and is_schedule(desc):
                    schedules.append(f"«{g['group']}»: {m['who']} ({m['when']}) - rasm")
            if m["text"] and is_schedule(m["text"]):
                schedules.append(f"«{g['group']}»: {m['who']} ({m['when']}) - {m['text'][:80]}")
            lines.append(f"[{m['when']}] {m['who']}: {m['text']}{note}")
        parts.append(f"### {g['group']}\n" + "\n".join(lines))
    return "\n\n".join(parts), schedules


def _ready_apps() -> list[str]:
    from . import local_ai
    return local_ai.connected() if local_ai.access() is True else []


def review_class(hours: float = 24, notify=None, remind=None, ask_json=None, groups=None) -> dict:
    """Sinf rahbari uchun: yangi (oldin ko'rilmagan) sinfga oid xabarlar, muammolar va dars jadvali."""
    from . import team_hub
    from .memory import memory
    state = _state()
    seen = state.setdefault("seen", {})
    groups = collect_groups(hours) if groups is None else groups
    fresh = []
    for g in groups:
        msgs = [m for m in g["messages"] if m["id"] > seen.get(str(g["id"]), 0)]
        if msgs:
            fresh.append({**g, "messages": msgs})
            seen[str(g["id"])] = max(m["id"] for m in g["messages"])
    if not fresh:
        _save(state)
        return {"issues": [], "schedules": [], "summary": ""}
    text, schedules = _render(fresh)
    data = {"issues": [], "summary": ""}
    if any(is_class(g["group"]) or any(is_class(m["text"]) for m in g["messages"]) for g in fresh):
        try:
            from .service import _ask_json
            data = (ask_json or (lambda p: _ask_json(p, _ready_apps())))(
                CLASS_TASK.format(owner=config.user_name, cls=CLASS_NAME, messages=text[:50000]))
        except Exception as e:
            log.warning("Sinf xabarlari tahlil qilinmadi: %s", e)
            data = {"issues": [], "summary": text[:1500]}
    issues = [i for i in data.get("issues") or [] if str(i.get("what", "")).strip()]
    lines = [f"⚠️ {i.get('group', '')}: {i['what']}" + (f" — {i.get('who')}" if i.get("who") else "")
             + (f"\n   👉 {i['action']}" if i.get("action") else "") for i in issues]
    for s in schedules:  # dars jadvali keldi - sinf guruhiga tashlashni eslatamiz
        reminder = f"📅 Dars jadvali keldi ({s}). {CLASS_NAME} sinf guruhiga tashlashni unutmang!"
        (remind or (lambda t: memory.add_reminder(t, datetime.now() + timedelta(minutes=1))))(reminder)
    report = (f"🏫 {CLASS_NAME} sinf — yangi xabarlar\n\n" + (str(data.get("summary", "")).strip() + "\n\n" if data.get("summary") else "")
              + ("\n".join(lines) if lines else "Muammo topilmadi.")
              + ("\n\n📅 Dars jadvali:\n" + "\n".join(schedules) if schedules else ""))
    team_hub.post("sinf", report)
    if notify and (issues or schedules):
        notify(report[:3500])
    _save(state)
    return {"issues": issues, "schedules": schedules, "summary": str(data.get("summary", ""))}


def check_group(name: str, hours: float = 72, ask=None) -> str:
    """Talab bo'yicha: guruhni to'liq ko'rib chiqadi, hisobot beradi va foydali narsalarni bilimga qo'shadi."""
    from . import ingest, team_hub, tg_account
    items = tg_account.channels()
    ch = tg_account._match(items, name)
    if ch is None:
        raise RuntimeError(f"«{name}» topilmadi. Bor guruhlar: " + ", ".join(c["title"] for c in items[:30]))
    groups = collect_groups(hours, only=ch["id"], everything=True)
    if not groups:
        return f"«{ch['title']}»: oxirgi {int(hours)} soatda xabar yo'q."
    text, schedules = _render(groups)
    prompt = GROUP_TASK.format(owner=config.user_name, group=ch["title"], hours=int(hours), messages=text[:60000])
    try:
        report = ask(prompt) if ask else team_hub.agent_answer("telegram_nazoratchi", prompt, _ready_apps())
    except Exception as e:
        log.warning("Guruh hisoboti tuzilmadi: %s", e)
        report = ""
    report = report or providers_fallback(text)
    try:
        ingest.learn(f"Guruh: {ch['title']} ({time.strftime('%Y-%m-%d')})", text[:20000], f"Telegram guruh: {ch['title']}")
    except Exception as e:
        log.info("Guruhdan bilim olinmadi: %s", e)
    out = f"🔎 «{ch['title']}» — oxirgi {int(hours)} soat\n\n{report}" + (
        "\n\n📅 Dars jadvali topildi:\n" + "\n".join(schedules) if schedules else "")
    team_hub.post("telegram", out)
    team_hub.touch("telegram_nazoratchi")
    return out


def providers_fallback(text: str) -> str:
    """AI javob bermasa - oxirgi xabarlarning o'zi."""
    return "AI hozir band, oxirgi xabarlar:\n" + text[-2500:]


def review_bots_and_media(hours: float = 24) -> dict:
    """Botlardan kelgan ma'lumot va shaxsiy yozishmalarda kelgan rasm/videolar - o'rganiladi."""
    from . import ingest, team_hub, tg_account
    state = _state()
    seen = state.setdefault("seen_private", {})
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    MEDIA.mkdir(parents=True, exist_ok=True)

    async def go(client):
        bots, media = [], []
        async for d in client.iter_dialogs():
            if not d.is_user or d.date is None or d.date < since:
                continue
            is_bot = bool(getattr(d.entity, "bot", False))
            last = seen.get(str(d.id), 0)
            texts, top = [], last
            async for m in client.iter_messages(d.id, limit=60, min_id=last):
                top = max(top, m.id)
                if m.out or m.date < since:
                    continue
                if is_bot and m.text:
                    texts.append(m.text[:3000])
                if (m.photo or m.video) and len(media) < MAX_PHOTOS:
                    path = MEDIA / f"p{d.id}_{m.id}.jpg"
                    try:
                        got = await client.download_media(m, file=str(path), thumb=-1 if not m.photo else None)
                        if got:
                            media.append({"who": d.name, "path": str(got), "text": m.text or "", "video": bool(m.video)})
                    except Exception as e:
                        log.info("Media yuklanmadi: %s", e)
            seen[str(d.id)] = top
            if texts:
                bots.append({"bot": d.name, "text": "\n\n".join(reversed(texts))})
        return bots, media

    bots, media = tg_account._run(go, 900)
    learned = []
    for b in bots:
        if len(b["text"]) < 200:  # qisqa javoblar (tugmalar, salom) - o'rganishga arzimaydi
            continue
        try:
            r = ingest.learn(f"Bot: {b['bot']}", b["text"], f"Telegram bot: {b['bot']}")
            learned.append(f"🤖 {b['bot']} → {r['icon']} {r['name']}: {r['saved']} ta bilim")
        except Exception as e:
            log.info("Bot ma'lumoti o'rganilmadi: %s", e)
    for m in media:
        desc = describe_image(m["path"], m["text"])
        if not desc:
            continue
        try:
            kind = "video kadri" if m["video"] else "rasm"
            r = ingest.learn(f"{m['who']} yuborgan {kind}", f"{desc}\n{m['text']}".strip(), f"Telegram: {m['who']}",
                             [m["path"]])
            learned.append(f"🖼 {m['who']} ({kind}) → {r['icon']} {r['name']}: {desc[:120]}")
        except Exception as e:
            log.info("Rasm o'rganilmadi: %s", e)
    _save(state)
    if learned:
        team_hub.post("telegram", "🔎 Botlar va kelgan rasm/videolardan o'rganildi:\n" + "\n".join(learned))
        team_hub.touch("telegram_nazoratchi")
    return {"bots": len(bots), "media": len(media), "learned": learned}


def tick(notify=None, now: float | None = None) -> None:
    """Avtopilotdan (5 daqiqada bir): sinf - har soat, botlar va rasmlar - 3 soatda bir."""
    from . import tg_account
    if not tg_account.configured():
        return
    now = now or time.time()
    state = _state()
    if now - state.get("class_at", 0) >= CLASS_HOURS * 3600:
        state["class_at"] = now
        _save(state)
        try:
            review_class(24, notify)
        except Exception as e:
            log.warning("Sinf tekshiruvi bajarilmadi: %s", e)
    state = _state()
    if now - state.get("other_at", 0) >= OTHER_HOURS * 3600:
        state["other_at"] = now
        _save(state)
        try:
            review_bots_and_media(OTHER_HOURS * 2)
        except Exception as e:
            log.warning("Botlar/rasmlar tekshiruvi bajarilmadi: %s", e)
