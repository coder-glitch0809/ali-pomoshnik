"""Separate Telegram bot for scenario-driven, selectable-style Ali videos."""
import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)

from .config import config

log = logging.getLogger("ali.multik_bot")

STYLES = (
    ("2d", "2D serial", "2D serial"),
    ("3d", "3D", "3D multfilm"),
    ("anime", "Anime", "Anime"),
    ("fantasy", "Fantaziya", "Fantaziya"),
    ("kino", "Kino-ertak", "Kino-ertak"),
    ("book", "Ertak kitobi", "Ertak kitobi"),
    ("clay", "Plastilin", "Plastilin"),
)
STYLE_BY_KEY = {key: (label, value) for key, label, value in STYLES}


def _guess_style(idea: str) -> str:
    text = idea.casefold()
    clues = {
        "anime": ("anime", "manga", "yapon animatsiya"),
        "3d": ("3d", "uch o'lcham", "uch o‘lcham", "pixar"),
        "fantasy": ("fantaziya", "sehr", "ajdar", "ajdaho", "sehrgar", "magic"),
        "kino": ("kino", "film", "ertak kino", "cinematic"),
        "book": ("ertak kitobi", "kitob rasmlari", "illustratsiya", "sahifali"),
        "clay": ("plastilin", "loy", "claymation"),
        "2d": ("2d", "multfilm", "multik", "serial", "chizilgan"),
    }
    for key in ("anime", "3d", "fantasy", "kino", "book", "clay", "2d"):
        if any(word in text for word in clues[key]):
            return key
    return "2d"


def _style_keyboard(suggested: str) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for key, label, _ in STYLES:
        title = f"✓ {label}" if key == suggested else label
        row.append(InlineKeyboardButton(title, callback_data=f"multik_style:{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("Bekor qilish", callback_data="multik_cancel")])
    return InlineKeyboardMarkup(buttons)


class MultikBot:
    def __init__(self):
        self.app: Application | None = None
        self._locked = False
        self._initialized = False
        self.allowed = set(config.telegram_allowed)
        if config.telegram_owner_id:
            self.allowed.add(config.telegram_owner_id)
        self.pending: dict[int, str] = {}

    async def start(self) -> None:
        from . import instance
        if not self.allowed:
            raise RuntimeError("MULTIK_BOT_TOKEN uchun TELEGRAM_OWNER_ID yoki TELEGRAM_ALLOWED_USERS ni sozlang")
        if not instance.acquire(instance.bot_lock(config.multik_bot_token)):
            raise RuntimeError("Multik bot shu kompyuterda allaqachon ishlayapti")
        self._locked = True
        try:
            app = Application.builder().token(config.multik_bot_token).build()
            self.app = app
            app.add_handler(CommandHandler("start", self.start_chat))
            app.add_handler(CommandHandler("video", self.make_video))
            app.add_handler(CommandHandler("cancel", self.cancel))
            app.add_handler(CallbackQueryHandler(self.choose_style, pattern=r"^multik_(?:style:|cancel$)"))
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.make_video))
            await app.initialize()
            self._initialized = True
            await app.start()
            await app.updater.start_polling(drop_pending_updates=False, allowed_updates=["message", "callback_query"])
            me = await app.bot.get_me()
            log.info("Multik bot ishga tushdi: @%s", me.username)
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        app, self.app = self.app, None
        if app:
            if app.updater and app.updater.running:
                await app.updater.stop()
            if app.running:
                await app.stop()
            if self._initialized:
                await app.shutdown()
                self._initialized = False
        if self._locked:
            from . import instance
            instance.release(instance.bot_lock(config.multik_bot_token))
            self._locked = False

    async def start_chat(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        await update.effective_message.reply_text(
            "Ssenariy yoki g‘oyangizni yuboring. Men mazmunidan uslubni taxmin qilaman, "
            "keyin 2D, 3D, anime, fantaziya, kino-ertak, ertak kitobi yoki plastilindan tanlatasiz.\n\n"
            "Tanlovdan keyin ChatGPT qahramon va sahna rasmlarini yaratadi, ovoz, subtitr va yakuniy CTA bilan "
            "videoni shu chatga yuboraman. Ali jamoasi guruhi sozlangan bo‘lsa, videoni u yerga ham yuboraman. "
            "Bekor qilish: /cancel"
        )

    async def make_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        message = update.effective_message
        if not message or message.chat.type not in ("private", "group", "supergroup"):
            return
        idea = " ".join(context.args).strip() if context.args else (message.text or "").strip()
        if idea.startswith("/video"):
            idea = idea.removeprefix("/video").strip()
        if not idea:
            await message.reply_text("Ssenariy yoki video g‘oyasini yuboring.")
            return
        user_id = update.effective_user.id
        self.pending[user_id] = idea[:1200]
        guess = _guess_style(idea)
        guess_label = STYLE_BY_KEY[guess][0]
        await message.reply_text(
            f"Ssenariyni qabul qildim. Mazmuniga qarab {guess_label} uslubini tavsiya qilyapman. "
            "Quyidan tanlang:",
            reply_markup=_style_keyboard(guess),
        )

    async def choose_style(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not await self._authorized(update):
            if query:
                await query.answer()
            return
        await query.answer()
        user_id = update.effective_user.id
        if query.data == "multik_cancel":
            self.pending.pop(user_id, None)
            await query.edit_message_text("Video yaratish bekor qilindi. Yangi ssenariy uchun matn yuboring.")
            return
        key = query.data.split(":", 1)[-1]
        choice = STYLE_BY_KEY.get(key)
        idea = self.pending.pop(user_id, None)
        if not choice or not idea:
            await query.edit_message_text("Ssenariy topilmadi yoki eskirgan. Iltimos, qaytadan yuboring.")
            return
        try:
            from . import creative_video
            job_id = creative_video.create(idea, choice[1], "9:16")
        except (ValueError, RuntimeError) as error:
            await query.edit_message_text(str(error)[:900])
            return
        await query.edit_message_text(
            f"Tanlandi: {choice[0]}. Ssenariy, qahramon rasmlari, ovoz, subtitr va CTA bilan video tayyorlanmoqda…"
        )
        context.application.create_task(self._deliver(job_id, query.message.chat_id, context))

    async def cancel(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        self.pending.pop(update.effective_user.id, None)
        await update.effective_message.reply_text("Bekor qilindi. Yangi ssenariy yuborishingiz mumkin.")

    async def _authorized(self, update: Update) -> bool:
        user = update.effective_user
        if user and user.id in self.allowed:
            return True
        if update.effective_message:
            await update.effective_message.reply_text("Bu bot faqat Ali egasi uchun.")
        return False

    async def _deliver(self, job_id: str, requester_chat: int,
                       context: ContextTypes.DEFAULT_TYPE) -> None:
        from . import creative_video, outbox, team_hub, video_delivery
        try:
            while True:
                await asyncio.sleep(2)
                job = creative_video.get(job_id)
                if not job:
                    raise RuntimeError("Video vazifasi topilmadi")
                if job["status"] == "error":
                    raise RuntimeError(job.get("message") or "Video yaratilmadi")
                if job["status"] == "done":
                    break
            video = outbox.resolve(job.get("video", ""))
            if video is None:
                raise RuntimeError("Tayyor MP4 topilmadi")
            video = await asyncio.to_thread(video_delivery.telegram_video, video)
            story = job.get("story") or {}
            caption = f"🎬 {story.get('title', 'Ali multik')}\nUslub: {story.get('style', '')}. Subtitr va CTA bilan."[:900]
            with video.open("rb") as stream:
                await context.bot.send_video(chat_id=requester_chat, video=stream, caption=caption,
                                             supports_streaming=True, write_timeout=120)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            log.warning("Multik video yetkazilmadi: %s", type(error).__name__)
            try:
                detail = str(error)[:800] if isinstance(error, RuntimeError) else "Telegram orqali yuborishda xatolik."
                await context.bot.send_message(chat_id=requester_chat, text=f"Video yuborilmadi: {detail}")
            except Exception:
                log.warning("Multik xato xabari yuborilmadi")
            return

        group_id = team_hub.chat_id()
        if group_id and group_id != requester_chat:
            try:
                with video.open("rb") as stream:
                    await context.bot.send_video(chat_id=group_id, video=stream, caption=caption,
                                                 supports_streaming=True, write_timeout=120)
            except Exception as error:
                log.warning("Multik video guruhga yuborilmadi: %s", type(error).__name__)
