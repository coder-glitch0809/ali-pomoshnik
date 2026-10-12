"""Ali Telegram boti.

Imkoniyatlar: matn, ovozli xabar (golosovoy), rasm, joylashuv; javob matn + ovoz bilan;
xavfli amallarni tugma bilan tasdiqlash; eslatmalar; shaxsiy ovoz namunalarini yig'ish.
Faqat ruxsat berilgan foydalanuvchilar ishlata oladi (/login PAROL yoki TELEGRAM_ALLOWED_USERS).
"""
import asyncio
import base64
import html
import json
import logging
import re
import time

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from . import auth, providers, tts
from .config import config
from .hub import Listener, hub
from .service import AskError, brain, run_ask

log = logging.getLogger("ali.telegram")

USERS_FILE = config.data_dir / "telegram_users.json"
LIMIT = 4000

TOOL_LABELS = {
    "web_search": "🌐 Internetdan qidirish", "consult_experts": "✦ GPT + Gemini maslahati",
    "run_powershell": "💻 PowerShell", "take_screenshot": "🖥 Ekran rasmi", "get_weather": "⛅ Ob-havo",
    "get_my_location": "📍 Joylashuv", "open_application": "🚀 Ilova ochish", "open_website": "🔗 Sayt ochish",
    "instagram_analytics": "📊 Instagram analitika", "instagram_competitor": "🔍 Raqobatchi tahlili",
    "instagram_comments": "💬 Izohlar", "save_knowledge": "📚 Bilimni saqlash", "search_knowledge": "📚 Bilimlar bazasi",
    "remember_fact": "🧠 Eslab qolish", "set_reminder": "⏰ Eslatma",
}

COMMANDS = [
    ("new", "Yangi suhbat"),
    ("chuqur", "Chuqur fikrlash: yoqish/o'chirish"),
    ("super", "Super miya (Claude + GPT + Gemini)"),
    ("ovozli", "Javoblarni ovoz bilan yuborish"),
    ("ovoz", "Shaxsiy ovoz namunalarini yuborish"),
    ("ovoz_tayyor", "Namunalardan Ali ovozini yaratish"),
    ("ovoz_standart", "Standart ovozga qaytish"),
    ("holat", "Tizim holati"),
]


def md_to_html(text: str) -> str:
    """Claude markdown'ini Telegram HTML'iga aylantiradi."""
    parts = re.split(r"```(?:\w+)?\n?(.*?)```", text, flags=re.S)
    out = []
    for i, part in enumerate(parts):
        if i % 2:
            out.append(f"<pre>{html.escape(part)}</pre>")
            continue
        s = html.escape(part)
        s = re.sub(r"^#{1,3}\s+(.+)$", r"<b>\1</b>", s, flags=re.M)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
        s = re.sub(r"^\s*[-*]\s+", "• ", s, flags=re.M)
        out.append(s)
    return "".join(out)


def split_text(text: str, size: int = LIMIT) -> list[str]:
    chunks = []
    while len(text) > size:
        cut = text.rfind("\n", 0, size)
        cut = cut if cut > size // 2 else size
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks + [text] if text else chunks or [""]


class TelegramBot(Listener):
    def __init__(self):
        self.app: Application | None = None
        self.users: set[int] = set(config.telegram_allowed) | self._load_users()
        self.prefs: dict[int, dict] = {}
        self.sampling: set[int] = set()
        self.confirm_msgs: dict[str, list[tuple[int, int]]] = {}

    # ---------- ishga tushirish ----------
    async def start(self) -> None:
        self.app = Application.builder().token(config.telegram_token).build()
        a = self.app
        a.add_handler(CommandHandler("start", self.cmd_start))
        a.add_handler(CommandHandler("login", self.cmd_login))
        a.add_handler(CommandHandler("new", self.cmd_new))
        a.add_handler(CommandHandler("chuqur", lambda u, c: self.toggle(u, "deep", "Chuqur fikrlash")))
        a.add_handler(CommandHandler("super", lambda u, c: self.toggle(u, "super", "Super miya")))
        a.add_handler(CommandHandler("ovozli", lambda u, c: self.toggle(u, "voice", "Ovozli javob")))
        a.add_handler(CommandHandler("ovoz", self.cmd_samples))
        a.add_handler(CommandHandler("ovoz_tayyor", self.cmd_clone))
        a.add_handler(CommandHandler("ovoz_standart", self.cmd_default_voice))
        a.add_handler(CommandHandler("holat", self.cmd_status))
        a.add_handler(CallbackQueryHandler(self.on_button, pattern=r"^cf:"))
        a.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.on_voice))
        a.add_handler(MessageHandler(filters.PHOTO, self.on_photo))
        a.add_handler(MessageHandler(filters.LOCATION, self.on_location))
        a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
        await a.initialize()
        await a.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS])
        await a.start()
        await a.updater.start_polling(drop_pending_updates=True)
        hub.listeners.append(self)
        me = await a.bot.get_me()
        log.info("Telegram bot ishga tushdi: @%s", me.username)
        print(f"  Telegram:    @{me.username}")

    async def stop(self) -> None:
        if self in hub.listeners:
            hub.listeners.remove(self)
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()

    # ---------- ruxsat ----------
    def _load_users(self) -> set[int]:
        try:
            return set(json.loads(USERS_FILE.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return set()

    def _save_users(self) -> None:
        USERS_FILE.write_text(json.dumps(sorted(self.users)), encoding="utf-8")

    async def _guard(self, update: Update) -> bool:
        user = update.effective_user
        if user and user.id in self.users:
            return True
        if update.effective_message:
            await update.effective_message.reply_text(
                f"Salom! Men {config.assistant_name} - shaxsiy yordamchiman.\n"
                f"Kirish uchun: /login PAROL\n(Sizning ID: {user.id if user else '?'})"
            )
        return False

    def pref(self, chat_id: int) -> dict:
        return self.prefs.setdefault(chat_id, {"deep": False, "super": False, "voice": True})

    # ---------- buyruqlar ----------
    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        await update.message.reply_text(
            f"Xush kelibsiz, {config.user_name}. {config.assistant_name} tayyor.\n\n"
            "Yozing, ovozli xabar yuboring, rasm yoki joylashuv tashlang.\n\n"
            + "\n".join(f"/{c} - {d}" for c, d in COMMANDS)
        )

    async def cmd_login(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        password = " ".join(ctx.args or [])
        try:
            await update.message.delete()  # parol chatda qolmasin
        except BadRequest:
            pass
        if not auth.check_password(password):
            await asyncio.sleep(1.5)
            await update.effective_chat.send_message("Parol noto'g'ri.")
            return
        self.users.add(update.effective_user.id)
        self._save_users()
        await update.effective_chat.send_message(f"Kirish tasdiqlandi. Salom, {config.user_name}! /start")

    async def cmd_new(self, update: Update, ctx):
        if not await self._guard(update):
            return
        brain.new_session()
        hub.broadcast({"type": "session_reset"})
        await update.message.reply_text("Yangi suhbat boshlandi.")

    async def toggle(self, update: Update, key: str, label: str):
        if not await self._guard(update):
            return
        p = self.pref(update.effective_chat.id)
        p[key] = not p[key]
        await update.message.reply_text(f"{label}: {'yoqildi ✅' if p[key] else 'o‘chirildi'}")

    async def cmd_status(self, update: Update, ctx):
        if not await self._guard(update):
            return
        voice = tts.current_voice()
        p = self.pref(update.effective_chat.id)
        await update.message.reply_text(
            f"Miya: {config.model}\n"
            f"GPT: {config.openai_model if config.openai_api_key else 'ulanmagan'}\n"
            f"Gemini: {config.gemini_model if config.gemini_api_key else 'ulanmagan'}\n"
            f"Ovoz: {voice.get('name') or voice.get('voice')} ({voice['provider']}), namunalar: {len(tts.samples())}\n"
            f"Ulangan qurilmalar: {hub.summary() or 'yo‘q'}\n"
            f"Rejimlar: chuqur={'ha' if p['deep'] else 'yo‘q'}, super={'ha' if p['super'] else 'yo‘q'}, "
            f"ovozli={'ha' if p['voice'] else 'yo‘q'}"
        )

    # ---------- shaxsiy ovoz ----------
    async def cmd_samples(self, update: Update, ctx):
        if not await self._guard(update):
            return
        self.sampling.add(update.effective_chat.id)
        await update.message.reply_text(
            "🎙 Ovoz namunasi rejimi.\n\n"
            "Endi ovozli xabarlar yuboring - Ali shu ovozda gapiradi. Maslahatlar:\n"
            "• jami 1-3 daqiqa, har biri 10-60 soniya\n"
            "• jim xonada, mikrofonga yaqin, tabiiy ohangda\n"
            "• turli gaplar: savol, hayajon, oddiy hikoya\n\n"
            f"Hozir: {len(tts.samples())} ta namuna. Tugatgach: /ovoz_tayyor"
        )

    async def cmd_clone(self, update: Update, ctx):
        if not await self._guard(update):
            return
        self.sampling.discard(update.effective_chat.id)
        msg = await update.message.reply_text(f"⏳ {len(tts.samples())} ta namunadan ovoz yaratilmoqda…")
        try:
            await tts.clone_voice(config.assistant_name)
        except Exception as e:
            await msg.edit_text(f"⚠️ {e}")
            return
        await msg.edit_text("✅ Yangi ovoz tayyor! Endi Ali shu ovozda gapiradi (sayt va Telegram).")
        audio = await tts.synthesize(f"Salom, {config.user_name}. Men {config.assistant_name}. Yangi ovozim qanday?")
        await update.effective_chat.send_voice(voice=audio)

    async def cmd_default_voice(self, update: Update, ctx):
        if not await self._guard(update):
            return
        tts.use_default_voice()
        await update.message.reply_text(f"Standart ovozga qaytildi ({config.tts_voice}). Namunalar saqlanib qoldi.")

    # ---------- xabarlar ----------
    async def on_text(self, update: Update, ctx):
        if await self._guard(update):
            await self.process(update, ctx, update.message.text)

    async def on_voice(self, update: Update, ctx):
        if not await self._guard(update):
            return
        media = update.message.voice or update.message.audio
        file = await media.get_file()
        data = bytes(await file.download_as_bytearray())
        ext = (file.file_path or "voice.ogg").rsplit(".", 1)[-1].lower()
        ext = ext if f".{ext}" in tts.AUDIO_EXT else "ogg"

        if update.effective_chat.id in self.sampling:
            path = tts.SAMPLES_DIR / f"tg_{int(time.time())}_{media.file_unique_id}.{ext}"
            path.write_bytes(data)
            total = sum(1 for _ in tts.samples())
            await update.message.reply_text(f"✅ Namuna saqlandi ({media.duration or '?'} s). Jami: {total}. Yana yuboring yoki /ovoz_tayyor")
            return

        if not providers.can_transcribe():
            await update.message.reply_text("Ovozli xabarni tushunish uchun .env da OPENAI_API_KEY yoki GEMINI_API_KEY kerak.")
            return
        await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        try:
            text = await asyncio.to_thread(providers.transcribe, data, f"voice.{ext}")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Ovozni tanib bo'lmadi: {e}")
            return
        if not text:
            await update.message.reply_text("Tushunolmadim, qaytadan ayting.")
            return
        await update.message.reply_text(f"🎙 <i>{html.escape(text)}</i>", parse_mode=ParseMode.HTML)
        await self.process(update, ctx, text)

    async def on_photo(self, update: Update, ctx):
        if not await self._guard(update):
            return
        file = await update.message.photo[-1].get_file()
        data = base64.b64encode(bytes(await file.download_as_bytearray())).decode()
        await self.process(update, ctx, update.message.caption or "", [{"media_type": "image/jpeg", "data": data}])

    async def on_location(self, update: Update, ctx):
        if not await self._guard(update):
            return
        loc = update.message.location
        hub.last_location = {"lat": loc.latitude, "lon": loc.longitude, "accuracy": loc.horizontal_accuracy,
                             "device": "telegram", "time": time.strftime("%H:%M:%S")}
        await update.message.reply_text("📍 Joylashuv qabul qilindi. Endi “yaqin atrofda nima bor?” deb so‘rashingiz mumkin.")

    # ---------- asosiy jarayon ----------
    async def process(self, update: Update, ctx, text: str, images: list[dict] | None = None):
        chat = update.effective_chat
        p = self.pref(chat.id)
        status = await update.message.reply_text("⏳ O‘ylayapman…")
        state = {"text": "", "tools": [], "dirty": False}

        def on_event(kind, data):  # brain oqimidan chaqiriladi
            if kind == "text":
                state["text"] += data
            elif kind == "tool_start":
                state["tools"].append(TOOL_LABELS.get(data["name"], "🔧 " + data["name"]))
            else:
                return
            state["dirty"] = True

        async def live_editor():
            shown = ""
            while True:
                await asyncio.sleep(1.5)
                await ctx.bot.send_chat_action(chat.id, ChatAction.TYPING)
                if not state["dirty"]:
                    continue
                state["dirty"] = False
                head = " · ".join(dict.fromkeys(state["tools"]))
                body = (f"{head}\n\n" if head else "") + (state["text"] or "⏳ O‘ylayapman…")
                body = body[-LIMIT:]
                if body != shown:
                    try:
                        await status.edit_text(body)
                        shown = body
                    except BadRequest:
                        pass

        editor = asyncio.create_task(live_editor())
        try:
            answer = await run_ask(text, images, p["deep"], p["super"], source="telegram", on_event=on_event)
        except AskError as e:
            await status.edit_text(f"⚠️ {e}")
            return
        finally:
            editor.cancel()

        chunks = split_text(answer or "(bo‘sh javob)")
        await self._edit_html(status, chunks[0])
        for chunk in chunks[1:]:
            await self._send_html(chat.id, chunk)
        if p["voice"] and answer:
            try:
                audio = await tts.synthesize(answer)
                if audio:
                    await chat.send_voice(voice=audio)
            except Exception:
                log.exception("Ovozli javob xatosi")

    async def _edit_html(self, message, text: str):
        try:
            await message.edit_text(md_to_html(text), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except BadRequest:
            await message.edit_text(text)

    async def _send_html(self, chat_id: int, text: str):
        try:
            await self.app.bot.send_message(chat_id, md_to_html(text), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except BadRequest:
            await self.app.bot.send_message(chat_id, text)

    # ---------- tasdiqlash tugmalari ----------
    async def on_button(self, update: Update, ctx):
        query = update.callback_query
        if query.from_user.id not in self.users:
            await query.answer("Ruxsat yo'q")
            return
        _, cid, ok = query.data.split(":")
        hub.resolve_confirm(cid, ok == "1")
        await query.answer("Ruxsat berildi" if ok == "1" else "Rad etildi")

    def _run(self, coro) -> None:
        if hub.loop:
            asyncio.run_coroutine_threadsafe(coro, hub.loop)

    def on_confirm(self, cid: str, name: str, args: dict) -> None:
        detail = args.get("command") or json.dumps(args, ensure_ascii=False, indent=1)
        text = f"⚠️ <b>Ruxsat so‘ralmoqda</b>\n{html.escape(TOOL_LABELS.get(name, name))}\n<pre>{html.escape(detail[:3000])}</pre>"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Ruxsat", callback_data=f"cf:{cid}:1"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"cf:{cid}:0"),
        ]])

        async def send():
            sent = []
            for uid in self.users:
                try:
                    m = await self.app.bot.send_message(uid, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
                    sent.append((uid, m.message_id))
                except Exception:
                    log.exception("Tasdiq yuborilmadi: %s", uid)
            self.confirm_msgs[cid] = sent

        self._run(send())

    def on_confirm_closed(self, cid: str) -> None:
        async def close():
            for chat_id, msg_id in self.confirm_msgs.pop(cid, []):
                try:
                    await self.app.bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
                except BadRequest:
                    pass

        self._run(close())

    def on_notify(self, text: str) -> None:
        async def send():
            for uid in self.users:
                try:
                    await self.app.bot.send_message(uid, f"🔔 {text}")
                except Exception:
                    log.exception("Xabar yuborilmadi: %s", uid)

        self._run(send())
