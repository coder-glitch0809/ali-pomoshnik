"""Windows ilovasi (Ali.exe) uchun kirish nuqtasi: serverni shu kompyuterda ishga tushiradi va panelni ochadi.

Sozlamalar va xotira foydalanuvchi papkasida saqlanadi: %LOCALAPPDATA%\\Ali (.env, data\\, agents\\).
O'rnatuvchi (installer/ali.iss) u yerga ism, kalitlar va tanlangan ruxsatlarni yozadi.
"""
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

STATE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Ali"
os.environ.setdefault("ALI_STATE_DIR", str(STATE))
os.environ.setdefault("HOST", "127.0.0.1")  # faqat shu kompyuterdan ochiladi
STATE.mkdir(parents=True, exist_ok=True)


def _open_when_ready(url: str) -> None:
    import httpx
    for _ in range(60):
        try:
            if httpx.get(url + "/healthz", timeout=1).status_code == 200:
                webbrowser.open(url)
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)


def main() -> None:
    import uvicorn

    from ali.config import config
    from runtime import app

    url = f"http://localhost:{config.port}"
    print(f"{config.assistant_name} ishga tushmoqda: {url}\nBu oynani yopsangiz, {config.assistant_name} to'xtaydi.")
    if "--no-browser" not in sys.argv:
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    uvicorn.run(app, host=config.host, port=config.port, log_level="warning")


if __name__ == "__main__":
    main()
