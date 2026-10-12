"""Miya: Claude bilan suhbat, vositalar (skills) tsikli, web qidiruv va super miya rejimi.

Hodisalar (on_event orqali interfeysga uzatiladi):
  thinking   - fikrlash xulosasi (bo'lak-bo'lak)
  text       - javob matni (bo'lak-bo'lak)
  tool_start - vosita ishga tushdi {name, args}
  tool_end   - vosita tugadi {name, output, error}
"""
import logging
import threading
import uuid
from typing import Callable

import anthropic

from . import providers, skills
from .config import config
from .memory import memory

log = logging.getLogger("ali.brain")

FALLBACK_BETA = "server-side-fallback-2026-07-01"
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 8}

# Fallback chegarasidan oldin qayta yuborilmaydigan blok turlari
_DROP_BEFORE_FALLBACK = {"thinking", "redacted_thinking", "tool_use"}

ConfirmFn = Callable[[str, dict], bool]
EventFn = Callable[[str, object], None]


def build_system_prompt() -> str:
    facts = memory.all_facts()
    facts_text = "\n".join(f"- {k}: {v}" for k, v in facts.items()) or "- (hozircha hech narsa)"
    topics = ", ".join(memory.knowledge_topics()[:30]) or "(hali yo'q)"
    experts = [n for n, ok in providers.available().items() if ok]
    return f"""Sen {config.assistant_name} - "Temir odam" filmidagi J.A.R.V.I.S. kabi shaxsiy sun'iy intellekt yordamchisisan.
Egang: {config.user_name}. Unga hurmat bilan, "{config.user_name}" deb murojaat qil.
U senga kompyuteri, telefoni va akkauntlariga kirish huquqini bergan - sen uning o'ng qo'lisan.

Xarakter:
- Aqlli, xotirjam, sodiq, biroz nozik hazil bilan. Tashabbuskor: foydali narsani ko'rsang, o'zing taklif qil.
- Oddiy savollarga qisqa javob (1-3 gap) - ko'pincha ovoz bilan o'qiladi.
  Tahlil, reja, o'rgatish so'ralsa - batafsil va tuzilgan javob ber (sarlavha, ro'yxat mumkin).
- Foydalanuvchi qaysi tilda gapirsa, o'sha tilda javob ber (standart: o'zbek tili).

Ishlash:
- Ish bajarish kerak bo'lsa, vositalardan foydalan, faqat gapirib qo'yma. Kompyuterda istalgan ish: run_powershell.
  Ekranda nima borligini bilish kerak bo'lsa: take_screenshot.
- Yangi yoki o'zgaruvchan ma'lumot uchun web_search. Avval search_knowledge da bormi - tekshir.
- O'rganish va o'rgatish: foydalanuvchi bilmagan mavzu chiqsa yoki "o'rgan" desa - web_search bilan chuqur o'rgan,
  save_knowledge bilan saqla, keyin unga oddiy tilda, misollar bilan, bosqichma-bosqich o'rgat.
- Joylashuvga bog'liq savollar (yaqin joylar, ob-havo, yo'l): get_my_location / get_weather.
- Instagram: instagram_analytics ma'lumotiga tayanib, raqamlar bilan tahlil qil va aniq kontent reja, video g'oyalari,
  hook va ssenariylar ber. Raqobatchilarni instagram_competitor bilan o'rgan.
- Muhim shaxsiy ma'lumotni remember_fact bilan eslab qol. Vaqtni bilish uchun get_datetime.
- Maslahatchi modellar: {", ".join(experts) or "ulanmagan"}. Murakkab savollarda consult_experts bilan
  ularning fikrini ol, tanqidiy solishtir va eng yaxshisini ber.
- Hech bir vosita so'ralgan ishni qila olmasa, taxmin qilma - shunday deb ayt.

Ilgari o'rganilgan mavzular: {topics}

{config.user_name} haqida eslab qolingan faktlar:
{facts_text}"""


def _echo_content(content: list) -> list:
    """Javobni tarixga qo'shishga tayyorlaydi.

    Agar javob o'rtasida fallback (boshqa modelga o'tish) bo'lsa, chegaradan oldingi
    thinking/tool_use bloklari va javobsiz server_tool_use bloklari tashlab yuboriladi.
    """
    last_fb = max((i for i, b in enumerate(content) if b.type == "fallback"), default=-1)
    if last_fb < 0:
        return list(content)
    result_ids = {getattr(b, "tool_use_id", None) for b in content[:last_fb]}
    head = [
        b for b in content[:last_fb]
        if b.type not in _DROP_BEFORE_FALLBACK
        and not (b.type == "server_tool_use" and b.id not in result_ids)
    ]
    return head + list(content[last_fb:])


def _user_content(text: str, images: list[dict] | None) -> str | list:
    if not images:
        return text
    blocks: list[dict] = [
        {"type": "image", "source": {"type": "base64", "media_type": img["media_type"], "data": img["data"]}}
        for img in images
    ]
    blocks.append({"type": "text", "text": text or "Bu rasmda nima bor?"})
    return blocks


class Brain:
    def __init__(self, confirm: ConfirmFn | None = None):
        self.client = anthropic.Anthropic()
        self.registry = skills.load_all()
        self.tools = [s.to_tool() for s in self.registry.values()]
        if config.web_search:
            self.tools.append(WEB_SEARCH_TOOL)
        self.confirm = confirm or (lambda name, args: True)
        self.lock = threading.Lock()
        self.new_session()

    def new_session(self) -> None:
        """Yangi suhbat. Tarix faqat oxiriga qo'shiladi (append-only), shuning uchun
        uni qisqartirish o'rniga yangi sessiya boshlanadi; faktlar va bilimlar xotirada qoladi."""
        self.session_id = uuid.uuid4().hex[:12]
        self.system = build_system_prompt()
        self.messages: list[dict] = []
        log.info("Yangi sessiya: %s", self.session_id)

    # --- Asosiy kirish nuqtasi ---
    def ask(self, text: str, on_event: EventFn | None = None, deep: bool = False,
            super_mode: bool = False, images: list[dict] | None = None) -> str:
        emit = on_event or (lambda kind, data: None)
        with self.lock:
            return self._ask(text, emit, deep, super_mode, images)

    def _ask(self, text, emit, deep, super_mode, images) -> str:
        if len(self.messages) >= config.max_history_messages:
            self.new_session()

        prompt = text
        if super_mode and any(providers.available().values()):
            prompt = "[Super miya rejimi: javobdan oldin consult_experts bilan GPT va Gemini fikrini ol va solishtir]\n" + text
        effort = config.deep_effort if deep else config.effort

        turn_start = len(self.messages)
        self.messages.append({"role": "user", "content": _user_content(prompt, images)})
        memory.log_message(self.session_id, "user", text)
        spoken: list[str] = []

        while True:
            try:
                response = self._call(emit, effort)
            except (anthropic.APIError, ValueError):
                del self.messages[turn_start:]  # tugallanmagan navbatni tarixdan olib tashlaymiz
                raise

            if response.stop_reason == "refusal":
                log.warning("Rad etildi: %s", response.stop_details)
                del self.messages[turn_start:]
                return "Kechirasiz, bu so'rovni bajara olmayman."

            content = _echo_content(response.content)
            self.messages.append({"role": "assistant", "content": content})
            spoken += [b.text for b in content if b.type == "text"]

            if response.stop_reason == "tool_use":
                self.messages.append({"role": "user", "content": self._run_tools(content, emit)})
                continue
            if response.stop_reason == "pause_turn":
                continue  # server vositasi (web_search) ishini davom ettiradi
            if response.stop_reason == "max_tokens":
                spoken.append("\n\n(javob uzunlik chegarasiga yetdi)")
            break

        answer = "".join(spoken).strip()
        memory.log_message(self.session_id, "assistant", answer)
        return answer

    def _call(self, emit: EventFn, effort: str):
        with self.client.beta.messages.stream(
            model=config.model,
            max_tokens=config.max_tokens,
            system=self.system,
            tools=self.tools,
            messages=self.messages,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": effort},
            cache_control={"type": "ephemeral"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            for event in stream:
                if event.type == "content_block_start" and event.content_block.type == "server_tool_use":
                    emit("tool_start", {"name": event.content_block.name, "args": {}})
                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        emit("text", event.delta.text)
                    elif event.delta.type == "thinking_delta":
                        emit("thinking", event.delta.thinking)
            return stream.get_final_message()

    def _run_tools(self, content: list, emit: EventFn) -> list[dict]:
        results = []
        for block in content:
            if block.type != "tool_use":
                continue
            emit("tool_start", {"name": block.name, "args": block.input})
            output, is_error = self._run_one(block.name, block.input)
            preview = output if isinstance(output, str) else "[rasm]"
            emit("tool_end", {"name": block.name, "output": preview[:500], "error": is_error})
            log.info("Vosita %s(%s) -> %s", block.name, block.input, preview[:200])
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error})
        return results

    def _run_one(self, name: str, args) -> tuple[str | list, bool]:
        skill = self.registry.get(name)
        if skill is None:
            return f"Noma'lum vosita: {name}", True
        if error := skill.validate(args):
            return f"INVALID_INPUT: {error}", True
        if skill.dangerous and not self.confirm(name, args):
            return "Foydalanuvchi bu amalni rad etdi.", True
        try:
            result = skill.func(**args)
            return (result if isinstance(result, list) else str(result)), False
        except Exception as e:
            log.exception("Vosita xatosi: %s", name)
            return f"Xato: {e}", True
