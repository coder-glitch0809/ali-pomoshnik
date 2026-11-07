"""Ali jamoasi - Telegram'dagi forum-guruh: har agentning o'z mavzusi (topic), Ali'ning alohida joyi, maslahat kengashi.

Yaratish: /jamoa (yoki «jamoa guruhini och»). Shaxsiy akkaunt (Telethon) forum-guruh yaratadi va Ali botini admin
qiladi; keyin bot mavzularni o'zi ochadi va yozadi (Bot API). Guruhda faqat egasi va bot bo'ladi.

Mavzular:
  👑 Ali - eng muhim topilmalar, kunlik nazorat hisoboti (bekorchi agentlar ham shu yerda)
  🤝 Maslahat kengashi - agentlar bir-biri bilan maslahatlashadi, Ali xulosa qiladi
  🔎 Telegram nazorati - kanal, guruh, bot va yozishmalarni tekshirish natijalari
  🏫 5-D sinf - sinf rahbariga oid xabarlar, muammolar, dars jadvali
  har bir agent - u nima qilyapti (vazifa va natija); treyderda signallar va treyding yangiliklari
Egasi agent mavzusiga yozsa - o'sha agent javob beradi; Maslahat mavzusiga yozsa - kengash yig'iladi.
"""
import json
import logging
import queue
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx

from .config import config

log = logging.getLogger("ali.team_hub")

STATE = config.data_dir / "team_hub.json"
LOCK = threading.RLock()
TITLE = "🤖 Ali jamoasi"
ABOUT = "Ali va uning agentlari: har agentning o'z mavzusi, maslahat kengashi va nazorat."
FIXED = {"ali": "👑 Ali — asosiy", "maslahat": "🤝 Maslahat kengashi", "telegram": "🔎 Telegram nazorati",
         "sinf": "🏫 5-D sinf"}
# Agentlarning ismlari (yangi agentga POOL dan bo'sh ism beriladi)
NAMES = {"treyder": "Sardor", "dizayner": "Dilnoza", "dasturchi": "Jasur", "kontent": "Sevara",
         "video_montajchi": "Otabek", "informatika": "Nodira", "office": "Kamola", "murabbiy": "Bobur",
         "huquqshunos": "Farrux", "ingliz_tili": "Malika", "rus_tili": "Zarina", "yangiliklar": "Akmal",
         "ai_agentlar": "Temur", "telegram_nazoratchi": "Ulug'bek"}
POOL = ["Javohir", "Shahzod", "Madina", "Aziz", "Gulnoza", "Sherzod", "Lola", "Rustam", "Nilufar", "Doston",
        "Mohira", "Islom", "Feruza", "Bekzod", "Shahlo", "Anvar"]
COLORS = [0x6FB9F0, 0xFFD67E, 0xCB86DB, 0x8EEE98, 0xFF93B2, 0xFB6F5F]
IDLE_DAYS = 3        # shuncha kun hech ish qilmagan agent - "bekorchi"
REPORT_AT = "21:30"  # kunlik nazorat hisoboti (Ali mavzusiga)
MAX_MSG = 4000


# ---------- holat ----------
def _load() -> dict:
    try:
        with LOCK:
            data = json.loads(STATE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("topics", {})
            data.setdefault("names", {})
            data.setdefault("activity", {})
            return data
    except (OSError, ValueError):
        pass
    return {"topics": {}, "names": {}, "activity": {}}


def _save(data: dict) -> None:
    with LOCK:
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)


def chat_id() -> int | None:
    return _load().get("chat_id")


def ready() -> bool:
    return bool(config.telegram_token and chat_id())


# ---------- ismlar ----------
def name_of(key: str) -> str:
    """Agentning ismi (masalan Sardor). Yangi agentga bo'sh ism beriladi va eslab qolinadi."""
    if key == "ali":
        return config.assistant_name
    with LOCK:
        data = _load()
        if key in data["names"]:
            return data["names"][key]
        if key in NAMES:
            return NAMES[key]
        used = set(data["names"].values()) | set(NAMES.values())
        name = next((n for n in POOL if n not in used), f"Agent-{len(data['names']) + 1}")
        data["names"][key] = name
        _save(data)
        return name


def label(key: str, agents: dict | None = None) -> str:
    """«📈 Sardor (Treyder)» - guruhdagi imzo."""
    if key == "ali":
        return f"👑 {config.assistant_name}"
    a = (agents or {}).get(key)
    return f"{a.icon} {name_of(key)} ({a.name})" if a else f"🤖 {name_of(key)}"


def topic_title(key: str, agents: dict | None = None) -> str:
    return FIXED.get(key) or label(key, agents)


# ---------- Bot API ----------
def _api(method: str, **data):
    url = f"https://api.telegram.org/bot{config.telegram_token}/{method}"
    for attempt in range(3):
        r = httpx.post(url, json=data, timeout=40)
        body = r.json()
        if body.get("ok"):
            return body["result"]
        wait = (body.get("parameters") or {}).get("retry_after")
        if wait and attempt < 2:  # juda tez yozildi - Telegram aytgancha kutamiz
            time.sleep(min(int(wait), 60) + 1)
            continue
        raise RuntimeError(f"Telegram: {body.get('description', r.status_code)}")


def ensure_topic(key: str, agents: dict | None = None) -> int | None:
    """Mavzu (topic) id; yo'q bo'lsa ochadi."""
    data = _load()
    cid = data.get("chat_id")
    if not cid:
        return None
    if key in data["topics"]:
        return data["topics"][key]
    color = COLORS[len(data["topics"]) % len(COLORS)]
    res = _api("createForumTopic", chat_id=cid, name=topic_title(key, agents)[:128], icon_color=color)
    with LOCK:
        data = _load()
        data["topics"][key] = res["message_thread_id"]
        _save(data)
    return res["message_thread_id"]


def topic_key(thread_id: int | None) -> str | None:
    """Mavzu id -> kalit (agent yoki ali/maslahat/telegram/sinf)."""
    if thread_id is None:
        return None
    return next((k for k, v in _load()["topics"].items() if v == thread_id), None)


_CYR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюяўқғҳ",
                ["a", "b", "v", "g", "d", "e", "yo", "j", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u",
                 "f", "x", "ts", "ch", "sh", "sh", "", "i", "", "e", "yu", "ya", "o", "q", "g", "h"]))
EXTRA = {"kontent": ("kontent meyker", "kontent maker", "kontentchi", "kontent"), "dasturchi": ("programmist", "dasturchi"),
         "video_montajchi": ("montajchi", "montaj", "oybek", "ойбек"), "telegram_nazoratchi": ("nazoratchi",), "dizayner": ("dizayner", "dizaynir"),
         "yangiliklar": ("kutubxonachi",), "ingliz_tili": ("ingliz",), "rus_tili": ("rus tili",)}


def _norm(text: str) -> str:
    """Kirill -> lotin, kichik harf, tutuq belgisiz - «Контент мейкер» ham «kontent meyker» bo'ladi."""
    text = "".join(_CYR.get(ch, ch) for ch in (text or "").lower())
    return re.sub(r"['ʻ‘’`]", "", text)


def addressed(text: str, agents: dict) -> str | None:
    """Guruhda kimga yozilgani: matn boshida (birinchi 6 so'z) agent ismi yoki kasbi - «Sevara, ...», «Kontent meyker
    post yoz», «@dasturchi ...», «Dasturchiga ayt ...». Topilmasa None - Ali o'zi javob beradi/taqsimlaydi."""
    head = " ".join(_norm(text).split()[:6])
    head = re.sub(r"^\W*(ali|али)\b\W*", "", head)
    best = None
    for key, a in agents.items():
        names = {_norm(name_of(key)), _norm(a.name), key.replace("_", " "), *EXTRA.get(key, ())}
        for n in filter(None, names):
            m = re.search(rf"(^|[\s@,]){re.escape(n)}", head)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), key)
    return best[1] if best else None


def _chunks(text: str) -> list[str]:
    text = text.strip() or "…"
    out = []
    while text:
        cut = text[:MAX_MSG]
        if len(text) > MAX_MSG and "\n" in cut[MAX_MSG // 2:]:
            cut = cut[:cut.rindex("\n")]
        out.append(cut)
        text = text[len(cut):].lstrip()
    return out


def _send(key: str, text: str, agents: dict | None = None) -> None:
    cid = chat_id()
    for attempt in range(2):
        thread = ensure_topic(key, agents)
        try:
            for part in _chunks(text):
                _api("sendMessage", chat_id=cid, message_thread_id=thread, text=part, disable_web_page_preview=True)
            return
        except RuntimeError as e:
            if attempt == 0 and "thread" in str(e).lower():  # mavzu o'chirilgan - qayta ochamiz
                with LOCK:
                    data = _load()
                    data["topics"].pop(key, None)
                    _save(data)
                continue
            raise


_queue: "queue.Queue[tuple[str, str, dict | None]]" = queue.Queue(maxsize=500)
_worker: threading.Thread | None = None


def _work():
    while True:
        key, text, agents = _queue.get()
        try:
            _send(key, text, agents)
        except Exception as e:
            log.warning("Jamoa guruhiga yozilmadi (%s): %s", key, e)
        time.sleep(1.2)  # guruhga daqiqasiga ~20 xabardan oshmasin


def post_video(key: str, path: str, caption: str = "", agents: dict | None = None) -> bool:
    """Mavzuga video (o'lchami bilan - Telegram kesib ko'rsatmasin). Fon oqimidan chaqiriladi."""
    if not ready() or not Path(path).is_file():
        return False
    from .skills.video_edit import info
    try:
        thread, i = ensure_topic(key, agents), info(Path(path))
        with open(path, "rb") as fh:
            r = httpx.post(f"https://api.telegram.org/bot{config.telegram_token}/sendVideo",
                           data={"chat_id": chat_id(), "message_thread_id": thread, "caption": caption[:1000],
                                 "width": i["width"], "height": i["height"], "duration": int(round(i["duration"])),
                                 "supports_streaming": "true"}, files={"video": (Path(path).name, fh)}, timeout=300)
        return bool(r.json().get("ok"))
    except Exception as e:
        log.warning("Jamoa guruhiga video yuborilmadi (%s): %s", key, e)
        return False


SCORE = re.compile(r"(\d{1,2}(?:[.,]\d)?)\s*/\s*10|baho\D{0,25}?(\d{1,2}(?:[.,]\d)?)\b", re.I)


def score_of(decision: str) -> float | None:
    """Ali qaroridagi Instagram bahosi (1-10)."""
    m = SCORE.search(decision or "")
    if not m:
        return None
    value = float((m.group(1) or m.group(2)).replace(",", "."))
    return value if 0 <= value <= 10 else None


def review_video(path: str, about: str, agents: dict, ready_apps: list[str] | None = None) -> tuple[str, float | None]:
    """Har tayyor video Maslahat kengashi muhokamasidan o'tadi: video mavzuga qo'yiladi, Kontent-meyker, Montajchi va
    Dasturchi Instagram uchun baholaydi, Ali qaror va 1-10 baho chiqaradi. (qaror, baho)."""
    post_video("maslahat", path, f"🎬 Muhokamaga: {about[:900]}", agents)
    try:
        decision = council(f"Shu tayyor Reels videoni Instagram uchun baholang va kanalga joylashga arziydimi ayting. "
                           f"Video haqida: {about}", agents, None, ready_apps)
    except Exception as e:
        log.warning("Video muhokamasi bo'lmadi: %s", e)
        return "", None
    return decision, score_of(decision)


def post(key: str, text: str, agents: dict | None = None) -> bool:
    """Mavzuga xabar (fonda, navbat bilan). Guruh hali yaratilmagan bo'lsa - hech narsa qilmaydi."""
    global _worker
    if not ready() or not text.strip():
        return False
    with LOCK:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, daemon=True, name="team-hub")
            _worker.start()
    try:
        _queue.put_nowait((key, text, agents))
        return True
    except queue.Full:
        log.warning("Jamoa navbati to'la - xabar tashlab yuborildi")
        return False


# ---------- faoliyat ----------
def touch(key: str, kind: str = "ish") -> None:
    with LOCK:
        data = _load()
        rec = data["activity"].setdefault(key, {"total": 0})
        rec["last"] = time.time()
        rec["total"] = rec.get("total", 0) + 1
        rec[kind] = rec.get(kind, 0) + 1
        _save(data)


def feed(key: str, task: str, result: str, agents: dict | None = None) -> None:
    """Agent ish bajardi - faoliyat yoziladi va uning mavzusiga «vazifa → natija» chiqadi."""
    if not key or key == "ali":
        return
    touch(key)
    result = (result or "").strip()
    if ready() and result:
        post(key, f"📝 Vazifa: {task.strip()[:600]}\n\n{result[:3500]}", agents)


def skipped(key: str) -> None:
    """Agent maslahatda qatnashmadi (javob bermadi)."""
    with LOCK:
        data = _load()
        rec = data["activity"].setdefault(key, {"total": 0})
        rec["skips"] = rec.get("skips", 0) + 1
        _save(data)


def idle_agents(agents: dict, now: float | None = None) -> list[str]:
    """IDLE_DAYS dan beri ish qilmagan agentlar (guruh ochilganidan beri hisoblanadi)."""
    now = now or time.time()
    data = _load()
    since = data.get("created", now)
    limit = IDLE_DAYS * 86400
    return [k for k in agents if now - data["activity"].get(k, {}).get("last", since) >= limit]


def watch_report(agents: dict, now: float | None = None) -> str:
    """Ali'ning nazorati: kim qancha ishladi, kim maslahatda qatnashmadi, kim bekorchi."""
    now = now or time.time()
    data = _load()
    idle = set(idle_agents(agents, now))
    rows = []
    for key in agents:
        rec = data["activity"].get(key, {})
        last = rec.get("last")
        when = datetime.fromtimestamp(last).strftime("%d.%m %H:%M") if last else "hali ish qilmagan"
        mark = "😴" if key in idle else ("⚠️" if rec.get("skips", 0) >= 2 else "✅")
        rows.append(f"{mark} {label(key, agents)}: {rec.get('total', 0)} ta ish, oxirgisi {when}"
                    + (f", maslahatda qatnashmadi: {rec['skips']}" if rec.get("skips") else ""))
    text = "👑 Ali nazorati — jamoa faoliyati\n\n" + "\n".join(rows)
    if idle:
        text += (f"\n\n😴 Bekorchi ({IDLE_DAYS}+ kun ish yo'q): " + ", ".join(name_of(k) for k in idle)
                 + "\nUlarga o'z sohasidan vazifa beraman yoki Murabbiy qayta o'qitadi.")
    return text


# ---------- agent javobi ----------
def agent_answer(key: str | None, text: str, ready_apps: list[str] | None = None) -> str:
    """Agent (yoki Ali) o'z ko'rsatmasi va bilimlari bilan javob beradi. AI band bo'lsa - o'z bilimidan."""
    from . import local_ai, providers
    from .service import NO_EXCUSE, agent_system, brain, knowledge_answer, knowledge_block
    a = brain.agents.get(key) if key else None
    system = (agent_system(a) if a else brain.system) + knowledge_block(text, key) + NO_EXCUSE
    if a:
        system += (f"\n\nSening isming: {name_of(a.key)}. Ali jamoasining Telegram guruhida ishlayapsan: "
                   "qisqa, aniq va amaliy yoz.")
    reply = ""
    if ready_apps:
        got = local_ai.ask_pro(local_ai._prompt(system, [], text), local_ai.TIMEOUT)
        reply = got[1] if got else ""
    if not reply:
        try:
            reply = providers.chat(system, [], text, 2500)[1]
        except Exception as e:
            log.info("Agent javobi olinmadi (%s): %s", key, e)
    if not reply:
        reply = knowledge_answer(text, key, a)
    return (reply or "").strip()


# ---------- maslahat kengashi ----------
COUNCIL_TASK = """🤝 MASLAHAT KENGASHI. Ali jamoasi birga maslahatlashyapti.
Masala ({owner}dan): {question}

Hamkasblaringiz fikri:
{previous}

Sen - {me}. O'z sohang nuqtai nazaridan 3-8 gapda fikr bildir: nima qilish kerak, xavf va muhim jihatlar.
Video/kontent masalasi bo'lsa - Instagram'da qanchalik ishlashini 1-10 baho bilan ayt (hook, ushlab turish, saqlash).
Hamkasbing to'g'ri aytgan bo'lsa - qo'shil va to'ldir, noto'g'ri bo'lsa - asoslab e'tiroz bildir. Takrorlama."""

SUMMARY_TASK = """Sen {ali} - jamoa boshlig'isan. Maslahat kengashi tugadi.
Masala: {question}

Agentlar fikri:
{opinions}

Yakuniy QAROR chiqar: 1) qisqa xulosa, 2) aniq harakat rejasi (kim nima qiladi - agent ismi bilan),
3) xavflar. Agentlar kelishmagan joyni ochiq ayt va tanlovingni asosla.
Masala video, kontent, reklama yoki Instagram'ga tegishli bo'lsa, qo'shimcha:
4) 📊 Instagram uchun BAHO: 1-10 (raqam bilan) - nima uchun; ✅ yaxshi tomonlari va ❌ yomon tomonlari (aniq, 2-4 tadan);
5) 🎯 Kutilgan natija: qamrov/saqlash/direkt yozishlar bo'yicha taxmin va 7 kunda nimani o'lchab tekshiramiz."""


# Video/kontent/kod masalasida albatta qatnashadigan eng yaxshi maslahatchilar
EXPERTS = re.compile(r"video|видео|reels|рилс|kontent|контент|instagram|инстаграм|montaj|монтаж|post|пост|reklama|"
                     r"реклама|dastur|дастур|\bkod\b|\bкод\b|sayt|сайт|\bbot\b|\bбот\b", re.I)
CORE = ("kontent", "video_montajchi", "dasturchi")


def pick_members(question: str, agents: dict, limit: int = 3) -> list[str]:
    """Masalaga eng mos 2-3 agent: tavsifi va nomidagi so'zlar mosligi bo'yicha (+ dispetcher tanlagani).
    Video, kontent yoki kod haqida bo'lsa - Kontent-meyker, Video montajchi va Dasturchi albatta qatnashadi."""
    core = [k for k in CORE if k in agents] if EXPERTS.search(question) else []
    if core:
        return core
    words = {w[:5] for w in re.findall(r"\w{4,}", question.lower())}
    scored = []
    for key, a in agents.items():
        hay = {w[:5] for w in re.findall(r"\w{4,}", f"{a.name} {a.description} {key}".lower())}
        scored.append((len(words & hay), key))
    picked = [k for s, k in sorted(scored, reverse=True) if s > 0][:limit]
    try:
        from .service import route
        first = route(question, [])
        if first and first not in picked:
            picked = [first, *picked][:limit]
    except Exception:
        pass
    for key in ("murabbiy", *agents):  # kamida 2 kishi bo'lsin
        if len(picked) >= 2:
            break
        if key in agents and key not in picked:
            picked.append(key)
    return picked


def council(question: str, agents: dict, members: list[str] | None = None, ready_apps: list[str] | None = None,
            ask=None) -> str:
    """Agentlar navbat bilan fikr bildiradi (har biri oldingilarni ko'radi), Ali qaror chiqaradi.
    Hammasi «Maslahat kengashi» mavzusiga yoziladi; qaror Ali mavzusiga ham. Qaror matnini qaytaradi."""
    ask = ask or (lambda key, text: agent_answer(key, text, ready_apps))
    members = [k for k in (members or pick_members(question, agents)) if k in agents]
    post("maslahat", f"🤝 Yangi masala: {question[:1500]}\n\nKengash: " + ", ".join(label(k, agents) for k in members),
         agents)
    opinions = []
    for key in members:
        previous = "\n\n".join(opinions) or "(hali hech kim gapirmadi - birinchi bo'lib sen)"
        try:
            reply = ask(key, COUNCIL_TASK.format(owner=config.user_name, question=question, previous=previous,
                                                 me=label(key, agents)))
        except Exception as e:
            log.warning("Maslahatda %s javob bermadi: %s", key, e)
            reply = ""
        if not reply.strip():
            skipped(key)
            post("maslahat", f"🔇 {label(key, agents)} maslahatda qatnashmadi.", agents)
            continue
        touch(key, "maslahat")
        opinions.append(f"{label(key, agents)}: {reply.strip()}")
        post("maslahat", f"{label(key, agents)}:\n{reply.strip()}", agents)
    if not opinions:
        return "Maslahat bo'lmadi: hech bir agent javob bermadi (AI ulanishini tekshiring)."
    decision = ask(None, SUMMARY_TASK.format(ali=config.assistant_name, question=question,
                                             opinions="\n\n".join(opinions))) or "\n\n".join(opinions)
    post("maslahat", f"👑 Ali qarori:\n{decision}", agents)
    post("ali", f"🤝 Maslahat qarori: {question[:300]}\n\n{decision}", agents)
    return decision


# ---------- yaratish ----------
def setup(agents: dict) -> str:
    """Forum-guruhni yaratadi (bir marta), botni admin qiladi, mavzularni ochadi va agentlarni tanishtiradi."""
    from . import tg_account
    if not config.telegram_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN yo'q - bot ulanmagan")
    if chat_id():
        made = [k for k in [*FIXED, *agents] if ensure_topic(k, agents)]
        return f"Guruh allaqachon bor: «{TITLE}». Mavzular tekshirildi ({len(made)} ta)."
    if not tg_account.authorized():
        raise RuntimeError("Guruhni ochish uchun shaxsiy Telegram akkaunt kerak: Ruxsatlar → Telegram akkaunt → Kirish")
    bot = _api("getMe")["username"]

    async def go(client):
        from telethon.tl.functions.channels import CreateChannelRequest, EditAdminRequest, InviteToChannelRequest
        from telethon.tl.types import ChatAdminRights
        res = await client(CreateChannelRequest(title=TITLE, about=ABOUT, megagroup=True, forum=True))
        ch = res.chats[0]
        user = await client.get_input_entity(bot)
        await client(InviteToChannelRequest(ch, [user]))
        rights = ChatAdminRights(change_info=True, post_messages=True, edit_messages=True, delete_messages=True,
                                 invite_users=True, pin_messages=True, manage_topics=True, other=True)
        await client(EditAdminRequest(ch, user, rights, rank=config.assistant_name))
        return ch.id

    channel = tg_account._run(go, 120)
    with LOCK:
        data = _load()
        data.update(chat_id=int(f"-100{channel}"), created=time.time(), topics={})
        _save(data)
    for key in FIXED:
        ensure_topic(key, agents)
    for key, a in agents.items():
        ensure_topic(key, agents)
        post(key, f"Salom! Men {name_of(key)} — {a.name}. {a.description}\n"
                  f"Shu mavzuga yozsangiz, men javob beraman. Qilgan ishlarim ham shu yerda ko'rinadi.", agents)
    post("ali", f"👑 Ali jamoasi tayyor. Jamoa: " + ", ".join(label(k, agents) for k in agents)
         + "\n\nBu yerda eng muhim topilmalar va kunlik nazorat hisoboti bo'ladi.", agents)
    post("maslahat", "🤝 Maslahat kengashi. Shu yerga masala yozing - mos agentlar maslahatlashadi, Ali qaror chiqaradi.",
         agents)
    post("telegram", "🔎 Telegram nazorati: kanal, guruh, bot va yozishmalarni tekshirish natijalari shu yerda.\n"
                     "«X guruhini tekshir» deb yozing - darhol ko'rib chiqaman.", agents)
    post("sinf", "🏫 5-D sinf: guruhlardan sinfga oid muammo, rasm va dars jadvali shu yerga keladi.", agents)
    return (f"✅ «{TITLE}» guruhi ochildi: {len(FIXED) + len(agents)} ta mavzu. Telegram'da guruhlar ro'yxatida "
            "ko'rinadi. Agent mavzusiga yozsangiz - o'sha agent javob beradi.")


def tick(agents: dict, notify=None, now: float | None = None) -> None:
    """Avtopilotdan: kuniga bir marta nazorat hisoboti Ali mavzusiga (bekorchilar bo'lsa egasiga ham)."""
    if not ready():
        return
    now = now or time.time()
    day = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
    data = _load()
    if datetime.fromtimestamp(now).strftime("%H:%M") < REPORT_AT or data.get("report_day") == day:
        return
    with LOCK:
        data = _load()
        data["report_day"] = day
        _save(data)
    for k in agents:  # yangi agentlar uchun mavzu
        try:
            ensure_topic(k, agents)
        except Exception as e:
            log.warning("Mavzu ochilmadi %s: %s", k, e)
    text = watch_report(agents, now)
    post("ali", text, agents)
    if notify and idle_agents(agents, now):
        notify(text[:3500])
