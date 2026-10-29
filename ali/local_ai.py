"""Kompyuterdagi AI ilovalari: Claude Code, ChatGPT (Codex CLI), Gemini CLI.

Claude API ishlamasa (balans tugagan va h.k.) Ali javobni shu ilovalar orqali oladi - ular API kaliti bilan emas,
foydalanuvchining o'z akkaunti (obunasi) bilan ishlaydi. Ishlatish uchun egasi saytga kompyuterdan kirganda
ruxsat beradi (data/local_access.json).

O'rnatish (ixtiyoriy, har biridan keyin terminalda bir marta kirish kerak):
    Claude Code:  VS Code'dagi Claude Code kengaytmasi yoki  npm install -g @anthropic-ai/claude-code  -> claude
    ChatGPT:      npm install -g @openai/codex                -> codex   (ChatGPT akkaunti bilan kirish)
    Gemini:       npm install -g @google/gemini-cli           -> gemini  (Google akkaunti bilan kirish)
"""
import json
import re
import logging
import os
import shutil
import subprocess
import time
import hashlib
import platform
import getpass
from datetime import datetime, timedelta
from pathlib import Path

from .config import config

log = logging.getLogger("ali.local_ai")

ACCESS = config.data_dir / "local_access.json"
WORKDIR = config.data_dir / "local_ai"
TIMEOUT = 300
NAMES = {"claude": "Claude", "codex": "ChatGPT", "gemini": "Gemini"}


# --- ruxsat ---
def device_identity():
    return hashlib.sha256((platform.node()+'|'+getpass.getuser()+'|'+str(config.data_dir.resolve())).encode()).hexdigest()

def access() -> bool | None:
    """True - ruxsat berilgan, False - rad etilgan, None - hali so'ralmagan."""
    try:
        data = json.loads(ACCESS.read_text(encoding="utf-8"))
        if data.get('device')!=device_identity():return None
        value = data.get("allowed")
        return value if isinstance(value, bool) else None
    except (OSError, ValueError, AttributeError):
        return None


def set_access(allowed: bool) -> None:
    ACCESS.write_text(json.dumps({"allowed": bool(allowed), "device":device_identity(), "at": time.strftime("%Y-%m-%d %H:%M:%S")}), encoding="utf-8")
    log.info("Kompyuterdagi AI ilovalariga ruxsat: %s", allowed)


# --- ilovalarni topish ---
def _claude_exe() -> str | None:
    if exe := shutil.which("claude"):
        return exe
    # VS Code / Cursor kengaytmasi ichidagi Claude Code (eng yangi versiya)
    home = Path(os.path.expanduser("~"))
    found = []
    for editor in (".vscode", ".cursor", ".windsurf"):
        found += (home / editor / "extensions").glob("anthropic.claude-code-*/resources/native-binary/claude*")
    found = [p for p in found if p.is_file() and p.suffix.lower() in ("", ".exe")]
    return str(max(found, key=lambda p: p.stat().st_mtime)) if found else None


def app_exe(key: str) -> str | None:
    if key == "claude":
        return _claude_exe()
    # Server ishga tushgandan keyin o'rnatilgan bo'lsa, PATH hali yangilanmagan bo'ladi
    npm_dir = Path(os.environ.get("APPDATA", "")) / "npm"
    return shutil.which(key) or next((str(p) for p in (npm_dir / f"{key}.cmd", npm_dir / key) if p.exists()), None)


def apps() -> dict[str, str]:
    """Ishlatiladigan ilovalar: {kalit: bajariladigan fayl}. Egasi ulagan (tekshirilgan) ilovalar birinchi."""
    state = app_state()
    found = {"gemini": app_exe("gemini"), "codex": app_exe("codex")}
    if config.chat_provider == 'claude' or state.get("claude", {}).get("connected"):
        found['claude'] = _claude_exe()
    found = {k: v for k, v in found.items() if v and state.get(k, {}).get("connected") is not False}
    return dict(sorted(found.items(), key=lambda kv: not state.get(kv[0], {}).get("connected")))


def summary() -> dict:
    found, state = apps(), app_state()
    return {"allowed": access(), "primary": state.get("_primary"), "coach": bool(state.get("_coach")),
            "programs": programs(), "services": services(), "apps": [
        {"key": k, "name": NAMES[k], "ready": k in found, "installed": bool(app_exe(k)),
         "connected": state.get(k, {}).get("connected"), "at": state.get(k, {}).get("at", ""),
         "error": state.get(k, {}).get("error", "")} for k in NAMES]}


# --- boshqa dasturlar (kalit kerak emas - kompyuterda topiladi) ---
def _vscode_exe() -> str | None:
    if exe := shutil.which("code") or shutil.which("code.cmd"):
        return exe
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code"
    return next((str(p) for p in (base / "bin" / "code.cmd", base / "Code.exe") if p.exists()), None)


PROGRAMS = {"vscode": ("VS Code", _vscode_exe)}


def programs() -> list[dict]:
    return [{"key": k, "name": name, "found": bool(find())} for k, (name, find) in PROGRAMS.items()]


def open_program(key: str, path: str = "") -> None:
    name, find = PROGRAMS[key]
    exe = find()
    if not exe:
        raise RuntimeError(f"{name} topilmadi")
    subprocess.Popen([exe, *([path] if path else [])], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


# --- xizmatlar ilova (CLI) orqali: GitHub (gh), Vercel (vercel) - token qo'lda kiritilmaydi ---
def _gh_exe() -> str | None:
    found = shutil.which("gh")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
        p = Path(base) / "GitHub CLI" / "gh.exe"
        if p.exists():
            return str(p)
    return None


def _vercel_exe() -> str | None:
    npm_dir = Path(os.environ.get("APPDATA", "")) / "npm"
    return shutil.which("vercel") or next((str(p) for p in (npm_dir / "vercel.cmd",) if p.exists()), None)


SERVICES = {
    "github": {"name": "GitHub", "exe": _gh_exe, "login": ["auth", "login", "--web", "-h", "github.com", "-p", "https"],
               "install": ["winget", "install", "--id", "GitHub.cli", "-e", "--silent",
                           "--accept-source-agreements", "--accept-package-agreements"]},
    "vercel": {"name": "Vercel", "exe": _vercel_exe, "login": ["login"], "install": "npm:vercel"},
}


def service_token(key: str) -> str:
    """Ilova saqlagan kirish tokeni (egasi ilovada kirgan bo'lsa). Bo'lmasa - bo'sh."""
    try:
        if key == "github" and (exe := _gh_exe()):
            r = subprocess.run([exe, "auth", "token", "-h", "github.com"], capture_output=True, text=True, timeout=20,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return r.stdout.strip() if r.returncode == 0 else ""
        if key == "vercel":
            for base in (os.environ.get("APPDATA", ""), os.path.expanduser("~/.local/share")):
                auth = Path(base) / "com.vercel.cli" / "Data" / "auth.json"
                auth = auth if auth.exists() else Path(base) / "com.vercel.cli" / "auth.json"
                if auth.exists():
                    return json.loads(auth.read_text(encoding="utf-8")).get("token", "")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return ""


def install_service(key: str) -> str:
    spec = SERVICES[key]
    if spec["install"] == "npm:vercel":
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm:
            raise RuntimeError("Node.js (npm) o'rnatilmagan")
        cmd = [npm, "install", "-g", "vercel"]
    else:
        cmd = spec["install"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0 and not spec["exe"]():
        raise RuntimeError(f"O'rnatilmadi: {(r.stderr or r.stdout)[-300:]}")
    return f"{spec['name']} ilovasi o'rnatildi"


def login_service(key: str) -> None:
    exe = SERVICES[key]["exe"]()
    if not exe:
        raise RuntimeError(f"{SERVICES[key]['name']} ilovasi o'rnatilmagan")
    subprocess.Popen(["cmd", "/k", exe, *SERVICES[key]["login"]], env=clean_env(),
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


def verify_service(key: str) -> tuple[bool, str]:
    import httpx
    token = service_token(key)
    if not token:
        remember(key, False, "ilovada kirilmagan")
        return False, f"{SERVICES[key]['name']} ilovasida hali kirilmagan - “Kirish” ni bosing"
    url = {"github": "https://api.github.com/user", "vercel": "https://api.vercel.com/v2/user"}[key]
    try:
        r = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
        ok = r.status_code == 200
    except httpx.HTTPError as e:
        return False, f"Tekshirib bo'lmadi: {e}"
    if not ok:
        remember(key, False, f"HTTP {r.status_code}")
        return False, f"{SERVICES[key]['name']} kirishni tasdiqlamadi"
    data = r.json()
    who = data.get("login") or (data.get("user") or {}).get("username") or ""
    remember(key, True)
    return True, f"{SERVICES[key]['name']} ulandi{(' · ' + who) if who else ''}"


def services() -> list[dict]:
    state = app_state()
    return [{"key": k, "name": s["name"], "installed": bool(s["exe"]()), "connected": state.get(k, {}).get("connected"),
             "at": state.get(k, {}).get("at", ""), "error": state.get(k, {}).get("error", "")} for k, s in SERVICES.items()]


# --- ulanishni eslab qolish (data/ai_apps.json) ---
STATE = config.data_dir / "ai_apps.json"
PACKAGES = {"claude": "@anthropic-ai/claude-code", "codex": "@openai/codex", "gemini": "@google/gemini-cli"}
LOGIN_ARGS = {"claude": [], "codex": ["login"], "gemini": []}


def app_state() -> dict:
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def remember(key: str, connected: bool | None, error: str = "") -> None:
    data = app_state()
    if connected is None:
        data.pop(key, None)
    else:
        data[key] = {"connected": connected, "at": time.strftime("%Y-%m-%d %H:%M"), "error": error[:300]}
    STATE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    log.info("AI ilovasi %s: %s", key, "unutildi" if connected is None else ("ulandi" if connected else "ulanmadi"))


def option(name: str):
    """Saqlangan sozlama: _primary (asosiy Pro ilova), _coach (Murabbiy Pro orqali o'qitsin)."""
    return app_state().get(name)


def set_option(name: str, value) -> None:
    data = app_state()
    if value in (None, False, ""):
        data.pop(name, None)
    else:
        data[name] = value
    STATE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def connected() -> list[str]:
    """Egasi ulagan (tekshirilgan) ilovalar: asosiy (primary) birinchi."""
    state, first = app_state(), option("_primary")
    keys = [k for k in NAMES if state.get(k, {}).get("connected") and app_exe(k) and not paused_until(k)]
    return sorted(keys, key=lambda k: k != first)


def ask_pro(prompt: str, timeout: int = TIMEOUT, only: str | None = None,
            images: list[str] | None = None) -> tuple[str, str] | None:
    """Ulangan Pro ilovalardan (asosiysi birinchi) javob: (ilova nomi, javob). only - faqat shu ilova.
    Ruxsat bo'lmasa yoki hech biri javob bermasa None."""
    if access() is not True:
        return None
    for key in ([only] if only else connected()):
        try:
            return NAMES[key], ask_one(key, app_exe(key), prompt, timeout, images)
        except RuntimeError as e:
            log.warning("%s Pro ilovasi javob bermadi: %s", key, e)
    return None


def install(key: str) -> str:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise RuntimeError("Node.js (npm) o'rnatilmagan: https://nodejs.org")
    r = subprocess.run([npm, "install", "-g", PACKAGES[key]], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise RuntimeError(f"O'rnatilmadi: {(r.stderr or r.stdout)[-400:]}")
    return f"{NAMES[key]} o'rnatildi"


def open_login(key: str) -> None:
    """Kirish uchun kompyuterda terminal oynasini ochadi - parolni egasi o'zi kiritadi."""
    exe = app_exe(key)
    if not exe:
        raise RuntimeError(f"{NAMES[key]} o'rnatilmagan")
    subprocess.Popen(["cmd", "/k", exe, *LOGIN_ARGS[key]], env=clean_env(),
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


def verify(key: str) -> tuple[bool, str]:
    """Ilova akkaunt bilan haqiqatan javob beradimi - tekshiradi va natijani eslab qoladi."""
    exe = app_exe(key)
    if not exe:
        remember(key, False, "o'rnatilmagan")
        return False, f"{NAMES[key]} o'rnatilmagan"
    try:
        ask_one(key, exe, "Faqat bitta so'z bilan javob ber: OK", timeout=180)
    except RuntimeError as e:
        remember(key, False, str(e))
        return False, str(e)
    remember(key, True)
    return True, f"{NAMES[key]} ulandi va eslab qolindi"


# --- so'rov ---
def _command(key: str, exe: str, images: list[str] | None = None) -> list[str]:
    if key == "claude":
        # bilmagan narsani internetdan qidirib aniqlasin; rasm bo'lsa - Read bilan ko'radi (faqat o'qish vositalari)
        return [exe, "-p", "--output-format", "text", "--allowedTools", "WebSearch", "WebFetch",
                *(["Read"] if images else [])]
    if key == "codex":
        return [exe, "exec", "--sandbox", "read-only", "--skip-git-repo-check",
                *[arg for img in images or [] for arg in ("-i", img)], "-"]
    return [exe, "-p", "Quyidagi ko'rsatma va savolga javob ber."]


def _prompt(system: str, history: list[dict], text: str) -> str:
    lines = [f"<ko'rsatma>\n{system}\n</ko'rsatma>"]
    if history:
        lines.append("<suhbat_tarixi>\n" + "\n".join(
            f"{'Foydalanuvchi' if m['role'] == 'user' else 'Sen'}: {str(m['content'])[:2000]}" for m in history[-12:])
            + "\n</suhbat_tarixi>")
    lines.append(f"Foydalanuvchining yangi xabari:\n{text}\n\nFaqat javob matnini yoz (kod yoki fayl o'zgartirma).")
    return "\n\n".join(lines)


def clean_env() -> dict:
    """.env dagi API kalitlarisiz muhit - ilova akkaunt (obuna) bilan ishlashi uchun."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")}
    # Gemini CLI faqat "ishonchli" papkada ishlaydi; WORKDIR - Ali'ning o'z bo'sh ish papkasi
    env["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
    return env


# --- obuna limiti: tugasa tiklanguncha shu ilovaga murojaat qilinmaydi (fon ishlari limitni "yeb" qo'ymasin) ---
LIMITS = config.data_dir / "ai_limits.json"
_LIMIT_RE = re.compile(r"hit your .{0,20}limit|usage limit|rate limit|limit reached|quota", re.I)
_RESET_RE = re.compile(r"resets\s+(?:[A-Za-z]{3,9}\s+\d{1,2},?\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I)


def _limits() -> dict:
    try:
        return json.loads(LIMITS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def paused_until(key: str) -> float:
    """Limit tugagan bo'lsa - tiklanish vaqti (unix), aks holda 0."""
    until = float(_limits().get(key, 0))
    return until if until > time.time() else 0


def _reset_time(text: str) -> float:
    """"resets 4pm" -> keyingi 16:00; topilmasa - 3 soatdan keyin qayta sinab ko'riladi."""
    m = _RESET_RE.search(text or "")
    if not m:
        return time.time() + 3 * 3600
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    now = datetime.now()
    at = now.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
    if at <= now:
        at += timedelta(days=1)
    return at.timestamp() + 120


def _mark_limit(key: str, raw: str) -> float:
    data = _limits()
    data[key] = _reset_time(raw)
    LIMITS.write_text(json.dumps(data), encoding="utf-8")
    log.warning("%s obuna limiti tugadi - %s gacha murojaat qilinmaydi", NAMES[key],
                time.strftime("%d.%m %H:%M", time.localtime(data[key])))
    return data[key]


def ask_one(key: str, exe: str, prompt: str, timeout: int = TIMEOUT, images: list[str] | None = None) -> str:
    """Bitta ilovaga so'rov (ruxsatni chaqiruvchi tekshiradi). images - rasm fayllari yo'llari. Xatoda RuntimeError."""
    if until := paused_until(key):
        raise RuntimeError(f"{NAMES[key]} obuna limiti tugagan - {time.strftime('%d.%m %H:%M', time.localtime(until))} da tiklanadi")
    WORKDIR.mkdir(parents=True, exist_ok=True)
    if images and key == "claude":  # Claude Code rasmni fayl sifatida o'qib ko'radi
        prompt += "\n\nBiriktirilgan rasm(lar) - Read vositasi bilan ochib, diqqat bilan ko'r:\n" + "\n".join(images)
    try:
        proc = subprocess.run(_command(key, exe, images), input=prompt, cwd=WORKDIR, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, env=clean_env(),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{NAMES[key]} {timeout} soniyada javob bermadi")
    except OSError as e:
        raise RuntimeError(f"{NAMES[key]} ishga tushmadi: {e}")
    answer = proc.stdout.strip()
    if proc.returncode != 0 or not answer:
        raw = (proc.stderr or "") + answer
        detail = re.sub(r"\x1b\[[0-9;]*m", "", proc.stderr or answer).strip()[-400:]
        if "IneligibleTierError" in raw:
            detail = ("Google Gemini CLI'ni shaxsiy akkauntlar uchun to'xtatgan - bu ilova endi ishlamaydi. "
                      "Gemini'dan API kaliti orqali foydalaning.")
        elif _LIMIT_RE.search(raw):
            until = _mark_limit(key, raw)
            detail = f"obuna limiti tugagan - {time.strftime('%d.%m %H:%M', time.localtime(until))} da tiklanadi"
        raise RuntimeError(f"{NAMES[key]} javob bermadi (exit {proc.returncode}): {detail}")
    return answer


def ask(system: str, history: list[dict], text: str) -> tuple[str, str] | None:
    """Ruxsat bo'lsa, o'rnatilgan ilovalardan birinchi ishlaganidan javob oladi: (ilova nomi, javob)."""
    if access() is not True:
        return None
    WORKDIR.mkdir(parents=True, exist_ok=True)
    prompt = _prompt(system, history, text)
    # .env dagi API kalitlari ilovaga o'tmasin: aks holda ular akkaunt (obuna) o'rniga kalitni ishlatadi
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")}
    for key, exe in apps().items():
        if paused_until(key):
            continue
        try:
            proc = subprocess.run(_command(key, exe), input=prompt, cwd=WORKDIR, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=TIMEOUT, env=env,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning("%s ilovasi ishlamadi: %s", key, e)
            continue
        answer = proc.stdout.strip()
        if proc.returncode == 0 and answer:
            return NAMES[key], answer
        log.warning("%s ilovasi javob bermadi (exit %s): %s", key, proc.returncode, (proc.stderr or answer)[-300:])
    return None
