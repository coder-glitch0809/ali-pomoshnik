"""Ali o'zini o'zi kuchaytiradi - faqat egasi so'raganda va egasining tasdig'i bilan.

Jarayon (ishlab turgan Ali hech qachon buzilmaydi):
  1. Alohida git worktree (data/upgrade/<id>, "ali-upgrade/<id>" branch) yaratiladi.
  2. Claude Code (egasining obunasi) shu nusxada vazifani bajaradi - kod yozadi, kerak bo'lsa test qo'shadi.
  3. Testlar ishga tushadi: birorta yangi xato bo'lsa - o'zgarish bekor qilinadi.
  4. O'tsa - qisqa hisobot va diff egasiga yuboriladi, "Qo'llash" tugmasi bilan tasdiq kutiladi.
  5. Tasdiqlansa - main'ga qo'shiladi, GitHub'ga push qilinadi, Ali o'zini qayta ishga tushiradi.
"""
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

from .config import ROOT, config

log = logging.getLogger("ali.self_upgrade")

WORK = config.data_dir / "upgrade"
STATE = config.data_dir / "upgrade_state.json"
TIMEOUT_MIN = 40
QUERY = re.compile(r"(o['ʻ‘]?zingni|узингни|ўзингни|o['ʻ‘]?zini|ozingni)\s+(kuchaytir|кучайтир|takomillashtir|"
                   r"такомиллаштир|yaxshila|яхшила|rivojlantir|ривожлантир)|/kuchaytir", re.I)
_lock = threading.Lock()

TASK = """Sen Ali loyihasining (shaxsiy AI yordamchi, Python/FastAPI, Telegram bot, web/) dasturchisisan.
Egasi so'ragan o'zgarish:
<<<{task}>>>

Qoidalar:
- Mavjud kod uslubiga mos yoz: o'zbekcha izohlar va xabarlar, mavjud modullarni qayta ishlat (ali/skills, ali/*.py).
- .env, data/, xotira/, agents/18-agent.md va maxfiy kalitlarga TEGMA. Kalit, token yoki parolni kodga yozma.
- Kichik va aniq o'zgarish qil; keraksiz qayta yozma. Yangi funksiya bo'lsa - tests/ ga oddiy test qo'sh.
- Oxirida `python -X utf8 -m unittest discover -s tests` ni ishga tushir va testlar o'tishiga erish.
- Yakunda 3-6 qatorda o'zbekcha hisobot yoz: nima qo'shildi, qaysi fayllar, qanday ishlatiladi."""


def is_request(text: str) -> bool:
    return bool(QUERY.search(text or ""))


def extract_task(text: str) -> str:
    return re.sub(r"^\s*/kuchaytir\s*", "", text or "").strip()


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(state: dict) -> None:
    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _git(*args, cwd=ROOT, check=True) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()[-400:]}")
    return r.stdout.strip()


def _tests(cwd) -> tuple[bool, str]:
    """Testlar: muvaffaqiyatsiz test yoki import xatosi bo'lmasa - o'tdi (fayl bandligidagi tearDown xatosi hisobga olinmaydi)."""
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests"], cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                       env={**os.environ, "ALI_STATE_DIR": str(cwd / "data" / "_test_state")},
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out = r.stdout + r.stderr
    bad = [l for l in out.splitlines() if re.match(r"^(FAIL|ERROR): ", l) and "tearDownModule" not in l]
    ran = re.search(r"Ran (\d+) tests", out)
    return (not bad and ran is not None), (f"{ran.group(1) if ran else '?'} ta test; " +
                                           ("hammasi o'tdi" if not bad else "buzilgan: " + "; ".join(bad)[:600]))


def run(task: str, progress) -> dict:
    """Vazifani alohida nusxada bajaradi, testlaydi. Natija: {id, ok, report, diff, tests}."""
    from . import local_ai
    if not _lock.acquire(blocking=False):
        raise RuntimeError("Hozir boshqa kuchaytirish ketyapti - tugashini kuting")
    try:
        exe = local_ai._claude_exe()
        if not exe:
            raise RuntimeError("Claude Code topilmadi (VS Code kengaytmasi yoki npm i -g @anthropic-ai/claude-code)")
        uid = uuid.uuid4().hex[:8]
        branch, path = f"ali-upgrade/{uid}", WORK / uid
        WORK.mkdir(parents=True, exist_ok=True)
        _git("worktree", "add", "-b", branch, str(path), "HEAD")
        (path / "data").mkdir(exist_ok=True)  # data/ gitignore'da - testlar uchun bo'sh papka
        progress(f"🛠 Alohida nusxada ishlayapman ({branch}). Claude Code kod yozyapti - {TIMEOUT_MIN} daqiqagacha…")
        r = subprocess.run([exe, "-p", "--output-format", "text", "--permission-mode", "acceptEdits",
                            "--allowedTools", "Read", "Edit", "Write", "Glob", "Grep", "Bash(python *)", "Bash(git diff*)",
                            "Bash(git status*)"],
                           input=TASK.format(task=task), cwd=path, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=TIMEOUT_MIN * 60, env=local_ai.clean_env(),
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        report = (r.stdout or r.stderr).strip()[-2500:]
        if r.returncode != 0:
            discard(uid)
            raise RuntimeError(f"Claude Code vazifani bajarmadi: {report[-400:]}")
        _git("add", "-A", cwd=path)
        if not _git("diff", "--cached", "--stat", cwd=path):
            discard(uid)
            raise RuntimeError("Hech qanday o'zgarish qilinmadi")
        progress("🧪 Kod yozildi - testlarni tekshiryapman…")
        ok, tests = _tests(path)
        if not ok:
            discard(uid)
            return {"id": uid, "ok": False, "report": report, "tests": tests, "diff": ""}
        _git("commit", "-q", "-m", f"Ali o'zini kuchaytirdi: {task[:70]}\n\n{report[:1500]}\n\n"
             "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>", cwd=path)
        diff = _git("show", "--stat", "--format=", "HEAD", cwd=path)
        state = _state()
        state[uid] = {"task": task, "branch": branch, "at": time.time()}
        _save(state)
        return {"id": uid, "ok": True, "report": report, "tests": tests, "diff": diff}
    finally:
        _lock.release()


def discard(uid: str) -> None:
    path, branch = WORK / uid, f"ali-upgrade/{uid}"
    _git("worktree", "remove", "--force", str(path), check=False)
    shutil.rmtree(path, ignore_errors=True)
    _git("branch", "-D", branch, check=False)
    state = _state()
    state.pop(uid, None)
    _save(state)


def apply(uid: str) -> str:
    """Tasdiqlangan o'zgarishni main'ga qo'shadi va push qiladi."""
    state = _state()
    item = state.get(uid)
    if not item:
        raise RuntimeError("Bu kuchaytirish topilmadi yoki allaqachon bajarilgan")
    _git("merge", "--no-edit", item["branch"])
    pushed = "push qilindi"
    try:
        _git("push", "origin", "HEAD")
    except RuntimeError as e:
        pushed = f"push bo'lmadi: {e}"
    discard(uid)
    return pushed


def restart_later(delay: float = 3.0) -> None:
    """Yangi kod bilan Ali'ni qayta ishga tushiradi (shu buyruq bilan yangi jarayon, eskisi yopiladi)."""
    def go():
        time.sleep(delay)
        if os.getenv("ALI_SUPERVISED"):  # scripts/autostart.cmd o'zi qayta ishga tushiradi
            os._exit(75)
        # yangi jarayon port bo'shashini kutib turadi, keyin shu buyruq bilan ishga tushadi
        subprocess.Popen([sys.executable, "-c", "import subprocess,sys,time;time.sleep(4);subprocess.Popen(sys.argv[1:])",
                          sys.executable, *sys.argv], cwd=os.getcwd(),
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        os._exit(0)
    threading.Thread(target=go, daemon=True).start()
