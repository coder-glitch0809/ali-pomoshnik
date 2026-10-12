"""Avtopilot: agentlar o'z-o'zini o'qitadi va treyding loyihalari kuzatib boriladi.

Yoqish (.env):
  AUTO_LEARN=true        har bir agent "o'rganish" mavzulari bo'yicha AUTO_LEARN_HOURS da bir marta yangiliklarni
                         o'rganib, bilimlar bazasiga yozadi
  WATCH_PROJECTS=true    Dasturchi agent WATCH_HOURS da bir marta treyding loyihalarini (kompyuter, GitHub, Vercel)
                         tekshiradi va muammo bo'lsa telefonga/Telegramga xabar beradi
Avtopilot faqat tasdiq talab qilmaydigan (o'qish) vositalarini ishlatadi - siz yo'qligingizda hech narsa o'zgartirilmaydi.
Har bir ishga tushish API'dan pul sarflaydi.
"""
import json
import logging
import threading
import time

from .config import config
from .hub import hub

log = logging.getLogger("ali.autopilot")

STATE = config.data_dir / "autopilot.json"
CHECK_EVERY = 300  # soniya
TRADING_WORDS = "trade, trading, treyd, bot, binance, bybit, crypto, kripto, forex, mql, mt4, mt5, signal, indicator, indekator, strategy"

LEARN_TASK = """O'z-o'zini o'qitish vaqti. Mavzular: {topics}.
1. Avval search_knowledge bilan bilimlar bazangda nima borligini tekshir - takrorlama.
2. web_search bilan har bir mavzu bo'yicha eng so'nggi va eng foydali ma'lumotni o'rgan (sana: get_datetime).
3. 3-6 ta qisqa, amaliy xulosani save_knowledge bilan saqla. Mavzu nomi "[{key}] ..." bilan boshlansin, ichida manba va sana bo'lsin.
4. Oxirida nimani o'rganganingni 3-5 qatorda yoz."""

WATCH_TASK = """Treyding loyihalarini kuzat (faqat tekshir, hech narsani o'zgartirma).
1. list_projects, github_repos va vercel_projects bilan treydingga aloqador loyihalarni top
   (kalit so'zlar: {words}; foydalanuvchi faktlarida ko'rsatilganlari ham).
2. Har biri uchun: kompyuterdagi git holati (project_git_status), GitHub Actions natijasi (github_repo),
   Vercel oxirgi deploy holati (vercel_deployments) - xato bo'lsa vercel_logs bilan sababini aniqla.
3. Javob formati: agar hammasi joyida bo'lsa, faqat bitta qator: "OK: N ta loyiha tekshirildi".
   Muammo bo'lsa: "MUAMMO:" bilan boshla va har bir muammo uchun loyiha, nima bo'lgan, qanday tuzatish taklifi."""


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"learn": {}, "watch": 0}


def _save(state: dict) -> None:
    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def run_agent(brain, key: str, task: str, title: str, extra_tools: tuple = ()) -> str:
    """Agentni avtopilot rejimida ishga tushiradi (chaqiruvchi brain.lock ni ushlab turishi kerak)."""
    from .service import Tracker

    tracker = Tracker(key, title, "avtopilot")
    try:
        emit = lambda kind, data: kind != "agent" and tracker.event(kind, data)  # ish allaqachon ochilgan
        result, is_error = brain._run_agent({"agent": key, "task": task}, emit, safe_only=True, extra_tools=extra_tools)
    except Exception as e:
        log.exception("Avtopilot xatosi: %s", key)
        tracker.finish(None, f"Xato: {e}")
        return f"Xato: {e}"
    tracker.finish(None if is_error else result, result if is_error else None)
    return result


def learn(brain, key: str) -> str:
    a = brain.agents.get(key)
    if a is None:
        return "Bunday agent yo'q."
    topics = "; ".join(a.learn) or a.description
    return run_agent(brain, key, LEARN_TASK.format(topics=topics, key=key), f"O'z-o'zini o'qitish: {topics}",
                     extra_tools=("web_search", "search_knowledge", "save_knowledge", "get_datetime"))


def watch(brain) -> str:
    if "dasturchi" not in brain.agents:
        return "Dasturchi agent yo'q."
    return run_agent(brain, "dasturchi", WATCH_TASK.format(words=TRADING_WORDS), "Treyding loyihalarini kuzatish",
                     extra_tools=("list_projects", "project_git_status", "github_repos", "github_repo",
                                  "vercel_projects", "vercel_deployments", "vercel_logs"))


def _tick(brain) -> None:
    state = _load()
    now = time.time()
    if config.auto_learn:
        for key, a in list(brain.agents.items()):
            if not a.learn or now - state["learn"].get(key, 0) < config.auto_learn_hours * 3600:
                continue
            if not brain.lock.acquire(blocking=False):
                return  # Ali band - keyinroq
            try:
                result = learn(brain, key)
            finally:
                brain.lock.release()
            state["learn"][key] = now
            _save(state)
            log.info("O'rganish tugadi: %s", key)
            hub.notify(f"📚 {a.icon} {a.name} yangi bilim o'rgandi:\n{result[:600]}")
    if config.watch_projects and now - state.get("watch", 0) >= config.watch_hours * 3600:
        if not brain.lock.acquire(blocking=False):
            return
        try:
            result = watch(brain)
        finally:
            brain.lock.release()
        state["watch"] = now
        _save(state)
        if not result.strip().upper().startswith("OK"):
            hub.notify(f"🛠 Treyding loyihalari:\n{result[:1500]}")


def start(brain) -> None:
    if not (config.auto_learn or config.watch_projects):
        return

    def loop():
        time.sleep(60)  # server to'liq ishga tushsin
        while True:
            try:
                _tick(brain)
            except Exception:
                log.exception("Avtopilot tsikli xatosi")
            time.sleep(CHECK_EVERY)

    threading.Thread(target=loop, daemon=True, name="autopilot").start()
    log.info("Avtopilot yoqildi (o'rganish=%s, kuzatish=%s)", config.auto_learn, config.watch_projects)
