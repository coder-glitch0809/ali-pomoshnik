"""Egasining Telegram akkauntidan xabar yozish - ovoz yoki matn bilan: «Telegramda Akmalga yoz: ertaga 10 da uchrashamiz».

Kimga va nima yozilishi AI bilan aniqlanadi (AI bo'lmasa - oddiy qolip), suhbatdosh akkauntdagi suhbatlardan topiladi
va HAR SAFAR egasiga ko'rsatilib tasdiq so'raladi (tugma + ovozli xabar). Tasdiqsiz hech narsa yuborilmaydi.
"""
import logging
import re

log = logging.getLogger("ali.tg_send")

QUERY = re.compile(r"(telegram|телеграм|телеграмм)\S*.{0,80}(yoz|ёз|jo['ʻ‘]?nat|жўнат|жонат|yubor|юбор|xabar\s+qil|хабар\s+қил)"
                   r"|\S+(ga|га)\s+(yozib\s+qo['ʻ‘]?y|ёзиб\s+қўй|ёзиб\s+куй|xabar\s+(yubor|jo['ʻ‘]?nat)|хабар\s+(юбор|жўнат))", re.I | re.S)
SIMPLE = re.compile(r"(?:telegram\S*|телеграм\S*)?\s*(?:da|даги|да)?\s*(.+?)(?:ga|га)\s+(?:yoz\S*|ёз\S*|xabar\S*|хабар\S*"
                    r"|yubor\S*|юбор\S*|jo['ʻ‘]?nat\S*|жўнат\S*)\s*(?:qo['ʻ‘]?y|қўй)?[\s:,-]+(.+)", re.I | re.S)
LABEL = "telegram_send"

PARSE = """Foydalanuvchi o'z Telegram akkauntidan kimgadir xabar yozishni so'ramoqda (ovozli xabardan matnga o'girilgan
bo'lishi mumkin). Aniqla: KIMGA (ism, @username yoki telefon - so'zma-so'z, "ga" qo'shimchasisiz) va NIMA yozilsin.
Agar foydalanuvchi aniq matnni aytgan bo'lsa - o'shani so'zma-so'z ol (imlo xatolarini tuzat, ma'nosini o'zgartirma).
Agar "... deb tushuntir / ayt / so'ra" desa - uning nomidan birinchi shaxsda tabiiy, qisqa xabar tuzib ber.
Tilni saqla (o'zbekcha lotin/kirill yoki ruscha - qanday aytilgan bo'lsa).
So'rov: {text}
FAQAT JSON: {{"to": "...", "message": "..."}}  (aniqlab bo'lmasa: {{"to": "", "message": ""}})"""


def is_request(text: str) -> bool:
    return bool(QUERY.search(text or ""))


def parse(text: str, ready: list[str]) -> tuple[str, str]:
    """(kimga, matn). AI bo'lmasa yoki xato bersa - oddiy qolip."""
    if ready:
        from .service import _ask_json
        try:
            data = _ask_json(PARSE.format(text=text), ready, 120)
            to, msg = str(data.get("to", "")).strip(), str(data.get("message", "")).strip()
            if to and msg:
                return to, msg
        except (ValueError, RuntimeError) as e:
            log.warning("Xabar so'rovi tushunilmadi: %s", e)
    m = SIMPLE.search(text or "")
    return (m.group(1).strip(" ,.:"), m.group(2).strip()) if m else ("", "")


def handle(text: str, ready: list[str]) -> str:
    """So'rovni bajaradi: topadi -> tasdiq -> yuboradi. Javob matnini qaytaradi."""
    from . import tg_account
    from .hub import hub
    if not tg_account.credentials():
        return ("⚠️ Telegram akkauntingiz ulanmagan. Ruxsatlar -> Ulanishlar -> Telegram akkaunt -> Sozlash: api_id va api_hash, "
                "keyin telefon raqamingiz va kod bilan kiring.")
    to, message = parse(text, ready)
    if not to or not message:
        return "Kimga va nima yozishni tushunmadim. Masalan: «Telegramda Akmalga yoz: ertaga soat 10 da uchrashamiz»."
    try:
        found = tg_account.people(to)
    except RuntimeError as e:
        return f"⚠️ {e}"
    if not found:
        return f"«{to}» suhbatlaringiz orasidan topilmadi. Ismini Telegram'dagidek yoki @username bilan ayting."
    exact = [c for c in found if c["exact"]]
    if len(exact) != 1 and len(found) > 1:
        names = "\n".join(f"• {c['title']}" + (f" (@{c['username']})" if c["username"] else "") for c in found[:6])
        return f"«{to}» bo'yicha bir nechta suhbat topildi - aniqroq ayting (to'liq ism yoki @username):\n{names}"
    target = exact[0] if exact else found[0]
    who = target["title"] + (f" (@{target['username']})" if target["username"] else "")
    if not hub.confirm(LABEL, {"Kimga": who, "Matn": message}, timeout=600):
        return f"❌ Yuborilmadi (tasdiqlanmadi). Kimga: {who}\nMatn: {message}"
    try:
        tg_account.send_message(target["id"], message)
    except RuntimeError as e:
        return f"⚠️ Yuborib bo'lmadi: {e}"
    log.info("Telegram xabar yuborildi: %s", target["title"])
    return f"✅ Yuborildi → {who}:\n{message}"
