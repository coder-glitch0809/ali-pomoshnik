"""Obsidian: Ali xotirasi Obsidian omborida (vault) bog'langan eslatmalar sifatida.

Omborning "Ali" papkasiga har 5 daqiqada yoziladi:
  Ali/Ali.md                       - bosh sahifa (agentlar, statistika)
  Ali/Agentlar/<Agent>.md          - agent: tavsif, vositalar, tajriba saboqlari, bilimlariga havolalar
  Ali/Bilimlar/<agent>/<mavzu>.md  - har bir o'rganilgan bilim ([[Agent]] havolasi, teglar bilan)
  Ali/Xotira/Faktlar.md            - siz haqingizda eslab qolingan faktlar
  Ali/Suhbatlar/YYYY-MM-DD.md      - kunlik yozishmalar
  Ali/Mening yozuvlarim/           - SIZ yozasiz: bu yerdagi har bir eslatma Ali bilimiga qo'shiladi
Ombor: .env dagi OBSIDIAN_VAULT, bo'sh bo'lsa - Obsidian'da ochilgan ombor avtomatik topiladi.
"""
import json
import logging
import os
import re
import shutil
import threading
import time
from pathlib import Path

from .config import config

log = logging.getLogger("ali.obsidian")

INTERVAL = 300
STATE = config.data_dir / "obsidian_state.json"
INBOX = "Mening yozuvlarim"
_BAD = re.compile(r'[\\/:*?"<>|#^\[\]]+')


def vault() -> Path | None:
    """Obsidian ombori: OBSIDIAN_VAULT yoki Obsidian sozlamalaridagi ochiq (yoki birinchi) ombor."""
    if path := os.environ.get("OBSIDIAN_VAULT", "").strip():
        return Path(path) if Path(path).is_dir() else None
    try:
        data = json.loads((Path(os.environ.get("APPDATA", "")) / "obsidian" / "obsidian.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    vaults = sorted(data.get("vaults", {}).values(), key=lambda v: (not v.get("open"), -v.get("ts", 0)))
    return next((Path(v["path"]) for v in vaults if Path(v.get("path", "")).is_dir()), None)


def root() -> Path | None:
    v = vault()
    return v / "Ali" if v else None


def open_uri(note: str = "Ali/Ali") -> str:
    from urllib.parse import quote
    v = vault()
    return f"obsidian://open?vault={quote(v.name)}&file={quote(note)}" if v else ""


def _name(text: str, limit: int = 80) -> str:
    return _BAD.sub(" ", text).strip(" .")[:limit].strip() or "nomsiz"


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(path: Path, text: str) -> bool:
    """Faqat o'zgargan bo'lsa yozadi (Obsidian keraksiz qayta yuklanmasin)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def _yaml(**fields) -> str:
    lines = ["---"]
    for k, v in fields.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(json.dumps(x, ensure_ascii=False) for x in v)}]")
        else:
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    return "\n".join(lines + ["---", ""])


def sync() -> dict:
    from . import agents
    from .agents import split_lessons
    from .memory import JOURNAL_DIR, memory

    base = root()
    if base is None:
        raise RuntimeError("Obsidian ombori topilmadi (Obsidian'ni o'rnatib, bitta ombor oching yoki OBSIDIAN_VAULT ni yozing)")
    state, written = _state(), 0
    team = agents.load()
    names = {k: _name(f"{a.name}") for k, a in team.items()}

    # 1) Bilimlar - faqat yangilari (id bo'yicha)
    last = state.get("knowledge", 0)
    rows = memory._exec("SELECT id, topic, content, created_at FROM knowledge WHERE id>? ORDER BY id", (last,)).fetchall()
    for r in rows:
        m = re.match(r"\[([^\]]+)\]\s*(.*)", r["topic"])
        key, title = (m.group(1), m.group(2)) if m else ("umumiy", r["topic"])
        folder = base / "Bilimlar" / _name(key)
        path = folder / f"{_name(title)}.md"
        if path.exists():
            path = folder / f"{_name(title)} ({r['id']}).md"
        link = f"[[{names[key]}]]" if key in names else key
        written += _write(path, _yaml(agent=key, sana=r["created_at"][:10], tags=["ali", f"ali/{_name(key)}"])
                          + f"# {title}\n\nAgent: {link}\n\n{r['content']}\n")
        state["knowledge"] = r["id"]

    # 2) Agentlar - sozlama, tajriba saboqlari va bilimlariga havolalar
    for k, a in team.items():
        base_prompt, lessons = split_lessons(a.prompt)
        notes = sorted((base / "Bilimlar" / _name(k)).glob("*.md")) if (base / "Bilimlar" / _name(k)).exists() else []
        body = [f"# {a.icon} {a.name}", "", a.description, "",
                "## Tajriba (Murabbiy saboqlari)", *([f"- {l}" for l in lessons] or ["- hali yo'q"]), "",
                "## O'rganish mavzulari", *([f"- {t}" for t in a.learn] or ["- yo'q"]), "",
                f"## Bilimlari ({len(notes)})", *[f"- [[{n.stem}]]" for n in notes[-200:]], "",
                "## Vositalar", ", ".join(a.tools) or "-", "",
                "## Ko'rsatma", base_prompt]
        written += _write(base / "Agentlar" / f"{names[k]}.md",
                          _yaml(kalit=k, belgi=a.icon, tags=["ali", "ali/agent"]) + "\n".join(body) + "\n")

    # 3) Faktlar
    facts = memory.all_facts()
    written += _write(base / "Xotira" / "Faktlar.md", _yaml(tags=["ali", "ali/xotira"]) + "# Men haqimda eslab qolinganlar\n\n"
                      + ("\n".join(f"- **{k}**: {v}" for k, v in facts.items()) or "- hali yo'q") + "\n")

    # 4) Suhbatlar - kunlik jurnal nusxasi
    for src in sorted((JOURNAL_DIR / "suhbatlar").glob("*.md")) if (JOURNAL_DIR / "suhbatlar").exists() else []:
        dst = base / "Suhbatlar" / src.name
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            written += 1

    # 5) Siz yozgan eslatmalar -> Ali bilimi
    inbox = base / INBOX
    inbox.mkdir(parents=True, exist_ok=True)
    seen = state.setdefault("inbox", {})
    imported = 0
    for f in inbox.glob("*.md"):
        mtime = f.stat().st_mtime
        if seen.get(f.name) == mtime:
            continue
        text = f.read_text(encoding="utf-8").strip()
        if text:
            memory.add_knowledge(f"[obsidian] {f.stem}", text[:20000])
            imported += 1
        seen[f.name] = mtime

    # 6) Bosh sahifa
    stats = memory.stats()
    home = [f"# 🧠 {config.assistant_name} xotirasi", "",
            f"Yangilandi: {time.strftime('%Y-%m-%d %H:%M')}", "",
            f"- Yozishmalar: {stats['messages']} · agent ishlari: {stats['agent_tasks']}",
            f"- Bilimlar: {stats['knowledge']} · faktlar: {stats['facts']}", "",
            "## Agentlar", *[f"- [[{names[k]}]] — {team[k].description[:120]}" for k in team], "",
            "## Bo'limlar", "- [[Faktlar]] — siz haqingizda", "- Suhbatlar — `Ali/Suhbatlar`",
            f"- **{INBOX}** — shu papkaga yozgan har bir eslatmangiz Ali bilimiga qo'shiladi"]
    written += _write(base / "Ali.md", _yaml(tags=["ali"]) + "\n".join(home) + "\n")

    STATE.write_text(json.dumps(state), encoding="utf-8")
    if written or imported:
        log.info("Obsidian: %s ta fayl yangilandi, %s ta eslatma olindi", written, imported)
    return {"written": written, "imported": imported, "path": str(base)}


def start() -> None:
    from .config import ROOT, STATE_ROOT
    # Faqat asosiy (kompyuterdagi) Ali uchun: testlar va boshqa holat papkalari omborga yozmasin
    explicit = bool(os.environ.get("OBSIDIAN_VAULT", "").strip())
    if getattr(start, "_started", False) or vault() is None or (STATE_ROOT != ROOT and not explicit):
        return
    start._started = True

    def loop():
        time.sleep(20)
        while True:
            try:
                sync()
            except Exception as e:
                log.warning("Obsidian sinxronlash xatosi: %s", e)
            time.sleep(INTERVAL)

    threading.Thread(target=loop, daemon=True, name="obsidian-sync").start()
