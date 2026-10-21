"""Kompyuterdagi AI ilovalari: Claude (Claude Code), ChatGPT (Codex CLI), Gemini (Gemini CLI).

API kaliti emas - egasining o'z akkaunti (obunasi) bilan ishlaydi. Faqat egasi saytga kompyuterdan kirib
ruxsat bergandan keyin (local_ai.access). Ulangan ilovalar data/ai_apps.json da eslab qolinadi.
"""
from concurrent.futures import ThreadPoolExecutor

from .. import local_ai
from . import skill

LOGIN_HINT = {
    "claude": "ochilgan oynada /login -> Claude akkauntingiz (Pro/Max obuna) bilan kiring",
    "codex": "brauzer ochiladi -> 'Sign in with ChatGPT' -> ChatGPT akkauntingiz bilan kiring",
    "gemini": "ochilgan oynada 'Login with Google' ni tanlang -> Google akkauntingiz bilan kiring",
}
APP_ENUM = {"type": "string", "enum": list(local_ai.PACKAGES), "description": "claude (Claude), codex (ChatGPT), gemini (Gemini)"}


def _need_access() -> str | None:
    if local_ai.access() is not True:
        return ("Kompyuterdagi AI ilovalaridan foydalanishga ruxsat berilmagan. Saytni shu kompyuterda (localhost) oching "
                "va 'Ruxsat berish' ni bosing.")
    return None


@skill(description="Kompyuterdagi AI ilovalari holati: Claude, ChatGPT (Codex), Gemini - o'rnatilganmi, ulanganmi, ruxsat bormi.")
def ai_apps_status() -> str:
    allowed = {True: "berilgan", False: "rad etilgan", None: "hali so'ralmagan"}[local_ai.access()]
    lines = [f"Ruxsat: {allowed}"]
    for a in local_ai.summary()["apps"]:
        if not a["installed"]:
            state = "o'rnatilmagan -> ai_app_install"
        elif a["connected"]:
            state = f"ulangan ({a['at']})"
        elif a["connected"] is False:
            state = f"ulanmagan ({a['error'][:120]}) -> ai_app_login, keyin ai_app_verify"
        else:
            state = "o'rnatilgan, tekshirilmagan -> ai_app_verify"
        lines.append(f"- {a['name']} ({a['key']}): {state}")
    return "\n".join(lines)


@skill(
    description="AI ilovasini kompyuterga o'rnatadi (npm orqali rasmiy paket). Foydalanuvchi tasdiqlaydi.",
    params={"app": APP_ENUM},
    dangerous=True,
)
def ai_app_install(app: str) -> str:
    try:
        done = local_ai.install(app)
    except RuntimeError as e:
        return str(e)
    return f"{done}. Endi akkauntga kirish kerak: ai_app_login {app} ({LOGIN_HINT[app]})."


@skill(
    description=(
        "AI ilovasiga kirish (login) uchun kompyuterda terminal oynasini ochadi. Parolni foydalanuvchi o'zi kiritadi - "
        "sen hech qachon parol so'rama va kiritma. Foydalanuvchi tasdiqlaydi."
    ),
    params={"app": APP_ENUM},
    dangerous=True,
)
def ai_app_login(app: str) -> str:
    try:
        local_ai.open_login(app)
    except RuntimeError as e:
        return f"{e}: avval ai_app_install {app}."
    return (f"Kompyuterda terminal oynasi ochildi: {LOGIN_HINT[app]}. Kirgach, ai_app_verify {app} bilan tekshir - "
            "ulanish eslab qolinadi.")


@skill(
    description="AI ilovasi akkaunt bilan ishlayotganini tekshiradi va natijani eslab qoladi (keyingi safar qayta ulash shart emas).",
    params={"app": APP_ENUM},
)
def ai_app_verify(app: str) -> str:
    ok, message = local_ai.verify(app)
    return message if ok else f"Ulanmadi: {message}\n(Akkauntga kirilmagan bo'lsa: ai_app_login {app})"


@skill(
    description=(
        "Savolni kompyuterdagi AI ilovasiga (foydalanuvchining Claude / ChatGPT / Gemini akkaunti orqali) beradi va "
        "javobini qaytaradi. Savolni to'liq kontekst bilan yoz - ilova suhbat tarixini ko'rmaydi. 1-5 daqiqa."
    ),
    params={"app": APP_ENUM, "prompt": {"type": "string", "description": "To'liq savol yoki vazifa"}},
)
def ask_ai_app(app: str, prompt: str) -> str:
    if denied := _need_access():
        return denied
    exe = local_ai.app_exe(app)
    if not exe:
        return f"{local_ai.NAMES[app]} o'rnatilmagan: ai_app_install {app}."
    try:
        return local_ai.ask_one(app, exe, prompt)
    except RuntimeError as e:
        return f"Xato: {e}\n(Akkauntga kirilmagan bo'lsa: ai_app_login {app})"


@skill(
    description=(
        "Bitta savolni kompyuterdagi barcha ulangan AI ilovalariga (Claude, ChatGPT, Gemini) parallel beradi va "
        "javoblarini qaytaradi - solishtirib, eng yaxshi yakuniy javobni o'zing tuz."
    ),
    params={"prompt": {"type": "string", "description": "To'liq savol"}},
)
def ask_all_ai_apps(prompt: str) -> str:
    if denied := _need_access():
        return denied
    state = local_ai.app_state()
    ready = {k: e for k in local_ai.PACKAGES
             if (e := local_ai.app_exe(k)) and state.get(k, {}).get("connected") is not False}
    if not ready:
        return "Ulangan AI ilovasi yo'q: ai_apps_status."

    def one(item):
        key, exe = item
        try:
            return key, local_ai.ask_one(key, exe, prompt)
        except RuntimeError as e:
            return key, f"[xato: {e}]"

    with ThreadPoolExecutor(max_workers=len(ready)) as pool:
        results = list(pool.map(one, ready.items()))
    return "\n\n".join(f"=== {local_ai.NAMES[k]} ===\n{text}" for k, text in results)
