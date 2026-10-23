"""Telegram kanallari (egasining shaxsiy akkaunti orqali, faqat o'qish): ro'yxat va kanaldan o'rganish."""
from .. import tg_account
from . import skill


@skill(description="Egasining Telegram akkauntidagi kanal va guruhlar ro'yxati (nomi, username, o'qilmaganlar).")
def tg_channels() -> str:
    items = tg_account.channels()
    return "\n".join(f"- {c['title']}{' @' + c['username'] if c['username'] else ''} ({c['kind']}, o'qilmagan: {c['unread']})"
                     for c in items) or "Kanal yo'q."


@skill(
    description=(
        "Telegram kanal yoki guruhdagi yangi post va fayllarni (PDF, Word, Excel, rasm...) o'qib, mazmunini mos agentlar "
        "bazasiga bilim qilib yozadi. Avval o'qilganlari qaytarilmaydi. Bir necha daqiqa davom etishi mumkin."
    ),
    params={"name": {"type": "string", "description": "Kanal nomi yoki @username"},
            "limit": {"type": "integer", "description": "Nechta oxirgi xabar (standart 100)"}},
    required=["name"],
)
def tg_learn_channel(name: str, limit: int = 100) -> str:
    r = tg_account.learn_channel(name, max(1, min(limit, 500)))
    return (f"«{r['channel']}»: {r['posts']} ta post, {r['files']} ta fayl o'qildi -> {r['saved']} ta bilim. "
            f"Agentlar: {', '.join(r['agents']) or '-'}")
