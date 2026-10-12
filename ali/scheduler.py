"""Fon jarayoni: vaqti kelgan eslatmalarni tekshirib, e'lon qiladi."""
import logging
import threading
import time
from typing import Callable

from .memory import memory

log = logging.getLogger("ali.scheduler")


def start(notify: Callable[[str], None], interval: float = 10.0) -> threading.Thread:
    def loop():
        while True:
            try:
                for r in memory.due_reminders():
                    memory.mark_done(r["id"])
                    notify(f"Eslatma: {r['text']}")
            except Exception:
                log.exception("Eslatmalarni yuborishda xato")  # bitta xato butun jarayonni to'xtatmasin
            time.sleep(interval)

    t = threading.Thread(target=loop, daemon=True, name="scheduler")
    t.start()
    return t
