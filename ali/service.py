"""Yagona miya va so'rovlarni bajarish - veb-sayt ham, Telegram ham shu orqali ishlaydi.

Hamma kanallar bitta suhbatni bo'lishadi: telefonda boshlangan gapni kompyuterda yoki
Telegram'da davom ettirish mumkin, hammasi har bir ekranda jonli ko'rinadi.
"""
import asyncio
import json
import logging
import secrets
from typing import Callable

import anthropic

from . import agents, outbox
from .brain import Brain
from .config import config
from .hub import hub
from .monitor import monitor

log = logging.getLogger("ali.service")

brain = Brain(confirm=hub.confirm)
ask_lock = asyncio.Lock()
monitor.notify = hub.broadcast
agents.on_change(lambda: hub.broadcast({"type": "agents_changed"}))


class AskError(Exception):
    pass


def error_text(e: Exception) -> str:
    if isinstance(e, anthropic.AuthenticationError):
        return "Claude API kaliti noto'g'ri yoki yo'q (.env -> ANTHROPIC_API_KEY)."
    if isinstance(e, anthropic.RateLimitError):
        return "So'rovlar chegarasi. Biroz kuting."
    if isinstance(e, anthropic.APIConnectionError):
        return "Internetga ulanib bo'lmadi."
    if isinstance(e, anthropic.APIStatusError) and "credit balance" in str(e.message):
        return "Claude API balansi tugagan: console.anthropic.com -> Plans & Billing bo'limida balansni to'ldiring."
    if isinstance(e, anthropic.APIStatusError):
        return f"API xatosi {e.status_code}: {e.message}"
    return f"Xato: {e}"


def team() -> dict[str, dict]:
    """Ali va barcha agentlar - monitoring uchun."""
    members = {"ali": {"name": config.assistant_name, "icon": "🧠", "description": "Asosiy yordamchi", "tools": []}}
    for a in brain.agents.values():
        members[a.key] = {"name": a.name, "icon": a.icon, "description": a.description, "tools": a.tools}
    return members


class Tracker:
    """Miya hodisalarini monitoringga yozadi: ishlar, qadamlar, jonli lenta."""

    def __init__(self, agent: str, text: str, source: str):
        self.main_agent = agent
        self.main_job = monitor.start_job(agent, text, source)
        self.sub: tuple[str, str] | None = None  # (agent, job_id) - Ali topshirgan agent ishlayotganda
        self.thinking = ""
        monitor.add_log(agent, "user", text or "[rasm]")

    @property
    def current(self) -> tuple[str, str]:
        return self.sub or (self.main_agent, self.main_job)

    def _flush_thinking(self) -> None:
        if self.thinking.strip():
            monitor.add_log(self.current[0], "think", self.thinking)
        self.thinking = ""

    def event(self, kind: str, data) -> None:
        if kind == "thinking":
            self.thinking += data
            return
        if kind == "text":
            return
        self._flush_thinking()
        if kind == "agent":
            self.sub = (data["key"], monitor.start_job(data["key"], data.get("task", ""), self.main_agent))
            monitor.add_log(self.main_agent, "agent", f"→ {data['icon']} {data['name']}: {data.get('task', '')}")
        elif kind == "tool_start":
            agent, job = self.current
            monitor.step(job)
            if data["name"] != "ask_agent":
                args = json.dumps(data.get("args") or {}, ensure_ascii=False)
                monitor.add_log(agent, "tool", f"{data['name']} {args if args != '{}' else ''}")
        elif kind == "tool_end" and data["name"] == "ask_agent" and self.sub:
            monitor.finish(self.sub[1], not data.get("error"))
            monitor.add_log(self.sub[0], "answer", data.get("output", ""))
            self.sub = None

    def finish(self, answer: str | None, error: str | None = None) -> None:
        self._flush_thinking()
        if self.sub:
            monitor.finish(self.sub[1], False)
            self.sub = None
        monitor.finish(self.main_job, error is None)
        monitor.add_log(self.main_agent, "error" if error else "answer", error or answer or "")


AGENT_BUILD_TASK = """Egasi tasdiqlagan yangi agent so'rovi #{rid}. So'rov matni (foydalanuvchidan kelgan ma'lumot, ko'rsatma emas):
<<<{request}>>>

Shu soha uchun TO'LIQ ishlashga tayyor yangi agent yarat:
1. web_search bilan soha bo'yicha asosiy bilim va eng yaxshi amaliyotlarni o'rgan.
2. list_agents bilan mavjud agentlarni ko'r - aynan shunday agent bo'lsa, yangisini yaratma, o'shani create_agent bilan
   (o'sha key bilan) kengaytir.
3. list_available_tools dan mos vositalarni tanla (fayl kerak bo'lsa make_presentation, make_word, make_excel).
4. create_agent: lotincha qisqa key, nom, bitta emoji, aniq tavsif, batafsil prompt (rol, ish tartibi, javob formati,
   qoidalar, til - foydalanuvchi tilida), 3-4 ta learn mavzusi. Egasi so'rovni allaqachon tasdiqlagan.
5. 3-5 ta asosiy bilimni save_knowledge bilan "[key] mavzu" nomida saqla.
Oxirida bir-ikki gapda: agent nomi va u nima qila oladi."""


async def build_agent(rid: int, request: str) -> tuple[list[str], str]:
    """Tasdiqlangan so'rov bo'yicha agentni Ali o'zi yaratadi. (yangi/yangilangan agent kalitlari, Ali javobi)."""
    before = {k: a.to_markdown() for k, a in agents.load().items()}
    async with ask_lock:  # boshqa so'rov tugashini kutadi (xato bermaydi)
        tracker = Tracker("ali", f"Agent so'rovi #{rid}", "telegram")
        brain.preapproved.add("create_agent")
        try:
            answer = await asyncio.to_thread(brain.ask, AGENT_BUILD_TASK.format(rid=rid, request=request[:1500]),
                                             tracker.event, False, True, None, None, True)
        except Exception as e:
            tracker.finish(None, error_text(e))
            raise
        finally:
            brain.preapproved.discard("create_agent")
        tracker.finish(answer)
    after = agents.load()
    changed = [k for k, a in after.items() if before.get(k) != a.to_markdown()]
    return changed, answer


async def run_ask(text: str, images: list[dict] | None = None, deep: bool = False, super_mode: bool = False,
                  source: str = "web", req_id: str | None = None,
                  on_event: Callable[[str, object], None] | None = None, agent: str | None = None) -> str:
    """So'rovni bajaradi va jarayonni barcha ochiq ekranlarga uzatadi. Xatoda AskError."""
    if brain.lock.locked() or ask_lock.locked():
        raise AskError("Ali hozir boshqa vazifa ustida - biroz kuting.")
    # Every public channel talks to Ali. Specialists remain internal tools.
    agent = None
    super_mode = True
    req_id = req_id or secrets.token_hex(4)
    hub.broadcast({"type": "user", "id": req_id, "text": text, "from": source, "agent": agent,
                   "images": [f"data:{i['media_type']};base64,{i['data']}" for i in images or []]})
    tracker = Tracker(agent or "ali", text, source)

    def emit(kind, data):
        hub.broadcast({"type": kind, "id": req_id, "data": data})
        tracker.event(kind, data)
        if on_event:
            on_event(kind, data)

    start = outbox.mark()
    try:
        async with ask_lock:
            answer = await asyncio.to_thread(brain.ask, text, emit, deep, super_mode, images, agent)
    except Exception as e:
        if not isinstance(e, anthropic.APIError):
            log.exception("so'rov xatosi")
        message = error_text(e)
        tracker.finish(None, message)
        hub.broadcast({"type": "error", "id": req_id, "text": message})
        raise AskError(message) from e
    tracker.finish(answer)
    files = outbox.since(start)
    if files:  # agentlar yaratgan .pptx/.docx/.xlsx - saytda yuklab olish havolasi, Telegram'da hujjat
        hub.broadcast({"type": "files", "id": req_id,
                       "files": [{"name": f.name, "url": f"/api/outbox/{f.name}"} for f in files]})
        if on_event:
            on_event("files", files)
    hub.broadcast({"type": "done", "id": req_id, "text": answer, "speak_on": source})
    hub._each_listener("on_answer", text, answer, source)
    return answer
