"""Yuborilgan materialdan o'rganish: fayl (PDF, Word, Excel, PowerPoint, matn, kod), rasm, havola, uzatilgan xabar.

Har bir material: saqlanadi (data/inbox) -> matni ajratiladi -> qaysi agentga tegishliligi aniqlanadi ->
asl matn va undan chiqarilgan 3-8 ta amaliy bilim o'sha agent bazasiga yoziladi ("[agent] sarlavha").
Keyin bilimlar Obsidian va Firebase'ga ham avtomatik tushadi.
"""
import base64
import html
import json
import logging
import re
import time
from pathlib import Path

import httpx

from .config import config
from .memory import memory

log = logging.getLogger("ali.ingest")

INBOX = config.data_dir / "inbox"
MAX_TEXT = 60000
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0 Safari/537.36")
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")

NOTES_TASK = """Sen "{agent}" uchun o'qituvchisan. Quyidagi materialni (manba: {source}) diqqat bilan o'qi{see} va agent ishida
kerak bo'ladigan eng muhim, aniq va amaliy bilimlarni chiqar: 3-8 ta yozuv. Har yozuvda raqamlar, qoidalar, bosqichlar,
nomlar va xulosalar aniq bo'lsin; materialda yo'q narsani qo'shma.
Faqat JSON qaytar: {{"summary": "2-3 gapli umumiy mazmun", "notes": [{{"topic": "qisqa sarlavha", "content": "amaliy bilim"}}]}}

Material:
<<<{text}>>>"""


def save_upload(name: str, data: bytes) -> Path:
    INBOX.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\- ]+", "_", name, flags=re.UNICODE).strip() or "fayl"
    path = INBOX / f"{time.strftime('%Y%m%d_%H%M%S')}_{safe}"
    path.write_bytes(data)
    return path


def save_image_b64(data_b64: str, ext: str = ".jpg") -> Path:
    return save_upload(f"rasm{ext}", base64.b64decode(data_b64))


def extract_text(path: Path) -> str:
    """Fayl matni (Word, Excel, PowerPoint, PDF, matn/kod). Rasm uchun - bo'sh (rasmni AI ko'radi)."""
    from .skills import desktop
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return ""
    try:
        return desktop.READERS.get(ext, desktop._read_text)(path)[:MAX_TEXT]
    except Exception as e:
        raise RuntimeError(f"{path.name} faylini o'qib bo'lmadi: {e}") from e


def fetch_url(url: str) -> str:
    """Havoladagi sahifa matni (skript va stillarsiz)."""
    r = httpx.get(url, timeout=25, follow_redirects=True, headers={"User-Agent": BROWSER_UA, "Accept-Language": "uz,ru;q=0.9,en;q=0.8"})
    r.raise_for_status()
    if "html" not in r.headers.get("content-type", "html"):
        return r.text[:MAX_TEXT]
    body = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header)[^>]*>.*?</\1>", " ", r.text)
    title = re.search(r"(?is)<title[^>]*>(.*?)</title>", body)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", body))
    text = re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()
    return ((html.unescape(title.group(1)).strip() + "\n\n") if title else "") + text[:MAX_TEXT]


def _notes(agent_name: str, source: str, text: str, images: list[str]) -> dict:
    """Materialdan bilimlar: Pro ilova (rasmni ham ko'radi) -> Gemini/Bedrock API."""
    from . import local_ai, providers
    if not text and source.startswith("http"):  # sahifani Ali ocholmadi - Claude WebFetch bilan o'zi ochadi
        text = f"(Sahifa matni yuklanmadi. Havolani WebFetch bilan o'zing ochib o'qi: {source})"
    prompt = NOTES_TASK.format(agent=agent_name, source=source, text=text[:30000] or "(matn yo'q - rasmga qara)",
                               see=" va biriktirilgan rasmni ko'r" if images else "")
    raw = ""
    if local_ai.access() is True and local_ai.connected():
        got = local_ai.ask_pro(prompt, local_ai.TIMEOUT, None, images or None)
        raw = got[1] if got else ""
    if not raw:
        try:
            raw = providers.chat("Faqat so'ralgan JSON'ni qaytar.", [], prompt, 3000, True)[1]
        except RuntimeError as e:
            log.warning("Material bo'yicha bilim chiqarilmadi: %s", e)
            return {"summary": "", "notes": []}
    try:
        return json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except ValueError:
        return {"summary": raw.strip()[:1500], "notes": []}


def learn(title: str, text: str, source: str, images: list[str] | None = None, hint: str = "") -> dict:
    """Materialni o'rganadi va mos agent bazasiga yozadi. {agent, name, icon, saved, summary}."""
    from . import local_ai
    from .service import brain, route
    ready = local_ai.connected() if local_ai.access() is True else []
    key = route(f"{hint}\n{title}\n{text[:3000]}".strip() or title, ready)
    a = brain.agents.get(key) if key else None
    prefix = a.key if a else "umumiy"
    stamp = time.strftime("%Y-%m-%d")
    if text.strip():  # asl material ham saqlanadi - keyin aynan shundan javob topiladi
        memory.add_knowledge(f"[{prefix}] {title}", f"{text[:20000]}\n\nManba: {source} ({stamp})")
    data = _notes(a.name if a else config.assistant_name, source, text, images or [])
    saved = 0
    for n in (data.get("notes") or [])[:8]:
        topic, content = str(n.get("topic", "")).strip()[:120], str(n.get("content", "")).strip()[:3000]
        if topic and content:
            memory.add_knowledge(f"[{prefix}] {topic}", f"{content}\n\nManba: {source} ({stamp})")
            saved += 1
    summary = str(data.get("summary", "")).strip()
    if not text.strip() and summary:  # faqat rasm bo'lsa - tavsifi ham saqlanadi
        memory.add_knowledge(f"[{prefix}] {title}", f"{summary}\n\nManba: {source} ({stamp})")
    log.info("Material o'rganildi: %s -> %s, %s ta bilim", title, prefix, saved)
    return {"agent": prefix, "name": a.name if a else config.assistant_name, "icon": a.icon if a else "🧠",
            "saved": saved + (1 if text.strip() else 0), "summary": summary}
