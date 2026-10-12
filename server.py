"""Ali serveri: veb-sayt (telefon va kompyuter) + Telegram bot.

    python server.py
    Kompyuterda:  http://localhost:8000
    Telefonda:    tunnel.bat ishga tushiring (HTTPS havola beradi - mikrofon uchun kerak)
    Telegram:     .env da TELEGRAM_BOT_TOKEN bo'lsa, bot avtomatik ishga tushadi
"""
import asyncio
import logging
import socket
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, File, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from ali import auth, providers, scheduler, tts
from ali.config import ROOT, config
from ali.hub import hub
from ali.memory import memory
from ali.service import AskError, brain, run_ask

WEB = ROOT / "web"
COOKIE = "ali_token"

logging.basicConfig(
    filename=config.log_path, level=logging.INFO, encoding="utf-8",
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
log = logging.getLogger("ali.server")


def is_authed(cookies) -> bool:
    return auth.check_token(cookies.get(COOKIE, ""))


# --- Ilova ---
@asynccontextmanager
async def lifespan(_app):
    hub.loop = asyncio.get_running_loop()
    scheduler.start(hub.notify)
    bot = None
    if config.telegram_token:
        from ali.telegram_bot import TelegramBot
        bot = TelegramBot()
        try:
            await bot.start()
        except Exception as e:
            log.exception("Telegram bot ishga tushmadi")
            print(f"  Telegram:    xato - {e}")
            bot = None
    yield
    if bot:
        await bot.stop()


app = FastAPI(title="Ali", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
async def index(request: Request):
    if not is_authed(request.cookies):
        return RedirectResponse("/login")
    return FileResponse(WEB / "index.html")


@app.get("/login")
async def login_page():
    return FileResponse(WEB / "login.html")


@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    if not auth.check_password(body.get("password", "")):
        await asyncio.sleep(1.5)  # parol terishni sekinlashtirish
        return JSONResponse({"ok": False, "locked": auth.locked_for()}, status_code=401)
    response = JSONResponse({"ok": True})
    response.set_cookie(COOKIE, auth.TOKEN, max_age=60 * 60 * 24 * 365, httponly=True, samesite="lax")
    return response


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(WEB / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/api/status")
async def status(request: Request):
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    voice = tts.current_voice()
    return {
        "assistant": config.assistant_name,
        "user": config.user_name,
        "models": {
            "claude": config.model,
            "openai": config.openai_model if config.openai_api_key else None,
            "gemini": config.gemini_model if config.gemini_api_key else None,
        },
        "devices": hub.summary(),
        "telegram": bool(hub.listeners),
        "voice": voice.get("name") if voice["provider"] == "elevenlabs" else voice.get("voice"),
        "facts": len(memory.all_facts()),
        "knowledge": len(memory.knowledge_topics()),
        "instagram": list(config.ig_accounts),
        "wake_words": config.wake_words,
        "stt_language": config.stt_language,
        "server_stt": providers.can_transcribe(),
    }


@app.post("/api/tts")
async def speak(request: Request):
    if not is_authed(request.cookies):
        return Response(status_code=401)
    audio = await tts.synthesize((await request.json()).get("text", ""))
    return Response(audio, media_type="audio/mpeg") if audio else Response(status_code=204)


@app.post("/api/transcribe")
async def transcribe(request: Request, file: UploadFile = File(...)):
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    if not providers.can_transcribe():
        return JSONResponse({"error": "OPENAI_API_KEY yoki GEMINI_API_KEY yo'q"}, status_code=400)
    data = await file.read()
    text = await asyncio.to_thread(providers.transcribe, data, file.filename or "audio.webm")
    return {"text": text}


# --- Jonli aloqa ---
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    if not is_authed(ws.cookies):
        await ws.close(code=4401)
        return
    await ws.accept()
    device = hub.add(ws, ws.query_params.get("device", "desktop"))
    await ws.send_json({"type": "hello", "device_id": device.id})
    hub.broadcast({"type": "devices", "devices": hub.summary()})
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "ask":
                asyncio.create_task(handle_ask(device.id, msg))
            elif kind == "confirm":
                hub.resolve_confirm(msg.get("id", ""), bool(msg.get("ok")))
            elif kind == "location":
                hub.set_location(device.id, {
                    "lat": msg["lat"], "lon": msg["lon"], "accuracy": msg.get("accuracy"),
                    "device": device.kind, "time": time.strftime("%H:%M:%S"),
                })
            elif kind == "new_session":
                brain.new_session()
                hub.broadcast({"type": "session_reset"})
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove(device.id)
        hub.broadcast({"type": "devices", "devices": hub.summary()})


async def handle_ask(device_id: str, msg: dict):
    text = str(msg.get("text", "")).strip()
    images = msg.get("images") or None
    if not text and not images:
        return
    if brain.lock.locked():
        hub.broadcast({"type": "busy"})
        return
    try:
        await run_ask(text, images, bool(msg.get("deep")), bool(msg.get("super")),
                      source=device_id, req_id=msg.get("id"))
    except AskError:
        pass  # xato allaqachon ekranlarga yuborilgan


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


if __name__ == "__main__":
    print(f"\n  {config.assistant_name} serveri ishga tushdi")
    print(f"  Kompyuter:   http://localhost:{config.port}")
    print(f"  Wi-Fi:       http://{lan_ip()}:{config.port}   (mikrofon faqat HTTPS da ishlaydi -> tunnel.bat)")
    if not config.access_password:
        print(f"  Parol:       {auth.PASSWORD}   (data/password.txt; .env da ACCESS_PASSWORD bilan o'zgartiring)")
    uvicorn.run(app, host=config.host, port=config.port, log_level="warning")
