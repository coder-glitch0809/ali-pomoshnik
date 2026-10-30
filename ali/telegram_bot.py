"""Ali Telegram boti.

Imkoniyatlar: matn, ovozli xabar (golosovoy), rasm, joylashuv; javob matn + ovoz bilan;
xavfli amallarni tugma bilan tasdiqlash; eslatmalar; shaxsiy ovoz namunalarini yig'ish.
Faqat ruxsat berilgan foydalanuvchilar ishlata oladi (/login PAROL yoki TELEGRAM_ALLOWED_USERS).
"""
import asyncio
import base64
import html
import hashlib
import json
import logging
import re
import threading
import time

from telegram import BotCommand, BotCommandScopeChat, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update, WebAppInfo, MenuButtonCommands, MenuButtonWebApp
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, TelegramError, RetryAfter
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from . import auth, outbox, providers, tts
from .config import config
from .hub import Listener, hub
from .service import AskError, brain, run_ask
from .telegram_public import PublicTelegram

log = logging.getLogger("ali.telegram")

USERS_FILE = config.data_dir / "telegram_users.json"
LIMIT = 4000

TOOL_LABELS = {
    "web_search": "🌐 Internetdan qidirish",
    "telegram_send": "✉️ Telegram'da xabar yuborish (sizning nomingizdan)",
    "fire_agent": "🚪 Agentni ishdan bo'shatish (3 marta past baho)",
    "run_powershell": "💻 PowerShell", "take_screenshot": "🖥 Ekran rasmi", "get_weather": "⛅ Ob-havo",
    "get_my_location": "📍 Joylashuv", "open_application": "🚀 Ilova ochish", "open_website": "🔗 Sayt ochish",
    "instagram_analytics": "📊 Instagram analitika", "instagram_competitor": "🔍 Raqobatchi tahlili",
    "instagram_comments": "💬 Izohlar", "save_knowledge": "📚 Bilimni saqlash", "search_knowledge": "📚 Bilimlar bazasi",
    "remember_fact": "🧠 Eslab qolish", "set_reminder": "⏰ Eslatma", "ask_agent": "🧑‍💼 Agentga topshiriq",
    "market_data": "📈 Bozor ma'lumotlari",
}

COMMANDS = [
    ("start", "Ali Pomoshnik — bosh menyu"),
    ("ai", "Kim javob bersin: Ali, Claude Pro, ChatGPT Pro, Bedrock"),
    ("kanallar", "Telegram kanal va guruhlarim"),
    ("kanal", "Kanalni o'qib o'rganish: /kanal NOMI"),
    ("kanallar_organ", "Barcha kanallardan hozir o'rganish"),
    ("bugun", "Yozishmalardan bugungi rejalar va eslatmalar"),
    ("jadval", "Dars jadvalim"),
    ("dars", "Dars taqdimoti: /dars 5-A [mavzu]"),
    ("instagram", "Instagram profil audit: nimani to'g'rilash kerak"),
    ("kuchaytir", "Ali o'zini kuchaytirsin: /kuchaytir yangi imkoniyat"),
    ("tugma_test", "Tugmalar ishlayotganini tekshirish"),
    ("ekotizim", "Agentlar: baho, rag'bat va jazo"),
    ("kompyuter", "Kompyuterni telefondan boshqarish (ekran + bosish)"),
    ("kontent_reja", "Instagram tahlili va kontent reja: /kontent_reja [kunlar]"),
    ("kontent", "Bugungi kontent (hook, ssenariy, caption)"),
    ("tayyor", "Kontent bajarildi: /tayyor RAQAM"),
    ("menu", "Xizmatlarni tanlash"),
    ("ob_havo", "Hudud va kundalik ob-havo"),
    ("sorovlar", "Administrator: kelgan so‘rovlar"),
    ("stop", "Bildirishnomalarni o‘chirish"),
    ("tozala", "Ommaviy suhbat tarixini tozalash"),
    ("sayt", "To'liq boshqaruv panelini ochish"),
    ("monitor", "Agentlar va vazifalar holati"),
    ("new", "Yangi suhbat"),
    ("chuqur", "Chuqur fikrlash: yoqish/o'chirish"),
    ("super", "Super miya — doim yoqilgan"),
    ("ovozli", "Javoblarni ovoz bilan yuborish"),
    ("ovoz", "Shaxsiy ovoz namunalarini yuborish"),
    ("ovoz_tayyor", "Namunalardan Ali ovozini yaratish"),
    ("ovoz_standart", "Standart ovozga qaytish"),
    ("holat", "Tizim holati"),
]
PUBLIC_COMMANDS = [(c,d) for c,d in COMMANDS if c in {'start','menu','ob_havo','stop','tozala'}]


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


class TelegramBot(PublicTelegram, Listener):
    def __init__(self):
        self.app: Application | None = None
        self.users: set[int] = set(config.telegram_allowed) | self._load_users()
        self.prefs: dict[int, dict] = {}
        self.sampling: set[int] = set()
        self.confirm_msgs: dict[str, list[tuple[int, int]]] = {}
        self.init_public()

    # ---------- ishga tushirish ----------
    async def configure_bot(self, method, **kwargs):
        """Cosmetic/menu rate limits must never prevent message polling."""
        key=method+':'+str(kwargs.get('chat_id',kwargs.get('scope','default')))
        fingerprint=hashlib.sha256(str(kwargs).encode()).hexdigest()
        saved=self.public.meta('bot_setup') or {}
        item=saved.get(key,{})
        if item.get('fingerprint')==fingerprint or item.get('retry_at',0)>time.time():return
        try:
            await getattr(self.app.bot,method)(**kwargs)
            saved[key]={'fingerprint':fingerprint}
        except TelegramError as error:
            delay=getattr(error,'retry_after',300)
            if hasattr(delay,'total_seconds'):delay=delay.total_seconds()
            saved[key]={'retry_at':time.time()+float(delay)}
            log.warning('Telegram setup deferred: %s (%s); polling continues',method,type(error).__name__)
        self.public.set_meta('bot_setup',saved)

    async def start(self) -> None:
        from . import instance
        if not instance.acquire(instance.bot_lock(config.telegram_token)):  # bitta token - bitta so'rovchi (Conflict yo'q)
            raise RuntimeError("bu bot shu kompyuterdagi boshqa Ali nusxasida ishlayapti")
        self.app = Application.builder().token(config.telegram_token).concurrent_updates(8).build()
        a = self.app
        a.add_error_handler(self.on_error)
        a.add_handler(CommandHandler("start", self.cmd_start))
        a.add_handler(CommandHandler("menu", self.cmd_start))
        a.add_handler(CommandHandler("stop", self.public_stop))
        a.add_handler(CommandHandler("tozala", self.clear_public))
        a.add_handler(CommandHandler("sorovlar", self.owner_requests))
        a.add_handler(CommandHandler("ob_havo", self.cmd_weather))
        a.add_handler(CommandHandler("sayt", self.cmd_site))
        a.add_handler(CommandHandler("monitor", self.cmd_monitor))
        a.add_handler(CommandHandler("login", self.cmd_login))
        a.add_handler(CommandHandler("new", self.cmd_new))
        a.add_handler(CommandHandler("chuqur", lambda u, c: self.toggle(u, "deep", "Chuqur fikrlash")))
        a.add_handler(CommandHandler("super", lambda u, c: self.toggle(u, "super", "Super miya")))
        a.add_handler(CommandHandler("ovozli", lambda u, c: self.toggle(u, "voice", "Ovozli javob")))
        a.add_handler(CommandHandler("ovoz", self.cmd_samples))
        a.add_handler(CommandHandler("ovoz_tayyor", self.cmd_clone))
        a.add_handler(CommandHandler("ovoz_standart", self.cmd_default_voice))
        a.add_handler(CommandHandler("holat", self.cmd_status))
        a.add_handler(CommandHandler("agent", self.cmd_agent))
        a.add_handler(CommandHandler("ai", self.cmd_ai))
        a.add_handler(CommandHandler("kanallar", self.cmd_channels))
        a.add_handler(CommandHandler("kanal", self.cmd_channel))
        a.add_handler(CommandHandler("bugun", self.cmd_today))
        a.add_handler(CommandHandler("jadval", self.cmd_schedule))
        a.add_handler(CommandHandler("dars", self.cmd_lesson))
        a.add_handler(CommandHandler("kontent_reja", self.cmd_content_plan))
        a.add_handler(CommandHandler("instagram", self.cmd_instagram))
        a.add_handler(CommandHandler("kuchaytir", self.cmd_upgrade))
        a.add_handler(CommandHandler("tugma_test", self.cmd_button_test))
        a.add_handler(CommandHandler("ekotizim", self.cmd_ecosystem))
        a.add_handler(CommandHandler("kompyuter", self.cmd_pc))
        a.add_handler(CommandHandler("kontent", self.cmd_content_today))
        a.add_handler(CommandHandler("tayyor", self.cmd_content_done))
        a.add_handler(CommandHandler("kanallar_organ", self.cmd_learn_all))
        a.add_handler(CallbackQueryHandler(self.on_ai_button, pattern=r"^ai:"))
        a.add_handler(CallbackQueryHandler(self.on_button, pattern=r"^cf:"))
        a.add_handler(CallbackQueryHandler(self.on_agent_button, pattern=r"^ag:"))
        a.add_handler(CallbackQueryHandler(self.on_upgrade_button, pattern=r"^up:"))
        a.add_handler(CallbackQueryHandler(self.on_button_test, pattern=r"^tst:"))
        a.add_handler(CallbackQueryHandler(self.on_pc_button, pattern=r"^pc:"))
        a.add_handler(CallbackQueryHandler(self.public_button, pattern=r"^(pub:|own:)"))
        a.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.on_voice))
        a.add_handler(MessageHandler(filters.PHOTO, self.on_photo))
        a.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE | filters.Document.VIDEO, self.on_video))
        a.add_handler(MessageHandler(filters.Document.ALL, self.on_document))
        a.add_handler(MessageHandler(filters.LOCATION, self.on_location))
        a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
        await a.initialize()
        await self.configure_bot('set_my_commands',commands=[BotCommand(c, d) for c, d in PUBLIC_COMMANDS])
        for uid in self.users:
            await self.configure_bot('set_my_commands',commands=[BotCommand(c,d) for c,d in COMMANDS],scope=BotCommandScopeChat(uid))
        await self.configure_bot('set_my_name',name=config.telegram_name)
        await self.configure_bot('set_my_description',description="✨ Ali — AI yordamchingiz. Savol bering, kontent uchun ruxsat so‘rang, ob-havoni bilib oling va mutaxassis agentlardan foydalaning. Boshlash: /start")
        await self.configure_bot('set_my_short_description',short_description="Ali Pomoshnik — shaxsiy yordamchingiz va AI jamoangiz.")
        # Replace stale Mini App buttons pointing at a failed web deployment.
        await self.configure_bot('set_chat_menu_button',menu_button=MenuButtonCommands())
        for uid in self.users:
            await self.configure_bot('set_chat_menu_button',chat_id=uid, menu_button=self.owner_menu())
        await a.start()
        # allowed_updates aniq beriladi: Telegram oxirgi sozlamani eslab qoladi - boshqa dastur tugmalarni (callback_query)
        # o'chirib qo'ygan bo'lsa ham, Ali'ga barcha turdagi yangilanishlar keladi
        await a.updater.start_polling(drop_pending_updates=False, allowed_updates=Update.ALL_TYPES)
        hub.listeners.append(self)
        from . import tunnel
        tunnel.on_url(lambda url: self._run(self.refresh_menus()))  # tunnel manzili o'zgarsa - "Ali panel" yangilanadi
        if config.public_url.startswith("https://"):
            await self.refresh_menus()
        self.public_task=asyncio.create_task(self.public_loop())
        me = await a.bot.get_me()
        log.info("Telegram bot ishga tushdi: @%s", me.username)
        print(f"  Telegram:    @{me.username}")

    async def stop(self) -> None:
        if self.public_task:
            self.public_task.cancel()
            try: await self.public_task
            except asyncio.CancelledError: pass
        if self in hub.listeners:
            hub.listeners.remove(self)
        from . import instance
        instance.release(instance.bot_lock(config.telegram_token))
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
        if not update.effective_chat or update.effective_chat.type != "private":
            if update.effective_message:
                await update.effective_message.reply_text("Shaxsiy boshqaruv uchun botning o'ziga yozing.")
            return False
        user = update.effective_user
        if user and user.id in self.users:
            return True
        if update.effective_message:
            await update.effective_message.reply_text(
                "Bu shaxsiy boshqaruv faqat administrator uchun. Xizmatlardan foydalanish uchun /start ni bosing."
            )
        return False

    def pref(self, chat_id: int) -> dict:
        return self.prefs.setdefault(chat_id, {"deep": False, "super": True, "voice": True, "agent": None, "ai": None})

    # ---------- buyruqlar ----------
    async def refresh_menus(self) -> None:
        for uid in self.users:
            await self.configure_bot('set_chat_menu_button', chat_id=uid, menu_button=self.owner_menu())
        log.info("Ali panel tugmasi yangilandi: %s", config.public_url or "(manzil yo'q)")

    def owner_menu(self):
        if config.public_url.startswith('https://'):
            return MenuButtonWebApp(text='Ali panel',web_app=WebAppInfo(url=config.public_url+'/miniapp'))
        return MenuButtonCommands()

    def site_keyboard(self):
        if config.public_url.startswith("https://"):
            return InlineKeyboardMarkup([[InlineKeyboardButton(
                "🖥 Ali Pomoshnik — to'liq panel", web_app=WebAppInfo(url=config.public_url+'/miniapp'))]])
        return None

    async def cmd_site(self, update: Update, ctx):
        if not await self._guard(update):
            return
        keyboard = self.site_keyboard()
        if keyboard:
            import httpx
            try:
                async with httpx.AsyncClient(timeout=8,follow_redirects=True) as client:
                    response=await client.get(config.public_url+'/miniapp')
                    if response.status_code!=200:keyboard=None
            except httpx.HTTPError:keyboard=None
        await update.message.reply_text(
            "Abbos, shaxsiy panelingiz tayyor. Telegram ID’ingiz avtomatik tekshiriladi."
            if keyboard else "Veb-panel hozir mavjud emas. Telegram menyusidagi xizmatlardan foydalaning. Kompyuterda http://localhost:8000 ishlaydi.",
            reply_markup=keyboard)

    async def cmd_monitor(self, update: Update, ctx):
        if not await self._guard(update):
            return
        from .monitor import monitor
        from .service import team
        snapshot = monitor.snapshot(team())
        jobs = snapshot.get("jobs", [])[:8]
        lines = [f"{j.get('status', '')}: {j.get('text', '')[:180]}" for j in jobs]
        await update.message.reply_text("📊 Monitoring\n\n" + ("\n".join(lines) or "Hozircha vazifalar yo'q."),
                                        reply_markup=self.site_keyboard())

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await self.public_start(update, ctx)

    async def cmd_weather(self, update, ctx):
        if self.is_private(update): await self.weather_menu(update)

    async def cmd_login(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not update.effective_chat or update.effective_chat.type != "private":
            return
        if self.owner_id and update.effective_user.id != self.owner_id:
            await update.message.reply_text('Shaxsiy boshqaruv administrator uchun. /start orqali xizmatlarni tanlang.')
            return
        password = " ".join(ctx.args or [])
        try:
            await update.message.delete()  # parol chatda qolmasin
        except BadRequest:
            pass
        if not auth.check_password(password):
            await asyncio.sleep(1.5)
            if wait := auth.locked_for():
                await update.effective_chat.send_message(f"Ko'p xato urinish. {wait // 60 + 1} daqiqadan keyin qayta urinib ko'ring.")
            else:
                await update.effective_chat.send_message("Parol noto'g'ri.")
            return
        self.users.add(update.effective_user.id)
        self.owner_id=update.effective_user.id
        self._save_users()
        await update.effective_chat.send_message("Kirish tasdiqlandi. Salom, Abbos! /start")

    async def cmd_ecosystem(self, update: Update, ctx):
        """/ekotizim - agentlar bahosi va ogohlantirishlari; /ekotizim baholash - hozir baholash."""
        from . import ecosystem
        if not await self._guard(update):
            return
        if ctx.args and ctx.args[0].lower().startswith("baho"):
            text = await asyncio.to_thread(ecosystem.review, brain, None,
                                           lambda name, args: hub.confirm(name, args, timeout=1800))
        else:
            text = ecosystem.report(brain)
        await update.message.reply_text(text[:4000])

    async def cmd_button_test(self, update: Update, ctx):
        """/tugma_test - tugmalar Ali'ga yetib kelayotganini tekshirish."""
        if not await self._guard(update):
            return
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"{n}-tugma", callback_data=f"tst:{n}") for n in (1, 2, 3)]])
        await update.message.reply_text("🧪 Tugmalar sinovi: istalganini bosing - xabar «✅ ishladi» ga o'zgaradi.",
                                        reply_markup=keyboard)

    async def on_button_test(self, update: Update, ctx):
        query = update.callback_query
        n = query.data.split(":", 1)[1]
        await self.safe_answer(query, f"✅ {n}-tugma ishladi")
        try:
            await query.edit_message_text(f"✅ {n}-tugma ishladi ({time.strftime('%H:%M:%S')}). Tugmalar Ali'ga yetib kelyapti.",
                                          reply_markup=query.message.reply_markup)
        except TelegramError:
            pass

    async def on_error(self, update, ctx) -> None:
        """Ishlovchidagi har qanday xato logga yoziladi (avval jim yo'qolardi)."""
        log.error("Telegram ishlovchisida xato (%s): %s", type(update).__name__, ctx.error, exc_info=ctx.error)

    NEW_CHAT = re.compile(r"^\s*(yangi|янги|boshqa|бошқа|бошка)\s+(suhbat|сухбат|суҳбат|mavzu|мавзу)", re.I)

    async def cmd_new(self, update: Update, ctx):
        if self.is_private(update) and update.effective_user.id != self.owner_id:
            await self.clear_public(update,ctx)
            return
        if not await self._guard(update):
            return
        from . import remote_pc
        remote_pc.stop(update.effective_chat.id)  # kompyuter rejimi ham yopiladi
        if brain.lock.locked():  # joriy vazifa tugashi bilan o'zi yangi suhbat boshlaydi
            await update.message.reply_text("⏳ Joriy vazifa tugashi bilan yangi suhbat boshlanadi.")
            async with brain.lock:
                brain.new_session()
        else:
            brain.new_session()
        hub.broadcast({"type": "session_reset"})
        await update.message.reply_text("🧹 Yangi suhbat boshlandi. Avvalgi mavzu davom ettirilmaydi.")

    async def toggle(self, update: Update, key: str, label: str):
        if not await self._guard(update):
            return
        p = self.pref(update.effective_chat.id)
        p[key] = True if key == "super" else not p[key]
        await update.message.reply_text(f"{label}: {'yoqildi ✅' if p[key] else 'o‘chirildi'}")

    def _agent_label(self, key: str | None) -> str:
        a = brain.agents.get(key or "")
        return f"{a.icon} {a.name}" if a else f"🤖 {config.assistant_name}"

    async def cmd_agent(self, update: Update, ctx):
        if not await self._guard(update):
            return
        await update.message.reply_text("Topshiriqni Aliga yozing. Agentlarni Ali o'zi tanlaydi va boshqaradi.")

    AI_CHOICES = {"": "🧠 Ali (avtomatik)", "claude": "✳️ Claude Pro", "codex": "◎ ChatGPT Pro", "bedrock": "☁️ Bedrock (Claude)"}

    async def cmd_ai(self, update: Update, ctx):
        """/ai - kim javob berishini tanlash: Ali o'zi yoki to'g'ridan-to'g'ri Claude Pro / ChatGPT Pro / Bedrock."""
        if not await self._guard(update):
            return
        cur = self.pref(update.effective_chat.id).get("ai") or ""
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(("✅ " if k == cur else "") + label, callback_data=f"ai:{k}")]
                                         for k, label in self.AI_CHOICES.items()])
        await update.message.reply_text("Kim javob bersin?", reply_markup=keyboard)

    async def on_ai_button(self, update: Update, ctx):
        query = update.callback_query
        if query.from_user.id not in self.users:
            await self.safe_answer(query, "Ruxsat yo'q")
            return
        key = query.data.split(":", 1)[1]
        key = key if key in self.AI_CHOICES else ""
        self.pref(query.message.chat.id)["ai"] = key or None
        await self.safe_answer(query, self.AI_CHOICES[key])
        try:
            await query.edit_message_text(f"Endi javob beradi: {self.AI_CHOICES[key]}")
        except BadRequest:
            pass

    async def on_agent_button(self, update: Update, ctx):
        query = update.callback_query
        if query.from_user.id not in self.users:
            await self.safe_answer(query, "Ruxsat yo'q")
            return
        await self.safe_answer(query, "Agentlarni Ali boshqaradi")
        await query.edit_message_text("Topshiriqni Aliga yozing.")

    async def cmd_status(self, update: Update, ctx):
        if not await self._guard(update):
            return
        voice = tts.current_voice()
        p = self.pref(update.effective_chat.id)
        await update.message.reply_text(
            f"Miya: {config.model}\n"
            f"Gemini: {'ovoz va rasm' if config.gemini_api_key else 'ulanmagan'}\n"
            f"Ovoz: {voice.get('name') or voice.get('voice')} ({voice['provider']}), namunalar: {len(tts.samples())}\n"
            f"Ulangan qurilmalar: {hub.summary() or 'yo‘q'}\n"
            f"Rejimlar: chuqur={'ha' if p['deep'] else 'yo‘q'}, super={'ha' if p['super'] else 'yo‘q'}, "
            f"ovozli={'ha' if p['voice'] else 'yo‘q'}\n"
            f"Agent: {self._agent_label(p['agent'])}"
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
        if not self.is_private(update): return
        if await self.menu_text(update,ctx,update.message.text):return
        if update.effective_user.id==self.owner_id:
            text = update.message.text
            from . import remote_pc
            if self.NEW_CHAT.match(text):  # «yangi suhbat» / «yangi mavzu» - /new bilan bir xil
                await self.cmd_new(update, ctx)
                return
            # /kompyuter rejimi: faqat katak (B3), +tugmalar va «yoz: matn» kompyuterga boradi, qolgani - oddiy suhbat
            if remote_pc.active(update.effective_chat.id) and remote_pc.is_command(text):
                await self.pc_text(update, text)
                return
            # Uzatilgan (forward) xabar - o'rganiladigan material; havolalar - sahifasi o'qiladi va o'rganiladi
            if getattr(update.message, "forward_origin", None):
                self.learn_bg(update, " ".join(text.split()[:8]), text, "Telegram (uzatilgan xabar)")
            if await self.channel_in_text(update, text):  # «X kanalini o'rgan» - kanal o'qiladi
                return
            from . import self_upgrade
            if self_upgrade.is_request(text):  # «o'zingni kuchaytir: ...» - Dasturchi o'z kodini yaxshilaydi
                await self.start_upgrade(update, text)
                return
            text = await self.read_links(update, text)
            await self.process(update, ctx, text)
        else:
            await self.public_process(update,ctx,update.message.text)

    # ---------- Telegram kanallaridan o'rganish (shaxsiy akkaunt, faqat o'qish) ----------
    async def cmd_channels(self, update: Update, ctx):
        from . import tg_account
        if not await self._guard(update):
            return
        try:
            items = await asyncio.to_thread(tg_account.channels)
        except Exception as e:
            await update.message.reply_text(f"⚠️ {e}")
            return
        lines = [f"{'📢' if c['kind'] == 'kanal' else '👥'} {c['title']}" + (f" (@{c['username']})" if c["username"] else "")
                 for c in items[:80]]
        await update.message.reply_text(f"Kanal va guruhlaringiz ({len(items)}):\n\n" + "\n".join(lines)
                                        + "\n\nO'rganish uchun: /kanal NOMI  (yoki shunchaki «NOMI kanalini o'rgan»)")

    async def cmd_channel(self, update: Update, ctx):
        if not await self._guard(update):
            return
        name = " ".join(ctx.args or []).strip()
        if not name:
            await update.message.reply_text("Kanal nomini yozing: /kanal Kanal nomi")
            return
        self.learn_channel_bg(update, name)

    async def cmd_instagram(self, update: Update, ctx):
        """/instagram - profil audit: postlarni ko'rib, aniq tavsiyalar (bir necha daqiqa)."""
        from . import instagram_audit
        if not await self._guard(update):
            return
        msg = await update.message.reply_text("🔍 Instagram profilingizni tahlil qilyapman: postlar, muqovalar, chastota (2-5 daqiqa)…")
        try:
            text = instagram_audit.report(await asyncio.to_thread(instagram_audit.audit))
        except Exception as e:
            await msg.edit_text(f"⚠️ Tahlil bajarilmadi: {str(e)[:400]}")
            return
        await msg.edit_text(text[:4000])
        for i in range(4000, len(text), 4000):
            await update.message.reply_text(text[i:i + 4000])

    # ---------- o'zini kuchaytirish (Dasturchi + Claude Code, egasining tasdig'i bilan) ----------
    async def cmd_upgrade(self, update: Update, ctx):
        """/kuchaytir TALAB - Ali o'z kodiga yangi imkoniyat qo'shadi (alohida nusxada, testlar, tasdiq)."""
        if not await self._guard(update):
            return
        if update.effective_user.id != self.owner_id:
            await update.message.reply_text("O'zini kuchaytirishni faqat egasi buyura oladi.")
            return
        await self.start_upgrade(update, " ".join(ctx.args))

    async def start_upgrade(self, update: Update, text: str) -> None:
        from . import self_upgrade
        task = self_upgrade.extract_task(text)
        if len(task) < 10:
            await update.message.reply_text("Nimani qo'shay? Masalan:\n/kuchaytir /ob_havo buyrug'iga 3 kunlik prognoz qo'sh")
            return
        auto = self_upgrade.auto_apply()
        msg = await update.message.reply_text(
            "👨‍💻 Dasturchi agent ishga tushdi. Ishlab turgan Ali'ga tegmayman - alohida nusxada yozaman va testlayman. "
            + ("Testlar o'tsa - o'zim qo'llayman va GitHub'ga push qilaman." if auto else "Keyin tasdig'ingizni so'rayman."))
        loop = asyncio.get_running_loop()

        def progress(note: str) -> None:
            asyncio.run_coroutine_threadsafe(msg.edit_text(note), loop)

        try:
            res = await asyncio.to_thread(self_upgrade.run, task, progress)
        except Exception as e:
            await update.message.reply_text(f"⚠️ Kuchaytirish bajarilmadi: {str(e)[:600]}")
            return
        if not res["ok"]:
            await update.message.reply_text(f"❌ Testlar o'tmadi - o'zgarish bekor qilindi, Ali avvalgidek ishlayapti.\n"
                                            f"🧪 {res['tests']}\n\n{res['report'][-1500:]}")
            return
        if auto:  # Ruxsatlar -> ali_kuchaytirish = auto: so'ramasdan qo'llaydi va push qiladi
            try:
                pushed = await asyncio.to_thread(self_upgrade.apply, res["id"])
            except Exception as e:
                await update.message.reply_text(f"⚠️ Testlar o'tdi, lekin qo'llab bo'lmadi: {str(e)[:500]}")
                return
            text = (f"🚀 Dasturchi agent Ali'ni kuchaytirdi va qo'lladi ({pushed}). Testlar: {res['tests']}.\n\n"
                    f"{res['report'][-2200:]}\n\n📁 O'zgargan fayllar:\n{res['diff'][-1000:]}\n\n5 soniyada qayta ishga tushaman…")
            await update.message.reply_text(text[-4000:])
            self_upgrade.restart_later(5)
            return
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Qo'llash", callback_data=f"up:{res['id']}:1"),
                                          InlineKeyboardButton("❌ Bekor qilish", callback_data=f"up:{res['id']}:0")]])
        text = (f"✅ Tayyor, testlar o'tdi ({res['tests']}).\n\n{res['report'][-2200:]}\n\n📁 O'zgargan fayllar:\n"
                f"{res['diff'][-1200:]}\n\nQo'llasam - GitHub'ga push qilaman va qayta ishga tushaman.")
        await update.message.reply_text(text[-4000:], reply_markup=keyboard)

    @staticmethod
    async def safe_answer(query, text: str | None = None, **kw) -> None:
        """Tugma javobi: Telegram eski so'rovga javob bermaydi (BadRequest) - bu asosiy ishni to'xtatmasligi kerak."""
        try:
            await query.answer(text, **kw)
        except TelegramError:
            pass

    @staticmethod
    async def drop_buttons(query) -> None:
        try:
            await query.edit_message_reply_markup(None)
        except TelegramError:
            pass

    async def on_upgrade_button(self, update: Update, ctx):
        from . import self_upgrade
        query = update.callback_query
        if query.from_user.id != self.owner_id:
            await self.safe_answer(query, "Ruxsat yo'q")
            return
        _, uid, ok = query.data.split(":")
        await self.safe_answer(query)  # eski tugma (15+ daqiqa) bo'lsa ham ish davom etadi
        await self.drop_buttons(query)
        if ok != "1":
            await asyncio.to_thread(self_upgrade.discard, uid)
            await query.message.reply_text("❌ Bekor qilindi. Ali o'zgarmadi.")
            return
        await query.message.reply_text("⏳ Qo'llayapman: main'ga qo'shib, GitHub'ga push qilyapman…")
        try:
            pushed = await asyncio.to_thread(self_upgrade.apply, uid)
        except Exception as e:
            await query.message.reply_text(f"⚠️ Qo'llab bo'lmadi: {str(e)[:500]}")
            return
        await query.message.reply_text(f"🚀 Qo'llandi ({pushed}). 5 soniyada yangi kod bilan qayta ishga tushaman…")
        self_upgrade.restart_later(5)

    # ---------- kompyuterni telefondan boshqarish (/kompyuter) ----------
    def pc_keyboard(self, s):
        from . import remote_pc as rp
        b = InlineKeyboardButton
        on = lambda flag: " ✅" if flag else ""
        rows = [[b(f"{rp.LETTERS[c]}{r + 1}", callback_data=f"pc:c:{c}{r}") for c in range(rp.COLS)]
                for r in range(rp.ROWS)]
        rows += [
            [b("🔄", callback_data="pc:r"), b("🔍" + on(s.zoom), callback_data="pc:z"),
             b("🖥 To'liq", callback_data="pc:f"), b("⬆️", callback_data="pc:s:5"), b("⬇️", callback_data="pc:s:-5")],
            [b(k, callback_data=f"pc:k:{v}") for k, v in
             [("Enter", "enter"), ("Esc", "esc"), ("Tab", "tab"), ("⌫", "backspace"), ("Win", "win")]],
            [b(k, callback_data=f"pc:k:{v}") for k, v in
             [("Alt+Tab", "alt+tab"), ("Ctrl+C", "ctrl+c"), ("Ctrl+V", "ctrl+v"), ("Ctrl+Z", "ctrl+z")]],
            [b("🖱 O'ng" + on(s.button == "right"), callback_data="pc:b"), b("2x" + on(s.double), callback_data="pc:d"),
             b("❌ Chiqish", callback_data="pc:x")],
        ]
        return InlineKeyboardMarkup(rows)

    async def cmd_pc(self, update: Update, ctx):
        """/kompyuter - ekran rasmi katakchali to'r bilan keladi; tugmalar orqali bosish, yozish, aylantirish."""
        from . import remote_pc
        if not await self._guard(update) or update.effective_user.id != self.owner_id:
            return
        if config.public_url.startswith("https://"):  # jonli ekran (translyatsiya) - Mini App ichida
            await update.message.reply_text(
                "📺 Jonli boshqarish: ekran uzluksiz ko'rinadi, barmoq bilan bosasiz, sudraysiz va yozasiz.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "📺 Jonli boshqarish", web_app=WebAppInfo(url=config.public_url + "/remote"))]]))
        s = remote_pc.session(update.effective_chat.id)
        s.region, s.zoom = None, False
        try:
            photo = await asyncio.to_thread(remote_pc.capture, s)
        except Exception as e:
            remote_pc.stop(update.effective_chat.id)
            await update.message.reply_text(f"⚠️ Ekranni olib bo'lmadi: {str(e)[:300]}")
            return
        await update.message.reply_photo(photo, caption=remote_pc.caption(s), reply_markup=self.pc_keyboard(s))

    async def pc_text(self, update: Update, text: str):
        from . import remote_pc
        s = remote_pc.session(update.effective_chat.id)
        try:
            result = await asyncio.to_thread(remote_pc.handle_text, s, text)
            photo = await asyncio.to_thread(remote_pc.capture, s)
        except Exception as e:
            await update.message.reply_text(f"⚠️ {str(e)[:300]}")
            return
        await update.message.reply_photo(photo, caption=f"{result}\n{remote_pc.caption(s)}",
                                         reply_markup=self.pc_keyboard(s))

    async def on_pc_button(self, update: Update, ctx):
        from . import remote_pc
        query = update.callback_query
        if query.from_user.id != self.owner_id:
            await self.safe_answer(query, "Ruxsat yo'q")
            return
        chat = query.message.chat_id
        parts = query.data.split(":", 2)
        action, arg = parts[1], (parts[2] if len(parts) > 2 else "")
        if action == "x":
            remote_pc.stop(chat)
            await self.safe_answer(query, "Boshqaruv tugadi")
            await self.drop_buttons(query)
            return
        s = remote_pc.session(chat)
        try:
            if action == "c":
                result = await asyncio.to_thread(remote_pc.click_cell, s, int(arg[0]), int(arg[1]))
            elif action == "s":
                result = await asyncio.to_thread(remote_pc.scroll, int(arg))
            elif action == "k":
                result = await asyncio.to_thread(remote_pc.keys, arg)
            elif action == "z":
                s.zoom, result = not s.zoom, "Kattalashtirish: katakni tanlang"
            elif action == "f":
                s.region, s.zoom, result = None, False, "To'liq ekran"
            elif action == "b":
                s.button, result = ("left" if s.button == "right" else "right"), "Tugma almashtirildi"
            elif action == "d":
                s.double, result = not s.double, "Ikki marta bosish"
            else:
                result = "Yangilandi"
            photo = await asyncio.to_thread(remote_pc.capture, s)
        except Exception as e:
            await self.safe_answer(query, f"⚠️ {str(e)[:180]}", show_alert=True)
            return
        await self.safe_answer(query, result[:180])
        try:
            await query.edit_message_media(InputMediaPhoto(photo, caption=remote_pc.caption(s)),
                                           reply_markup=self.pc_keyboard(s))
        except BadRequest:
            await query.message.reply_photo(photo, caption=remote_pc.caption(s), reply_markup=self.pc_keyboard(s))

    async def cmd_content_plan(self, update: Update, ctx):
        """/kontent_reja [kunlar] - Instagram statistikasini tahlil qilib, 3 yo'nalish uchun kontent reja tuzadi."""
        from . import content_plan
        if not await self._guard(update):
            return
        days = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 14
        msg = await update.message.reply_text(f"📊 Statistikani tahlil qilib, {days} kunlik kontent reja tuzyapman (1-3 daqiqa)…")
        try:
            start = outbox.mark()
            plan = await asyncio.to_thread(content_plan.generate, days)
            await asyncio.to_thread(content_plan.word, plan)
            await asyncio.to_thread(content_plan.excel, plan)
        except Exception as e:
            await msg.edit_text(f"⚠️ Reja tuzilmadi: {str(e)[:400]}")
            return
        text = content_plan.plan_summary()
        await msg.edit_text(text[:4000])
        for f in outbox.since(start):  # Word - o'qish uchun, Excel - jadval
            with open(f, "rb") as fh:
                await update.message.reply_document(fh, filename=f.name, caption="🗓 Kontent reja (" +
                                                    ("Word - o'qish uchun" if f.suffix == ".docx" else "Excel jadval") + ")")
        try:  # ichida nima borligini ovozda o'qib beradi
            audio = await tts.synthesize(content_plan.voice_summary(plan))
            if audio:
                await update.message.reply_voice(audio, caption="🔊 Kontent reja - qisqa xulosa")
        except Exception:
            log.exception("Kontent reja ovozli xulosasi yuborilmadi")

    async def cmd_content_today(self, update: Update, ctx):
        from . import content_plan
        if not await self._guard(update):
            return
        text = content_plan.today_text()
        for i in range(0, len(text), 3900):
            await update.message.reply_text(text[i:i + 3900])

    async def cmd_content_done(self, update: Update, ctx):
        from . import content_plan
        if not await self._guard(update):
            return
        if not ctx.args or not ctx.args[0].isdigit():
            await update.message.reply_text("Raqamini yozing: /tayyor 3")
            return
        await update.message.reply_text(content_plan.mark_done(int(ctx.args[0])))

    async def cmd_schedule(self, update: Update, ctx):
        """/jadval - haftalik dars jadvali (bugun va ertangi kun bilan)."""
        from . import schedule
        if not await self._guard(update):
            return
        from datetime import date, timedelta
        await update.message.reply_text(schedule.week_text() + "\n\n" + schedule.day_text(date.today())
                                        + "\n" + schedule.day_text(date.today() + timedelta(days=1)))

    async def cmd_lesson(self, update: Update, ctx):
        """/dars 5-A [mavzu] - shu sinfga mos dars taqdimoti (API kalitisiz ham)."""
        from . import schedule
        if not await self._guard(update):
            return
        args = " ".join(ctx.args or [])
        cls = schedule.class_from(args)
        if not cls:
            nxt = schedule.next_lesson()
            if not nxt:
                await update.message.reply_text("Sinfni yozing: /dars 5-A [mavzu]")
                return
            cls = nxt["class"]
        topic = re.sub(r"^\s*\d{1,2}\s*[-–]?\s*[A-Za-zА-Яа-яЁё]\b", "", args).strip()
        if topic:
            schedule.remember_topic(cls, topic)
        await self.process(update, ctx, schedule.lesson_request(cls, topic))

    async def cmd_today(self, update: Update, ctx):
        """/bugun - yozishmalarni hozir ko'rib chiqadi: faktlar xotiraga, rejalar eslatmaga."""
        from . import tg_account
        if not await self._guard(update):
            return
        msg = await update.message.reply_text("📖 Yozishmalaringizni o'qib, rejalar va faktlarni ajratyapman…")
        try:
            r = await asyncio.to_thread(tg_account.review_chats)
        except Exception as e:
            await msg.edit_text(f"⚠️ {str(e)[:400]}")
            return
        text = (f"✅ Ko'rib chiqildi: {r['facts']} ta fakt xotiraga yozildi.\n\n"
                + ("📅 Eslatmalar:\n" + "\n".join(r["reminders"]) if r["reminders"] else "📅 Yangi reja topilmadi.")
                + (f"\n\n📝 {r['summary']}" if r["summary"] else ""))
        await msg.edit_text(text[:4000])

    async def cmd_learn_all(self, update: Update, ctx):
        """/kanallar_organ - barcha kanallardagi yangi post va fayllardan hozir o'rganish."""
        from . import tg_account
        if not await self._guard(update):
            return
        chat_id = update.effective_chat.id
        loop = asyncio.get_running_loop()
        progress = lambda m: asyncio.run_coroutine_threadsafe(self.app.bot.send_message(chat_id, m), loop)
        await update.message.reply_text("📚 Barcha kanallarni o'qishni boshladim - har birining natijasini yozib boraman.")

        async def run():
            try:
                results = await asyncio.to_thread(tg_account.learn_all_channels, progress)
            except Exception as e:
                await self.app.bot.send_message(chat_id, f"⚠️ {str(e)[:400]}")
                return
            total = sum(r["saved"] for r in results)
            await self.app.bot.send_message(chat_id, f"✅ Tugadi: {len(results)} ta kanaldan {total} ta bilim.")
        task = asyncio.create_task(run())
        self.learn_tasks = getattr(self, "learn_tasks", set())
        self.learn_tasks.add(task)
        task.add_done_callback(self.learn_tasks.discard)

    def learn_channel_bg(self, update: Update, name: str) -> None:
        """Kanalni fonda o'qib o'rganadi; har bir natija va yakuniy hisobot Telegram'ga keladi."""
        from . import tg_account
        chat_id = update.effective_chat.id
        loop = asyncio.get_running_loop()

        def progress(msg):
            asyncio.run_coroutine_threadsafe(self.app.bot.send_message(chat_id, msg), loop)

        async def run():
            await self.app.bot.send_message(chat_id, f"📖 «{name}» kanalini o'qiyapman - post va fayllarni o'rganib, "
                                                     "mos agentlarga bilim qilaman…")
            try:
                r = await asyncio.to_thread(tg_account.learn_channel, name, 100, progress)
            except Exception as e:
                await self.app.bot.send_message(chat_id, f"⚠️ {str(e)[:500]}")
                return
            if not r["posts"] and not r["files"]:
                await self.app.bot.send_message(chat_id, f"«{r['channel']}»: yangi post yoki fayl yo'q (avvalgilari o'rganilgan).")
                return
            await self.app.bot.send_message(chat_id, f"✅ «{r['channel']}» o'rganildi: {r['posts']} ta post, {r['files']} ta fayl → "
                                                     f"{r['saved']} ta bilim.\nAgentlar: {', '.join(r['agents']) or '-'}")

        task = asyncio.create_task(run())
        self.learn_tasks = getattr(self, "learn_tasks", set())
        self.learn_tasks.add(task)
        task.add_done_callback(self.learn_tasks.discard)

    async def channel_in_text(self, update: Update, text: str) -> bool:
        """«... kanalini o'rgan / ko'r» kabi xabar - kanal o'rganiladi. True - ishlov berildi."""
        from . import tg_account
        low = text.lower()
        if not tg_account.configured() or not any(w in low for w in ("kanal", "канал", "guruh", "группа", "@")):
            return False
        ch = await asyncio.to_thread(tg_account.find_in_text, text)
        if ch is None:
            return False
        self.learn_channel_bg(update, ch["title"])
        return True

    # ---------- yuborilgan materialdan o'rganish ----------
    def learn_bg(self, update: Update, title: str, text: str, source: str, images: list[str] | None = None,
                 hint: str = "") -> None:
        """Materialni fonda o'rganib, mos agent bazasiga yozadi va natijani egasiga xabar qiladi."""
        from . import ingest
        chat_id = update.effective_chat.id

        async def run():
            try:
                r = await asyncio.to_thread(ingest.learn, title, text, source, images, hint)
            except Exception as e:
                log.exception("Materialdan o'rganilmadi: %s", title)
                await self.app.bot.send_message(chat_id, f"⚠️ «{title[:60]}» o'rganilmadi: {str(e)[:200]}")
                return
            msg = f"📚 {r['icon']} {r['name']} bazasiga {r['saved']} ta bilim qo'shildi: «{title[:80]}»"
            await self.app.bot.send_message(chat_id, msg + (f"\n\n{r['summary'][:600]}" if r["summary"] else ""))

        task = asyncio.create_task(run())
        self.learn_tasks = getattr(self, "learn_tasks", set())
        self.learn_tasks.add(task)
        task.add_done_callback(self.learn_tasks.discard)

    async def read_links(self, update: Update, text: str) -> str:
        """Xabardagi havolalar (2 tagacha) ochib o'qiladi, o'rganiladi va javob uchun matnga qo'shiladi."""
        from . import ingest
        extra = []
        for url in dict.fromkeys(ingest.URL_RE.findall(text or "")).keys():
            if len(extra) >= 2:
                break
            try:
                page = await asyncio.to_thread(ingest.fetch_url, url)
            except Exception as e:
                log.info("Havola o'qilmadi %s: %s - Claude WebFetch bilan ochadi", url, e)
                page = ""
            title = (page.split("\n", 1)[0][:100] if page.strip() else "") or url
            self.learn_bg(update, title, page, url, hint=text)
            extra.append(f"[Havola mazmuni: {url}]\n{page[:8000]}" if page.strip()
                         else f"[Havola: {url} - sahifani WebFetch bilan o'zing ochib o'qi]")
        return text + ("\n\n" + "\n\n".join(extra) if extra else "")

    async def on_video(self, update: Update, ctx):
        """Video: saqlanadi va montaj qilinadi - izoh (caption) topshiriq; izohsiz - 9:16 + avtomatik subtitr."""
        from . import ingest, local_ai, montage
        if not await self._guard(update) or update.effective_user.id != self.owner_id:
            return
        m = update.message
        media = m.video or m.video_note or m.document
        if media.file_size and media.file_size > 20 * 1024 * 1024:
            await m.reply_text("Video juda katta: Telegram botlar 20 MB gacha yuklab oladi. Qisqaroq yoki siqilgan "
                               "variantini yuboring, yoki kompyuterdagi fayl yo'lini yozing.")
            return
        file = await media.get_file()
        name = getattr(media, "file_name", None) or f"video_{media.file_unique_id}.mp4"
        path = await asyncio.to_thread(ingest.save_upload, name, bytes(await file.download_as_bytearray()))
        task = m.caption or ""
        status = await m.reply_text("🎬 Video qabul qilindi. " + ("Topshiriq bo'yicha montaj qilyapman…" if task else
                                    "Reels qilyapman: 9:16 + avtomatik subtitr (topshiriq bo'lsa, videoga izoh yozing)…"))
        loop = asyncio.get_running_loop()

        def progress(note: str) -> None:
            asyncio.run_coroutine_threadsafe(status.edit_text(note), loop)

        start = outbox.mark()
        ready = local_ai.connected() if local_ai.access() is True else []
        try:
            report = await asyncio.to_thread(montage.run, task, str(path), brain.registry, ready, progress)
        except Exception as e:
            await m.reply_text(f"⚠️ Montaj bajarilmadi: {str(e)[:500]}")
            return
        await m.reply_text(report[:4000])
        for f in outbox.since(start):
            try:
                with open(f, "rb") as fh:
                    if f.suffix == ".mp4":
                        await m.reply_video(fh, caption=f"🎬 {f.name}", supports_streaming=True)
                    else:
                        await m.reply_document(fh, filename=f.name)
            except Exception:
                log.exception("Montaj natijasi yuborilmadi: %s", f)
                await m.reply_text(f"⚠️ {f.name} tayyor, lekin yuborilmadi (hajmi katta bo'lishi mumkin) - saytdan oling.")

    async def on_document(self, update: Update, ctx):
        """Fayl (PDF, Word, Excel, PowerPoint, matn, kod, rasm): o'qiladi, javob beriladi va bilim bo'ladi."""
        from . import ingest
        if self.is_private(update) and update.effective_user.id != self.owner_id:
            await update.message.reply_text("Fayllarni hozircha faqat administrator yubora oladi. Savolingizni matn qilib yozing.")
            return
        if not await self._guard(update):
            return
        doc = update.message.document
        if doc.file_size and doc.file_size > 20 * 1024 * 1024:
            await update.message.reply_text("Fayl juda katta (Telegram botlar 20 MB gacha yuklab oladi).")
            return
        file = await doc.get_file()
        path = await asyncio.to_thread(ingest.save_upload, doc.file_name or "fayl", bytes(await file.download_as_bytearray()))
        caption = update.message.caption or ""
        if path.suffix.lower() in ingest.IMAGE_EXT:
            data = base64.b64encode(path.read_bytes()).decode()
            self.learn_bg(update, f"Rasm: {path.name}", caption, "Telegram (rasm fayl)", [str(path)], hint=caption)
            await self.process(update, ctx, caption, [{"media_type": "image/jpeg", "data": data}])
            return
        try:
            text = await asyncio.to_thread(ingest.extract_text, path)
        except RuntimeError as e:
            await update.message.reply_text(f"⚠️ {e}")
            return
        if not text.strip():
            await update.message.reply_text("Fayldan matn topilmadi (skanerlangan PDF bo'lishi mumkin - rasm qilib yuboring).")
            return
        self.learn_bg(update, doc.file_name or path.name, text, f"Telegram fayl: {doc.file_name}", hint=caption)
        question = caption or "Shu faylni o'qib chiq: asosiy mazmuni, muhim raqam va xulosalarini qisqa ayt."
        await self.process(update, ctx, f"{question}\n\n[Fayl: {doc.file_name}]\n{text[:12000]}")

    async def on_voice(self, update: Update, ctx):
        if self.is_private(update) and update.effective_user.id!=self.owner_id:
            await update.message.reply_text('Hozircha savolingizni matn qilib yuboring. Ovozli xizmat administrator uchun yoqilgan.',reply_markup=self.keyboard())
            return
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
            await update.message.reply_text("Ovozli xabarni tushunish uchun .env da GEMINI_API_KEY kerak.")
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
        if self.is_private(update) and update.effective_user.id!=self.owner_id:
            await self.send_request(update,'image',update.message.caption or 'Foydalanuvchi rasm yubordi; topshiriqni aniqlashtiring.')
            return
        if not await self._guard(update):
            return
        from . import ingest
        file = await update.message.photo[-1].get_file()
        raw = bytes(await file.download_as_bytearray())
        data = base64.b64encode(raw).decode()
        caption = update.message.caption or ""
        # Rasm ham o'rganiladi: Pro ilova ko'radi, mos agent bazasiga tavsif va bilim yoziladi
        path = await asyncio.to_thread(ingest.save_upload, "telegram_rasm.jpg", raw)
        from . import studio_flow  # kreativ video brifi rasm kutyapti: izohsiz yoki «#B12» izohli rasm - brifga
        if studio_flow.waiting() and (not caption.strip() or studio_flow.TAG.match(caption.strip())):
            full, note = await asyncio.to_thread(studio_flow.add_image, str(path), caption)
            if note:
                await update.message.reply_text(note)
            if full:
                threading.Thread(target=studio_flow._build_and_send, args=(full["id"], hub.notify), daemon=True).start()
            return
        self.learn_bg(update, f"Rasm {time.strftime('%Y-%m-%d %H:%M')}" + (f": {caption[:60]}" if caption else ""),
                      caption, "Telegram (rasm)", [str(path)], hint=caption)
        await self.process(update, ctx, caption, [{"media_type": "image/jpeg", "data": data}])

    async def on_location(self, update: Update, ctx):
        if not self.is_private(update):
            return
        loc = update.message.location
        if update.effective_user.id==self.owner_id:
            hub.last_location = {"lat": loc.latitude, "lon": loc.longitude, "accuracy": loc.horizontal_accuracy,
                                 "device": "telegram", "time": time.strftime("%H:%M:%S")}
        await self.save_location(update,{'lat':loc.latitude,'lon':loc.longitude,'name':'Sizning hududingiz'})

    # ---------- asosiy jarayon ----------
    async def process(self, update: Update, ctx, text: str, images: list[dict] | None = None):
        chat = update.effective_chat
        p = self.pref(chat.id)
        status = await update.message.reply_text("⏳ O‘ylayapman…")
        files: list = []

        def on_event(kind, data):  # brain oqimidan chaqiriladi
            if kind == "files":
                files.extend(data)

        async def live_editor():
            # Javob tayyor bo'lguncha faqat "⏳ O'ylayapman…" va "yozmoqda" belgisi: vosita va model nomlari ko'rsatilmaydi.
            while True:
                await ctx.bot.send_chat_action(chat.id, ChatAction.TYPING)
                await asyncio.sleep(4)

        editor = asyncio.create_task(live_editor())
        try:
            answer = await run_ask(text, images, p["deep"], p["super"], source="telegram", on_event=on_event,
                                   agent=p["agent"], direct=p.get("ai"))
        except AskError as e:
            await status.edit_text(f"⚠️ {e}")
            return
        finally:
            editor.cancel()

        chunks = split_text(answer or "(bo‘sh javob)")
        await self._edit_html(status, chunks[0])
        for chunk in chunks[1:]:
            await self._send_html(chat.id, chunk)
        for path in files:  # Office ekspert yaratgan taqdimot / Excel / Word
            try:
                with open(path, "rb") as fh:
                    await chat.send_document(document=fh, filename=path.name, caption=f"📎 {path.name}")
            except Exception:
                log.exception("Faylni yuborib bo'lmadi: %s", path)
                await chat.send_message(f"⚠️ Fayl tayyor, lekin yuborilmadi: {path.name}. Saytdan yuklab oling.")
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
            await self.safe_answer(query, "Ruxsat yo'q")
            return
        _, cid, ok = query.data.split(":")
        hub.resolve_confirm(cid, ok == "1")
        await self.safe_answer(query, "Ruxsat berildi" if ok == "1" else "Rad etildi")

    def _run(self, coro) -> None:
        if hub.loop and not hub.loop.is_closed():
            asyncio.run_coroutine_threadsafe(coro, hub.loop)
        else:
            coro.close()

    def on_confirm(self, cid: str, name: str, args: dict) -> None:
        detail = args.get("command") or json.dumps(args, ensure_ascii=False, indent=1)
        text = f"⚠️ <b>Ruxsat so‘ralmoqda</b>\n{html.escape(TOOL_LABELS.get(name, name))}\n<pre>{html.escape(detail[:3000])}</pre>"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Ruxsat", callback_data=f"cf:{cid}:1"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"cf:{cid}:0"),
        ]])

        label = TOOL_LABELS.get(name, name)

        async def send():
            sent = []
            for uid in self.users:
                try:
                    m = await self.app.bot.send_message(uid, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
                    sent.append((uid, m.message_id))
                except Exception:
                    log.exception("Tasdiq yuborilmadi: %s", uid)
            self.confirm_msgs[cid] = sent
            await self.voice_ask(label, sent)
            # Javob bo'lmasa - 3 va 8 daqiqadan keyin qayta eslatadi (tugmali xabarga javob tarzida)
            for wait in (180, 300):
                await asyncio.sleep(wait)
                if cid not in self.confirm_msgs:
                    return
                for chat_id, msg_id in sent:
                    try:
                        await self.app.bot.send_message(chat_id, f"⏰ Ali hali javobingizni kutyapti: {label}. "
                                                                 "Yuqoridagi «✅ Ruxsat» yoki «❌ Rad etish» ni bosing.",
                                                        reply_to_message_id=msg_id)
                    except TelegramError:
                        pass

        self._run(send())

    async def voice_ask(self, label: str, sent: list) -> None:
        """Ali Pomoshnik ovozi bilan vaziyatni tushuntiradi (Telegram botlari qo'ng'iroq qila olmaydi - ovozli xabar)."""
        try:
            audio = await tts.synthesize(f"{config.user_name}, {config.assistant_name} ruxsat so'rayapti. {label}. "
                                         "Ruxsat bersangiz, xabardagi yashil tugmani bosing. Rad etsangiz - qizil tugmani.")
        except Exception:
            log.exception("Ovozli ruxsat so'rovi tayyorlanmadi")
            return
        for chat_id, msg_id in sent:
            try:
                await self.app.bot.send_voice(chat_id, voice=audio, reply_to_message_id=msg_id)
            except TelegramError:
                log.exception("Ovozli ruxsat so'rovi yuborilmadi")

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

    def on_answer(self, question: str, answer: str, source: str) -> None:
        if source == "telegram":
            return
        async def send():
            for uid in self.users:
                try:
                    for chunk in split_text(f"🖥 Saytdagi suhbat\n\nSiz: {question}\n\n{config.assistant_name}: {answer}"):
                        await self._send_html(uid, chunk)
                except Exception:
                    log.exception("Sayt javobini Telegramga yuborib bo'lmadi")
        self._run(send())
