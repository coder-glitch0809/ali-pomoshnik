"""OmniRoute (https://github.com/cheaper-inference/OmniRoute) - kompyuterdagi AI shlyuz: bitta OpenAI uslubidagi
manzil (http://127.0.0.1:20128/v1) orqali yuzlab modellar, o'zi eng yaxshi ishlayotganiga yo'naltiradi.

Ali uni Pro ilovalar qatoriga oxirgi zaxira sifatida qo'shadi: Claude/ChatGPT javob bermasa yoki limiti tugasa -
OmniRoute javob beradi. Provayderlar OmniRoute dashboard'ida (http://localhost:20128) ulanadi.
Server kalit talab qilsa - OMNIROUTE_API_KEY (Ruxsatlar -> Ulanishlar -> OmniRoute).
"""
import base64
import logging
import mimetypes
import time
from pathlib import Path

import httpx

from .config import config

log = logging.getLogger("ali.omniroute")

_seen = {"at": 0.0, "ok": False}
_models = {"at": 0.0, "ids": []}
_good: dict[str, str] = {}  # oxirgi ishlagan model - keyingi so'rovda birinchi sinaladi
_bad: dict[str, float] = {}  # ishlamagan provayder -> qachon (30 daqiqa chetlab o'tiladi)
BAD_FOR = 30 * 60
MAX_TRIES = 8
SKIP = ("auto", "aihorde/", "veo")  # auto - avval aniq sinaladi; rasm/video modellari matnga yaramaydi


def _root() -> str:
    return config.omniroute_url.rstrip("/").removesuffix("/v1")


def available() -> bool:
    """OmniRoute serveri ishlayaptimi (60 soniya eslab qolinadi - har so'rovda tekshirilmaydi)."""
    if not config.omniroute_url:
        return False
    if time.time() - _seen["at"] < 60:
        return _seen["ok"]
    try:
        ok = httpx.get(_root() + "/api/health", timeout=1.5).status_code == 200
    except httpx.HTTPError:
        ok = False
    _seen.update(at=time.time(), ok=ok)
    return ok


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.omniroute_api_key}"} if config.omniroute_api_key else {}


def model_ids() -> list[str]:
    """OmniRoute'dagi modellar ro'yxati (10 daqiqa eslab qolinadi)."""
    if time.time() - _models["at"] > 600:
        try:
            r = httpx.get(config.omniroute_url.rstrip("/") + "/models", headers=_headers(), timeout=20)
            _models.update(at=time.time(), ids=[m["id"] for m in r.json().get("data", [])] if r.status_code == 200 else [])
        except (httpx.HTTPError, ValueError):
            _models.update(at=time.time(), ids=[])
    return _models["ids"]


def _provider(model: str) -> str:
    """"ddgw/gpt-5.4-mini" -> "ddgw"; "no-think/dva/x" -> "dva" (bitta provayder ishlamasa - hamma modeli o'tkaziladi)."""
    parts = [p for p in model.split("/") if p != "no-think"]
    return parts[0] if len(parts) > 1 else model


def chat(prompt: str, timeout: int = 300, images: list[str] | None = None, model: str | None = None) -> str:
    """Javob matni. model berilmasa: oxirgi ishlagani -> OMNIROUTE_MODEL (auto) -> ro'yxatdagi boshqa modellar
    (OmniRoute'ning auto yo'nalishi ishlamaydigan manbaga tushsa ham, Ali o'zi ishlaydiganini topadi)."""
    if model:
        return _chat_one(prompt, timeout, images, model)
    now = time.time()
    order = [m for m in (_good.get("model"), config.omniroute_model) if m]
    order += [m for m in model_ids() if not m.startswith(SKIP)]
    tried, errors = [], []
    for m in dict.fromkeys(order):
        if len(tried) >= MAX_TRIES:
            break
        if now - _bad.get(_provider(m), 0) < BAD_FOR and m != config.omniroute_model:
            continue
        tried.append(m)
        try:
            answer = _chat_one(prompt, timeout, images, m)
        except RuntimeError as e:
            _bad[_provider(m)] = time.time()
            errors.append(f"{m}: {str(e)[:120]}")
            if "kalit kerak" in str(e) or "ulanib bo'lmadi" in str(e):
                break  # server/kalit muammosi - boshqa modelni sinash befoyda
            continue
        _good["model"] = m
        _bad.pop(_provider(m), None)
        return answer
    raise RuntimeError("OmniRoute'da ishlaydigan model topilmadi (" + str(len(tried)) + " ta sinaldi): " + " | ".join(errors)[-500:])


def _chat_one(prompt: str, timeout: int, images: list[str] | None, model: str) -> str:
    """Bitta model bilan so'rov. Xatoda RuntimeError (sababi bilan)."""
    content: str | list = prompt
    if images:
        content = [{"type": "text", "text": prompt}] + [
            {"type": "image_url", "image_url": {"url": f"data:{mimetypes.guess_type(p)[0] or 'image/jpeg'};base64,"
                                                      f"{base64.b64encode(Path(p).read_bytes()).decode()}"}}
            for p in images if Path(p).is_file()]
    try:
        r = httpx.post(config.omniroute_url.rstrip("/") + "/chat/completions", headers=_headers(), timeout=timeout,
                       json={"model": model, "messages": [{"role": "user", "content": content}]})
    except httpx.HTTPError as e:
        _seen.update(at=time.time(), ok=False)
        raise RuntimeError(f"OmniRoute'ga ulanib bo'lmadi: {e}") from None
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code != 200:
        err = (body.get("error") or {}) if isinstance(body, dict) else {}
        msg = err.get("message") if isinstance(err, dict) else str(err)
        if r.status_code == 401:
            msg = "kalit kerak - Ruxsatlar -> Ulanishlar -> OmniRoute"
        raise RuntimeError(f"OmniRoute javob bermadi ({r.status_code}): {(msg or r.text)[:300]}")
    try:
        answer = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("OmniRoute javobi tushunarsiz") from None
    if isinstance(answer, list):
        answer = "".join(p.get("text", "") for p in answer if isinstance(p, dict))
    if not (answer or "").strip():
        raise RuntimeError("OmniRoute bo'sh javob qaytardi")
    return answer.strip()
