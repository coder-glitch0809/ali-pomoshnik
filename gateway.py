"""Stateless Vercel entrypoint. The assistant lives on a persistent host."""
import os
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="Ali Pomoshnik")


def backend_url():
    value = os.getenv("ALI_BACKEND_URL", "").strip().rstrip("/")
    parts = urlsplit(value)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path not in ("", "/")):
        return None
    return value


@app.get("/healthz")
async def health():
    return {"ok": True, "backend_configured": bool(backend_url())}


@app.get("/{path:path}")
async def open_assistant(request: Request, path: str):
    target = backend_url()
    if target and urlsplit(target).hostname != request.url.hostname:
        # Redirect, instead of proxying: WebSocket and cookies stay on one origin.
        suffix = request.url.path
        if request.url.query:
            suffix += "?" + request.url.query
        return RedirectResponse(target + suffix, status_code=307,
                                headers={"Cache-Control": "no-store"})
    return HTMLResponse("""<!doctype html><html lang="uz"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ali Pomoshnik</title><style>
body{margin:0;background:#0b0f17;color:#e8eefb;font:18px system-ui;display:grid;min-height:100vh;place-items:center}
main{max-width:540px;padding:32px}h1{font-size:38px}p{line-height:1.7;color:#aab8ce}
a{color:#8cabff}</style><main><h1>Ali Pomoshnik</h1>
<p>24/7 yordamchi serveri hali ulanmagan. Server ulangach, ushbu manzil to‘liq boshqaruv panelini ochadi.</p>
<p>Hozir kompyuterda ishga tushirilgan Ali uchun <a href="http://localhost:8000">mahalliy panelni ochish</a> mumkin.</p>
</main></html>""", status_code=503, headers={"Cache-Control": "no-store"})
