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
    from ali import cloud
    cloud.start()  # xotiraning Firebase'dagi nusxasi (kalit bo'lsa)
    from ali import obsidian
    obsidian.start()  # xotira Obsidian omborida (Ali papkasi), o'rnatilgan bo'lsa
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


@app.middleware("http")
async def fresh_assets(request: Request, call_next):
    """Brauzer sahifa va JS/CSS ning eski nusxasini ko'rsatmasin: har safar serverdan tekshiradi (o'zgarmagan
    bo'lsa 304 - tez). Aks holda yangilanishdan keyin localhost va boshqa manzillarda sayt har xil ko'rinadi."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/") or path in ("/", "/miniapp", "/login"):
        response.headers["Cache-Control"] = "no-cache"
    return response

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


@app.get("/ig-media/{name}")
async def ig_media(name: str):
    """Instagram joylash uchun vaqtinchalik ochiq rasm (tasodifiy 32 belgili nom, joylangach o'chiriladi)."""
    import re
    from ali.skills.instagram import PUBLIC_MEDIA
    if not re.fullmatch(r"[0-9a-f]{32}\.(jpe?g|png|webp)", name) or not (PUBLIC_MEDIA / name).is_file():
        return JSONResponse({}, status_code=404)
    return FileResponse(PUBLIC_MEDIA / name)


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
    return {**local_ai.summary(), "local": is_local(request), "facts": len(memory.all_facts())}


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


@app.get("/api/dashboard")
async def dashboard_data(request: Request, refresh: int = 0):
    """Asosiy ekran: ob-havo, kripto, aksiya/fyuchers, yangiliklar (10 daqiqa kesh)."""
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    from ali import dashboard
    return await asyncio.to_thread(dashboard.get, bool(refresh))


@app.get("/api/memory-info")
async def memory_info(request: Request):
    """Ali xotirasi qayerda va nimalar saqlangan - egasi aniq bilib tursin."""
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    from ali import agents as agents_mod
    from ali.agents import split_lessons
    from ali import obsidian
    from ali.memory import JOURNAL_DIR
    team = []
    for a in agents_mod.load().values():
        _, lessons = split_lessons(a.prompt)
        team.append({"key": a.key, "name": a.name, "icon": a.icon, "lessons": len(lessons), "learn": len(a.learn),
                     "knowledge": memory.agent_knowledge_summary(a.key)["count"]})
    return {**memory.stats(), "db": str(config.db_path.resolve()), "journal": str(JOURNAL_DIR.resolve()),
            "agents_dir": str(agents_mod.AGENTS_DIR.resolve()), "team": team, "local": is_local(request),
            "obsidian": str(obsidian.root() or ""), "obsidian_uri": obsidian.open_uri()}


@app.post("/api/memory-open")
async def memory_open(request: Request):
    """Xotira papkasini shu kompyuterda Explorer'da ochadi (faqat localhost)."""
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    if not is_local(request):
        return JSONResponse({"error": "Faqat shu kompyuterdan"}, status_code=403)
    import os
    from ali.memory import JOURNAL_DIR
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    os.startfile(str(JOURNAL_DIR.resolve()))
    return {"ok": True}


MEMORY_SOURCES = {"codex": "ChatGPT", "claude": "Claude", "gemini": "Gemini", "other": "Boshqa"}


@app.post("/api/memory-import")
async def memory_import(request: Request):
    """ChatGPT / Claude / Gemini'dagi saqlangan xotiralarni Ali xotirasiga qo'shadi (egasi nusxalab joylaydi)."""
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    if request.headers.get('origin') and request.headers['origin'].rstrip('/') != str(request.base_url).rstrip('/'):
        return JSONResponse({'error': 'Boshqa manbadan so‘rov rad etildi'}, status_code=403)
    import hashlib
    import re
    body = await json_object(request)
    source = MEMORY_SOURCES.get(str(body.get("source")), "Boshqa")
    text = str(body.get("text") or "")[:20000]
    lines = [re.sub(r"^\s*(?:[-*•·]|\d+[.)])\s*", "", line).strip() for line in text.splitlines()]
    lines = [l for l in lines if len(l) >= 3][:150]
    if not lines:
        return JSONResponse({"error": "Xotira matni bo‘sh"}, status_code=400)
    known = set(memory.all_facts().values())
    added = 0
    for line in lines:
        if line[:500] in known:
            continue
        memory.set_fact(f"{source} xotirasi {hashlib.sha1(line.encode()).hexdigest()[:6]}", line[:500])
        added += 1
    memory.add_knowledge(f"[xotira] {source} saqlangan xotiralari", "\n".join(f"- {l}" for l in lines))
    from ali.evolution import refresh_ali
    refresh_ali(brain)  # yangi faktlar Ali ko'rsatmasiga darhol kirsin
    return {"message": f"{source}: {added} ta yangi xotira qo‘shildi ({len(lines) - added} tasi allaqachon bor edi)",
            "facts": len(memory.all_facts())}


@app.post("/api/ai-apps/{key}/{action}")
async def ai_app_action(key: str, action: str, request: Request):
    """AI ilovasini API'siz ulash: o'rnatish, kirish oynasini ochish, tekshirish (eslab qolinadi), unutish.
    Faqat shu kompyuterdan - ilova shu kompyuterda ishlaydi."""
    if not is_authed(request.cookies):
        return JSONResponse({}, status_code=401)
    if not is_local(request):
        return JSONResponse({"error": "Ilovalarni faqat shu kompyuterning o'zidan ulash mumkin"}, status_code=403)
    if request.headers.get('origin') and request.headers['origin'].rstrip('/') != str(request.base_url).rstrip('/'):
        return JSONResponse({'error': 'Boshqa manbadan so‘rov rad etildi'}, status_code=403)
    from ali import local_ai
    if key == "_coach" and action == "learn":  # hozir: barcha agentlarni Pro AI'lardan o'qitish (fonda)
        if not local_ai.connected():
            return JSONResponse({"error": "Avval kamida bitta AI ilovani ulang va tekshiring"}, status_code=400)
        from ali import autopilot
        asyncio.get_running_loop().run_in_executor(None, autopilot.pro_learn_all, brain)
        return {"message": f"Murabbiy {len(brain.agents)} ta agentni {', '.join(local_ai.NAMES[k] for k in local_ai.connected())} "
                           "orqali o'qitishni boshladi. Jarayon Monitoring’da, tugagach xabar keladi.", **local_ai.summary()}
    if key == "_coach" and action in {"on", "off"}:  # Murabbiy Pro ilova orqali o'qitsin
        local_ai.set_option("_coach", action == "on")
        return {"message": "Murabbiy Pro orqali o'qitadi" if action == "on" else "Murabbiy oddiy rejimda", **local_ai.summary()}
    if key in local_ai.PROGRAMS and action == "open":
        try:
            await asyncio.to_thread(local_ai.open_program, key)
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return {"message": f"{local_ai.PROGRAMS[key][0]} ochildi", **local_ai.summary()}
    if key in local_ai.SERVICES and action in {"install", "login", "verify", "forget"}:  # GitHub, Vercel ilovalari
        try:
            if action == "install":
                message = await asyncio.to_thread(local_ai.install_service, key)
            elif action == "login":
                await asyncio.to_thread(local_ai.login_service, key)
                message = "Oyna ochildi - brauzerda akkauntingizga kiring, keyin “Tekshirish” ni bosing."
            elif action == "verify":
                ok, message = await asyncio.to_thread(local_ai.verify_service, key)
                if not ok:
                    return JSONResponse({"error": message, **local_ai.summary()}, status_code=400)
            else:
                local_ai.remember(key, None)
                message = "Ulanish unutildi"
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return {"message": message, **local_ai.summary()}
    if key not in local_ai.PACKAGES or action not in {"install", "login", "verify", "forget", "primary", "unprimary"}:
        return JSONResponse({"error": "Noma'lum ilova yoki amal"}, status_code=400)
    try:
        if action in {"primary", "unprimary"}:
            if action == "primary" and key not in local_ai.connected():
                return JSONResponse({"error": "Avval ilovani ulang va tekshiring"}, status_code=400)
            local_ai.set_option("_primary", key if action == "primary" else None)
            message = (f"{local_ai.NAMES[key]} Pro endi Ali'ning asosiy miyasi (shu kompyuterdan)" if action == "primary"
                       else "Asosiy miya: Claude API")
        elif action == "install":
            message = await asyncio.to_thread(local_ai.install, key)
        elif action == "login":
            await asyncio.to_thread(local_ai.open_login, key)
            message = "Kompyuterda oyna ochildi - akkauntingizga kiring, keyin “Tekshirish” ni bosing."
        elif action == "verify":
            ok, message = await asyncio.to_thread(local_ai.verify, key)
            if ok:
                local_ai.set_access(True)  # egasi shu kompyuterdan o'zi uladi - foydalanishga ruxsat
            else:
                return JSONResponse({"error": message, **local_ai.summary()}, status_code=400)
        else:
            local_ai.remember(key, None)
            if local_ai.option("_primary") == key:
                local_ai.set_option("_primary", None)
            message = "Ulanish unutildi"
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"message": message, **local_ai.summary()}


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
                asyncio.create_task(handle_ask(device.id, msg, allow_local=is_local(ws)))
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


async def handle_ask(device_id: str, msg: dict, allow_local: bool = False):
    text = str(msg.get("text", "")).strip()
    images = msg.get("images") or None
    if not text and not images:
        return
    if brain.lock.locked():
        hub.broadcast({"type": "busy"})
        return
    try:
        await run_ask(text, images, bool(msg.get("deep")), bool(msg.get("super")),
                      source=device_id, req_id=msg.get("id"), agent=str(msg.get("agent") or "") or None, allow_local=allow_local,
                      direct=(str(msg.get("ai") or "") if str(msg.get("ai") or "") in {"claude", "codex", "bedrock"} else None))
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
