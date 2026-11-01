"""Planet Print moliya paneli (planet-print-max, https://planet-print-max.vercel.app) - Ali xarajat yozadi.

Kirish: panelda Ali uchun alohida foydalanuvchi (xarajat ruxsati bilan) yarating va Ruxsatlar -> Ulanishlar ->
Planet Print ga «login parol» ni O'ZINGIZ kiriting (.env: PP_USER, PP_PASS).

Guruh kuzatuvi: guruhlarda «NOMI SUMMA SOM» ro'yxati (masalan Jasurning to'lovlar ro'yxati) tushsa:
  1) ro'yxat eslatmaga qo'yiladi (ertasi kun 09:00);
  2) bandlar saralanadi: 📦 xarajat/material bo'lishi mumkin bo'lganlar va 📌 boshqalar (mijoz, to'lov);
  3) egasiga tugmalar bilan yuboriladi - qaysi band xarajatga qo'shilishini egasi tanlaydi -> zakaz va to'lov turi
     tanlanadi -> Planet Print'ga yoziladi (izohda manba: kim, qaysi guruh, sana).
"""
import json
import logging
import os
import re
import time
import uuid
from datetime import date, datetime, timedelta

import httpx

from .config import config

log = logging.getLogger("ali.planetprint")

URL = os.getenv("PP_URL", "https://planet-print-max.vercel.app").rstrip("/")
STATE = config.data_dir / "planetprint.json"
PAYMENT = {"naqd": "Naqd", "klik": "Klik", "shot": "Shot (kartadan)"}
LINE = re.compile(r"^\s*(?:\d{1,2}[.)]\s+)?[-•*]?\s*(?P<name>[^\n]*?[^\W\d_][^\n]*?)\s*[-:–]?\s*(?P<sum>\d{1,3}(?:[ .,'’]\d{3})+|\d{4,})\s*"
                  r"(?:so['ʻ‘’]?m|som|сум|sum|uzs|сўм)?\.?\s*$", re.I)
MATERIAL = re.compile(r"masla|moy|kraska|bo['ʻ‘’]?yoq|banner|plyonka|plenka|oracal|orakal|akril|akrilik|profil|lampa|led|"
                      r"modul|blok|kabel|sim\b|vinil|kompozit|list|metall|temir|svarka|elektrod|bolt|samorez|skotch|lenta|"
                      r"pech|siyoh|chernila|kartrij|qog['ʻ‘’]?oz|bumaga|plastik|pvx|pvc|forex|lightbox|transformator|"
                      r"bloq|truba|ugolok|kraska|rezina|kley|yelim|zamena|ehtiyot|zapchast|benzin|dizel|gaz", re.I)


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"token": "", "token_at": 0, "batches": {}}


def _save(st: dict) -> None:
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def configured() -> bool:
    return bool(os.getenv("PP_USER") and os.getenv("PP_PASS"))


# ---------------- API ----------------
def _login() -> str:
    if not configured():
        raise RuntimeError("Planet Print ulanmagan: Ruxsatlar -> Ulanishlar -> Planet Print (Ali uchun login va parol)")
    r = httpx.post(f"{URL}/api/auth/login", json={"username": os.getenv("PP_USER"), "password": os.getenv("PP_PASS")},
                   timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Planet Print'ga kirib bo'lmadi: {(r.json() if r.content else {}).get('error', r.status_code)}")
    st = _state()
    st.update(token=r.json()["token"], token_at=time.time())
    _save(st)
    return st["token"]


def _api(method: str, path: str, **kw):
    st = _state()
    token = st.get("token") if time.time() - st.get("token_at", 0) < 6 * 3600 else ""
    for attempt in range(2):
        token = token or _login()
        r = httpx.request(method, f"{URL}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=45, **kw)
        if r.status_code == 401 and attempt == 0:
            token = ""
            continue
        body = r.json() if r.content else {}
        if r.status_code >= 400:
            raise RuntimeError(body.get("error") or f"Planet Print xatosi {r.status_code}")
        return body
    raise RuntimeError("Planet Print'ga kirib bo'lmadi")


def finance() -> tuple[dict, int]:
    body = _api("GET", "/api/finance")
    return body.get("finance") or {}, body.get("revision")


def projects(limit: int = 12) -> list[dict]:
    """Faol (yakunlanmagan) zakazlar - xarajat taqsimlash uchun, eng yangilari birinchi."""
    f, _ = finance()
    items = [p for p in f.get("projects", []) if str(p.get("status", "")) != "Yakunlangan"]
    return [{"id": p["id"], "name": p.get("name", ""), "client": p.get("client", "")} for p in items[:limit]]


def add_expense(type_: str, amount: float, note: str, project_id: str, payment: str = "naqd",
                day: str | None = None) -> str:
    """Xarajat yozadi (zakazga to'liq taqsimlangan - panel qoidasi). Boshqa foydalanuvchi o'zgartirgan bo'lsa qayta urinadi."""
    if payment not in PAYMENT:
        raise RuntimeError("To'lov turi: naqd / klik / shot")
    for _ in range(3):
        f, rev = finance()
        if not any(str(p.get("id")) == str(project_id) for p in f.get("projects", [])):
            raise RuntimeError("Zakaz topilmadi")
        rec = {"id": uuid.uuid4().hex[:12], "date": day or date.today().isoformat(), "type": type_[:60],
               "amount": float(amount), "paymentType": payment, "note": note[:500], "workerId": None, "founderId": None,
               "allocations": [{"projectId": project_id, "amount": float(amount)}]}
        f.setdefault("expenses", []).insert(0, rec)
        try:
            _api("PUT", "/api/finance", json={"finance": f, "revision": rev})
            return rec["id"]
        except RuntimeError as e:
            if "o'zgartirilgan" in str(e) or "yangilandi" in str(e):
                continue  # 409 - boshqa foydalanuvchi bir vaqtda yozdi
            raise
    raise RuntimeError("Planet Print band - keyinroq qayta urinib ko'ring")


# ---------------- Guruhdagi ro'yxatlar ----------------
def parse(text: str) -> list[dict]:
    """«AVTO MAKTAB 12.180.000 SOM» qatorlari -> [{name, amount}]. 2 tadan kam qator bo'lsa - ro'yxat emas."""
    items = []
    for line in (text or "").splitlines():
        m = LINE.match(line)
        if m:
            amount = int(re.sub(r"\D", "", m.group("sum")))
            if amount >= 1000:
                items.append({"name": m.group("name").strip(" -:•*"), "amount": amount})
    return items if len(items) >= 2 else []


def classify(items: list[dict], ready: list[str]) -> list[dict]:
    """Har bandga «material» (xarajat bo'lishi mumkin) yoki «boshqa» (mijoz, to'lov, xizmat) belgisi."""
    marks = {}
    if ready:
        from .service import _ask_json
        prompt = ("Planet Print (tashqi reklama ishlab chiqarish) uchun ro'yxat. Har band XARAJAT/MATERIAL (sex uchun xarid: "
                  "material, ehtiyot qism, yoqilg'i, ta'mir) yoki BOSHQA (mijoz nomi, kirim, to'lov, qarz) ekanini aniqla.\n"
                  + "\n".join(f"{n}. {i['name']} - {i['amount']}" for n, i in enumerate(items, 1))
                  + '\nFAQAT JSON: {"items": [{"n": 1, "kind": "material|boshqa", "why": "qisqa"}]}')
        try:
            marks = {int(x["n"]): x for x in _ask_json(prompt, ready, 120).get("items", []) if isinstance(x, dict)}
        except Exception as e:
            log.warning("Ro'yxat AI bilan saralanmadi: %s", e)
    for n, i in enumerate(items, 1):
        guess = marks.get(n, {})
        i["kind"] = guess.get("kind") if guess.get("kind") in ("material", "boshqa") else (
            "material" if MATERIAL.search(i["name"]) else "boshqa")
        i["why"] = guess.get("why", "")
    return items


def money(v: float) -> str:
    return f"{int(v):,}".replace(",", " ") + " so'm"


def new_batch(items: list[dict], source: str, author: str) -> str:
    st = _state()
    bid = uuid.uuid4().hex[:6]
    st.setdefault("batches", {})[bid] = {"items": items, "source": source, "author": author,
                                         "at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    st["batches"] = dict(list(st["batches"].items())[-30:])
    _save(st)
    return bid


def batch(bid: str) -> dict | None:
    return _state().get("batches", {}).get(bid)


def report_text(items: list[dict], source: str, author: str) -> str:
    mats = [i for i in items if i["kind"] == "material"]
    other = [i for i in items if i["kind"] != "material"]
    total = sum(i["amount"] for i in items)
    lines = [f"💰 {author} ({source}) ro'yxat tashladi - jami {money(total)}. Eslatmaga qo'yildi.", ""]
    if mats:
        lines.append("📦 XARAJAT / MATERIAL bo'lishi mumkin (qo'shish uchun tugmani bosing):")
        lines += [f"  {n}. {i['name']} - {money(i['amount'])}" for n, i in enumerate(items, 1) if i["kind"] == "material"]
    if other:
        lines.append("\n📌 BOSHQA (mijoz / to'lov - faqat eslatma):")
        lines += [f"  {n}. {i['name']} - {money(i['amount'])}" for n, i in enumerate(items, 1) if i["kind"] != "material"]
    lines.append("\nIstalgan bandni Planet Print xarajatiga qo'shish mumkin - raqamli tugmani bosing.")
    return "\n".join(lines)


def remember(items: list[dict], source: str, author: str) -> None:
    """Ro'yxatni oddiy eslatmaga qo'yadi (ertasi kun 09:00)."""
    from .memory import memory
    due = (datetime.now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    body = "; ".join(f"{i['name']} {money(i['amount'])}" for i in items)
    memory.add_reminder(f"💰 {author} ({source}) ro'yxati: {body}"[:900], due)


# ---------------- Telegram guruh kuzatuvi (shaxsiy akkaunt, faqat o'qish) ----------------
def start_watch(on_list) -> None:
    """Guruhlarga tushgan pul ro'yxatlarini kuzatadi: on_list(items, source, author) chaqiriladi."""
    import threading

    def register():
        from telethon import events
        from . import tg_account
        if not tg_account.authorized():
            return

        async def setup(client):
            async def handler(event):
                text = event.raw_text or ""
                items = parse(text)
                if not items:
                    return
                chat = await event.get_chat()
                sender = await event.get_sender()
                author = " ".join(filter(None, [getattr(sender, "first_name", ""), getattr(sender, "last_name", "")])) or "?"
                source = getattr(chat, "title", "") or "guruh"
                threading.Thread(target=on_list, args=(items, source, author), daemon=True).start()
            client.add_event_handler(handler, events.NewMessage(func=lambda e: e.is_group))
            return True
        tg_account._run(setup)
        log.info("Planet Print: guruhlardagi pul ro'yxatlari kuzatilmoqda")
    threading.Thread(target=lambda: (time.sleep(40), register()), daemon=True).start()
