"""Shaxsiy Telegram akkaunt (Telethon): kanallar va guruhlarni ko'rish, ichidagi post va fayllardan o'rganish.

Faqat O'QISH: Ali akkauntingizdan hech narsa yubormaydi, o'chirmaydi va kanallarga a'zo bo'lmaydi.
Sozlash (bir marta):
  1. https://my.telegram.org -> API development tools -> api_id va api_hash oling.
  2. Ali: Ruxsatlar -> Ulanishlar -> Telegram akkaunt -> ikkalasini kiriting ("12345 abcdef...").
  3. Kompyuterda oyna ochiladi: telefon raqamingiz, Telegram yuborgan kod va (bo'lsa) 2 bosqichli parolni
     O'ZINGIZ kiritasiz. Sessiya data/telegram_user.session da saqlanadi - keyin qayta kirish shart emas.
"""
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from .config import ROOT, config

log = logging.getLogger("ali.tg_account")

SESSION = config.data_dir / "telegram_user"
STATE = config.data_dir / "tg_channels.json"
FILE_EXT = {".pdf", ".docx", ".xlsx", ".xlsm", ".pptx", ".txt", ".md", ".csv", ".json", ".py", ".html", ".mq5", ".mq4"}
MAX_FILE = 20 * 1024 * 1024


def credentials() -> tuple[int, str] | None:
    api_id, api_hash = os.environ.get("TG_API_ID", "").strip(), os.environ.get("TG_API_HASH", "").strip()
    return (int(api_id), api_hash) if api_id.isdigit() and api_hash else None


def configured() -> bool:
    return credentials() is not None and Path(str(SESSION) + ".session").exists()


def _client():
    from telethon import TelegramClient
    creds = credentials()
    if not creds:
        raise RuntimeError("Telegram akkaunt ulanmagan: Ruxsatlar -> Ulanishlar -> Telegram akkaunt")
    return TelegramClient(str(SESSION), *creds)


def _run(coro_fn):
    """Telethon so'rovini alohida oqimda o'z event loop'i bilan bajaradi."""
    async def main():
        client = _client()
        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise RuntimeError("Telegram akkauntga kirilmagan: Ruxsatlar -> Telegram akkaunt -> Kirish")
            return await coro_fn(client)
        finally:
            await client.disconnect()
    return asyncio.run(main())


def open_login() -> None:
    """Kompyuterda kirish oynasini ochadi - raqam, kod va parolni egasi O'ZI kiritadi."""
    if not credentials():
        raise RuntimeError("Avval api_id va api_hash ni kiriting")
    subprocess.Popen(["cmd", "/k", sys.executable, "-m", "ali.tg_account"], cwd=str(ROOT),
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


def channels() -> list[dict]:
    """Akkauntdagi kanallar va guruhlar: nomi, username, a'zolar soni, o'qilmagan."""
    async def go(client):
        out = []
        async for d in client.iter_dialogs():
            if d.is_channel or d.is_group:
                ent = d.entity
                out.append({"id": d.id, "title": d.name, "username": getattr(ent, "username", None) or "",
                            "kind": "kanal" if d.is_channel and not d.is_group else "guruh", "unread": d.unread_count})
        return out
    return _run(go)


def _match(items: list[dict], name: str) -> dict | None:
    low = name.lower().strip().lstrip("@")
    exact = [c for c in items if low in (c["title"].lower(), c["username"].lower())]
    if exact:
        return exact[0]
    part = [c for c in items if low in c["title"].lower() or (c["username"] and low in c["username"].lower())]
    return part[0] if len(part) == 1 else None


def find_in_text(text: str) -> dict | None:
    """Xabarda tilga olingan kanal (nomi yoki @username)."""
    try:
        items = channels()
    except Exception:
        return None
    low = text.lower()
    hits = [c for c in items if (len(c["title"]) >= 3 and c["title"].lower() in low)
            or (c["username"] and ("@" + c["username"].lower() in low or c["username"].lower() in low))]
    return max(hits, key=lambda c: len(c["title"])) if hits else None


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def learn_channel(name: str, limit: int = 100, progress=None) -> dict:
    """Kanal/guruhdagi yangi post va fayllarni o'qib, mos agentlar bazasiga yozadi (avval o'qilganlari qaytarilmaydi)."""
    from . import ingest

    items = channels()
    ch = _match(items, name)
    if ch is None:
        raise RuntimeError(f"«{name}» kanali topilmadi. Mavjudlar: " + ", ".join(c["title"] for c in items[:30]))
    state = _state()
    last = state.get(str(ch["id"]), 0)
    folder = ingest.INBOX / re.sub(r"[^\w\- ]+", "_", ch["title"])[:60]

    async def go(client):
        posts, files = [], []
        async for m in client.iter_messages(ch["id"], limit=limit, min_id=last):
            if m.text:
                posts.append((m.id, m.date.strftime("%Y-%m-%d"), m.text))
            f = m.file
            if f and f.size and f.size <= MAX_FILE:
                ext = (f.ext or "").lower()
                if ext in FILE_EXT or (m.photo and len([x for x in files if x[2] == "photo"]) < 10):
                    folder.mkdir(parents=True, exist_ok=True)
                    path = await m.download_media(file=str(folder))
                    if path:
                        files.append((m.id, Path(path), "photo" if m.photo else "file", m.text or ""))
        return posts, files

    posts, files = _run(go)
    learned, total = [], 0
    source = f"Telegram: {ch['title']}"
    # Postlar - bo'laklab (har bo'lak ~15 ming belgi)
    posts.sort()
    chunk, size = [], 0
    for mid, day, text in posts + [(None, None, None)]:
        if text is None or size + len(text) > 15000:
            if chunk:
                days = f"{chunk[0][1]} - {chunk[-1][1]}"
                r = ingest.learn(f"{ch['title']}: postlar {days}", "\n\n---\n\n".join(f"[{d}] {t}" for _, d, t in chunk),
                                 source)
                learned.append(r)
                total += r["saved"]
                if progress:
                    progress(f"📚 {r['icon']} {r['name']}: {r['saved']} ta bilim ({ch['title']} postlari)")
            chunk, size = [], 0
        if text is not None:
            chunk.append((mid, day, text))
            size += len(text)
    # Fayllar va rasmlar
    for mid, path, kind, caption in files:
        try:
            text = ingest.extract_text(path)
        except RuntimeError as e:
            log.warning("Kanal fayli o'qilmadi: %s", e)
            continue
        images = [str(path)] if path.suffix.lower() in ingest.IMAGE_EXT else None
        r = ingest.learn(f"{ch['title']}: {path.name}", text, source, images, hint=caption)
        learned.append(r)
        total += r["saved"]
        if progress:
            progress(f"📚 {r['icon']} {r['name']}: {r['saved']} ta bilim ({path.name})")
    ids = [p[0] for p in posts] + [f[0] for f in files]
    if ids:
        state[str(ch["id"])] = max(ids + [last])
        STATE.write_text(json.dumps(state), encoding="utf-8")
    agents = sorted({f"{r['icon']} {r['name']}" for r in learned})
    return {"channel": ch["title"], "posts": len(posts), "files": len(files), "saved": total, "agents": agents}


if __name__ == "__main__":  # kirish oynasi: python -m ali.tg_account
    from telethon.sync import TelegramClient
    creds = credentials()
    if not creds:
        print("TG_API_ID va TG_API_HASH .env da yo'q")
        sys.exit(1)
    print("Telegram akkauntga kirish. Telefon raqamingizni (+998...) va Telegram yuborgan kodni kiriting.\n"
          "Ma'lumotlaringiz faqat shu kompyuterda (data/telegram_user.session) qoladi.\n")
    with TelegramClient(str(SESSION), *creds) as c:
        me = c.get_me()
        print(f"\nTayyor: {me.first_name} (@{me.username or '-'}) bilan kirildi. Oynani yopishingiz mumkin.")
