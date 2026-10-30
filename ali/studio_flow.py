"""Kreativ video oqimi (telefondan): Ali brif beradi -> egasi rasmlarni ChatGPT/Gemini ilovasida yaratadi -> botga yoki
@planetprint_reels kanaliga tashlaydi -> Ali videoni o'zi yig'adi va kanalga joylaydi.

Nega shunday: Pro obuna (ChatGPT/Gemini) faqat ilova ichida ishlaydi; ilovani dastur bilan boshqarish akkauntni xavf
ostiga qo'yadi. Rasmni egasi yaratadi (1 bosish), qolgan hammasi - Ali: brif, promptlar, ovoz, subtitr, montaj, joylash.
Har video uslubi «[video_montajchi] Uslub» bilimi bo'lib saqlanadi va keyingi briflarda ishlatiladi.
"""
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

import httpx

from .config import config

log = logging.getLogger("ali.studio")

STATE = config.data_dir / "studio_briefs.json"
CHANNEL = os.getenv("VIDEO_CHANNEL", "planetprint_reels").lstrip("@")  # «🎬 Planet Print | Reels studiya"
QUERY = re.compile(r"(brif|бриф|kreativ|креатив|rasmli\s+video|расмли\s+видео|virus|вирус)", re.I)
TAG = re.compile(r"#?\s*[BbВв](\d{1,4})")

BRIEF = """Sen Instagram strategi va Reels rejissyorisan. Egang: targetolog va tashqi reklama agentligi egasi (Planet Print,
Beshariq). Maqsad - Instagram tavsiyasiga (Explore/Reels) chiqadigan VIRUSLI, kreativ Reels.
Mavzu / topshiriq: {task}
{styles}
Egang rasmlarni ChatGPT yoki Gemini ilovasida O'ZI yaratadi - har sahna uchun tayyor, batafsil INGLIZCHA rasm prompti yoz
(vertikal 9:16, fotorealistik yoki kinematografik, MATNSIZ - yozuvni Ali qo'yadi, brend ranglari, aniq kompozitsiya).
Egamning darslari kunduzi - Instagram ishlari faqat 13:00 dan keyin.

FAQAT JSON qaytar:
{{"title": "...", "hook": "birinchi 1-2 soniyadagi kuchli yozuv (o'zbekcha)",
  "scenes": [{{"title": "ekrandagi qisqa yozuv (3-6 so'z)", "narration": "diktor matni (o'zbekcha, 1-2 gap)",
              "image_prompt": "English detailed prompt, vertical 9:16, no text", "duration": 3}}],
  "caption": "post matni (CTA bilan)", "hashtags": "#... (8-12 ta)",
  "post_time": "kun va soat (masalan: bugun 19:30) + nega",
  "trial": "Instagram «sinov Reels» (trial reels - faqat obunachi bo'lmaganlarga) qilib joylashmi: ha/yo'q + nega",
  "why_viral": "nega tavsiyaga chiqishi mumkin (2-3 gap)",
  "style": "uslub: ranglar, shrift, ritm, o'tishlar, kayfiyat (1-2 gap)"}}
Sahnalar soni: 4-6."""


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"next": 1, "briefs": {}, "channel_last": 0}


def _save(state: dict) -> None:
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


INSTANT = re.compile(r"rasmsiz|расмсиз|darhol|дарҳол|дархол|gradient|tezkor\s+video", re.I)


def is_query(text: str) -> bool:
    """Brif yo'li: «kreativ/virusli video, brif» yoki oddiy «video yarat» (egasi 2-yo'lni tanlagan - rasmlarni o'zi
    ilovada yaratadi). «rasmsiz / darhol» deyilsa - tezkor (gradient) video, bu yo'l emas."""
    from . import montage
    t = text or ""
    if INSTANT.search(t):
        return False
    brief = bool(QUERY.search(t)) and bool(re.search(r"video|видео|reels|рилс|ролик", t, re.I))
    return brief or montage.is_creation(t)


def waiting() -> dict | None:
    """Rasm kutayotgan oxirgi brif."""
    briefs = [b for b in _state()["briefs"].values() if b["status"] == "waiting"]
    return max(briefs, key=lambda b: b["id"]) if briefs else None


def _styles() -> str:
    from .memory import memory
    rows = memory.relevant_knowledge("video uslub reels", "[video_montajchi] Uslub", 3)
    return ("Oldingi muvaffaqiyatli uslublar (shunga yaqin, lekin takrorlamasdan):\n" +
            "\n".join(f"- {r['content'][:300]}" for r in rows)) if rows else ""


def start(task: str, ready: list[str]) -> list[str]:
    """Brif tuzadi va saqlaydi. Telegram'ga yuboriladigan xabarlar ro'yxatini qaytaradi."""
    from .service import _ask_json
    data = _ask_json(BRIEF.format(task=task[:1500], styles=_styles()), ready, 300)
    scenes = [s for s in data.get("scenes", []) if isinstance(s, dict) and s.get("image_prompt")][:6]
    if not scenes:
        raise RuntimeError("Brif tuzilmadi (sahnalar yo'q) - mavzuni aniqroq yozing")
    state = _state()
    try:  # kanaldagi eski rasmlar yangi brifga aralashmasin - hozirgi oxirgi post belgilanadi
        from . import tg_account

        async def top(client):
            async for m in client.iter_messages(CHANNEL, limit=1):
                return m.id
            return 0
        state["channel_last"] = max(state.get("channel_last", 0), tg_account._run(top) or 0)
    except Exception as e:
        log.warning("Kanal belgilanmadi: %s", e)
    bid = state["next"]
    state["next"] += 1
    state["briefs"][str(bid)] = {"id": bid, "task": task, "status": "waiting", "at": time.time(), "images": [],
                                 **{k: data.get(k, "") for k in ("title", "hook", "caption", "hashtags", "post_time",
                                                                 "trial", "why_viral", "style")}, "scenes": scenes}
    _save(state)
    head = (f"🎬 Brif #B{bid}: {data.get('title', '')}\n\n🪝 Hook: {data.get('hook', '')}\n"
            f"🕒 Joylash: {data.get('post_time', '')}\n🧪 Sinov Reels: {data.get('trial', '')}\n"
            f"🔥 Nega tavsiyaga chiqadi: {data.get('why_viral', '')}\n🎨 Uslub: {data.get('style', '')}\n\n"
            f"📲 QADAMLAR (telefonda):\n1) Pastdagi {len(scenes)} ta promptni ChatGPT yoki Gemini ilovasiga birma-bir "
            f"yuboring.\n2) Chiqqan rasmlarni TARTIB BILAN shu botga yoki @{CHANNEL} kanaliga tashlang.\n"
            f"3) Hammasi kelgach Ali videoni o'zi yig'adi va kanalga joylaydi. Kamroq rasm bilan qilish: «#B{bid} video qil».")
    prompts = [f"🖼 {i}/{len(scenes)} — {s.get('title', '')}\n\n{s['image_prompt']}" for i, s in enumerate(scenes, 1)]
    return [head, *prompts]


def add_image(path: str, caption: str = "") -> tuple[dict | None, str]:
    """Rasmni brifga qo'shadi. (to'lgan brif yoki None, holat matni)."""
    state = _state()
    m = TAG.search(caption or "")
    brief = state["briefs"].get(m.group(1)) if m else None
    brief = brief if brief and brief["status"] == "waiting" else waiting()
    if not brief:
        return None, ""
    b = state["briefs"][str(brief["id"])]
    b["images"].append(str(path))
    _save(state)
    need = len(b["scenes"])
    if len(b["images"]) >= need:
        return b, f"✅ #B{b['id']}: {need}/{need} rasm keldi - videoni yig'yapman…"
    return None, f"🖼 #B{b['id']}: {len(b['images'])}/{need} rasm qabul qilindi"


def build(bid: int, progress=lambda note: None) -> dict:
    """Videoni yig'adi (rasmlar fon, diktor ovozi, subtitr, sahna yozuvlari), kanalga joylaydi, uslubni eslab qoladi."""
    from . import outbox
    from .memory import memory
    from .plugins.video_studio import make_content_video
    state = _state()
    b = state["briefs"][str(bid)]
    b["status"] = "building"
    _save(state)
    scenes = [{"title": (b["hook"] if i == 0 and b.get("hook") else s.get("title", "")), "text": s.get("title", "") if i else "",
               "narration": s.get("narration", ""), "image_prompt": s.get("image_prompt", ""),
               "duration": s.get("duration", 3)} for i, s in enumerate(b["scenes"])]
    start = outbox.mark()
    try:
        result = make_content_video(b.get("title") or b["task"], scenes=scenes, images=b["images"],
                                    ai_images=False, platform="reels")
    except Exception:
        b["status"] = "waiting"
        _save(state)
        raise
    files = outbox.since(start)
    video = next((f for f in files if f.suffix == ".mp4"), None)
    b["status"], b["video"] = "done", str(video) if video else ""
    _save(state)
    posted = ""
    if video:
        caption = f"{b.get('caption', '')}\n\n{b.get('hashtags', '')}\n\n🕒 {b.get('post_time', '')}"[:1000]
        try:
            from . import tg_account
            tg_account.send_file(CHANNEL, str(video), caption)
            posted = f"📢 @{CHANNEL} kanaliga joylandi"
        except Exception as e:
            posted = f"⚠️ Kanalga joylanmadi: {e}"
        memory.add_knowledge(f"[video_montajchi] Uslub: {b.get('title', '')[:60]}",
                             f"Uslub: {b.get('style', '')}\nHook: {b.get('hook', '')}\nMavzu: {b['task'][:200]}\n"
                             f"Nega virusli: {b.get('why_viral', '')}")
    return {"text": f"{result}\n{posted}", "files": [str(f) for f in files]}


# --- @kanal kuzatuvi: rasm kutayotgan brif bo'lsa, kanalga tashlangan yangi rasmlar olinadi ---
def _poll_channel(notify) -> None:
    from . import tg_account
    if not waiting() or not tg_account.authorized():
        return
    state = _state()
    last = state.get("channel_last", 0)
    folder = config.data_dir / "inbox" / "studio"
    folder.mkdir(parents=True, exist_ok=True)

    async def go(client):
        got = []
        async for m in client.iter_messages(CHANNEL, limit=30, min_id=last):
            if m.photo or (m.file and (m.file.mime_type or "").startswith("image/")):
                path = await m.download_media(file=str(folder))
                got.append((m.id, path, m.text or ""))
            state["channel_last"] = max(state.get("channel_last", 0), m.id)
        return sorted(got)
    try:
        items = tg_account._run(go)
    except Exception as e:
        log.warning("Kanal kuzatilmadi: %s", e)
        return
    fresh = _state()
    fresh["channel_last"] = state.get("channel_last", last)
    _save(fresh)
    for _, path, caption in items:
        full, note = add_image(path, caption)
        if note:
            notify(note)
        if full:
            threading.Thread(target=_build_and_send, args=(full["id"], notify), daemon=True).start()


def _build_and_send(bid: int, notify) -> None:
    try:
        res = build(bid)
    except Exception as e:
        notify(f"⚠️ #B{bid} video yig'ilmadi: {e}")
        return
    send_files(res["text"], res["files"])


def send_files(text: str, files: list[str]) -> None:
    """Natijani egasiga Telegram bot orqali yuboradi (video - video bo'lib, qolgani - fayl)."""
    api = f"https://api.telegram.org/bot{config.telegram_token}"
    uid = config.telegram_owner_id
    if not (config.telegram_token and uid):
        return
    try:
        httpx.post(api + "/sendMessage", data={"chat_id": uid, "text": text[:4000]}, timeout=30)
        for f in files:
            kind, field = ("sendVideo", "video") if f.endswith(".mp4") else ("sendDocument", "document")
            with open(f, "rb") as fh:
                httpx.post(f"{api}/{kind}", data={"chat_id": uid}, files={field: (Path(f).name, fh)}, timeout=300)
    except (httpx.HTTPError, OSError) as e:
        log.warning("Studio natijasi yuborilmadi: %s", e)


def loop(notify) -> None:
    while True:
        time.sleep(60)
        try:
            _poll_channel(notify)
        except Exception:
            log.exception("Studio kanal kuzatuvi xatosi")


def start_watch(notify) -> None:
    threading.Thread(target=loop, args=(notify,), daemon=True, name="studio").start()
