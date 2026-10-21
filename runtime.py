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
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from ali import agents, auth, autopilot, plugins, providers, scheduler, tts
from ali.config import ROOT, config
from ali.hub import hub
from ali.memory import memory
from ali.monitor import monitor
from ali.service import AskError, brain, run_ask, team

WEB = ROOT / "web"
COOKIE = "ali_token"

logging.basicConfig(
    filename=config.log_path, level=logging.INFO, encoding="utf-8",
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
log = logging.getLogger("ali.server")
# httpx logs contain Telegram's token-bearing request URLs.
logging.getLogger("httpx").setLevel(logging.WARNING)


def is_authed(cookies) -> bool:
    return auth.check_token(cookies.get(COOKIE, ""))


async def json_object(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="JSON formati noto‘g‘ri")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON obyekt yuborilishi kerak")
    return body


# --- Ilova ---
@asynccontextmanager
async def lifespan(_app):
    hub.loop = asyncio.get_running_loop()
    scheduler.start(hub.notify)
    autopilot.start(brain)
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
    try:
        yield
    finally:
        if bot:
            await bot.stop()
        hub.loop = None


app = FastAPI(title="Ali", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB), name="static")

from ali.mobile_api import router as mobile_router  # noqa: E402 - telefon ilovasi API'si
app.include_router(mobile_router)


@app.get("/healthz")
async def health():
    return {"ok": True}


@app.get("/")
async def index(request: Request):
    if not is_authed(request.cookies):
        return RedirectResponse("/login")
    return FileResponse(WEB / "index.html")


@app.get("/privacy")
async def privacy_page():
    # App Store va Play Market talab qiladigan maxfiylik siyosati
    return FileResponse(WEB / "privacy.html")


@app.get("/login")
async def login_page():
    return FileResponse(WEB / "login.html")


@app.get('/miniapp')
async def miniapp_page():
    return FileResponse(WEB/'miniapp.html',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})


@app.post('/api/telegram/login')
async def telegram_login(request: Request):
    if request.headers.get('origin') and request.headers['origin'].rstrip('/')!=str(request.base_url).rstrip('/'):
        return JSONResponse({'ok':False},status_code=403)
    body=await json_object(request)
    if not auth.telegram_owner(body.get('init_data')):
        return JSONResponse({'ok':False,'error':'Mini App faqat Abbos uchun. Botdagi tugmadan qayta oching.'},status_code=403)
    response=JSONResponse({'ok':True,'name':'Abbos'},headers={'Cache-Control':'no-store'})
    # Telegram Desktop/Web Mini App'ni iframe ichida ochadi: u yerda cookie faqat SameSite=None; Secure bilan yuboriladi.
    secure=request.url.scheme=='https' or request.headers.get('x-forwarded-proto')=='https'
    response.set_cookie(COOKIE,auth.telegram_session(),max_age=8*3600,httponly=True,
                        secure=secure,samesite='none' if secure else 'lax')
    return response


@app.post("/api/login")
async def login(request: Request):
    body = await json_object(request)
    if not auth.check_password(body.get("password", "")):
        await asyncio.sleep(1.5)  # parol terishni sekinlashtirish
        return JSONResponse({"ok": False, "locked": auth.locked_for()}, status_code=401)
    response = JSONResponse({"ok": True})
    response.set_cookie(COOKIE, auth.TOKEN, max_age=60 * 60 * 24 * 365, httponly=True,
                        secure=request.url.scheme == "https", samesite="lax")
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
            "gemini": "ovoz va rasm" if config.gemini_api_key else None,
        },
        "devices": hub.summary(),
        "agents": [a.summary() for a in brain.agents.values()],
        "plugins": plugins.summary(),
        "telegram": bool(hub.listeners),
        "voice": voice.get("name") if voice["provider"] == "elevenlabs" else voice.get("voice"),
        "facts": len(memory.all_facts()),
        "knowledge": len(memory.knowledge_topics()),
        "instagram": list(config.ig_accounts),
        "wake_words": config.wake_words,
        "stt_language": config.stt_language,
        "server_stt": providers.can_transcribe(),
    }


@app.get("/api/monitor")
async def monitor_state(request: Request):
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    snapshot = monitor.snapshot(team())
    snapshot["learning"] = autopilot.learning_status(brain)
    return snapshot


@app.get("/api/agents")
async def agents_list(request: Request):
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    tools = [{"name": "web_search", "description": "Internetdan qidirish", "dangerous": False}] + [
        {"name": s.name, "description": s.description, "dangerous": s.dangerous} for s in brain.registry.values()]
    return {"agents": [a.full() for a in agents.load().values()], "tools": tools}


@app.get("/api/outbox/{name}")
async def outbox_file(name: str, request: Request):
    """Agentlar yaratgan Office fayllari (faqat kirgan foydalanuvchiga)."""
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    from ali import outbox
    path = outbox.resolve(name)
    if path is None:
        return JSONResponse({"error": "Fayl topilmadi"}, status_code=404)
    return FileResponse(path, filename=path.name)


@app.get("/api/vault")
async def vault_list(request: Request, q: str = '', folder: str = '', offset: int = 0):
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    return memory.vault_list(q[:300], folder, max(0, offset))


@app.get("/api/permissions")
async def permissions_get(request: Request):
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    from ali import permissions
    data = permissions.catalog(brain.registry)
    from ali.connections import catalog
    data['connections'] = catalog(bool(hub.listeners))
    return data


@app.post('/api/connections/{provider}')
async def connection_save(provider: str, request: Request):
    if not is_authed(request.cookies):return JSONResponse({},status_code=401)
    if request.headers.get('origin') and request.headers['origin'].rstrip('/')!=str(request.base_url).rstrip('/'):
        return JSONResponse({'error':'Boshqa manbadan so‘rov rad etildi'},status_code=403)
    from ali.connections import connect
    body=await json_object(request)
    try:return await connect(provider,body.get('token'))
    except ValueError as error:return JSONResponse({'error':str(error)},status_code=400)


def is_local(request: Request) -> bool:
    """So'rov aynan shu kompyuterdan (localhost) - tunnel/proxy orqali emas."""
    host = (request.headers.get("host") or "").split(":")[0]
    proxied = any(h in request.headers for h in ("x-forwarded-for", "cf-connecting-ip", "x-real-ip"))
    return (request.client is not None and request.client.host in ("127.0.0.1", "::1")
            and host in ("localhost", "127.0.0.1", "[::1]") and not proxied)


@app.get("/api/local-access")
async def local_access_get(request: Request):
    """Kompyuterdagi AI ilovalari (Claude, ChatGPT, Gemini) - ruxsat holati. Faqat localhost'da so'raladi."""
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    from ali import local_ai
    return {**local_ai.summary(), "local": is_local(request)}


@app.post("/api/local-access")
async def local_access_save(request: Request):
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    if not is_local(request):
        return JSONResponse({"error": "Ruxsat faqat shu kompyuterning o'zidan beriladi"}, status_code=403)
    if request.headers.get('origin') and request.headers['origin'].rstrip('/') != str(request.base_url).rstrip('/'):
        return JSONResponse({'error': 'Boshqa manbadan so‘rov rad etildi'}, status_code=403)
    body = await json_object(request)
    if not isinstance(body.get("allowed"), bool):
        return JSONResponse({"error": "allowed: true/false"}, status_code=400)
    from ali import local_ai
    local_ai.set_access(body["allowed"])
    return local_ai.summary()


@app.post("/api/permissions")
async def permissions_save(request: Request):
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    if request.headers.get('origin') and request.headers['origin'].rstrip('/') != str(request.base_url).rstrip('/'):
        return JSONResponse({'error':'Boshqa manbadan so‘rov rad etildi'}, status_code=403)
    from ali import permissions
    body = await json_object(request)
    try:
        permissions.save(body.get('rules') if isinstance(body, dict) else None, brain.registry)
    except (ValueError, TypeError):
        return JSONResponse({'error':'Ruxsatlar formati noto‘g‘ri'}, status_code=400)
    return {'ok':True}


@app.get("/api/vault/entry")
async def vault_entry(request: Request, id: str):
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    row = memory.vault_detail(id)
    return row if row else JSONResponse({"error": "Yozuv topilmadi"}, status_code=404)


@app.post("/api/vault")
async def vault_save(request: Request):
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    body = await json_object(request)
    title, content = body.get('title'), body.get('content')
    if not isinstance(title, str) or not isinstance(content, str) or not title.strip() or not content.strip() or len(title)>200 or len(content)>20000:
        return JSONResponse({"error": "Sarlavha va matnni tekshiring (200 / 20000 belgi)."}, status_code=400)
    return {"id": memory.add_vault_note(title, content)}


@app.post("/api/agents")
async def agents_save(request: Request):
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    b = await json_object(request)
    if not isinstance(b.get('tools', []), list) or not isinstance(b.get('learn', []), list):
        return JSONResponse({'error': 'Vositalar va mavzular ro‘yxat bo‘lishi kerak'}, status_code=400)
    try:
        a = agents.save(str(b.get("key", "")), str(b.get("name", "")), str(b.get("icon", "")),
                        str(b.get("description", "")), [str(t) for t in b.get("tools") or [] if str(t) in brain.registry or t == "web_search"],
                        str(b.get("prompt", "")), [str(t) for t in b.get("learn") or []])
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True, "agent": a.full()}


@app.delete("/api/agents/{key}")
async def agents_delete(key: str, request: Request):
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    try:
        return {"ok": agents.delete(key)}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/tts")
async def speak(request: Request):
    if not is_authed(request.cookies):
        return Response(status_code=401)
    body = await json_object(request)
    if not isinstance(body.get('text', ''), str):
        return JSONResponse({'error': 'Matn satr bo‘lishi kerak'}, status_code=400)
    audio = await tts.synthesize(body.get("text", ""))
    return Response(audio, media_type="audio/mpeg") if audio else Response(status_code=204)


@app.post("/api/transcribe")
async def transcribe(request: Request, file: UploadFile = File(...)):
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    if not providers.can_transcribe():
        return JSONResponse({"error": "GEMINI_API_KEY yo'q"}, status_code=400)
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
    await ws.send_json({"type": "history", "messages": memory.recent_messages(brain.session_id)})
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
                if brain.lock.locked():
                    await ws.send_json({"type": "busy"})
                    continue
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
                      source=device_id, req_id=msg.get("id"), agent=str(msg.get("agent") or "") or None)
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
