"""Separate Telegram bot for scenario-driven, selectable-style Ali videos."""
import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)

from .config import config
from .multik_panel import StudioPanel

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


class MultikBot(StudioPanel):
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
            from .telegram_memory import MemoryBot, observe
            app = Application.builder().bot(MemoryBot(config.multik_bot_token, source='Multik')).build()
            self.app = app
            app.add_handler(observe('Multik', lambda: self.allowed), group=-100)
            app.add_handler(CommandHandler("start", self.start_chat))
            app.add_handler(CommandHandler("panel", self.panel))
            app.add_handler(CallbackQueryHandler(self.studio_action, pattern=r"^studio:"))
            app.add_handler(MessageHandler(filters.Document.ALL | filters.AUDIO, self.receive_audio))
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
        await self.panel(update, _context)

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
        self._remember(user_id, idea=idea[:1200])
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
            self._remember(user_id, idea=None)
            await query.edit_message_text("Video yaratish bekor qilindi. Yangi ssenariy uchun matn yuboring.")
            return
        key = query.data.split(":", 1)[-1]
        choice = STYLE_BY_KEY.get(key)
        prefs = self._state().get(str(user_id), {})
        idea = self.pending.pop(user_id, None) or prefs.get('idea')
        if not choice or not idea:
            await query.edit_message_text("Ssenariy topilmadi yoki eskirgan. Iltimos, qaytadan yuboring.")
            return
        try:
            from . import creative_video
            job_id = creative_video.create(idea, choice[1], prefs.get('format', '9:16'), review=True)
            creative_video._update(job_id, bot_user=user_id, bot_chat=query.message.chat_id,
                                   bot_voice=prefs.get('voice', 'aistudio'))
            self._remember(user_id, job=job_id, idea=None, upload=None)
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
        self._remember(update.effective_user.id, idea=None, upload=None)
        await update.effective_message.reply_text("Kutilayotgan tanlov bekor qilindi. Boshlangan video davom etadi. /panel — holati.")

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
        progress_message = None
        last_text = None
        try:
            while True:
                await asyncio.sleep(2)
                job = creative_video.get(job_id)
                if not job:
                    raise RuntimeError("Video vazifasi topilmadi")
                if job.get('bot_user'):
                    text = self._progress_text(job)
                    if text != last_text:
                        try:
                            if progress_message:
                                await context.bot.edit_message_text(chat_id=requester_chat,
                                    message_id=progress_message.message_id, text=text,
                                    reply_markup=self._controls(job_id, job))
                            else:
                                progress_message = await context.bot.send_message(chat_id=requester_chat,
                                    text=text, reply_markup=self._controls(job_id, job))
                            last_text = text
                        except Exception:
                            log.warning('Multik progress update failed')
                if job["status"] == "error":
                    raise RuntimeError(job.get("message") or "Video yaratilmadi")
                if job["status"] == "ready" and job.get('review'):
                    if job.get('bot_voice') in ('sardor', 'madina') and not job.get('bot_auto_started'):
                        voices = {str(s.get('speaker') or 'Hikoyachi'): job['bot_voice']
                                  for s in job['story']['scenes']}
                        creative_video.start_render(job_id, voices)
                        creative_video._update(job_id, bot_auto_started=True)
                        continue
                    base = config.public_url.rstrip('/') or 'http://localhost:8000'
                    await context.bot.send_message(chat_id=requester_chat, text=(
                        'Ssenariy va rasmlar tayyor. API kalitisiz ovoz uchun Ali’da har sahnaning '
                        'matnini AI Studio’ga nusxalang, yaratilgan WAV’larni yuklang va «Videoni yasash»ni bosing.\n'
                        f'{base}/?creative_job={job_id}#video'))
                    return
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
