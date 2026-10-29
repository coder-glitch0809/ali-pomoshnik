"""Telefondan istalgan joydan kirish: Cloudflare tunnel (bepul, akkauntsiz) - https://....trycloudflare.com.

Ali ishga tushganda cloudflared'ni o'zi yoqadi, berilgan manzilni config.public_url ga yozadi va Telegram'dagi
"Ali panel" tugmasini yangilaydi (manzil har ishga tushishda o'zgaradi). Tunnel uzilsa - qayta ochiladi.
Kirish: sayt - parol bilan, Mini App va masofaviy boshqaruv - faqat egasining Telegram akkaunti bilan.
O'chirish: .env da TUNNEL=off.
"""
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .config import config

log = logging.getLogger("ali.tunnel")

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
state = {"url": "", "running": False, "error": ""}
_listeners: list = []  # manzil o'zgarganda chaqiriladi: fn(url)


def exe() -> str | None:
    for p in (shutil.which("cloudflared"), r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
              r"C:\Program Files\cloudflared\cloudflared.exe"):
        if p and Path(p).exists():
            return p
    return None


def enabled() -> bool:
    return os.getenv("TUNNEL", "auto").lower() not in ("off", "0", "false", "no") and exe() is not None


def on_url(fn) -> None:
    _listeners.append(fn)


PID = config.data_dir / "tunnel.pid"


def _kill_old() -> None:
    """Oldingi Ali'dan qolib ketgan cloudflared (Ali qulasa, bola jarayon o'chmaydi)."""
    try:
        pid = int(PID.read_text())
    except (OSError, ValueError):
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    PID.unlink(missing_ok=True)


def _run_once(path: str) -> None:
    _kill_old()
    proc = subprocess.Popen([path, "tunnel", "--no-autoupdate", "--url", f"http://localhost:{config.port}"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    PID.write_text(str(proc.pid))
    state["running"] = True
    try:
        for line in proc.stdout:
            m = URL_RE.search(line)
            if m and m.group(0) != state["url"]:
                state.update(url=m.group(0), error="")
                config.public_url = m.group(0)
                log.info("Tunnel ochildi: %s", m.group(0))
                for fn in list(_listeners):
                    try:
                        fn(m.group(0))
                    except Exception:
                        log.exception("Tunnel manzilini yangilab bo'lmadi")
    finally:
        proc.kill()
        state["running"] = False


def _loop() -> None:
    while True:
        path = exe()
        if not path:
            state["error"] = "cloudflared o'rnatilmagan"
            return
        try:
            _run_once(path)
            state["error"] = "tunnel uzildi - qayta ochilmoqda"
        except OSError as e:
            state["error"] = str(e)
        log.warning("Tunnel to'xtadi, 15 soniyada qayta ochiladi")
        time.sleep(15)


def start() -> None:
    if enabled():
        config.public_url = ""  # .env dagi eski manzil emas - tunnel ochilgach yangisi yoziladi
        threading.Thread(target=_loop, daemon=True, name="tunnel").start()
