"""Qotishga qarshi nazoratchi: asosiy oqim (sayt + Telegram bot) har 5 s da «tirikman» belgisini yangilaydi.
Belgi 2 daqiqa yangilanmasa - Ali qotib qolgan: qaysi joyda qotgani logga yoziladi va jarayon to'xtatiladi,
avtoyuklash (scripts/autostart.cmd) uni 10 s da qayta ishga tushiradi. Avtoyuklashsiz (qo'lda ishga tushirilgan) -
faqat logga yoziladi.
"""
import asyncio
import faulthandler
import logging
import os
import threading
import time

from .config import ROOT

log = logging.getLogger("ali.watchdog")

STALL = 120  # soniya
_beat = {"at": time.monotonic()}


async def _heartbeat() -> None:
    while True:
        _beat["at"] = time.monotonic()
        await asyncio.sleep(5)


def _watch(exit_on_stall: bool) -> None:
    while True:
        time.sleep(15)
        stalled = time.monotonic() - _beat["at"]
        if stalled < STALL:
            continue
        log.critical("Ali %d s dan beri qotib qolgan - oqimlar holati logs/stall.txt ga yozildi", stalled)
        try:
            with open(ROOT / "logs" / "stall.txt", "a", encoding="utf-8") as f:
                f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} ({int(stalled)} s) =====\n")
                f.flush()
                faulthandler.dump_traceback(file=f, all_threads=True)
        except OSError:
            pass
        if exit_on_stall:
            logging.shutdown()
            os._exit(3)  # avtoyuklash qayta ishga tushiradi
        _beat["at"] = time.monotonic()  # qo'lda ishga tushirilgan - faqat ogohlantirish, keyingisi 2 daqiqadan keyin


def start(loop: asyncio.AbstractEventLoop) -> None:
    loop.create_task(_heartbeat())
    threading.Thread(target=_watch, args=(bool(os.getenv("ALI_SUPERVISED")),), daemon=True, name="watchdog").start()
