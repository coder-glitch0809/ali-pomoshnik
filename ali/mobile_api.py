"""Telefon ilovasi (Android / iPhone) uchun API.

Foydalanuvchi ilovada Firebase Auth orqali kiradi va har so'rovda ID tokenini yuboradi
(Authorization: Bearer <token>). Server tokenni tekshiradi, javob beradi va telefonda bajariladigan
amallarni (ilova ochish, sozlamalar...) qaytaradi. Suhbat tarixi va profil telefondan to'g'ridan-to'g'ri
foydalanuvchining o'z Firestore hujjatida saqlanadi - server ularni saqlamaydi.
"""
import asyncio
import json
import logging
import threading
import time
from datetime import date

from fastapi import APIRouter, HTTPException, Request

from . import public_ai
from .config import config

log = logging.getLogger("ali.mobile")
router = APIRouter(prefix="/api/mobile")

# Telefon bajara oladigan amallar: nomi -> kerakli imkoniyat (ilova yuboradigan capabilities ro'yxatidan)
ACTIONS = {
    "open_app": "apps",            # {"target": "telegram"} - ilovani ochish
    "open_url": "web",             # {"target": "https://..."}
    "open_settings": "settings",   # {"target": "wifi|bluetooth|location|display|sound|apps|battery|main"}
    "call": "phone",               # {"target": "+998..."} - qo'ng'iroq oynasini ochadi
    "sms": "phone",                # {"target": "+998...", "text": "..."}
    "global": "control",           # {"target": "back|home|recents|notifications|quick_settings"}
    "click_text": "control",       # {"target": "Yuborish"} - ekrandagi tugmani bosish (APK versiya)
    "type_text": "control",        # {"target": "matn"} - faol maydonga yozish (APK versiya)
}
SETTINGS = {"wifi", "bluetooth", "location", "display", "sound", "apps", "battery", "main"}
_lock = threading.Lock()
_firebase = None


def _verify(request: Request) -> dict:
    """Firebase ID tokenini tekshiradi va foydalanuvchi ma'lumotini qaytaradi."""
    global _firebase
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Avval tizimga kiring")
    if not config.firebase_project_id:
        raise HTTPException(status_code=503, detail="Server Firebase bilan sozlanmagan (FIREBASE_PROJECT_ID)")
    import firebase_admin
    from firebase_admin import auth as fb_auth
    with _lock:
        if _firebase is None:
            _firebase = firebase_admin.initialize_app(options={"projectId": config.firebase_project_id}, name="ali-mobile")
    try:
        return fb_auth.verify_id_token(header[7:].strip(), app=_firebase)
    except Exception:
        raise HTTPException(status_code=401, detail="Kirish muddati tugagan. Qayta kiring.") from None


def _usage_path():
    return config.data_dir / "mobile_usage.json"


def _take_quota(uid: str, limit: int) -> int | None:
    """Kunlik limitdan bittasini oladi; qolgan sonni yoki limit tugagan bo'lsa None qaytaradi."""
    today = date.today().isoformat()
    with _lock:
        try:
            usage = json.loads(_usage_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            usage = {}
        if usage.get("day") != today:
            usage = {"day": today, "users": {}}
        used = usage["users"].get(uid, 0)
        if used >= limit:
            return None
        usage["users"][uid] = used + 1
        tmp = _usage_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(usage), encoding="utf-8")
        tmp.replace(_usage_path())
        return limit - used - 1


def _system(name: str, platform: str, caps: set[str]) -> str:
    allowed = [a for a, cap in ACTIONS.items() if cap in caps]
    actions = ("\nTelefonda bajarish mumkin bo'lgan amallar (faqat foydalanuvchi so'raganda): " + ", ".join(allowed)
               + ". open_settings target: " + "|".join(sorted(SETTINGS)) + "; global target: back|home|recents|"
               "notifications|quick_settings.") if allowed else "\nTelefonda amal bajarish imkoni yo'q."
    return (f"Sen {config.assistant_name} - shaxsiy AI yordamchisan. Foydalanuvchi ismi: {name or 'foydalanuvchi'}. "
            f"U {platform} telefonidan yozmoqda. Oddiy savolga qisqa va oddiy javob ber (1-3 gap), batafsil so'ralsa - "
            "batafsil. Foydalanuvchi qaysi tilda yozsa, o'sha tilda javob ber (standart: o'zbek). Boshqa foydalanuvchilar "
            "yoki server egasi haqida ma'lumoting yo'q. Qila olmaydigan ishni qildim deb aytma." + actions +
            '\nJavobni faqat JSON qilib qaytar: {"reply": "foydalanuvchiga matn", "actions": [{"type": "open_app", '
            '"target": "telegram"}]}. Amal kerak bo\'lmasa actions bo\'sh ro\'yxat.')


def _parse(raw: str, caps: set[str]) -> tuple[str, list[dict]]:
    text = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        obj = json.loads(text)
    except ValueError:
        return raw.strip(), []
    if not isinstance(obj, dict):
        return raw.strip(), []
    actions = []
    for a in obj.get("actions") or []:
        if not isinstance(a, dict) or ACTIONS.get(a.get("type")) not in caps:
            continue
        target = str(a.get("target", ""))[:500]
        if a["type"] == "open_settings" and target not in SETTINGS:
            target = "main"
        if a["type"] == "open_url" and not target.startswith(("https://", "http://")):
            target = "https://" + target
        item = {"type": a["type"], "target": target}
        if a["type"] == "sms":
            item["text"] = str(a.get("text", ""))[:1000]
        actions.append(item)
    return str(obj.get("reply", "")).strip(), actions[:5]


@router.get("/ping")
async def ping(request: Request):
    """Ilova Vercel manzilidan (GET yo'naltiriladi) haqiqiy server manzilini bilib oladi - POST to'g'ridan-to'g'ri boradi."""
    return {"ok": True, "base": str(request.base_url).rstrip("/"), "firebase": bool(config.firebase_project_id)}


@router.post("/ask")
async def ask(request: Request):
    user = await asyncio.to_thread(_verify, request)
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="JSON formati noto'g'ri") from None
    text = body.get("text") if isinstance(body, dict) else None
    if not isinstance(text, str) or not text.strip() or len(text) > 6000:
        raise HTTPException(status_code=400, detail="Xabar 1-6000 belgi bo'lishi kerak")
    history = [
        {"role": m["role"], "content": m["content"][:6000]}
        for m in (body.get("history") or [])[-10:]
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
        and m["content"].strip()
    ]
    while history and history[0]["role"] != "user":
        history.pop(0)
    caps = {c for c in body.get("capabilities") or [] if isinstance(c, str)}
    left = _take_quota(user["uid"], config.mobile_daily_questions)
    if left is None:
        raise HTTPException(status_code=429, detail=f"Bugungi {config.mobile_daily_questions} ta savol limiti tugadi")
    name = str(body.get("name") or user.get("name") or "")[:80]
    platform = "iPhone" if body.get("platform") == "ios" else "Android"
    try:
        raw = await public_ai.ask_model(False, _system(name, platform, caps), history, text.strip(), 1500,
                                        json_mode=True)
    except Exception:
        log.warning("Telefon javobi xato (uid=%s)", user["uid"], exc_info=True)
        raise HTTPException(status_code=502, detail="AI xizmati hozir javob bera olmadi. Birozdan so'ng urinib ko'ring.") from None
    reply, actions = _parse(raw, caps)
    return {"reply": reply or "Javob olinmadi. Qayta urinib ko'ring.", "actions": actions, "left": left,
            "at": int(time.time())}
