"""Kompyuterni to'liq boshqarish: PowerShell buyruqlari va ekranni ko'rish."""
import base64
import io
import subprocess

from ..hub import hub
from . import skill

MAX_OUTPUT = 8000


@skill(
    description=(
        "Windows kompyuterda PowerShell buyrug'ini bajaradi va natijasini qaytaradi. Har qanday ish uchun: "
        "fayllar, papkalar, jarayonlar, tarmoq, ovoz balandligi, o'chirish/qayta yoqish va h.k. "
        "Foydalanuvchi har safar tasdiqlaydi. Buyruqni xavfsiz va aniq yoz."
    ),
    params={"command": {"type": "string", "description": "PowerShell buyrug'i"}},
    dangerous=True,
)
def run_powershell(command: str) -> str:
    script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + command
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
    except subprocess.TimeoutExpired:
        return "Vaqt tugadi (120 s)"
    out = (proc.stdout + ("\n[stderr]\n" + proc.stderr if proc.stderr.strip() else "")).strip()
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + f"\n... ({len(out) - MAX_OUTPUT} belgi qisqartirildi)"
    return f"exit={proc.returncode}\n{out or '(bo`sh)'}"


@skill(description="Kompyuter ekranining rasmini oladi va uni ko'rasan. 'Ekranda nima bor', 'buni ko'r' kabi so'rovlarda ishlat.")
def take_screenshot():
    from PIL import ImageGrab

    image = ImageGrab.grab()
    image.thumbnail((1568, 1568))
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=80)
    data = base64.b64encode(buf.getvalue()).decode()
    hub.broadcast({"type": "image", "src": f"data:image/jpeg;base64,{data}", "caption": "Ekran rasmi"})
    return [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}},
        {"type": "text", "text": f"Ekran rasmi ({image.width}x{image.height})."},
    ]
