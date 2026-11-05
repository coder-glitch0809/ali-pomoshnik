"""Telegram kanallari (egasining shaxsiy akkaunti orqali, faqat o'qish): ro'yxat va kanaldan o'rganish."""
from .. import tg_account
from . import skill


@skill(description="Telegram eslatmalariga ruxsat berilgan guruh va kanallar ro'yxati.")
def tg_reminder_sources() -> str:
    return "\n".join(f"- {title} (ID: {cid})" for cid, title in tg_account.reminder_sources().items()) or "Eslatmalar uchun hech bir guruh yoki kanalga ruxsat berilmagan."


@skill(
    description="Egasi tanlagan Telegram guruh/kanalidan avtomatik eslatmalarga ruxsat beradi yoki bekor qiladi. Avval tg_channels orqali ID ni aniqlang.",
    params={"chat_id": {"type": "integer", "description": "Guruh yoki kanal ID si"},
            "allowed": {"type": "boolean", "description": "true — ruxsat, false — bekor qilish"}},
    dangerous=True,
)
def tg_reminder_permission(chat_id: int, allowed: bool) -> str:
    if not allowed:
        tg_account.set_reminder_source(chat_id, "", False)
        return "Eslatmalarga ruxsat bekor qilindi."
    ch = next((c for c in tg_account.channels() if c["id"] == chat_id), None)
    if ch is None:
        return "Guruh yoki kanal topilmadi. ID ni tg_channels orqali tekshiring."
    tg_account.set_reminder_source(chat_id, ch["title"], True)
    return f"«{ch['title']}» eslatmalariga ruxsat berildi."


@skill(description="Egasining Telegram akkauntidagi kanal va guruhlar ro'yxati (nomi, username, o'qilmaganlar).")
def tg_channels() -> str:
    items = tg_account.channels()
    return "\n".join(f"- {c['title']}{' @' + c['username'] if c['username'] else ''} (ID: {c['id']}, {c['kind']}, o'qilmagan: {c['unread']})"
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


@skill(
    description=(
        "Telegram kanal/guruhga tashlangan ENG OXIRGI videoni yuklab oladi, ko'radi va montaj qiladi (jump-cut, subtitr, "
        "ovoz, rang; Reels 9:16). task - montaj topshirig'i (ixtiyoriy; bo'sh bo'lsa standart professional ishlov). "
        "Kanalga hech narsa yuborilmaydi, tayyor video egasiga beriladi."
    ),
    params={"channel": {"type": "string", "description": "Kanal nomi yoki @username"},
            "task": {"type": "string", "description": "Montaj topshirig'i, masalan: «hook qo'sh, subtitr qo'y» (ixtiyoriy)"}},
    required=["channel"],
)
def channel_video_edit(channel: str, task: str = "") -> str:
    from .. import local_ai, montage
    from ..service import brain
    path, title = tg_account.download_latest_video(channel)
    ready = local_ai.connected() if local_ai.access() is True else []
    report = montage.run(task, str(path), brain.registry, ready)
    return f"«{title}» kanalidagi oxirgi video ({path.name}) olindi.\n{report}"
