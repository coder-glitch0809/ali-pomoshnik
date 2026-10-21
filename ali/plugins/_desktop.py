"""Kompyuter dasturlari (Photoshop, CorelDRAW) bilan COM orqali ishlash - PowerShell yordamida,
qo'shimcha kutubxona (pywin32) talab qilmaydi."""
import platform
import subprocess
import tempfile
from pathlib import Path

MAX_OUTPUT = 4000


def find_progid(prefix: str) -> str | None:
    """Ro'yxatdan o'tgan COM nomini topadi (masalan CorelDRAW.Application yoki CorelDRAW.Application.25)."""
    if platform.system() != "Windows":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prefix):
            return prefix
    except OSError:
        pass
    found = []
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "") as root:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(root, i)
                except OSError:
                    break
                if name.lower().startswith(prefix.lower() + "."):
                    found.append(name)
                i += 1
    except OSError:
        return None
    def version(name: str) -> int:
        tail = name.rsplit(".", 1)[-1]
        return int(tail) if tail.isdigit() else 0
    return max(found, key=version, default=None)


def run_ps(script: str, timeout: int = 180) -> str:
    """PowerShell skriptini vaqtinchalik fayl orqali bajaradi; xato bo'lsa RuntimeError."""
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8-sig") as f:
        f.write("$ErrorActionPreference = 'Stop'\n[Console]::OutputEncoding=[Text.Encoding]::UTF8\n" + script)
        path = Path(f.name)
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Dastur {timeout} soniyada javob bermadi") from None
    finally:
        path.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip()[:MAX_OUTPUT] or f"exit={proc.returncode}")
    return proc.stdout.strip()[:MAX_OUTPUT]


def ps_str(value: str) -> str:
    """PowerShell uchun xavfsiz qator ('...' ichida)."""
    return "'" + str(value).replace("'", "''") + "'"


def hex_rgb(value: str, default: str = "000000") -> tuple[int, int, int]:
    h = str(value or default).strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return hex_rgb(default)
