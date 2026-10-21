# Ali — Jarvis uslubidagi shaxsiy yordamchi

"Temir odam" filmidagi J.A.R.V.I.S. kabi: telefon, kompyuter va Telegram orqali ovoz bilan boshqariladi,
o'zbekcha gapiradi, kompyuterda ish bajaradi, internetdan o'rganib sizga o'rgatadi, joylashuvni biladi
va Instagram akkauntlaringizni tahlil qilib kontent reja tuzadi.

## Imkoniyatlar

| | |
|---|---|
| **Super miya** | Claude — asosiy miya. Barcha savol va vazifalarni o'zi bajaradi; Gemini faqat ovozni matnga aylantirish va rasm uchun |
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
start-full.bat     # TO'LIQ RUXSAT: barcha vositalar tasdiqsiz (faqat o'z kompyuteringizda)
```

**To'liq ruxsat rejimi** (`start-full.bat`): Ali dasturlarni ochadi, oynalarga kiradi, bosadi va yozadi
(`list_windows`, `focus_window`, `mouse_click`, `type_text`, `press_keys`), fayl va papkalarni o'qib tahlil qiladi
(`read_file`, `list_folder`: docx, xlsx, pptx, pdf, kod), internetdan qidiradi va murakkab savolda GPT + Gemini
fikrini oladi (`consult_experts`, `OPENAI_API_KEY` / `GEMINI_API_KEY` kerak). Ruxsatlar bo'limida "Taqiqlangan"
qilingan vosita bu rejimda ham bloklanadi. Sichqonchani ekranning burchagiga olib borsangiz, boshqaruv to'xtaydi.
Administrator huquqi kerak bo'lsa — `start-full.bat` ni "Run as administrator" bilan oching.

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

Ovozli xabarlarni tushunish uchun `GEMINI_API_KEY` kerak.

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
  providers.py           Gemini: faqat ovozni matnga aylantirish va rasm
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
    memory_skills.py     Eslab qolish
    reminders.py         Eslatmalar
    market.py            Kripto narxlari va texnik ko'rsatkichlar (Binance)
    projects.py          Kompyuterdagi loyihalar (VS Code)
    github.py            GitHub
    vercel.py            Vercel
    coding.py            Claude Code vazifalari
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
| 👨‍💻 Dasturchi | `dasturchi.md` | Kompyuterdagi (VS Code), GitHub va Vercel loyihalari: kodni o'qish, xato tuzatish, deploy tekshirish, Claude Code'ga vazifa |
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

## Dasturlash: GitHub, Vercel, VS Code, Claude Code

`.env` ga yozing:
- `GITHUB_TOKEN` — https://github.com/settings/tokens → Fine-grained token → *All repositories*; ruxsatlar: Contents, Issues, Pull requests, Actions — *Read and write*.
- `VERCEL_TOKEN` — https://vercel.com/account/tokens (jamoa loyihalari uchun `VERCEL_TEAM_ID` ham).
- `PROJECTS_DIRS` — loyihalar papkalari (`;` bilan). Bo'sh bo'lsa: Ali turgan papkaning ota papkasi + VS Code'da ochilgan papkalar.

Kod yozuvchi agent (ixtiyoriy) — terminalda:

```
npm install -g @anthropic-ai/claude-code
```

Keyin bir marta `claude` (kirish). Shundan so'ng Dasturchi katta vazifalarni unga topshiradi —
vazifa fonda ishlaydi, tugagach telefonga/Telegramga xabar keladi. Faylni yozish, buyruq bajarish, issue ochish,
redeploy kabi amallar har doim sizdan tasdiq so'raydi.

## Avtomatik agentlar: rus tili va Office fayllari

- **Ruscha yozsangiz** (Telegram yoki sayt) — Ali so'rovni avtomatik **💻 Учитель информатики** agentiga beradi,
  javob rus tilida keladi. O'zbekcha (lotin yoki kirill) yozsangiz — oddiy Ali.
- **Taqdimot, Excel yoki Word** so'rasangiz — **📊 Office ekspert** haqiqiy faylni yaratadi
  (`make_presentation`, `make_excel`, `make_word`): 16:9 chiroyli dizayn, bo'limlar, jadval, diagramma, izohlar.
  Fayl Telegram'ga **hujjat** bo'lib keladi, saytda esa yuklab olish tugmasi chiqadi.
- Ruscha + fayl (masalan "Сделай презентацию про алгоритмы") — ikkala agent ishlaydi: o'qituvchi mazmunni tayyorlaydi,
  Office ekspert faylni yasaydi.
- **🎨 Dizayner** agenti taqdimotni professional darajada, mavzuga mos dizayn bilan yasaydi: qidiruv mavzusida lupa,
  kodlashda ikkilik kod, tarmoqda tugunlar, algoritmda blok-sxema; ikonkali kartalar, jarayon, test (A/B/C/D),
  amaliy topshiriq, "Bilasizmi?", kod bloki, jadval, diagramma.
- **Dars taqdimoti** (`make_lesson_presentation`) dars ishlanmasi bo'yicha 50 daqiqa: Tashkiliy qism 5, Uy vazifasini
  so'rash 10, Yangi mavzu 15, Mustahkamlash 15, Yakuniy qism 5 daqiqa; har slaydda bosqich va vaqt, uy vazifasi slaydi,
  o'qituvchi uchun izohlar va javoblar. Qo'shimcha **Word dars ishlanmasi** (T/r, bosqich, nima qilinadi, vaqt jadvali).
- Fayllar `data/outbox` da 14 kun saqlanadi. Hech qanday skript yoki tasdiq kerak emas, Render'da ham ishlaydi.

## 🎨 Dizayn studiyasi (Dizayner agenti)

| So'rov | Natija (Telegram'ga fayl bo'lib keladi) |
|---|---|
| "80 m² uyimga reja va dizayn" (rasmlar bilan ham) | `design_floor_plan`: AutoCAD **.dxf** (mm, qatlamlar, o'lchamlar), reja **PNG**, 3ds Max/Blender uchun **.obj+.mtl**, **3D ko'rinish** PNG |
| "120 m² do'konni joylashtir" / kafe / ofis | javonlar, gondolalar, kassa, 1.2 m+ yo'laklar, mijoz harakati yo'li, zonalar (dekompressiya, impuls tovar) |
| "MARKET 24 uchun hajmli harflar, 5×1.2 m" | `design_signage`: haqiqiy o'lchamli **.svg** (Illustrator/CorelDraw), **kunduzgi va tungi maket**, harf balandligi va o'qilish masofasi, materiallar, LED va quvvat bloki |
| "Ochilish uchun reklama video" | `make_promo_video`: **.mp4** (9:16 / 16:9 / 1:1) va After Effects **.jsx** (AE'da qatlamlar va kalit kadrlar bilan qayta yaratadi) |

Agent Photoshop, CorelDraw, Illustrator, AutoCAD, 3ds Max va After Effects bo'yicha ish tartibini biladi va o'rgatadi.
Rejalar - konsept: qurilishdan oldin joyida o'lchash va mutaxassis tekshiruvi kerak.

## Treyding: barcha timeframe'lar va MT5

- **📈 Treyder** agenti `mtf_signal` bilan bitta belgini 15m, 1h, 4h, 1d da birga tekshiradi va signalni faqat
  qarshi omil yo'q hamda yuqori timeframe'lar qarshi bo'lmasa beradi (MT5 EA bilan bir xil qoida). Chatda: "XAUUSD signal".
- MT5 robot (AI Zone Trader 5) — alohida repozitoriy **mql5-mt5**: bitta chart M5..D1 ni skanerlaydi, signalni Claude
  tekshiradi va Telegram'ga EA'ning o'zi yuboradi. Ali EA bilan bir kompyuterda bo'lsa, `mt5_signals` va
  `signal_results` bilan signallar va natijalarni o'qiydi (`MT5_FILES_DIR` — MT5 `MQL5\Files` papkasi).
- Agent fayllaridagi `versiya:` raqami oshirilsa, Render'dagi doimiy diskdagi nusxa ham yangilanadi
  (Murabbiy yozgan saboqlar saqlanadi).

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

## Plaginlar

`ali/plugins/` dagi har bir fayl — plagin. Ali ishga tushganda hammasi o'zi (fonda) ishga tushadi:
Gemini, ChatGPT (`OPENAI_API_KEY`), Photoshop va CorelDRAW (o'rnatilgan bo'lsa, COM orqali).
O'chirish: `PLUGINS_DISABLED=chatgpt`. Holat: Ruxsatlar → Ulanishlar.

## Telefon ilovasi va Windows o'rnatuvchisi

- **Telefon (Flutter)** — `mobile/`: Android va iPhone. Ism va har bir ruxsat alohida so'raladi, Firebase'da
  akkaunt va suhbatlar saqlanadi, bulut serverdagi `/api/mobile/ask` javob beradi. Batafsil: [mobile/README.md](mobile/README.md).
- **Firebase** — `firebase/`: Firestore xavfsizlik qoidalari (har kim faqat o'z ma'lumotini ko'radi).
- **Windows** — `installer/`: `powershell -ExecutionPolicy Bypass -File installer\build_windows.ps1` →
  `dist\Ali-Setup-1.0.0.exe`. O'rnatishda ism, ruxsatlar (kompyuter, ekran, dasturlar, fayllar, Photoshop,
  CorelDRAW, AI, akkauntlar) va kalitlar so'raladi; ular `%LOCALAPPDATA%\Ali\.env` ga yoziladi.
- Maxfiylik siyosati: `/privacy` (do'konlar talab qiladi).

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
