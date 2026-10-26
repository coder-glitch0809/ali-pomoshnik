"""Tashqi MCP serverlarga ulanish (OAuth 2.1 + PKCE, dinamik ro'yxatdan o'tish) - hozircha ChatPlace.

ChatPlace (https://mcp.chatplace.io/mcp): Instagram/Telegram avtomatlashtirish, chatlar, xabar tarqatish, AI agent,
izohlar, botlar, teglar. Ulash: Ruxsatlar -> Ulanishlar -> ChatPlace -> "ChatPlace'ga kirish" (brauzerda ruxsat
berasiz). Token data/mcp_<nom>.json da saqlanadi va muddati tugasa avtomatik yangilanadi.
"""
import base64
import hashlib
import json
import logging
import secrets
import time
from urllib.parse import urlencode

import httpx

from .config import config

log = logging.getLogger("ali.mcp")

SERVERS = {
    "chatplace": {"name": "ChatPlace", "url": "https://mcp.chatplace.io/mcp", "issuer": "https://mcp.chatplace.io",
                  "scopes": ["automations:read", "automations:write", "chats:read", "chats:write", "mailings:read",
                             "mailings:write", "aiAgent:read", "aiAgent:write", "bots:read", "bots:write", "tags:read",
                             "tags:write", "variables:read", "variables:write", "comments:read", "comments:write",
                             "mediaFiles:read", "products:read", "refLinks:read", "virale:read"]},
}
PROTOCOL = "2025-06-18"
_pending: dict[str, dict] = {}  # state -> {server, verifier, redirect}


def _path(key: str):
    return config.data_dir / f"mcp_{key}.json"


def _load(key: str) -> dict:
    try:
        return json.loads(_path(key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _store(key: str, data: dict) -> None:
    _path(key).write_text(json.dumps(data), encoding="utf-8")


def connected(key: str) -> bool:
    return bool(_load(key).get("access_token"))


def _meta(key: str) -> dict:
    return httpx.get(SERVERS[key]["issuer"] + "/.well-known/oauth-authorization-server", timeout=20).json()


# --- OAuth ---
def start_auth(key: str, redirect: str) -> str:
    """Ro'yxatdan o'tadi (kerak bo'lsa) va brauzerda ochiladigan kirish havolasini qaytaradi."""
    srv, data, meta = SERVERS[key], _load(key), _meta(key)
    if data.get("redirect") != redirect or not data.get("client_id"):
        reg = httpx.post(meta["registration_endpoint"], json={
            "client_name": f"{config.assistant_name} (shaxsiy yordamchi)", "redirect_uris": [redirect],
            "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
            "token_endpoint_auth_method": "none", "scope": " ".join(srv["scopes"])}, timeout=20)
        reg.raise_for_status()
        data = {"client_id": reg.json()["client_id"], "redirect": redirect}
        _store(key, data)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    _pending[state] = {"server": key, "verifier": verifier, "redirect": redirect, "at": time.time()}
    return meta["authorization_endpoint"] + "?" + urlencode({
        "response_type": "code", "client_id": data["client_id"], "redirect_uri": redirect, "scope": " ".join(srv["scopes"]),
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256", "resource": srv["url"]})


def finish_auth(state: str, code: str) -> str:
    """Brauzerdan qaytgan kodni tokenga almashtiradi. Server nomini qaytaradi."""
    p = _pending.pop(state, None)
    if not p or time.time() - p["at"] > 900:
        raise RuntimeError("Kirish so'rovi eskirgan - qaytadan “ChatPlace'ga kirish” ni bosing")
    key, data = p["server"], _load(p["server"])
    r = httpx.post(_meta(key)["token_endpoint"], data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": p["redirect"], "client_id": data["client_id"],
        "code_verifier": p["verifier"], "resource": SERVERS[key]["url"]}, timeout=20)
    r.raise_for_status()
    _save_token(key, r.json())
    return SERVERS[key]["name"]


def _save_token(key: str, tok: dict) -> None:
    data = _load(key)
    data.update(access_token=tok["access_token"], refresh_token=tok.get("refresh_token", data.get("refresh_token")),
                expires_at=time.time() + int(tok.get("expires_in", 3600)) - 60)
    data.pop("session", None)
    _store(key, data)


def _token(key: str) -> str:
    data = _load(key)
    if not data.get("access_token"):
        raise RuntimeError(f"{SERVERS[key]['name']} ulanmagan: Ruxsatlar -> Ulanishlar -> {SERVERS[key]['name']}")
    if time.time() >= data.get("expires_at", 0) and data.get("refresh_token"):
        r = httpx.post(_meta(key)["token_endpoint"], data={"grant_type": "refresh_token", "refresh_token": data["refresh_token"],
                                                           "client_id": data["client_id"], "resource": SERVERS[key]["url"]},
                       timeout=20)
        if r.status_code != 200:
            raise RuntimeError(f"{SERVERS[key]['name']} tokeni eskirgan - qaytadan ulang")
        _save_token(key, r.json())
        data = _load(key)
    return data["access_token"]


def disconnect(key: str) -> None:
    _path(key).unlink(missing_ok=True)


# --- MCP (Streamable HTTP) ---
def _rpc(key: str, method: str, params: dict | None = None, notify: bool = False) -> dict:
    data = _load(key)
    headers = {"Authorization": f"Bearer {_token(key)}", "Content-Type": "application/json",
               "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": PROTOCOL}
    if data.get("session"):
        headers["Mcp-Session-Id"] = data["session"]
    body = {"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}
    if not notify:
        body["id"] = secrets.randbelow(10**9)
    r = httpx.post(SERVERS[key]["url"], json=body, headers=headers, timeout=120)
    if r.status_code == 404 and data.get("session"):  # sessiya eskirgan - qayta boshlaymiz
        data.pop("session")
        _store(key, data)
        _initialize(key)
        return _rpc(key, method, params, notify)
    r.raise_for_status()
    if sid := r.headers.get("mcp-session-id"):
        data = _load(key)
        data["session"] = sid
        _store(key, data)
    if notify or not r.content:
        return {}
    if "text/event-stream" in r.headers.get("content-type", ""):
        msgs = [json.loads(line[5:]) for line in r.text.splitlines() if line.startswith("data:") and line[5:].strip()]
        msg = next((m for m in reversed(msgs) if "result" in m or "error" in m), {})
    else:
        msg = r.json()
    if "error" in msg:
        raise RuntimeError(msg["error"].get("message", str(msg["error"])))
    return msg.get("result", {})


def _initialize(key: str) -> None:
    _rpc(key, "initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                             "clientInfo": {"name": "ali", "version": "1.0"}})
    _rpc(key, "notifications/initialized", notify=True)


def _ensure(key: str) -> None:
    if not _load(key).get("session"):
        _initialize(key)


def list_tools(key: str) -> list[dict]:
    _ensure(key)
    tools, cursor = [], None
    while True:
        res = _rpc(key, "tools/list", {"cursor": cursor} if cursor else {})
        tools += res.get("tools", [])
        cursor = res.get("nextCursor")
        if not cursor:
            return tools


def call_tool(key: str, name: str, arguments: dict, limit: int | None = 20000) -> str:
    """limit - AI'ga beriladigan javob uchun; ichki (JSON) ishlov uchun None - kesilmaydi."""
    _ensure(key)
    res = _rpc(key, "tools/call", {"name": name, "arguments": arguments or {}})
    parts = [c.get("text", "") if c.get("type") == "text" else f"[{c.get('type')}]" for c in res.get("content", [])]
    out = "\n".join(p for p in parts if p) or json.dumps(res.get("structuredContent", {}), ensure_ascii=False)
    return ("XATO: " if res.get("isError") else "") + (out[:limit] if limit else out)
