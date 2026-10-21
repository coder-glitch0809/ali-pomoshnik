"""Plaginlar: Ali'ga tashqi AI xizmatlar va kompyuter dasturlarini ulaydi.

Har bir plagin shu papkadagi alohida .py fayl. U @skill bilan vositalarini ro'yxatdan o'tkazadi
va PLUGIN = Plugin(...) e'lon qiladi. Ali ishga tushganda barcha plaginlar avtomatik
(fonda) ishga tushadi - qo'lda yoqish shart emas. Yangi plagin qo'shish:

    from ..skills import skill
    from . import Plugin

    def _start():
        return True, "Ulangan"           # (tayyormi, holat matni)

    PLUGIN = Plugin(key="misol", name="Misol", icon="*", description="...", start=_start)

    @skill(description="...", params={...})
    def misol_ish(...): ...

O'chirish: .env da PLUGINS_DISABLED=chatgpt,coreldraw
"""
import importlib
import logging
import pkgutil
import threading
from dataclasses import dataclass, field
from typing import Callable

from ..config import config

log = logging.getLogger("ali.plugins")


@dataclass
class Plugin:
    key: str
    name: str
    icon: str
    description: str
    start: Callable[[], tuple[bool, str]]
    tools: list[str] = field(default_factory=list)
    ready: bool = False
    status: str = "Ishga tushmoqda..."

    def summary(self) -> dict:
        return {"key": self.key, "name": self.name, "icon": self.icon, "description": self.description,
                "ready": self.ready, "status": self.status, "tools": self.tools}


PLUGINS: dict[str, Plugin] = {}
_lock = threading.Lock()
_started = False


def load_all() -> dict[str, Plugin]:
    """Plagin modullarini import qiladi; har bir plaginga uning vositalari biriktiriladi."""
    from .. import skills
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_") or mod.name in config.plugins_disabled or mod.name in PLUGINS:
            continue
        name = f"{__name__}.{mod.name}"
        try:
            module = importlib.import_module(name)
        except Exception:
            log.exception("Plagin yuklanmadi: %s", mod.name)
            continue
        p = getattr(module, "PLUGIN", None)
        if isinstance(p, Plugin):
            p.tools = sorted(k for k, s in skills.REGISTRY.items() if s.func.__module__ == name)
            PLUGINS[p.key] = p
    return PLUGINS


def restart(key: str) -> None:
    """Bitta plaginni qayta ishga tushiradi (masalan, kalit saqlangandan keyin)."""
    p = PLUGINS.get(key)
    if p is None:
        return
    try:
        p.ready, p.status = p.start()
    except Exception as e:
        log.exception("Plagin ishga tushmadi: %s", key)
        p.ready, p.status = False, f"Xato: {e}"
    log.info("Plagin %s: %s", key, p.status)


def start_all() -> None:
    """Barcha plaginlarni fonda avtomatik ishga tushiradi (bir marta)."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    for key in list(PLUGINS):
        threading.Thread(target=restart, args=(key,), name=f"plugin-{key}", daemon=True).start()


def hidden_tools() -> set[str]:
    """Ishlamaydigan plaginlarning vositalari (modelga ko'rsatilmaydi). Ishga tushayotganlari ko'rinadi."""
    return {t for p in PLUGINS.values() if not p.ready and p.status != "Ishga tushmoqda..." for t in p.tools}


def summary() -> list[dict]:
    return [p.summary() for p in PLUGINS.values()]
