# Ali Pomoshnik — 24/7

Asosiy sayt va Telegram bot **bitta doimiy serverda, bitta worker bilan** ishlaydi.
Render `render.yaml` shu variantni tayyorlaydi. Bu pulli Starter server va 1 GB disk;
ishga tushirishdan oldin amaldagi tarifni tasdiqlang.

## Joylashtirish

1. Repozitoriydagi o'zgarishlarni saqlang va Render Blueprint orqali `render.yaml` ni tanlang.
2. Render sirlar sozlamasiga `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `TELEGRAM_BOT_TOKEN`,
   `ACCESS_PASSWORD` ni mahalliy `.env` dan kiriting. Kalitlarni Git'ga yubormang.
   `TELEGRAM_ALLOWED_USERS` ixtiyoriy: bo'sh bo'lsa, botdagi `/login PAROL` orqali kiriladi.
   Kerak bo'lsa `GEMINI_API_KEY`, ovoz va boshqa sozlamalarni ham kiriting.
3. `/healthz`, saytga kirish, WebSocket va botdagi `/start` ni tekshiring.
   Render `RENDER_EXTERNAL_URL` orqali botning Mini App manzilini avtomatik belgilaydi.
4. Vercel loyihasida `ALI_BACKEND_URL=https://<render-server>.onrender.com` ni o'rnating
   va yangi kodni qayta deploy qiling. `server.py` Vercel'da diskka yozmaydigan gateway'ni
   yuklaydi, foydalanuvchini asosiy serverga yo'naltiradi. Shu sababli cookie va WebSocket
   bir manzilda ishlaydi. Backend yo'q bo'lsa, yolg'on ishlayotgan panel emas, 503 sozlash
   sahifasi ko'rsatiladi.
5. Mahalliy Telegram polling jarayonini o'chiring: **bir bot tokeni bilan bitta server**
   ishlashi kerak. Production'da bir nechta worker yoki replica qo'ymang.

## Saqlanadigan ma'lumotlar

`ALI_STATE_DIR=/var/data`: SQLite xotira, suhbatlar, faol sessiya, agentlar, Telegram
ruxsatlari va ovoz namunalari doimiy diskda. Birinchi ishga tushishda standart agentlar
ko'chiriladi; foydalanuvchi o'chirgan agentlar keyingi deploy'da qayta yaratilmaydi.
Diskni muntazam zaxiralang. Mavjud mahalliy `data/`, `agents/` va `voices/` ma'lumotlarini
ko'chirish alohida, maxfiy migratsiya bo'lishi kerak; Docker image ichiga kiritilmaydi.

Kompyuterni yoqish/o'chirish, ekran rasmi va Windows ilovalari bulut serveridan mahalliy
kompyuterga avtomatik ulanmaydi. Ular uchun alohida kompyuter ulanishi kerak.

## Mahalliy tekshirish

`python -m unittest discover -s tests -v`

`python server.py` → http://localhost:8000

Bot ko'rinadigan nomi va buyruqlarini serverni boshlamasdan sozlash:
`python scripts/configure_telegram.py`. Username'ni almashtirish Telegram BotFather orqali.
