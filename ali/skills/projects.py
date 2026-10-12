"""Kompyuterdagi loyihalar (VS Code): ro'yxat, fayllarni o'qish, qidirish, o'zgartirish, buyruq bajarish.

Loyihalar qayerdan olinadi: .env dagi PROJECTS_DIRS papkalari (standart - Ali turgan papkaning ota papkasi)
va VS Code'da yaqinda ochilgan papkalar.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from ..config import config
from . import skill

SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", ".next", "dist", "build", ".vercel", ".idea", ".cache"}
MAX_OUTPUT = 12000
MARKERS = {
    "package.json": "Node/JS", "requirements.txt": "Python", "pyproject.toml": "Python", "next.config.js": "Next.js",
    "next.config.mjs": "Next.js", "vercel.json": "Vercel", "Cargo.toml": "Rust", "go.mod": "Go", "composer.json": "PHP",
    "pubspec.yaml": "Flutter", "index.html": "HTML",
}


def _cut(text: str, limit: int = MAX_OUTPUT) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n... ({len(text) - limit} belgi qisqartirildi)"


def _vscode_recent() -> list[Path]:
    db = Path(os.environ.get("APPDATA", "")) / "Code" / "User" / "globalStorage" / "state.vscdb"
    if not db.exists():
        return []
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        row = con.execute("SELECT value FROM ItemTable WHERE key='history.recentlyOpenedPathsList'").fetchone()
        con.close()
    except sqlite3.Error:
        return []
    paths = []
    for entry in json.loads(row[0]).get("entries", []) if row else []:
        uri = entry.get("folderUri") or ""
        if uri.startswith("file://"):
            p = unquote(urlparse(uri).path).lstrip("/")
            paths.append(Path(p))
    return [p for p in paths if p.is_dir()]


def all_projects() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for base in config.projects_dirs:
        if base.is_dir():
            for p in sorted(base.iterdir()):
                if p.is_dir() and not p.name.startswith("."):
                    found.setdefault(p.name, p)
    for p in _vscode_recent():
        found.setdefault(p.name, p)
    return found


def _project(name: str) -> Path:
    projects = all_projects()
    if name in projects:
        return projects[name]
    low = name.lower()
    matches = [p for n, p in projects.items() if low in n.lower()]
    if len(matches) == 1:
        return matches[0]
    p = Path(name)
    if p.is_absolute() and p.is_dir():
        return p
    raise ValueError(f"Loyiha topilmadi yoki aniq emas: {name}. list_projects bilan ro'yxatni ko'r.")


def _inside(root: Path, rel: str) -> Path:
    target = (root / rel).resolve()
    if target != root.resolve() and root.resolve() not in target.parents:
        raise ValueError("Yo'l loyiha papkasidan tashqarida")
    return target


def _kind(p: Path) -> str:
    kinds = {k for f, k in MARKERS.items() if (p / f).exists()}
    try:
        exts = {f.suffix.lower() for f in p.iterdir() if f.is_file()}
    except OSError:
        exts = set()
    if exts & {".mq4", ".mq5", ".mqh"}:
        kinds.add("MQL (MetaTrader)")
    if (p / ".git").exists():
        kinds.add("git")
    return ", ".join(sorted(kinds)) or "papka"


def _git(root: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30)
        return (r.stdout or r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"[git xatosi: {e}]"


@skill(
    description=(
        "Kompyuterdagi barcha loyihalar ro'yxati (PROJECTS_DIRS papkalari va VS Code'da ochilganlar): nomi, yo'li, turi, "
        "oxirgi o'zgarish vaqti. query bilan nom bo'yicha filtrlash mumkin (masalan 'trade', 'bot')."
    ),
    params={"query": {"type": "string", "description": "Nom bo'yicha filtr (ixtiyoriy)"}},
    required=[],
)
def list_projects(query: str = "") -> str:
    rows = []
    for name, p in all_projects().items():
        if query and query.lower() not in name.lower():
            continue
        try:
            mtime = time.strftime("%Y-%m-%d", time.localtime(p.stat().st_mtime))
        except OSError:
            mtime = "?"
        rows.append(f"- {name} | {_kind(p)} | {mtime} | {p}")
    return "\n".join(rows) or "Loyiha topilmadi."


@skill(
    description="Loyiha fayllari daraxti (node_modules, .git kabilar o'tkazib yuboriladi).",
    params={
        "project": {"type": "string", "description": "Loyiha nomi (list_projects dan)"},
        "subpath": {"type": "string", "description": "Ichki papka (ixtiyoriy)"},
        "depth": {"type": "integer", "description": "Chuqurlik, standart 3"},
    },
    required=["project"],
)
def project_tree(project: str, subpath: str = "", depth: int = 3) -> str:
    root = _project(project)
    start = _inside(root, subpath)
    lines: list[str] = []

    def walk(d: Path, level: int):
        if len(lines) > 400:
            return
        try:
            items = sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        except OSError:
            return
        for item in items:
            if item.name in SKIP:
                continue
            lines.append("  " * level + item.name + ("/" if item.is_dir() else ""))
            if item.is_dir() and level + 1 < depth:
                walk(item, level + 1)

    walk(start, 0)
    return f"{start}\n" + "\n".join(lines[:400]) + ("\n..." if len(lines) > 400 else "")


@skill(
    description="Loyihadagi faylni o'qiydi (qator raqamlari bilan).",
    params={
        "project": {"type": "string", "description": "Loyiha nomi"},
        "path": {"type": "string", "description": "Loyiha ichidagi fayl yo'li"},
        "start_line": {"type": "integer", "description": "Boshlang'ich qator (standart 1)"},
        "max_lines": {"type": "integer", "description": "Nechta qator (standart 400)"},
    },
    required=["project", "path"],
)
def read_project_file(project: str, path: str, start_line: int = 1, max_lines: int = 400) -> str:
    f = _inside(_project(project), path)
    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, start_line)
    chunk = lines[start - 1:start - 1 + max_lines]
    body = "\n".join(f"{i:5} | {line}" for i, line in enumerate(chunk, start))
    more = f"\n... (jami {len(lines)} qator)" if start - 1 + max_lines < len(lines) else ""
    return _cut(body + more)


@skill(
    description="Loyihalar kodida matn qidiradi (ripgrep). project bo'sh bo'lsa - barcha loyihalarda.",
    params={
        "query": {"type": "string", "description": "Qidiriladigan matn yoki regex"},
        "project": {"type": "string", "description": "Loyiha nomi (ixtiyoriy)"},
    },
    required=["query"],
)
def search_projects(query: str, project: str = "") -> str:
    roots = [_project(project)] if project else list(all_projects().values())
    rg = shutil.which("rg")
    out: list[str] = []
    for root in roots:
        if rg:
            cmd = [rg, "-n", "--max-count", "5", "--max-columns", "200", "-S", *sum((["-g", f"!{s}"] for s in SKIP), []),
                   query, str(root)]
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            out.append(r.stdout)
        else:
            for f in root.rglob("*"):
                if f.is_file() and not (set(f.parts) & SKIP) and f.stat().st_size < 1_000_000:
                    for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                        if query.lower() in line.lower():
                            out.append(f"{f}:{i}:{line[:200]}\n")
        if sum(map(len, out)) > MAX_OUTPUT:
            break
    return _cut("".join(out).strip() or "Topilmadi.")


@skill(
    description="Loyihaning git holati: branch, o'zgargan fayllar, oxirgi commitlar, remote (GitHub) manzili.",
    params={"project": {"type": "string", "description": "Loyiha nomi"}},
)
def project_git_status(project: str) -> str:
    root = _project(project)
    if not (root / ".git").exists():
        return f"{root} - git repozitoriy emas."
    return "\n\n".join([
        _git(root, "status", "-sb"),
        "Oxirgi commitlar:\n" + _git(root, "log", "--oneline", "-8"),
        "Remote:\n" + _git(root, "remote", "-v"),
    ])


@skill(
    description=(
        "Loyihadagi faylni yaratadi yoki to'liq qayta yozadi. Avval read_project_file bilan o'qi, keyin to'liq yangi "
        "mazmunni yoz. Foydalanuvchi tasdiqlaydi."
    ),
    params={
        "project": {"type": "string", "description": "Loyiha nomi"},
        "path": {"type": "string", "description": "Fayl yo'li"},
        "content": {"type": "string", "description": "Faylning to'liq yangi mazmuni"},
    },
    dangerous=True,
)
def write_project_file(project: str, path: str, content: str) -> str:
    f = _inside(_project(project), path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return f"Yozildi: {f} ({len(content)} belgi)"


@skill(
    description=(
        "Loyiha papkasida buyruq bajaradi (PowerShell): npm install/test/build, python skript, git commit/push va h.k. "
        "Foydalanuvchi tasdiqlaydi. 5 daqiqagacha."
    ),
    params={
        "project": {"type": "string", "description": "Loyiha nomi"},
        "command": {"type": "string", "description": "PowerShell buyrug'i"},
    },
    dangerous=True,
)
def run_in_project(project: str, command: str) -> str:
    root = _project(project)
    script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + command
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], cwd=root,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    except subprocess.TimeoutExpired:
        return "Vaqt tugadi (5 daqiqa)"
    out = (r.stdout + ("\n[stderr]\n" + r.stderr if r.stderr.strip() else "")).strip()
    return f"exit={r.returncode}\n" + _cut(out or "(bo'sh)")


@skill(
    description="Loyihani (yoki undagi faylni) kompyuterda VS Code'da ochadi.",
    params={
        "project": {"type": "string", "description": "Loyiha nomi"},
        "path": {"type": "string", "description": "Fayl (ixtiyoriy)"},
    },
    required=["project"],
)
def open_in_vscode(project: str, path: str = "") -> str:
    root = _project(project)
    code = shutil.which("code") or shutil.which("code.cmd")
    if not code:
        return "VS Code (code buyrug'i) topilmadi."
    args = [code, str(root)] + ([str(_inside(root, path))] if path else [])
    subprocess.Popen(args, shell=False)
    return f"VS Code'da ochildi: {root}"
