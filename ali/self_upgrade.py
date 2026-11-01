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
from pathlib import Path

from .config import ROOT, config

log = logging.getLogger("ali.self_upgrade")

WORK = config.data_dir / "upgrade"
STATE = config.data_dir / "upgrade_state.json"
TIMEOUT_MIN = 40
QUERY = re.compile(r"(o['ʻ‘’]?zingni|ozingni|узингни|ўзингни|озингни|o['ʻ‘’]?zini|ozini|узини|ўзини|озини|ali|али)\s+"
                   r"(o['ʻ‘’]?zi\s+|ози\s+|ўзи\s+)?(kuchaytir|кучайтир|takomillashtir|такомиллаштир|yaxshila|яхшила|"
                   r"rivojlantir|ривожлантир)|/kuchaytir", re.I)
# «Dasturchiga ayt: ... to'g'irlasin», «dasturchi, X ni qo'sh» - buyruq (o'tgan zamon/inkor emas: «to'g'irlamadi» buyruq emas)
CODER = re.compile(r"(dasturchi|дастурчи|programmist|программист)", re.I)
CHANGE = re.compile(r"(to['ʻ‘’]?g['ʻ‘’]?irla|togirla|тогирла|тўғрила|туғрила|tuzat|тузат|o['ʻ‘’]?zgartir|ozgartir|озгартир|"
                    r"ўзгартир|узгартир|qo['ʻ‘’]?sh|qosh|кош|қўш|кўш|sozla|созла|qil|кил|қил|yoz|ёз|йоз|"
                    r"olib\s*tashla|олиб\s*ташла|o['ʻ‘’]?chir|очир|ўчир|ulab\s*ber|улаб\s*бер)"
                    r"(sin|син|gin|гин|ib\s+ber|иб\s+бер|ing|инг)?(?=[\s.,!:;)]|$)", re.I)
# «dasturchiga ayt/yoz/buyur ...», «dasturchiga: ...» - qanday fe'l bo'lishidan qat'i nazar topshiriq
TO_CODER = re.compile(r"(dasturchi|дастурчи|programmist|программист)(ga|га)\b\s*[:,-]?\s*"
                      r"(ayt|айт|yoz|ёз|йоз|buyur|буюр|топшир|topshir|тушунтир|tushuntir|\S)", re.I)
# Dasturchi haqidagi shikoyat/savol - topshiriq emas («nega to'g'irlamadi», «javob bermayapti»)
NOT_ORDER = re.compile(r"^\W*(ali|али)?\W*(nega|нега|nima\s+uchun|нима\s+учун|qachon|качон|қачон)\b", re.I)
PERMISSION = "ali_kuchaytirish"  # Ruxsatlar: "auto" - testlar o'tsa o'zi qo'llaydi va GitHub'ga push qiladi; "ask" - tugma
SECRET_ENV = re.compile(r"TOKEN|KEY|SECRET|PASSWORD|CREDENTIAL|TELEGRAM|SESSION", re.I)
_lock = threading.Lock()

TASK = """{agent}

Sen Ali loyihasining (shaxsiy AI yordamchi, Python/FastAPI, Telegram bot, web/) dasturchisisan.
Egasi so'ragan o'zgarish:
<<<{task}>>>

Qoidalar:
- Mavjud kod uslubiga mos yoz: o'zbekcha izohlar va xabarlar, mavjud modullarni qayta ishlat (ali/skills, ali/*.py).
- .env, data/, xotira/, agents/18-agent.md va maxfiy kalitlarga TEGMA. Kalit, token yoki parolni kodga yozma.
- Ali serverini, Telegram botni ishga tushirma va tashqi xizmatlarga so'rov yuborma - faqat kod va testlar.
- Kichik va aniq o'zgarish qil; keraksiz qayta yozma. Yangi funksiya bo'lsa - tests/ ga oddiy test qo'sh.
- Oxirida `python -X utf8 -m unittest discover -s tests` ni ishga tushir va testlar o'tishiga erish.
- Yakunda 3-6 qatorda o'zbekcha hisobot yoz: nima qo'shildi, qaysi fayllar, qanday ishlatiladi."""


def is_request(text: str) -> bool:
    text = text or ""
    if text.rstrip().endswith("?") or NOT_ORDER.search(text):
        return bool(QUERY.search(text))
    return bool(QUERY.search(text) or TO_CODER.search(text) or (CODER.search(text) and CHANGE.search(text)))


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


def _safe_env(cwd) -> dict:
    """Nusxa uchun muhit: kalit/token yo'q (aks holda nusxa Telegram botni ishga tushirib, tugmalarni "o'g'irlaydi")."""
    from . import local_ai
    env = {k: v for k, v in local_ai.clean_env().items() if not SECRET_ENV.search(k)}
    env["ALI_STATE_DIR"] = str(cwd / "data" / "_test_state")
    return env


def _tests(cwd) -> tuple[bool, str]:
    """Testlar: muvaffaqiyatsiz test yoki import xatosi bo'lmasa - o'tdi (fayl bandligidagi tearDown xatosi hisobga olinmaydi)."""
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests"], cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                       env=_safe_env(cwd), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out = r.stdout + r.stderr
    bad = [l for l in out.splitlines() if re.match(r"^(FAIL|ERROR): ", l) and "tearDownModule" not in l]
    ran = re.search(r"Ran (\d+) tests", out)
    return (not bad and ran is not None), (f"{ran.group(1) if ran else '?'} ta test; " +
                                           ("hammasi o'tdi" if not bad else "buzilgan: " + "; ".join(bad)[:600]))


def _dasturchi(task: str) -> str:
    """Dasturchi agentning ko'rsatmasi va shu vazifaga mos bilimlari - kuchaytirishni u bajaradi."""
    try:
        from .service import agent_system, brain, knowledge_block
        a = brain.agents.get("dasturchi")
        return (agent_system(a) + knowledge_block(task, "dasturchi")) if a else ""
    except Exception as e:  # agent yuklanmasa ham kuchaytirish ishlayveradi
        log.warning("Dasturchi ko'rsatmasi olinmadi: %s", e)
        return ""


def _coders() -> list[tuple[str, str]]:
    """Kod yozadigan ilovalar navbati: Claude Code, keyin Codex (ChatGPT) - limiti tugaganlari o'tkaziladi."""
    from . import local_ai
    found = [("claude", local_ai._claude_exe()), ("codex", local_ai.app_exe("codex"))]
    return [(k, exe) for k, exe in found if exe and not local_ai.paused_until(k)]


def _code(key: str, exe: str, prompt: str, path: Path) -> tuple[bool, str]:
    """Bitta ilova bilan kod yozish. (muvaffaqiyatli, hisobot). Limit tugasa - Ali uni eslab qoladi."""
    from . import local_ai
    if key == "claude":
        cmd = [exe, "-p", "--output-format", "text", "--permission-mode", "acceptEdits", "--allowedTools", "Read", "Edit",
               "Write", "Glob", "Grep", "Bash(python *)", "Bash(git diff*)", "Bash(git status*)"]
    else:  # Codex: faqat shu nusxa papkasiga yozadi (workspace-write sandbox)
        cmd = [exe, "exec", "--sandbox", "workspace-write", "--skip-git-repo-check", "-C", str(path), "-"]
    try:
        r = subprocess.run(cmd, input=prompt, cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=TIMEOUT_MIN * 60, env=_safe_env(path), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return False, f"{TIMEOUT_MIN} daqiqada tugatolmadi"
    except OSError as e:
        return False, f"ishga tushmadi: {e}"
    out = (r.stdout or "").strip()
    raw = (r.stderr or "") + out
    if r.returncode != 0 and local_ai._LIMIT_RE.search(raw):
        local_ai._mark_limit(key, raw)
    return r.returncode == 0, (out or r.stderr or "").strip()[-2500:]


API_PICK = """{agent}

Ali loyihasi fayllari (yo'l - qisqa tavsif):
{index}

Egasi so'ragan o'zgarish: <<<{task}>>>
Shu o'zgarish uchun o'qish va tahrirlash kerak bo'lgan 1-5 ta faylni tanla (yangi fayl kerak bo'lsa ham mavjud
bog'liq fayllarni tanla). FAQAT JSON: {{"files": ["ali/...py"]}}"""

API_EDIT = """{prompt}

Fayllar (to'liq matn):
{files}

Endi o'zgarishni qil. Har tahrir: "old" - fayldagi AYNAN mavjud, takrorlanmaydigan parcha (bo'shliqlari bilan),
"new" - uning o'rniga. Yangi fayl: "old" bo'sh, "new" - to'liq matn. .env, data/, xotira/ ga tegma.
FAQAT JSON: {{"edits": [{{"file": "ali/...py", "old": "...", "new": "..."}}], "report": "3-6 qator o'zbekcha hisobot"}}"""


def _index(path: Path) -> str:
    """Fayllar ro'yxati: yo'l va birinchi docstring qatori - AI qaysi faylni o'qishni tanlashi uchun."""
    rows = []
    for f in sorted([*path.glob("*.py"), *path.glob("ali/**/*.py"), *path.glob("agents/*.md"), *path.glob("web/*.html")]):
        rel = f.relative_to(path).as_posix()
        if "18-agent" in rel:
            continue
        head = f.read_text(encoding="utf-8", errors="replace")[:400]
        m = re.search(r'"""(.+)', head) or re.search(r"^#\s*(.+)", head, re.M)
        rows.append(f"{rel} - {m.group(1).strip()[:110] if m else ''}")
    return "\n".join(rows)


def _safe_rel(path: Path, rel: str) -> Path | None:
    """Faqat loyiha ichidagi oddiy fayllar: .env, data/, xotira/, .git va 18+ agentga yozilmaydi."""
    rel = rel.replace("\\", "/").lstrip("/")
    target = (path / rel).resolve()
    if path.resolve() not in target.parents or re.match(r"(\.env|data/|xotira/|\.git)", rel) or "18-agent" in rel:
        return None
    return target


def _api_code(prompt: str, task: str, path: Path) -> tuple[bool, str]:
    """Claude Code/Codex'siz kod yozish: AI (Gemini API va boshqalar) fayllarni tanlaydi, keyin aniq tahrirlarni beradi."""
    from . import local_ai
    from .service import _ask_json
    ready = local_ai.connected()
    try:
        picked = _ask_json(API_PICK.format(agent=_dasturchi(task)[:6000], index=_index(path)[:20000], task=task), ready, 300)
        files, total = [], 0
        for rel in [str(x) for x in picked.get("files", [])][:5]:
            f = _safe_rel(path, rel)
            if f and f.is_file():
                body = f.read_text(encoding="utf-8", errors="replace")
                if total + len(body) > 120000:
                    continue
                total += len(body)
                files.append(f"===== {rel} =====\n{body}")
        res = _ask_json(API_EDIT.format(prompt=prompt, files="\n\n".join(files) or "(fayl tanlanmadi)"), ready, 600)
    except (ValueError, RuntimeError) as e:
        return False, f"AI javob bermadi: {e}"
    applied = []
    for e in res.get("edits", []) if isinstance(res.get("edits"), list) else []:
        f = _safe_rel(path, str(e.get("file", "")))
        old, new = str(e.get("old", "")), str(e.get("new", ""))
        if not f or not (old or new):
            continue
        if not old:  # yangi fayl
            if f.exists():
                continue
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(new, encoding="utf-8")
        else:
            body = f.read_text(encoding="utf-8") if f.is_file() else ""
            if body.count(old) != 1:
                log.warning("Dasturchi tahriri mos kelmadi: %s", e.get("file"))
                continue
            f.write_text(body.replace(old, new), encoding="utf-8")
        applied.append(str(e.get("file")))
    if not applied:
        return False, "AI tahrirlari fayllarga mos kelmadi yoki tahrir berilmadi"
    return True, (str(res.get("report") or "") + "\n\nO'zgargan: " + ", ".join(sorted(set(applied)))).strip()


def _reopen_note() -> str:
    """Limitlar qachon ochilishi - egasi qachon qayta yuborishni bilsin."""
    from datetime import datetime
    from . import local_ai
    times = [t for t in (local_ai.paused_until(k) for k in ("claude", "codex", "gemini")) if t]
    return (f"\n\n⏳ AI limitlari {datetime.fromtimestamp(min(times)).strftime('%H:%M')} da ochiladi - shunda qayta yuboring."
            if times else "")


def auto_apply() -> bool:
    """Ruxsatlar -> ali_kuchaytirish = "auto" bo'lsa testlar o'tgach o'zi qo'llaydi va GitHub'ga push qiladi."""
    from . import permissions
    return permissions.mode(PERMISSION, True) == "auto"


def learn(task: str, report: str, applied: bool) -> None:
    """Natija Dasturchi agentning bilimi bo'ladi (keyingi ishlarda tayanadi)."""
    from .memory import memory
    memory.add_knowledge(f"[dasturchi] Ali kuchaytirildi: {task[:80]}",
                         f"Vazifa: {task}\nHolat: {'qo‘llandi va GitHub’ga push qilindi' if applied else 'tayyor, tasdiq kutilmoqda'}\n\n{report}")


def run(task: str, progress) -> dict:
    """Dasturchi agent vazifani alohida nusxada bajaradi, testlaydi. Natija: {id, ok, report, diff, tests}."""
    from . import local_ai
    from .monitor import monitor
    if not _lock.acquire(blocking=False):
        raise RuntimeError("Hozir boshqa kuchaytirish ketyapti - tugashini kuting")
    uid, ok = None, False
    job = monitor.start_job("dasturchi", f"Ali'ni kuchaytirish: {task[:200]}", "self_upgrade")
    try:
        coders = _coders()
        uid = uuid.uuid4().hex[:8]
        branch, path = f"ali-upgrade/{uid}", WORK / uid
        WORK.mkdir(parents=True, exist_ok=True)
        _git("worktree", "add", "-b", branch, str(path), "HEAD")
        (path / "data").mkdir(exist_ok=True)  # data/ gitignore'da - testlar uchun bo'sh papka
        state = _state()
        state[uid] = {"task": task, "branch": branch, "at": time.time(), "running": True}  # uzilsa - qayta yoqilganda topiladi
        _save(state)
        prompt, report, failures = TASK.format(agent=_dasturchi(task), task=task), "", []
        for key, exe in coders:  # Claude Code -> Codex: biri ishlamasa yoki limiti tugasa - keyingisi boshidan
            progress(f"👨‍💻 Dasturchi agent {local_ai.NAMES[key]} bilan alohida nusxada kod yozyapti ({branch}) - "
                     f"{TIMEOUT_MIN} daqiqagacha…")
            done, report = _code(key, exe, prompt, path)
            if done and _git("status", "--porcelain", cwd=path):
                break
            failures.append(f"{local_ai.NAMES[key]}: {report[-300:] if not done else 'hech narsa o‘zgartirmadi'}")
            _git("reset", "-q", "--hard", cwd=path)
            _git("clean", "-qfd", "-e", "data/", cwd=path)
        else:  # Claude Code ham, Codex ham yo'q/limitda - Dasturchi o'z bilimi + API AI (Gemini) bilan aniq tahrir qiladi
            key = "api"
            progress("👨‍💻 Claude Code/Codex band - Dasturchi o'z bilimi va Gemini bilan kodni o'zgartiryapti…")
            done, report = _api_code(prompt, task, path)
            if not done:
                failures.append(f"Dasturchi (API): {report[-300:]}")
                raise RuntimeError("Dasturchi vazifani bajara olmadi:\n" + "\n".join(failures) + _reopen_note())
        _git("add", "-A", cwd=path)
        if not _git("diff", "--cached", "--stat", cwd=path):
            raise RuntimeError("Hech qanday o'zgarish qilinmadi")
        progress("🧪 Kod yozildi - testlarni tekshiryapman…")
        passed, tests = _tests(path)
        if not passed:
            return {"id": uid, "ok": False, "report": report, "tests": tests, "diff": ""}
        _git("commit", "-q", "-m", f"Ali o'zini kuchaytirdi ({local_ai.NAMES.get(key, 'Dasturchi')}):{task[:70]}\n\n{report[:1500]}"
             + ("\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" if key == "claude" else ""), cwd=path)
        diff = _git("show", "--stat", "--format=", "HEAD", cwd=path)
        state = _state()
        state[uid] = {"task": task, "branch": branch, "at": time.time(), "report": report[:2500]}
        _save(state)
        ok = True
        return {"id": uid, "ok": True, "report": report, "tests": tests, "diff": diff}
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Dasturchi {TIMEOUT_MIN} daqiqada tugatolmadi - vazifani kichikroq qilib qayta yozing") from None
    finally:
        if uid and not ok:
            discard(uid)  # har qanday xatoda nusxa qolib ketmaydi
        monitor.finish(job, ok)
        _lock.release()


def interrupted(notify=None) -> list[str]:
    """Ali qayta ishga tushganda: yarim qolgan kuchaytirishlar (jarayon uzilgan) tozalanadi, egasiga aytiladi."""
    lost = []
    for uid, item in list(_state().items()):
        if item.get("running"):
            lost.append(item.get("task", ""))
            discard(uid)
    if lost and notify:
        notify("⚠️ Ali qayta ishga tushgani sabab kuchaytirish yarim yo'lda to'xtadi (o'zgarish qo'llanmadi):\n"
               + "\n".join(f"• {t[:200]}" for t in lost) + "\nQayta yuboring: /kuchaytir …")
    return lost


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
    learn(item["task"], item.get("report", ""), True)
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
