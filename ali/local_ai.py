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
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from .config import config

log = logging.getLogger("ali.local_ai")

ACCESS = config.data_dir / "local_access.json"
WORKDIR = config.data_dir / "local_ai"
TIMEOUT = 300
NAMES = {"claude": "Claude", "codex": "ChatGPT", "gemini": "Gemini"}


# --- ruxsat ---
def access() -> bool | None:
    """True - ruxsat berilgan, False - rad etilgan, None - hali so'ralmagan."""
    try:
        value = json.loads(ACCESS.read_text(encoding="utf-8")).get("allowed")
        return value if isinstance(value, bool) else None
    except (OSError, ValueError, AttributeError):
        return None


def set_access(allowed: bool) -> None:
    ACCESS.write_text(json.dumps({"allowed": bool(allowed), "at": time.strftime("%Y-%m-%d %H:%M:%S")}), encoding="utf-8")
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


def apps() -> dict[str, str]:
    """O'rnatilgan ilovalar: {kalit: bajariladigan fayl} - ishlatish tartibida."""
    found = {"claude": _claude_exe(), "codex": shutil.which("codex"), "gemini": shutil.which("gemini")}
    return {k: v for k, v in found.items() if v}


def summary() -> dict:
    found = apps()
    return {"allowed": access(), "apps": [{"key": k, "name": NAMES[k], "ready": k in found} for k in NAMES]}


# --- so'rov ---
def _command(key: str, exe: str) -> list[str]:
    if key == "claude":
        return [exe, "-p", "--output-format", "text"]
    if key == "codex":
        return [exe, "exec", "--skip-git-repo-check", "-"]
    return [exe, "-p", "Quyidagi ko'rsatma va savolga javob ber."]


def _prompt(system: str, history: list[dict], text: str) -> str:
    lines = [f"<ko'rsatma>\n{system}\n</ko'rsatma>"]
    if history:
        lines.append("<suhbat_tarixi>\n" + "\n".join(
            f"{'Foydalanuvchi' if m['role'] == 'user' else 'Sen'}: {str(m['content'])[:2000]}" for m in history[-12:])
            + "\n</suhbat_tarixi>")
    lines.append(f"Foydalanuvchining yangi xabari:\n{text}\n\nFaqat javob matnini yoz (kod yoki fayl o'zgartirma).")
    return "\n\n".join(lines)


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
