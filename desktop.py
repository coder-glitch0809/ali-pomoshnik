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

def _ali_ready(url: str) -> bool:
    import httpx

    try:
        with httpx.Client(timeout=1, trust_env=False) as client:
            if client.get(url + "/healthz").raise_for_status().json() != {"ok": True}:
                return False
            manifest = client.get(url + "/manifest.webmanifest").raise_for_status().json()
            return isinstance(manifest, dict) and manifest.get("short_name") == "Ali"
    except (httpx.HTTPError, ValueError):
        return False


def _open_when_ready(url: str) -> None:
    for _ in range(60):
        if _ali_ready(url):
            if not webbrowser.open(url):
                print(f"Brauzer ochilmadi. Manzilni qo‘lda oching: {url}")
            return
        time.sleep(0.5)
    print(f"Ali {url} manzilida javob bermadi. Server xabarlarini tekshiring.")


def main() -> None:
    import uvicorn

    default_state = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Ali"
    state = Path(os.environ.setdefault("ALI_STATE_DIR", str(default_state)))
    state.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HOST", "127.0.0.1")
    if "--localhost" in sys.argv:
        os.environ.update(HOST="127.0.0.1", TUNNEL="off", PUBLIC_URL="", RENDER_EXTERNAL_URL="", VERCEL="0")
    from ali.config import config

    url = f"http://127.0.0.1:{config.port}"
    open_browser = "--no-browser" not in sys.argv
    if _ali_ready(url):
        print(f"{config.assistant_name} allaqachon ishlayapti: {url}")
        if open_browser:
            _open_when_ready(url)
        return

    from runtime import app

    print(f"{config.assistant_name} ishga tushmoqda: {url}\nBu oynani yopsangiz, {config.assistant_name} to'xtaydi.")
    if not config.access_password:
        print(f"Kirish paroli saqlangan fayl: {config.data_dir / 'password.txt'}")
    if open_browser:
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    uvicorn.run(app, host=config.host, port=config.port, log_level="warning")


if __name__ == "__main__":
    main()
