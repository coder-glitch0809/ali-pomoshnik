"""Sozlamalar: .env faylidan o'qiladi, standart qiymatlar shu yerda."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
STATE_ROOT = Path(os.getenv("ALI_STATE_DIR", str(ROOT)))
# O'rnatilgan Windows ilovasi: sozlamalar foydalanuvchi papkasida (%LOCALAPPDATA%\Ali\.env)
load_dotenv(STATE_ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    return _env(name, str(default)).lower() in ("1", "true", "yes", "ha")


@dataclass
class Config:
    # Yordamchi shaxsiyati
    assistant_name: str = field(default_factory=lambda: _env("ASSISTANT_NAME", "Ali"))
    user_name: str = field(default_factory=lambda: _env("USER_NAME", "Ser"))

    chat_provider: str = field(default_factory=lambda: _env("CHAT_PROVIDER", "claude").lower())

    # Asosiy miya (Claude)
    model: str = field(default_factory=lambda: _env("CLAUDE_MODEL", "claude-opus-5-5"))
    effort: str = field(default_factory=lambda: _env("CLAUDE_EFFORT", "medium"))
    deep_effort: str = field(default_factory=lambda: _env("CLAUDE_DEEP_EFFORT", "xhigh"))
    max_tokens: int = field(default_factory=lambda: int(_env("CLAUDE_MAX_TOKENS", "32000")))
    web_search: bool = field(default_factory=lambda: _env_bool("WEB_SEARCH", True))
    # Suhbat shuncha xabardan oshsa, yangi suhbat boshlanadi (uzoq xotira saqlanadi)
    # Ommaviy bot tariflari: bepul - arzon tez model, Pro (pullik) - asosiy model va ko'proq rasm
    free_model: str = field(default_factory=lambda: _env("FREE_MODEL", "claude-haiku-5-5"))
    free_daily_questions: int = field(default_factory=lambda: int(_env("FREE_DAILY_QUESTIONS", "3")))
    pro_daily_questions: int = field(default_factory=lambda: int(_env("PRO_DAILY_QUESTIONS", "100")))
    free_daily_images: int = field(default_factory=lambda: int(_env("FREE_DAILY_IMAGES", "3")))
    pro_daily_images: int = field(default_factory=lambda: int(_env("PRO_DAILY_IMAGES", "30")))
    max_history_messages: int = field(default_factory=lambda: int(_env("MAX_HISTORY_MESSAGES", "80")))

    # Gemini: faqat ovozni matnga aylantirish va rasm (Claude qila olmaydigan ishlar)
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    gemini_image_model: str = field(default_factory=lambda: _env("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"))
    gemini_fast_model: str = field(default_factory=lambda: _env("GEMINI_FAST_MODEL", "gemini-flash-latest"))
    # Bepul suhbat uchun Gemini modeli (bepul API limiti bor)
    gemini_chat_model: str = field(default_factory=lambda: _env("GEMINI_CHAT_MODEL", "gemini-flash-latest"))
    # Ommaviy botning bepul tarifi kim bilan javob beradi: gemini (bepul API) | claude (FREE_MODEL, pullik)
    free_provider: str = field(default_factory=lambda: _env("FREE_PROVIDER", "gemini").lower())
    # Claude API ishlamasa (balans tugagan va h.k.) - Gemini javob bersin
    gemini_fallback: bool = field(default_factory=lambda: _env_bool("GEMINI_FALLBACK", True))

    # Maslahatchi modellar (consult_experts): GPT va Gemini fikri, Claude solishtiradi
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    openai_model: str = field(default_factory=lambda: _env("OPENAI_MODEL", "gpt-5"))
    # Amazon Bedrock (Claude AWS orqali): Bedrock API kaliti, mintaqa va model (bo'sh - avtomatik topiladi)
    bedrock_api_key: str = field(default_factory=lambda: _env("BEDROCK_API_KEY") or _env("AWS_BEARER_TOKEN_BEDROCK"))
    bedrock_region: str = field(default_factory=lambda: _env("BEDROCK_REGION", "us-east-1"))
    bedrock_model: str = field(default_factory=lambda: _env("BEDROCK_MODEL"))
    gemini_model: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-pro-latest"))

    # To'liq ruxsat (faqat o'z kompyuterida, start-full.bat): barcha vositalar tasdiqsiz, internet doim ochiq.
    # Serverda (Render) hech qachon yoqilmaydi.
    full_access: bool = field(default_factory=lambda: _env_bool("FULL_ACCESS", False) and not os.getenv("RENDER"))
    powershell_timeout: int = field(default_factory=lambda: int(_env("POWERSHELL_TIMEOUT", "300")))
    # ChatGPT plagini (OpenAI API)
    openai_image_model: str = field(default_factory=lambda: _env("OPENAI_IMAGE_MODEL", "gpt-image-1"))

    # Plaginlar: hammasi avtomatik ishga tushadi; o'chirish uchun PLUGINS_DISABLED=chatgpt,coreldraw
    plugins_disabled: set[str] = field(default_factory=lambda: {
        x.strip().lower() for x in _env("PLUGINS_DISABLED").split(",") if x.strip()
    })
    # Ali ishga tushganda Photoshop/CorelDRAW ham darhol ochilsinmi (false - faqat kerak bo'lganda)
    plugins_open_apps: bool = field(default_factory=lambda: _env_bool("PLUGINS_OPEN_APPS", False))

    # Telefon ilovasi: Firebase loyihasi (kirish tokenlarini tekshirish) va kunlik bepul savollar
    firebase_project_id: str = field(default_factory=lambda: _env("FIREBASE_PROJECT_ID"))
    mobile_daily_questions: int = field(default_factory=lambda: int(_env("MOBILE_DAILY_QUESTIONS", "30")))

    # Windows o'rnatuvchisida ruxsat berilgan guruhlar (pc,screen,apps,files,photoshop,coreldraw,ai,online).
    # None - o'rnatuvchisiz ishga tushirilgan (cheklov yo'q)
    install_groups: set[str] | None = field(default_factory=lambda: (
        {x.strip() for x in os.environ["ALI_INSTALL_GROUPS"].split(",") if x.strip()}
        if "ALI_INSTALL_GROUPS" in os.environ else None))

    # Telegram bot
    telegram_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    public_url: str = field(default_factory=lambda: (_env("PUBLIC_URL") or _env("RENDER_EXTERNAL_URL")).rstrip("/"))
    telegram_name: str = field(default_factory=lambda: _env("TELEGRAM_BOT_NAME", "Ali Pomoshnik"))
    telegram_owner_id: int = field(default_factory=lambda: int(_env("TELEGRAM_OWNER_ID", "0") or 0))
    telegram_payment_text: str = field(default_factory=lambda: _env("TELEGRAM_PAYMENT_TEXT", "Obuna narxi va to‘lov ma’lumoti hali e’lon qilinmagan. So‘rovni administratorga yuboring."))
    telegram_allowed: set[int] = field(default_factory=lambda: {
        int(x) for x in _env("TELEGRAM_ALLOWED_USERS").replace(" ", "").split(",") if x.isdigit()
    })

    # Shaxsiy ovoz (ElevenLabs klonlash)
    elevenlabs_api_key: str = field(default_factory=lambda: _env("ELEVENLABS_API_KEY"))
    elevenlabs_voice_id: str = field(default_factory=lambda: _env("ELEVENLABS_VOICE_ID"))
    elevenlabs_model: str = field(default_factory=lambda: _env("ELEVENLABS_MODEL", "eleven_v3"))

    # Instagram (Graph API): IG_ACCOUNTS="brend=17841400000000000,shaxsiy=1784..."
    ig_access_token: str = field(default_factory=lambda: _env("IG_ACCESS_TOKEN"))
    ig_accounts: dict[str, str] = field(default_factory=lambda: dict(
        pair.split("=", 1) for pair in _env("IG_ACCOUNTS").split(",") if "=" in pair
    ))
    ig_graph_version: str = field(default_factory=lambda: _env("IG_GRAPH_VERSION", "v23.0"))

    # Veb-server
    host: str = field(default_factory=lambda: _env("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(_env("PORT", "8000")))
    access_password: str = field(default_factory=lambda: _env("ACCESS_PASSWORD"))

    # Ovoz
    wake_words: list[str] = field(
        default_factory=lambda: [w.strip().lower() for w in _env("WAKE_WORDS", "ali,али,jarvis").split(",") if w.strip()]
    )
    stt_language: str = field(default_factory=lambda: _env("STT_LANGUAGE", "uz-UZ"))
    tts_backend: str = field(default_factory=lambda: _env("TTS_BACKEND", "edge"))  # edge | pyttsx3 | none
    tts_voice: str = field(default_factory=lambda: _env("TTS_VOICE", "uz-UZ-SardorNeural"))

    # Dasturlash: GitHub, Vercel, kompyuterdagi loyihalar
    github_token: str = field(default_factory=lambda: _env("GITHUB_TOKEN"))
    vercel_token: str = field(default_factory=lambda: _env("VERCEL_TOKEN"))
    vercel_team_id: str = field(default_factory=lambda: _env("VERCEL_TEAM_ID"))
    render_api_key: str = field(default_factory=lambda: _env("RENDER_API_KEY"))
    projects_dirs: list[Path] = field(default_factory=lambda: [
        Path(p.strip()) for p in (_env("PROJECTS_DIRS") or str(ROOT.parent)).split(";") if p.strip()
    ])
    # Claude Code CLI vazifasi uchun maksimal vaqt (daqiqa)
    code_task_minutes: int = field(default_factory=lambda: int(_env("CODE_TASK_MINUTES", "30")))

    # Avtopilot: o'z-o'zini o'rgatish va loyihalarni kuzatish
    auto_learn: bool = field(default_factory=lambda: _env_bool("AUTO_LEARN", False))
    auto_learn_hours: float = field(default_factory=lambda: float(_env("AUTO_LEARN_HOURS", "24")))
    watch_projects: bool = field(default_factory=lambda: _env_bool("WATCH_PROJECTS", False))
    watch_hours: float = field(default_factory=lambda: float(_env("WATCH_HOURS", "6")))
    self_improve: bool = field(default_factory=lambda: _env_bool("SELF_IMPROVE", False))
    self_improve_hours: float = field(default_factory=lambda: float(_env("SELF_IMPROVE_HOURS", "24")))

    # Fayllar
    data_dir: Path = STATE_ROOT / "data"
    db_path: Path = STATE_ROOT / "data" / "ali.db"
    log_path: Path = STATE_ROOT / "logs" / "ali.log"


config = Config()
config.data_dir.mkdir(parents=True, exist_ok=True)
config.log_path.parent.mkdir(parents=True, exist_ok=True)
