# Ali — Jarvis uslubidagi shaxsiy yordamchi

"Temir odam" filmidagi J.A.R.V.I.S. kabi: telefon, kompyuter va Telegram orqali ovoz bilan boshqariladi,
o'zbekcha gapiradi, kompyuterda ish bajaradi, internetdan o'rganib sizga o'rgatadi, joylashuvni biladi
va Instagram akkauntlaringizni tahlil qilib kontent reja tuzadi.

## Imkoniyatlar

| | |
|---|---|
| **Super miya** | Claude — asosiy miya. "Super miya" rejimida GPT va Gemini fikrini ham so'rab, solishtirib javob beradi |
| **Chuqur fikrlash** | Murakkab vazifalar uchun chuqurroq o'ylash rejimi; fikrlash jarayoni ekranda jonli ko'rinadi |
| **Veb-sayt** | Telefon va kompyuterda bir xil, Jarvis HUD dizayni, bosh ekranga ilova sifatida o'rnatiladi |
| **Telegram bot** | Matn, ovozli xabar, rasm, joylashuv; javob matn + ovoz bilan; xavfli amallarni tugma bilan tasdiqlash |
| **Ovoz** | Gapirib boshqarish, "Ali" deb chaqirish, o'zbekcha javob. **O'z ovozingizni** yuklab, Ali'ni shu ovozda gapirtirish |
| **Kompyuterni boshqarish** | PowerShell orqali istalgan ish (har safar tasdiq bilan), ekranni ko'rish, ilova/sayt ochish |
| **O'rganish** | Bilmagan mavzuni internetdan o'rganadi, bilimlar bazasiga saqlaydi va sizga o'rgatadi |
| **Joylashuv** | Telefon GPS, ob-havo, yaqin atrofdagi joylar |
| **Instagram** | Statistika, eng yaxshi postlar tahlili, izohlar, raqobatchilar, video g'oyalari va ssenariylar |
| **Xotira** | Siz haqingizdagi faktlar, eslatmalar, barcha suhbatlar |

Barcha kanallar **bitta suhbat**ni bo'lishadi: Telegram'da yozgan narsangiz kompyuter ekranida ham jonli ko'rinadi.

## O'rnatish

```bash
pip install -r requirements.txt
copy .env.example .env
```

`.env` faylida kamida `ANTHROPIC_API_KEY` ni yozing (https://console.anthropic.com).
Qolganlari ixtiyoriy — qo'shgan sari imkoniyat ko'payadi.

## Ishga tushirish

```bash
start.bat          # yoki: python server.py
```

- **Kompyuterda:** http://localhost:8000 (parol terminalda chiqadi yoki `.env` dagi `ACCESS_PASSWORD`)
- **Telefonda:** `tunnel.bat` ni ishga tushiring → chiqqan `https://...trycloudflare.com` havolani telefonda oching →
  brauzer menyusidan "Bosh ekranga qo'shish". Mikrofon va GPS faqat HTTPS orqali ishlaydi, tunnel shu uchun kerak.
  Havola internetdan ochiladi, shuning uchun **kuchli parol** qo'ying.
- **Telegram:** pastga qarang.

## Telegram bot

1. Telegram'da [@BotFather](https://t.me/BotFather) → `/newbot` → token oling
2. `.env` ga yozing: `TELEGRAM_BOT_TOKEN=...`
3. Serverni qayta ishga tushiring, botga `/login PAROL` yozing (parol xabari avtomatik o'chiriladi)

Buyruqlar: `/new` yangi suhbat · `/chuqur` · `/super` · `/ovozli` ovozli javob · `/holat` ·
`/ovoz` `/ovoz_tayyor` `/ovoz_standart` — shaxsiy ovoz.

Ovozli xabarlarni tushunish uchun `OPENAI_API_KEY` yoki `GEMINI_API_KEY` kerak.

## O'z ovozingizni qo'yish

Ali sizning (yoki tanlagan) ovozda gapiradi — ElevenLabs ovoz klonlash orqali.

1. https://elevenlabs.io dan API kalit oling → `.env`: `ELEVENLABS_API_KEY=...`
2. Telegram botga `/ovoz` yozing va **ovozli xabarlar (golosovoy)** yuboring: jami 1–3 daqiqa,
   jim xonada, tabiiy ohangda. Yoki audio fayllarni `voices/samples/` papkasiga tashlang.
3. `/ovoz_tayyor` — yangi ovoz yaratiladi va Ali darhol shu ovozda javob beradi (sayt va Telegram'da).
4. Qaytish: `/ovoz_standart` (bepul Edge ovozi `uz-UZ-SardorNeural`).

## Instagram

Instagram **Business** yoki **Creator** akkaunt kerak (Facebook sahifaga ulangan).

1. https://developers.facebook.com → ilova yarating → Instagram Graph API qo'shing
2. Graph API Explorer'da token oling, ruxsatlar: `instagram_basic`, `instagram_manage_insights`,
   `pages_show_list`, `pages_read_engagement` (uzoq muddatli tokenga almashtiring)
3. Akkaunt ID: `GET /me/accounts?fields=instagram_business_account`
4. `.env`: `IG_ACCESS_TOKEN=...` va `IG_ACCOUNTS=brend=1784...,shaxsiy=1784...`

So'rash misollari: *"Instagramimni tahlil qil va keyingi haftaga 5 ta reels g'oyasi ber"*,
*"@raqobatchi akkauntini o'rgan, ular nimasi bilan yutyapti?"*

## Tuzilishi

```
server.py                Veb-server + Telegram bot (asosiy ishga tushirish)
main.py                  Terminal rejimi (matn / ovoz)
ali/
  brain.py               Miya: Claude, vositalar tsikli, fikrlash, web qidiruv, super miya
  service.py             Yagona miya va so'rov bajarish (sayt va Telegram uchun umumiy)
  providers.py           GPT va Gemini, ovozni matnga aylantirish
  telegram_bot.py        Telegram bot
  tts.py                 Ovoz: Edge yoki shaxsiy klon (ElevenLabs)
  hub.py                 Ulangan qurilmalar, tasdiqlash, bildirishnomalar
  auth.py                Parol va kirish tokeni
  memory.py              SQLite: faktlar, bilimlar, eslatmalar, suhbatlar
  scheduler.py           Eslatmalarni vaqtida yuborish
  skills/                Ko'nikmalar (har bir fayl avtomatik yuklanadi)
    system.py            Vaqt, ilova, sayt, tizim holati
    pc.py                PowerShell, ekran rasmi
    phone.py             Telefonga havola/xabar, joylashuv, ob-havo
    knowledge.py         O'rganish va bilimlar bazasi
    instagram.py         Instagram analitika va raqobatchilar
    experts.py           GPT + Gemini maslahati
    memory_skills.py     Eslab qolish
    reminders.py         Eslatmalar
  voice/                 Terminal rejimi uchun mikrofon va karnay
web/                     Interfeys (HTML/CSS/JS, PWA)
voices/samples/          Shaxsiy ovoz namunalari
data/                    Baza, kalitlar (avtomatik)
```

## Yangi ko'nikma qo'shish

`ali/skills/` ga yangi fayl — boshqa hech narsa o'zgartirilmaydi:

```python
from . import skill

@skill(description="Kompyuterni qulflaydi", dangerous=True)
def lock_pc() -> str:
    import ctypes
    ctypes.windll.user32.LockWorkStation()
    return "Qulflandi"
```

`dangerous=True` — bajarishdan oldin sayt yoki Telegram'da tasdiq so'raladi.

## Xavfsizlik

- Ali kompyuteringizda buyruq bajara oladi — saytga kirish paroli va Telegram ruxsatlari shu sababli majburiy.
- Har bir PowerShell buyrug'i oldin sizga ko'rsatiladi va faqat tasdiqlasangiz bajariladi.
- `.env`, `data/` va `voices/samples/` ni hech kimga bermang.

## Keyingi qadamlar (taklif)

- [ ] **Kompyuterni sichqoncha/klaviatura bilan boshqarish** (Claude computer use) — Ali ekranni ko'rib, o'zi bosib ishlaydi
- [ ] **Telefonni to'liq boshqarish** — Android ilova (qo'ng'iroq, SMS, ilovalar) yoki Tasker integratsiyasi
- [ ] Instagram'ga post/reels joylash va izohlarga javob berish (tasdiq bilan)
- [ ] Har kuni ertalab avtomatik xulosa: ob-havo, eslatmalar, Instagram statistikasi
- [ ] Gmail / Google Calendar
- [ ] Doimiy HTTPS manzil (Cloudflare named tunnel + o'z domeningiz)
- [ ] Windows ishga tushganda Ali avtomatik yoqilishi
- [ ] Musiqa, ovoz balandligi, aqlli uy qurilmalari
