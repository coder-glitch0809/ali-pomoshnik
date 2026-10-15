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

Kompyuter o'chiq bo'lganda ham ishlaydigan sayt + Telegram uchun
[24/7 joylashtirish yo'riqnomasi](DEPLOYMENT.md) va `render.yaml` tayyor.
Telegram'da `/sayt` to'liq panelni, `/monitor` vazifalar holatini ochadi.

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
  brain.py               Miya: Claude, vositalar tsikli, fikrlash, web qidiruv, super miya, agentlar
  agents.py              agents/*.md fayllarini yuklash va saqlash
  autopilot.py           O'z-o'zini o'rganish va loyihalarni kuzatish
  monitor.py             Monitoring: ishlar, agentlar statistikasi, jonli lenta
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
    market.py            Kripto narxlari va texnik ko'rsatkichlar (Binance)
    projects.py          Kompyuterdagi loyihalar (VS Code)
    github.py            GitHub
    vercel.py            Vercel
    coding.py            Claude Code va Codex vazifalari
    agent_admin.py       Agent yaratish/tahrirlash
    autopilot_skills.py  Avtopilotni qo'lda ishga tushirish
  voice/                 Terminal rejimi uchun mikrofon va karnay
agents/                  Agentlar: har biri bitta .md fayl
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

## Agentlar

Agent — o'z roli, ko'rsatmasi, vositalari va bilimlariga ega mutaxassis. Tayyorlari (`agents/` papkasida):

| Agent | Fayl | Nima qiladi |
|---|---|---|
| 👨‍💻 Dasturchi | `dasturchi.md` | Kompyuterdagi (VS Code), GitHub va Vercel loyihalari: kodni o'qish, xato tuzatish, deploy tekshirish, Claude Code / Codex'ga vazifa |
| 📈 Treyder | `treyder.md` | Bozor tahlili (Binance, RSI/SMA/ATR), savdo rejasi, risk; treyding loyihalaringiz kodini tahlil qiladi |
| 🎬 Kontent-meyker | `kontent.md` | Reels ssenariylari, hook, post matni, kontent-reja, Instagram tahlili |
| 💻 Учитель информатики | `informatika.md` | Ruscha ishlaydi: dasturlash va informatikani o'rgatish; dars rejasi, test, topshiriqlar |

Foydalanish:
- **Sayt / telefon:** Chat tepasidagi tugmalardan agentni tanlang. "Agentlar" bo'limida agent yaratish, tahrirlash, o'chirish mumkin.
- **Telegram:** `/agent` (tugmalar) yoki `/agent treyder`, `/agent ali`.
- **Chat orqali:** "Huquqshunos agent yarat ..." — Ali sohani o'rganib, agentni va uning bilimlarini o'zi to'ldiradi.
- **Avtomatik:** oddiy rejimda Ali katta vazifani mos agentga o'zi topshiradi (`ask_agent`).

Agent fayli formati (qo'lda ham yozish mumkin — o'zgarishlar darhol kuchga kiradi):

```markdown
---
nom: Huquqshunos
belgi: ⚖️
tavsif: O'zbekiston qonunchiligi bo'yicha maslahat, shartnoma va ariza matnlari
vositalar: web_search, search_knowledge, save_knowledge
o'rganish: O'zbekiston qonunchiligidagi yangi o'zgarishlar; sud amaliyoti
---
Sen tajribali huquqshunossan... (agentning to'liq ko'rsatmasi)
```

## Dasturlash: GitHub, Vercel, VS Code, Claude Code, Codex

`.env` ga yozing:
- `GITHUB_TOKEN` — https://github.com/settings/tokens → Fine-grained token → *All repositories*; ruxsatlar: Contents, Issues, Pull requests, Actions — *Read and write*.
- `VERCEL_TOKEN` — https://vercel.com/account/tokens (jamoa loyihalari uchun `VERCEL_TEAM_ID` ham).
- `PROJECTS_DIRS` — loyihalar papkalari (`;` bilan). Bo'sh bo'lsa: Ali turgan papkaning ota papkasi + VS Code'da ochilgan papkalar.

Kod yozuvchi agentlar (ixtiyoriy) — terminalda:

```
npm install -g @anthropic-ai/claude-code
npm install -g @openai/codex
```

Keyin bir marta `claude` (kirish) va `codex login`. Shundan so'ng Dasturchi katta vazifalarni ularga topshiradi —
vazifa fonda ishlaydi, tugagach telefonga/Telegramga xabar keladi. Faylni yozish, buyruq bajarish, issue ochish,
redeploy kabi amallar har doim sizdan tasdiq so'raydi.

## Avtopilot: o'z-o'zini o'rganish va loyihalarni kuzatish

`.env` da yoqiladi (API'dan pul sarflaydi):
- `AUTO_LEARN=true` — har bir agent `AUTO_LEARN_HOURS` da bir marta o'z "o'rganish" mavzulari bo'yicha internetdan
  yangiliklarni o'rganib, bilimlar bazasiga yozadi va keyingi javoblarida ishlatadi. Qo'lda: chatda "Treyderni hozir o'qit".
- `WATCH_PROJECTS=true` — Dasturchi `WATCH_HOURS` da bir marta treyding loyihalarini (git, GitHub Actions, Vercel) tekshiradi
  va muammo bo'lsa xabar beradi. Qo'lda: "Treyding loyihalarimni tekshir".

- `SELF_IMPROVE=true` — har kuni (`SELF_IMPROVE_HOURS`) har bir agent tekshiriladi va rivojlantiriladi:
  1. sog'lik tekshiruvi (0-100 ball): mavjud bo'lmagan vositalar, so'nggi 7 kundagi xatolar, o'rganish xatolari, bo'sh bilim;
  2. aniq xatolar darhol tuzatiladi (masalan mavjud bo'lmagan vosita olib tashlanadi);
  3. muammosi yoki yangi ishi bo'lgan agentni **🧑‍🏫 Murabbiy** agent tahlil qilib, unga "Tajriba" saboqlari,
     bilim bo'shlig'ini to'ldiradigan o'rganish mavzulari va kerakli (xavfsiz) vositalarni qo'shadi;
  4. kunlik hisobot Telegram/telefonga keladi. Xato bo'lsa 1 soatdan keyin qayta uriniladi — tsikl to'xtamaydi.

  **Ali'ning o'zi ham** shu tsiklda: xato bilan tugagan so'rovlari, tez-tez buziladigan vositalar tahlil qilinadi,
  saboqlar `data/ali-tajriba.md` ga yoziladi va Ali'ning tizim ko'rsatmasidagi "Tajriba" bo'limiga darhol qo'shiladi.

  Agentning asosiy ko'rsatmasi qayta yozilmaydi, har o'zgarishdan oldin nusxa `agents/_history` ga saqlanadi.
  Qo'lda: "Agentlarni hozir rivojlantir", "O'zingni tekshir", "Treyder holatini tekshir", "Treyderni oldingi holatiga qaytar".
  `AUTO_LEARN` bilan birga yoqing: Murabbiy qo'shgan mavzularni agentlar har kuni o'rganadi.

Avtopilot siz yo'qligingizda faqat tasdiq talab qilmaydigan vositalardan foydalanadi: loyihalar va fayllar o'zgartirilmaydi.
Hammasi Monitoring bo'limida jonli ko'rinadi.

**Eslatma:** Ali kompyuteringizda ishlaydi — kompyuter o'chiq bo'lsa Ali ham ishlamaydi. 24/7 ishlashi uchun uni
bulut serverga (VPS) qo'yish kerak; bunda kompyuterdagi loyihalar o'rniga GitHub/Vercel orqali ishlaydi.

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
