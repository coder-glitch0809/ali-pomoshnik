"""Ovozli xabar tuzatishlari: Ali noto'g'ri tanigan so'zni egam to'g'rilasa - eslab qoladi va keyingi safar o'zi tuzatadi.

Qanday: botning «🎙 ...» xabariga javob (reply) qilib to'g'ri matnni yozing. Farq qilgan so'zlar juft bo'lib saqlanadi
(«aybeik» -> «Oybek»), keyin har tanilgan matnga qo'llanadi va ovoz tanish modeliga «shu so'zlar bor» deb aytiladi.
"""
import difflib
import json
import re
import threading

from .config import config

FILE = config.data_dir / "voice_fixes.json"
_lock = threading.Lock()


def _load() -> dict:
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _words(text: str) -> list[str]:
    return re.findall(r"[\w'ʻ‘’`-]+", text or "")


def learn(heard: str, corrected: str) -> list[tuple[str, str]]:
    """Tanilgan va egam to'g'rilagan matn farqidan juftlar (har biri 1-4 so'z)."""
    a, b = _words(heard), _words(corrected)
    pairs = []

    def like(x: str, y: str) -> float:
        return difflib.SequenceMatcher(None, x.lower(), y.lower()).ratio()

    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [w.lower() for w in a], [w.lower() for w in b]).get_opcodes():
        if op != "replace":
            continue
        # blok ichida so'zma-so'z tekislash: har noto'g'ri so'zga tartib bo'yicha eng o'xshash to'g'ri so'z
        j = j1
        for i in range(i1, i2):
            best, score = None, .4
            for k in range(j, min(j2, j + 3)):
                r = like(a[i], b[k])
                if r > score:
                    best, score = k, r
            if best is None:
                continue
            if a[i].lower() != b[best].lower() and len(a[i]) >= 2:
                pairs.append((a[i], b[best]))
            j = best + 1
    if pairs:
        with _lock:
            data = _load()
            for wrong, right in pairs:
                data[wrong.lower()] = right
            FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return pairs


def apply(text: str) -> str:
    """Eslab qolingan tuzatishlarni qo'llaydi (uzunlari birinchi)."""
    data = _load()
    for wrong in sorted(data, key=len, reverse=True):
        text = re.sub(rf"(?<![\w']){re.escape(wrong)}(?![\w'])", data[wrong], text, flags=re.I)
    return text


def hint() -> str:
    """Ovoz tanish modeliga: egam ko'p aytadigan to'g'ri so'zlar."""
    return ", ".join(sorted(set(_load().values())))[:600]
