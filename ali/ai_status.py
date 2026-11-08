"""AI holati: hamma AI (Pro ilovalar va API'lar) javob bermasa - Ali buni eslab qoladi va bir muddat ularni kutib
o'tirmaydi: agentlar darhol O'Z bilim bazasi, eslab qolingan faktlar va ko'rsatmalari bilan ishlaydi.
Muddat tugagach AI qayta sinab ko'riladi; javob kelsa - holat darhol tiklanadi."""
import logging
import threading
import time

log = logging.getLogger("ali.ai_status")

PAUSE = 10 * 60  # hamma AI javob bermasa - shuncha vaqt faqat o'z bilimi bilan
_lock = threading.Lock()
_state = {"until": 0.0, "since": 0.0}


def is_down() -> bool:
    return time.time() < _state["until"]


def down(reason: str = "") -> None:
    with _lock:
        if not is_down():
            _state["since"] = time.time()
            log.warning("AI'lar javob bermadi (%s) - %d daqiqa agentlar faqat o'z bilimi bilan ishlaydi", reason[:120],
                        PAUSE // 60)
        _state["until"] = time.time() + PAUSE


def up() -> None:
    with _lock:
        if _state["until"]:
            log.info("AI qaytdi - agentlar yana AI bilan ishlaydi")
        _state["until"] = 0.0


def note() -> str:
    left = max(0, int(_state["until"] - time.time()))
    return f"AI'lar band - {left // 60 + 1} daqiqagacha o'z bilimi bilan" if left else "AI ishlayapti"
