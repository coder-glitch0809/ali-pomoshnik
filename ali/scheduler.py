"""Fon jarayoni: vaqti kelgan eslatmalarni tekshirib, e'lon qiladi."""
import threading
import time
from typing import Callable

from .memory import memory


def start(notify: Callable[[str], None], interval: float = 10.0) -> threading.Thread:
    def loop():
        while True:
            for r in memory.due_reminders():
                memory.mark_done(r["id"])
                notify(f"Eslatma: {r['text']}")
            time.sleep(interval)

    t = threading.Thread(target=loop, daemon=True, name="scheduler")
    t.start()
    return t
