"""Shaxsiy Telegram akkaunt (Telethon): kanallar va guruhlarni ko'rish, ichidagi post va fayllardan o'rganish.

O'qish - erkin. Xabar YUBORISH - faqat egasi so'raganda (ovoz yoki matn) va HAR SAFAR egasining tasdig'i bilan
(kimga va nima yozilishi ko'rsatiladi). Ali hech narsani o'chirmaydi va kanallarga a'zo bo'lmaydi.
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


_authorized: bool | None = None  # oxirgi ulanishda aniqlangan: kirish yakunlanganmi


def configured() -> bool:
    """Kalit va sessiya bor, va (tekshirilgan bo'lsa) telefon bilan kirish yakunlangan."""
    return credentials() is not None and Path(str(SESSION) + ".session").exists() and _authorized is not False


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
        global _authorized
        try:
            _authorized = bool(await client.is_user_authorized())
            if not _authorized:
                raise RuntimeError("Telegram akkauntga kirilmagan: Ruxsatlar -> Telegram akkaunt -> Kirish")
            if (await client.get_me()).bot:
                raise RuntimeError("Kirishda telefon raqami o'rniga BOT tokeni kiritilgan - bot kanallarni ko'ra olmaydi. "
                                   "Ruxsatlar -> Telegram akkaunt -> Sozlash: qayta kiring va TELEFON RAQAMINGIZNI yozing.")
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


def people(name: str, limit: int = 300) -> list[dict]:
    """Suhbatlar orasidan nomi/username/telefoni mos keladiganlar (shaxslar, guruhlar). Eng mosi birinchi."""
    low = name.lower().strip().lstrip("@")
    digits = re.sub(r"\D", "", name)

    async def go(client):
        out = []
        async for d in client.iter_dialogs(limit=limit):
            ent = d.entity
            if getattr(ent, "broadcast", False):  # kanallarga yozilmaydi
                continue
            title = d.name or ""
            username = (getattr(ent, "username", None) or "").lower()
            phone = getattr(ent, "phone", None) or ""
            exact = low in (title.lower(), username) or (len(digits) >= 7 and phone.endswith(digits[-9:]))
            part = low and (low in title.lower() or (username and low in username))
            if exact or part:
                out.append({"id": d.id, "title": title, "username": username, "exact": bool(exact),
                            "kind": "guruh" if d.is_group else "shaxs"})
        return sorted(out, key=lambda c: (not c["exact"], len(c["title"])))
    return _run(go)


def send_message(chat_id: int, text: str) -> str:
    """Xabar yuboradi (chaqiruvchi egasining tasdig'ini oldin oladi)."""
    async def go(client):
        await client.send_message(chat_id, text)
        return "yuborildi"
    return _run(go)


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


def learn_all_channels(progress=None, limit: int = 100) -> list[dict]:
    """Barcha kanallardagi yangi post va fayllardan o'rganish (avtopilot)."""
    results = []
    for ch in [c for c in channels() if c["kind"] == "kanal"]:
        try:
            r = learn_channel(ch["title"], limit, progress)
        except Exception as e:
            log.warning("Kanal o'rganilmadi %s: %s", ch["title"], e)
            continue
        if r["posts"] or r["files"]:
            results.append(r)
    return results


REVIEW_TASK = """Bugun {today}. Quyida egamning ({owner}) Telegram'dagi shaxsiy yozishmalari (oxirgi {hours} soat).
"Men" - egam. Diqqat bilan o'qib chiq va FAQAT JSON qaytar:
{{"facts": [{{"key": "qisqa kalit", "value": "egam haqida aniq fakt (ish, loyiha, odamlar, afzallik, manzil...)"}}],
  "plans": [{{"when": "YYYY-MM-DD HH:MM yoki YYYY-MM-DD (vaqt aytilmagan bo'lsa)", "with": "kim bilan", "what": "nima qilish/uchrashish/to'lash"}}],
  "summary": "3-6 gapda bugungi muhim gaplar"}}
Faqat egam KELISHGAN aniq reja va va'dalarni plans ga yoz (uchrashuv, qo'ng'iroq, to'lov, topshirish, yetkazish).
Taxmin qilma. Faktlar faqat egam haqida va aniq bo'lsin. Parol, kod, karta raqami kabi maxfiy narsalarni yozma.

Yozishmalar:
{chats}"""


def recent_chats(hours: int = 36, max_dialogs: int = 40, per_dialog: int = 80) -> str:
    """Shaxsiy (odamlar bilan) yozishmalar matni - oxirgi N soat. Botlar va kanallar kirmaydi."""
    from datetime import datetime, timedelta, timezone
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    async def go(client):
        parts, n = [], 0
        async for d in client.iter_dialogs():
            if not d.is_user or getattr(d.entity, "bot", False) or d.date is None or d.date < since:
                continue
            msgs = []
            async for m in client.iter_messages(d.id, limit=per_dialog, offset_date=None):
                if m.date < since:
                    break
                if m.text:
                    who = "Men" if m.out else d.name
                    msgs.append(f"[{m.date.astimezone().strftime('%m-%d %H:%M')}] {who}: {m.text[:1500]}")
            if msgs:
                parts.append(f"### {d.name}\n" + "\n".join(reversed(msgs)))
                n += 1
                if n >= max_dialogs:
                    break
        return "\n\n".join(parts)
    return _run(go)


def review_chats(hours: int = 36) -> dict:
    """Yozishmalarni ko'rib chiqadi: faktlar xotiraga, bugungi/yaqin rejalar eslatmaga. Hech narsa yuborilmaydi."""
    from datetime import datetime, timedelta

    from . import local_ai
    from .memory import memory
    from .service import _ask_json
    chats = recent_chats(hours)
    if not chats.strip():
        return {"facts": 0, "reminders": [], "summary": "Yangi yozishma yo'q."}
    ready = local_ai.connected() if local_ai.access() is True else []
    data = _ask_json(REVIEW_TASK.format(today=time.strftime("%Y-%m-%d %H:%M"), owner=config.user_name, hours=hours,
                                        chats=chats[:60000]), ready)
    facts = 0
    for f in data.get("facts") or []:
        k, v = str(f.get("key", "")).strip()[:80], str(f.get("value", "")).strip()[:500]
        if k and v:
            memory.set_fact(k, v)
            facts += 1
    state = _state()
    made = set(state.get("_reminders", []))
    reminders = []
    now = datetime.now()
    for p in data.get("plans") or []:
        what, who, when = str(p.get("what", "")).strip(), str(p.get("with", "")).strip(), str(p.get("when", "")).strip()
        if not what:
            continue
        try:
            due = datetime.strptime(when, "%Y-%m-%d %H:%M")
            notify_at = max(due - timedelta(minutes=30), now + timedelta(minutes=1))  # 30 daqiqa oldin eslatadi
        except ValueError:
            try:
                day = datetime.strptime(when[:10], "%Y-%m-%d")
                notify_at = max(day.replace(hour=9), now + timedelta(minutes=1))  # vaqtsiz - o'sha kuni 09:00 da
                due = day
            except ValueError:
                continue
        if due.date() < now.date():
            continue
        text = f"📅 {what}" + (f" — {who}" if who else "") + (f" ({when})" if when else "")
        if text in made:
            continue
        memory.add_reminder(text, notify_at)
        made.add(text)
        reminders.append(text)
    state["_reminders"] = sorted(made)[-300:]
    STATE.write_text(json.dumps(state), encoding="utf-8")
    summary = str(data.get("summary", "")).strip()
    if summary:
        memory.add_knowledge(f"[umumiy] Yozishmalar xulosasi {time.strftime('%Y-%m-%d %H:%M')}", summary)
    return {"facts": facts, "reminders": reminders, "summary": summary}


if __name__ == "__main__":  # kirish oynasi: python -m ali.tg_account
    from telethon.sync import TelegramClient
    creds = credentials()
    if not creds:
        print("TG_API_ID va TG_API_HASH .env da yo'q")
        sys.exit(1)
    session_file = Path(str(SESSION) + ".session")
    # Oldingi sessiya bot bo'lsa (bot tokeni kiritilgan) - o'chiramiz, akkaunt bilan qayta kirish kerak
    c = TelegramClient(str(SESSION), *creds)
    c.connect()
    stale = c.is_user_authorized() and c.get_me().bot
    c.disconnect()
    if stale:
        session_file.unlink(missing_ok=True)
        print("Oldingi kirish BOT bilan qilingan edi - u o'chirildi. Endi shaxsiy akkauntingiz bilan kiring.\n")
    print("Telegram akkauntga kirish (kanallarni o'qish uchun).\n"
          "Bot tokeni EMAS - o'zingizning TELEFON RAQAMINGIZNI kiriting (+998...), keyin Telegram yuborgan kodni.\n"
          "Ma'lumotlaringiz faqat shu kompyuterda (data/telegram_user.session) qoladi.\n")

    def ask_phone():
        while True:
            phone = input("Telefon raqamingiz (+998...): ").strip().replace(" ", "")
            if re.fullmatch(r"\+?\d{9,15}", phone):
                return phone
            print("Bu telefon raqami emas (bot tokeni kiritmang). Masalan: +998901234567")

    result = config.data_dir / "tg_login.log"  # natija (xato ham) - Ali ko'ra olishi uchun; raqam/kod yozilmaydi
    try:
        c = TelegramClient(str(SESSION), *creds)
        c.start(phone=ask_phone)  # kod va (bo'lsa) 2 bosqichli parolni Telethon o'zi so'raydi
        me = c.get_me()
        c.disconnect()
        result.write_text(f"{time.strftime('%F %T')} OK: {me.first_name} (@{me.username or '-'})", encoding="utf-8")
        print(f"\nTayyor: {me.first_name} (@{me.username or '-'}) bilan kirildi. Oynani yopishingiz mumkin.")
    except Exception as e:
        result.write_text(f"{time.strftime('%F %T')} XATO: {type(e).__name__}: {e}", encoding="utf-8")
        print(f"\n⚠️ Kirib bo'lmadi: {type(e).__name__}: {e}\nOynani yopib, Ali'dan qayta kirishni so'rang.")
        raise
