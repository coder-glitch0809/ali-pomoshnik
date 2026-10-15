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
import shutil
from dataclasses import dataclass, field
from typing import Callable

from .config import ROOT, STATE_ROOT

log = logging.getLogger("ali.agents")

AGENTS_DIR = STATE_ROOT / "agents"
LESSONS_HEADER = "## Tajriba (avtomatik)"


def split_lessons(prompt: str) -> tuple[str, list[str]]:
    """Ko'rsatma -> (asosiy qism, Murabbiy yozgan "Tajriba" saboqlari)."""
    base, sep, tail = prompt.partition(LESSONS_HEADER)
    if not sep:
        return prompt.strip(), []
    return base.strip(), [line.strip()[2:].strip() for line in tail.splitlines() if line.strip().startswith("- ")]


def join_lessons(base: str, lessons: list[str]) -> str:
    if not lessons:
        return base.strip()
    return base.strip() + f"\n\n{LESSONS_HEADER}\n" + "\n".join(f"- {l}" for l in lessons)


if STATE_ROOT != ROOT:
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    marker = AGENTS_DIR / ".initialized"
    if not marker.exists():
        for source in (ROOT / "agents").glob("*.md"):
            if not (AGENTS_DIR / source.name).exists():
                shutil.copy2(source, AGENTS_DIR / source.name)
        marker.touch()
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
    version: int = 0  # repodagi fayl versiyasi kattaroq bo'lsa, doimiy diskdagi nusxa yangilanadi

    def summary(self) -> dict:
        return {"key": self.key, "name": self.name, "icon": self.icon, "description": self.description}

    def full(self) -> dict:
        return {**self.summary(), "tools": self.tools, "prompt": self.prompt, "learn": self.learn}

    def to_markdown(self) -> str:
        return (f"---\nnom: {self.name}\nbelgi: {self.icon}\ntavsif: {self.description}\n"
                f"vositalar: {', '.join(self.tools)}\no'rganish: {'; '.join(self.learn)}\n"
                + (f"versiya: {self.version}\n" if self.version else "") + f"---\n{self.prompt.strip()}\n")


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
    path = AGENTS_DIR / f"{key}.md"
    version = _parse(key, path.read_text(encoding="utf-8")).version if path.exists() else 0
    agent = Agent(key=key, name=" ".join(name.split()) or key.capitalize(), icon=(icon or "🤖").strip()[:4],
                  description=" ".join(description.split()), tools=[t.strip() for t in tools if t.strip()],
                  prompt=prompt.strip(), learn=[t.strip() for t in (learn or []) if t.strip()], version=version)
    AGENTS_DIR.mkdir(exist_ok=True)
    (AGENTS_DIR / f"{key}.md").write_text(agent.to_markdown(), encoding="utf-8")
    log.info("Agent saqlandi: %s", key)
    _changed()
    return agent


def delete(key: str) -> bool:
    if not KEY_RE.fullmatch(key.strip().lower()):
        raise ValueError("Agent kaliti noto'g'ri")
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
        version=int(meta["versiya"]) if meta.get("versiya", "").isdigit() else 0,
    )


def upgrade_defaults(source_dir=None, target_dir=None) -> list[str]:
    """Repodagi agent fayli (versiya: N) doimiy diskdagi nusxadan yangi bo'lsa, uni yangilaydi.
    Murabbiy qo'shgan "Tajriba" saboqlari, qo'shimcha o'rganish mavzulari va vositalar saqlanadi."""
    source_dir, target_dir = source_dir or ROOT / "agents", target_dir or AGENTS_DIR
    if source_dir.resolve() == target_dir.resolve():
        return []
    upgraded = []
    for source in sorted(source_dir.glob("*.md")):
        target = target_dir / source.name
        if not target.exists():
            continue
        try:
            new = _parse(source.stem, source.read_text(encoding="utf-8").lstrip("\ufeff"))
            cur = _parse(source.stem, target.read_text(encoding="utf-8").lstrip("\ufeff"))
        except (OSError, UnicodeDecodeError, ValueError):
            log.exception("Agentni yangilab bo'lmadi: %s", source.name)
            continue
        if new.version <= cur.version:
            continue
        new.prompt = join_lessons(split_lessons(new.prompt)[0], split_lessons(cur.prompt)[1])
        new.learn += [t for t in cur.learn if t not in new.learn]
        new.tools += [t for t in cur.tools if t not in new.tools]
        history = target_dir / "_history"
        history.mkdir(exist_ok=True)
        shutil.copy2(target, history / f"{source.stem}-v{cur.version}-before-upgrade.md")
        target.write_text(new.to_markdown(), encoding="utf-8")
        upgraded.append(source.stem)
        log.info("Agent yangi versiyaga o'tdi: %s v%s -> v%s", source.stem, cur.version, new.version)
    return upgraded


def add_new_defaults(source_dir=None, target_dir=None) -> list[str]:
    """Repoga qo'shilgan YANGI standart agentni (masalan dizayner) doimiy diskka bir marta qo'shadi.
    Egasi keyin o'chirgan agent qayta paydo bo'lmaydi (.defaults ro'yxati)."""
    import json
    source_dir, target_dir = source_dir or ROOT / "agents", target_dir or AGENTS_DIR
    if source_dir.resolve() == target_dir.resolve():
        return []
    record = target_dir / ".defaults.json"
    try:
        known = set(json.loads(record.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        known = set()
    added = []
    for source in sorted(source_dir.glob("*.md")):
        if source.name in known:
            continue
        known.add(source.name)
        if not (target_dir / source.name).exists():
            shutil.copy2(source, target_dir / source.name)
            added.append(source.stem)
            log.info("Yangi standart agent qo'shildi: %s", source.stem)
    target_dir.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(sorted(known)), encoding="utf-8")
    return added


if STATE_ROOT != ROOT:
    add_new_defaults()
    upgrade_defaults()


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
