"""Kompyuter bilan ishlash: vaqt, ilovalar, saytlar, tizim holati."""
import os
import platform
import shutil
import subprocess
import webbrowser
from datetime import datetime

from . import skill

WEEKDAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]

# Tez-tez ishlatiladigan ilovalar. O'zingiznikini qo'shing: "nom": "buyruq yoki to'liq yo'l"
APPS = {
    "notepad": "notepad",
    "bloknot": "notepad",
    "kalkulyator": "calc",
    "calculator": "calc",
    "paint": "mspaint",
    "explorer": "explorer",
    "provodnik": "explorer",
    "cmd": "cmd",
    "terminal": "wt",
    "task manager": "taskmgr",
    "sozlamalar": "ms-settings:",
    "settings": "ms-settings:",
    "chrome": "chrome",
    "edge": "msedge",
    "telegram": "telegram",
    "vscode": "code",
}


@skill(description="Hozirgi sana, vaqt va hafta kunini qaytaradi.")
def get_datetime() -> str:
    now = datetime.now()
    return f"{now:%Y-%m-%d %H:%M:%S}, {WEEKDAYS[now.weekday()]}"


@skill(
    description="Brauzerda sayt yoki URL ochadi. Agar foydalanuvchi faqat nom aytsa (masalan 'youtube'), to'liq URL yasang.",
    params={"url": {"type": "string", "description": "To'liq URL, masalan https://youtube.com"}},
)
def open_website(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Ochildi: {url}"


@skill(
    description=f"Kompyuterda ilova ochadi. Ma'lum nomlar: {', '.join(sorted(APPS))}. Boshqa nomlarni ham sinab ko'radi.",
    params={"name": {"type": "string", "description": "Ilova nomi"}},
)
def open_application(name: str) -> str:
    target = APPS.get(name.strip().lower(), name.strip())
    try:
        if shutil.which(target):
            subprocess.Popen([target])
        elif platform.system() == "Windows":
            # URI (ms-settings:), fayl yo'li yoki ro'yxatdan o'tgan ilova (App Paths)
            os.startfile(target)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-a", target])
        else:
            return f"Ilova topilmadi: {name}"
        return f"Ishga tushirildi: {name}"
    except Exception as e:
        return f"Ochib bo'lmadi ({name}): {e}"


@skill(description="Kompyuter holati: protsessor, xotira (RAM), disk va batareya.")
def system_status() -> str:
    try:
        import psutil
    except ImportError:
        return "psutil o'rnatilmagan: pip install psutil"
    parts = [
        f"CPU: {psutil.cpu_percent(interval=0.5)}%",
        f"RAM: {psutil.virtual_memory().percent}%",
        f"Disk: {psutil.disk_usage(os.path.abspath(os.sep)).percent}%",
    ]
    battery = psutil.sensors_battery()
    if battery:
        parts.append(f"Batareya: {battery.percent:.0f}% ({'zaryadlanmoqda' if battery.power_plugged else 'zaryadsiz'})")
    return ", ".join(parts)
