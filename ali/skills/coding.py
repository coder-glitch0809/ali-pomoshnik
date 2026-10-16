"""Kod yozuvchi agentlar: Claude Code CLI orqali loyihada vazifa bajarish.

Vazifa fonda ishlaydi (uzoq bo'lishi mumkin); tugagach telefon/Telegramga xabar keladi.
O'rnatish:  npm install -g @anthropic-ai/claude-code   (keyin bir marta: claude  -> kirish)
"""
import shutil
import subprocess
import threading
import time
import uuid

from ..config import config
from ..hub import hub
from ..monitor import monitor
from .projects import _project
from . import skill

LOG_DIR = config.data_dir / "code_tasks"
TASKS: dict[str, dict] = {}

COMMANDS = {
    # Claude Code: fayllarni o'zgartirishga ruxsat, buyruqlar esa so'ralmaydi (xavfsiz rejim)
    "claude": ["-p", "--output-format", "text", "--permission-mode", "acceptEdits"],
}
INSTALL = {
    "claude": "npm install -g @anthropic-ai/claude-code  (keyin terminalda bir marta `claude` deb kiring)",
}


def _run(task: dict, exe: str) -> None:
    log_path = LOG_DIR / f"{task['id']}.log"
    job = monitor.start_job("dasturchi", f"[{task['tool']}] {task['project']}: {task['task']}", "ali")
    monitor.add_log("dasturchi", "tool", f"{task['tool']} → {task['project']}: {task['task'][:200]}")
    try:
        with open(log_path, "w", encoding="utf-8") as log:
            proc = subprocess.run(
                [exe, *COMMANDS[task["tool"]]], input=task["task"], cwd=task["cwd"], stdout=log,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                timeout=config.code_task_minutes * 60,
            )
        task["status"] = "done" if proc.returncode == 0 else f"xato (exit {proc.returncode})"
    except subprocess.TimeoutExpired:
        task["status"] = f"vaqt tugadi ({config.code_task_minutes} daqiqa)"
    except Exception as e:
        task["status"] = f"xato: {e}"
    task["end"] = time.time()
    tail = log_path.read_text(encoding="utf-8", errors="replace")[-600:].strip() if log_path.exists() else ""
    ok = task["status"] == "done"
    monitor.finish(job, ok)
    monitor.add_log("dasturchi", "answer" if ok else "error", tail[-300:] or task["status"])
    hub.notify(f"{'✅' if ok else '⚠️'} {task['tool']} vazifasi ({task['project']}) {task['status']}. "
               f"Natija: code_task_status {task['id']}")


@skill(
    description=(
        "Loyihada dasturlash vazifasini Claude Code agentiga topshiradi: yangi funksiya yozish, xatoni tuzatish, "
        "refaktoring, test yozish, README to'ldirish. Agent loyiha fayllarini o'zi o'qiydi va o'zgartiradi. Vazifa fonda "
        "ishlaydi, tugagach xabar keladi. Vazifani aniq va to'liq yoz (nima, qayerda, qanday natija kerak). Foydalanuvchi tasdiqlaydi."
    ),
    params={
        "tool": {"type": "string", "enum": ["claude"], "description": "claude (Claude Code)"},
        "project": {"type": "string", "description": "Loyiha nomi (list_projects)"},
        "task": {"type": "string", "description": "To'liq vazifa matni"},
    },
    dangerous=True,
)
def code_task(tool: str, project: str, task: str) -> str:
    if tool not in COMMANDS:
        return "tool: claude"
    exe = shutil.which(tool)
    if not exe:
        return f"{tool} CLI o'rnatilmagan. O'rnatish: {INSTALL[tool]}"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cwd = _project(project)
    t = {"id": uuid.uuid4().hex[:8], "tool": tool, "project": cwd.name, "cwd": str(cwd), "task": task,
         "status": "running", "start": time.time(), "end": None}
    TASKS[t["id"]] = t
    threading.Thread(target=_run, args=(t, exe), daemon=True, name=f"code-{t['id']}").start()
    return f"Vazifa {t['id']} boshlandi ({tool}, {cwd.name}). Tugagach xabar keladi; holat: code_task_status."


@skill(
    description="Claude Code vazifalari holati. task_id berilsa - o'sha vazifa natijasi (log oxiri).",
    params={"task_id": {"type": "string", "description": "Vazifa ID (ixtiyoriy)"}},
    required=[],
)
def code_task_status(task_id: str = "") -> str:
    if task_id:
        log_path = LOG_DIR / f"{task_id}.log"
        if not log_path.exists():
            return "Bunday vazifa topilmadi."
        t = TASKS.get(task_id, {})
        text = log_path.read_text(encoding="utf-8", errors="replace")
        return f"Holat: {t.get('status', 'tugagan')}\n" + (text[-8000:] or "(hali natija yo'q)")
    if not TASKS:
        return "Bu sessiyada vazifa yo'q."
    now = time.time()
    return "\n".join(
        f"- {t['id']} | {t['tool']} | {t['project']} | {t['status']} | {int(((t['end'] or now) - t['start']) / 60)} daq | {t['task'][:80]}"
        for t in TASKS.values()
    )


@skill(description="Kompyuterda Claude Code o'rnatilganini tekshiradi.")
def coding_tools_status() -> str:
    return "\n".join(
        f"- {name}: {'o`rnatilgan (' + shutil.which(name) + ')' if shutil.which(name) else 'yo`q -> ' + INSTALL[name]}"
        for name in COMMANDS
    )
