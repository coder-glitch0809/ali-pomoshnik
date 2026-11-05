"""ChatGPT va Claude suhbatlar tarixini Ali bilimiga o'tkazish - limitlar tugaganda ham agentlar shu bilimga tayanadi.

Eksport: ChatGPT -> Settings -> Data controls -> Export data (pochtaga zip keladi);
Claude -> Settings -> Privacy -> Export data. Zip (yoki ichidagi conversations.json) ni botga yuboring yoki
«Yuklab olishlar» papkasida qoldirib /tarix buyrug'ini bering - Ali o'zi topadi.
Har suhbat alohida bilim bo'ladi (savol-javoblar qisqartirilib), mavzusiga qarab mos agentga beriladi.
Eslatma: ChatGPT ichidagi plaginlar/GPTs ChatGPT serverida ishlaydi - ularni tashqaridan chaqirib bo'lmaydi,
lekin ular bilan bo'lgan suhbatlardagi javoblar shu yo'l bilan Ali bilimiga o'tadi.
"""
import json
import logging
import zipfile
from datetime import datetime
from pathlib import Path

log = logging.getLogger("ali.chat_import")

MAX_CHARS = 4000  # bitta suhbatdan olinadigan bilim hajmi


def _chatgpt(conv: dict) -> list[tuple[str, str]]:
    """ChatGPT: mapping daraxti -> vaqt tartibida (rol, matn)."""
    rows = []
    for node in (conv.get("mapping") or {}).values():
        msg = (node or {}).get("message") or {}
        role = (msg.get("author") or {}).get("role")
        parts = (msg.get("content") or {}).get("parts") or []
        text = "\n".join(p for p in parts if isinstance(p, str)).strip()
        if role in ("user", "assistant") and text:
            rows.append((msg.get("create_time") or 0, role, text))
    return [(r, t) for _, r, t in sorted(rows, key=lambda x: x[0] or 0)]


def _claude(conv: dict) -> list[tuple[str, str]]:
    rows = []
    for m in conv.get("chat_messages") or []:
        text = (m.get("text") or "").strip() or "\n".join(
            c.get("text", "") for c in m.get("content") or [] if isinstance(c, dict)).strip()
        if text:
            rows.append(("user" if m.get("sender") == "human" else "assistant", text))
    return rows


def parse(data) -> list[dict]:
    """conversations.json mazmuni -> [{title, source, messages: [(rol, matn)]}] (ChatGPT yoki Claude formati)."""
    out = []
    for conv in data if isinstance(data, list) else []:
        if not isinstance(conv, dict):
            continue
        if "mapping" in conv:
            out.append({"title": conv.get("title") or "Nomsiz", "source": "ChatGPT", "messages": _chatgpt(conv)})
        elif "chat_messages" in conv:
            out.append({"title": conv.get("name") or "Nomsiz", "source": "Claude", "messages": _claude(conv)})
    return [c for c in out if c["messages"]]


def load(path: Path) -> list[dict]:
    """Zip yoki .json fayldan suhbatlar."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            name = next((n for n in z.namelist() if n.endswith("conversations.json")), None)
            if not name:
                return []
            return parse(json.loads(z.read(name).decode("utf-8")))
    return parse(json.loads(path.read_text(encoding="utf-8")))


def digest(conv: dict) -> str:
    """Suhbatning bilim matni: savol -> javob juftliklari, uzunlari qisqartiriladi."""
    lines, total = [], 0
    for role, text in conv["messages"]:
        piece = f"{'❓' if role == 'user' else '💬'} {' '.join(text.split())[:900 if role == 'assistant' else 300]}"
        if total + len(piece) > MAX_CHARS:
            break
        lines.append(piece)
        total += len(piece)
    return "\n".join(lines)


def import_file(path: Path) -> dict:
    """Bilimga yozadi. {chats, saved, agents, source}."""
    from . import router
    from .memory import memory
    from .service import brain
    convs = load(path)
    agents: dict[str, int] = {}
    saved = 0
    for conv in convs:
        body = digest(conv)
        if len(body) < 40:
            continue
        key = router.subject(f"{conv['title']} {conv['messages'][0][1][:300]}", brain.agents)
        prefix = f"[{key}] " if key else ""
        memory.add_knowledge(f"{prefix}{conv['source']} suhbati: {conv['title'][:80]}", body)
        agents[key or "umumiy"] = agents.get(key or "umumiy", 0) + 1
        saved += 1
    return {"chats": len(convs), "saved": saved, "agents": agents,
            "source": ", ".join(sorted({c["source"] for c in convs})) or "-"}


def find_exports(days: int = 60) -> list[Path]:
    """«Yuklab olishlar» papkasidagi ChatGPT/Claude eksport zip'lari (oxirgi {days} kun)."""
    folder = Path.home() / "Downloads"
    if not folder.is_dir():
        return []
    limit = datetime.now().timestamp() - days * 86400
    found = []
    for f in folder.glob("*.zip"):
        if f.stat().st_mtime < limit or f.stat().st_size > 2 * 1024 ** 3:
            continue
        try:
            with zipfile.ZipFile(f) as z:
                if any(n.endswith("conversations.json") for n in z.namelist()):
                    found.append(f)
        except (zipfile.BadZipFile, OSError):
            continue
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)
