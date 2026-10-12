"""Agentlar: maxsus rol, ko'rsatma va vositalarga ega mutaxassislar.

Har bir agent - agents/ papkasidagi bitta .md fayl (kod yozish shart emas):

    ---
    nom: Treyder
    belgi: 📈
    tavsif: Bozor tahlili va savdo rejalari (Ali shu matnga qarab vazifa topshiradi)
    vositalar: web_search, market_data, get_datetime
    o'rganish: kripto bozor yangiliklari; yangi savdo strategiyalari   (ixtiyoriy, avtomatik o'rganish uchun)
    ---
    Sen tajribali treydersan... (agentning to'liq ko'rsatmasi)

Fayl nomi - agent kaliti (treyder.md -> "treyder"). Yangi agent qo'shgach serverni qayta ishga tushiring.
Agentdan ikki xil foydalaniladi:
  1. Foydalanuvchi saytda/Telegram'da agentni tanlaydi - Ali shu rolda javob beradi.
  2. Ali o'zi ask_agent vositasi bilan vazifani mos agentga topshiradi.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Callable

from .config import ROOT

log = logging.getLogger("ali.agents")

AGENTS_DIR = ROOT / "agents"
KEY_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,30}")


@dataclass
class Agent:
    key: str
    name: str
    icon: str
    description: str
    tools: list[str]
    prompt: str
    learn: list[str] = field(default_factory=list)  # avtomatik o'rganish mavzulari

    def summary(self) -> dict:
        return {"key": self.key, "name": self.name, "icon": self.icon, "description": self.description}

    def full(self) -> dict:
        return {**self.summary(), "tools": self.tools, "prompt": self.prompt, "learn": self.learn}

    def to_markdown(self) -> str:
        return (f"---\nnom: {self.name}\nbelgi: {self.icon}\ntavsif: {self.description}\n"
                f"vositalar: {', '.join(self.tools)}\no'rganish: {'; '.join(self.learn)}\n---\n{self.prompt.strip()}\n")


_listeners: list[Callable[[], None]] = []


def on_change(fn: Callable[[], None]) -> None:
    """Agentlar o'zgarganda chaqiriladi (miya ro'yxatni qayta yuklaydi)."""
    _listeners.append(fn)


def _changed() -> None:
    for fn in _listeners:
        try:
            fn()
        except Exception:
            log.exception("Agent o'zgarishi tinglovchisi xatosi")


def save(key: str, name: str, icon: str, description: str, tools: list[str], prompt: str,
         learn: list[str] | None = None) -> Agent:
    """Agentni yaratadi yoki yangilaydi (agents/<key>.md)."""
    key = key.strip().lower()
    if not KEY_RE.fullmatch(key):
        raise ValueError("Kalit faqat lotin harflari, raqam, - va _ dan iborat bo'lsin (masalan: huquqshunos)")
    if not prompt.strip():
        raise ValueError("Agent ko'rsatmasi (prompt) bo'sh")
    agent = Agent(key=key, name=" ".join(name.split()) or key.capitalize(), icon=(icon or "🤖").strip()[:4],
                  description=" ".join(description.split()), tools=[t.strip() for t in tools if t.strip()],
                  prompt=prompt.strip(), learn=[t.strip() for t in (learn or []) if t.strip()])
    AGENTS_DIR.mkdir(exist_ok=True)
    (AGENTS_DIR / f"{key}.md").write_text(agent.to_markdown(), encoding="utf-8")
    log.info("Agent saqlandi: %s", key)
    _changed()
    return agent


def delete(key: str) -> bool:
    path = AGENTS_DIR / f"{key.strip().lower()}.md"
    if not path.exists():
        return False
    path.unlink()
    log.info("Agent o'chirildi: %s", key)
    _changed()
    return True


def _parse(key: str, text: str) -> Agent:
    meta: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        head, _, body = text[3:].partition("\n---")
        for line in head.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
    return Agent(
        key=key,
        name=meta.get("nom", key.capitalize()),
        icon=meta.get("belgi", "🤖"),
        description=meta.get("tavsif", ""),
        tools=[t.strip() for t in meta.get("vositalar", "").split(",") if t.strip()],
        prompt=body.strip(),
        learn=[t.strip() for t in meta.get("o'rganish", "").split(";") if t.strip()],
    )


def load() -> dict[str, Agent]:
    agents: dict[str, Agent] = {}
    for path in sorted(AGENTS_DIR.glob("*.md")):
        if path.stem.startswith("_"):
            continue
        try:
            agents[path.stem.lower()] = _parse(path.stem.lower(), path.read_text(encoding="utf-8").lstrip("﻿"))
        except (OSError, UnicodeDecodeError):
            log.exception("Agent faylini o'qib bo'lmadi: %s", path)
    log.info("Agentlar: %s", ", ".join(agents) or "yo'q")
    return agents
