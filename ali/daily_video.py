"""Har kuni 11:00 va 16:00 da Ali jamoasi o'zi Reels yasaydi (egasi so'ramasa ham):

  1) Kontent-meyker - g'oya va sahnalar matni (haftalik Instagram audit xulosasi va oldingi videolarga qarab, takrorlamasdan);
  2) Dasturchi - shu sahnalar uchun animatsiya kodi (bitta HTML: CSS @keyframes, 1080x1920);
  3) Video montajchi - kodni kadrma-kadr videoga aylantiradi (Chrome, 30 fps), musiqa qo'shadi va kanalga/egasiga yuboradi.
AI'lar band bo'lsa ham to'xtamaydi: g'oya - tayyor mavzular navbati, kod - Ali'ning o'z animatsiya shabloni.
Har qadam «Ali jamoasi» guruhidagi agent mavzusiga yoziladi (Ali nazorat qiladi).
"""
import html as html_lib
import json
import logging
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from .config import config

log = logging.getLogger("ali.daily_video")

TIMES = ("11:00", "16:00")
LATE = 3 * 3600  # vaqtidan 3 soatdan ko'p o'tib ketgan bo'lsa (kompyuter o'chiq edi) - o'tkazib yuboriladi
STATE = config.data_dir / "daily_video.json"
DURATION, FPS = 15, 30
_lock = threading.Lock()

IDEA = """{agent}

Sen Kontent-meykersan. Planet Print (tashqi reklama: pilon, lightbox, hajmli harflar, banner, vizitka; Beshariq) uchun
bugungi {slot} Reels'ining g'oyasini tuz. {topic} Video - animatsiyali matn va grafika (motion design), {dur} soniya, ovozsiz
(musiqa bilan). Tomoshabin 1-2 soniyada to'xtashi, oxirigacha ko'rishi va direktga yozishi kerak.
Haftalik Instagram audit xulosasi (shunga tayan):
{audit}
Oldingi videolar (TAKRORLAMA): {previous}
FAQAT JSON: {{"title": "...", "hook": "1-sahna - 3-6 so'z, kuchli", "scenes": [{{"big": "3-6 so'z", "small": "qo'shimcha 0-8 so'z"}}],
"cta": "direktga chaqiruv", "caption": "Instagram matni", "hashtags": "#...", "mood": "energetic|cinematic|calm",
"why": "nega bu Instagram'da ishlaydi (1 gap)"}}  (scenes: 4-5 ta, hook birinchisi)"""

CODE = """{agent}

Sen Dasturchisan. Video montajchi uchun {dur} soniyalik vertikal motion-grafika ANIMATSIYA KODINI yoz - bitta HTML fayl.
Sahnalar (tartib bilan, teng vaqt): {scenes}
CTA (oxirgi sahna): {cta}
QOIDALAR (buzilsa video chiqmaydi):
- <body> aniq 1080x1920 px, margin 0, overflow hidden; fon to'q (qora/ko'k), Planet Print uslubi: neon sariq/to'q sariq nur.
- FAQAT CSS @keyframes animatsiyalar (animation-delay bilan sahnalarni almashtir), animation-fill-mode: both.
  JavaScript, setTimeout, tashqi shrift/rasm/URL ISHLATMA (internet yo'q). Shrift: Arial Black, Arial, sans-serif.
- Matn katta (asosiy 90-130px, kichik 48-60px), o'qiladigan; chetdan 110px ichkarida, 1500px dan pastga matn qo'yma (Reels tugmalari).
- Har sahna: kirish (pastdan uchib chiqish / zoom / glow), 1-2 s turadi, chiqish. Fonda sekin harakatlanuvchi nur/chiziqlar.
- Jami davomiylik aniq {dur} s; oxirgi sahna (CTA) oxirigacha ko'rinib turadi.
FAQAT JSON: {{"html": "<!doctype html>..."}}"""

# AI'lar band bo'lganda - Kontent-meyker o'z bilimidan navbat bilan oladi
IDEAS = [
    {"title": "Pilon kechasi", "hook": "TUNDA HAM KUNDUZDEK", "scenes": [{"big": "PILON", "small": "kechasi 1 km dan ko'rinadi"},
     {"big": "LED + AKRIL", "small": "yillab o'chmaydi"}, {"big": "MIJOZ OQIMI", "small": "yo'ldan to'g'ri kirib keladi"}],
     "cta": "Narxini bilish uchun direktga yozing", "mood": "energetic"},
    {"title": "Hajmli harflar", "hook": "DO'KONINGIZ KO'RINMAYAPTIMI?", "scenes": [{"big": "HAJMLI HARFLAR", "small": "brendingiz uzoqdan o'qiladi"},
     {"big": "3 KUNDA", "small": "o'lchovdan o'rnatishgacha"}, {"big": "KAFOLAT", "small": "yomg'ir va qorga chidamli"}],
     "cta": "Bepul o'lchov - direktga yozing", "mood": "energetic"},
    {"title": "Lightbox", "hook": "KECHQURUN SAVDO TUSHADIMI?", "scenes": [{"big": "LIGHTBOX", "small": "yorug' vitrina - ko'proq mijoz"},
     {"big": "TEJAMKOR LED", "small": "oyiga bir necha ming so'm tok"}, {"big": "ISTALGAN O'LCHAM", "small": "dizayn bepul"}],
     "cta": "Dizaynni bepul tayyorlaymiz - yozing", "mood": "cinematic"},
    {"title": "Banner", "hook": "AKSIYANGIZNI HAMMA KO'RSIN", "scenes": [{"big": "BANNER", "small": "1 kunda tayyor"},
     {"big": "YORQIN RANG", "small": "quyoshda o'chmaydi"}, {"big": "ISTALGAN HAJM", "small": "kichikdan 10 metrgacha"}],
     "cta": "Hoziroq buyurtma bering - direkt", "mood": "energetic"},
    {"title": "Reklama nega kerak", "hook": "MIJOZ SIZNI TOPA OLMAYAPTI", "scenes": [{"big": "1-TAASSUROT", "small": "mijoz avval peshlavhani ko'radi"},
     {"big": "ISHONCH", "small": "chiroyli belgi - ishonchli do'kon"}, {"big": "PLANET PRINT", "small": "Beshariq - tashqi reklama"}],
     "cta": "Maslahat bepul - direktga yozing", "mood": "cinematic"},
]


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"done": {}, "history": []}


def _save(st: dict) -> None:
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def _agent(key: str) -> str:
    try:
        from .service import agent_system, brain
        a = brain.agents.get(key)
        return agent_system(a) if a else ""
    except Exception:
        return ""


def _ready() -> list[str]:
    from . import local_ai
    return local_ai.connected() if local_ai.access() is True else []


def idea(slot: str, topic: str = "") -> tuple[dict, str]:
    """Kontent-meyker g'oyasi: (g'oya, manba)."""
    from .memory import memory
    from .service import _ask_json
    st = _state()
    previous = "; ".join(h["title"] for h in st.get("history", [])[-12:]) or "-"
    audit = "\n".join(r["content"][:1500] for r in memory.relevant_knowledge("instagram haftalik audit video", "[kontent]", 2))
    try:
        got = _ask_json(IDEA.format(agent=_agent("kontent")[:5000], slot=slot, dur=DURATION, audit=audit or "-",
                                    topic=f"Egam bergan mavzu: {topic}" if topic else "",
                                    previous=previous), _ready(), 240)
        scenes = [s for s in got.get("scenes", []) if isinstance(s, dict) and s.get("big")][:5]
        if len(scenes) >= 3:
            return {**got, "scenes": scenes}, "AI"
    except Exception as e:
        log.info("Kontent g'oyasi AI'siz: %s", e)
    used = {h["title"] for h in st.get("history", [])[-len(IDEAS) + 1:]}
    pick = next((i for i in IDEAS if i["title"] not in used), IDEAS[len(st.get("history", [])) % len(IDEAS)])
    return {**pick, "scenes": [{"big": pick["hook"], "small": ""}, *pick["scenes"]],
            "caption": f"{pick['title']} - Planet Print. {pick['cta']}.",
            "hashtags": "#planetprint #tashqireklama #reklama #beshariq #reels"}, "bilim"


def template(data: dict, dur: float = DURATION) -> str:
    """Ali'ning o'z animatsiya kodi (AI'siz): har sahna pastdan uchib chiqadi, neon nur, oxirida CTA."""
    scenes = [*data["scenes"], {"big": data.get("cta", "Direktga yozing"), "small": "PLANET PRINT"}]
    step = dur / len(scenes)
    blocks, css = [], []
    for k, s in enumerate(scenes):
        last = k == len(scenes) - 1
        anim = "inlast" if last else "scene"
        blocks.append(f'<div class="s" style="animation: {anim} {step:.2f}s {k * step:.2f}s both '
                      f'cubic-bezier(.2,.8,.2,1)"><div class="big">{html_lib.escape(s["big"])}</div>'
                      f'<div class="small">{html_lib.escape(s.get("small", ""))}</div></div>')
    css.append("@keyframes scene{0%{opacity:0;transform:translateY(160px) scale(.9)}12%{opacity:1;transform:none}"
               "82%{opacity:1;transform:none}100%{opacity:0;transform:translateY(-120px) scale(1.05)}}"
               "@keyframes inlast{0%{opacity:0;transform:scale(.6)}25%{opacity:1;transform:scale(1.04)}"
               "35%,100%{opacity:1;transform:scale(1)}}"
               "@keyframes sweep{0%{transform:translateX(-120%) rotate(-25deg)}100%{transform:translateX(220%) rotate(-25deg)}}"
               "@keyframes glow{0%,100%{text-shadow:0 0 18px #ffb300,0 0 48px #ff6d00}50%{text-shadow:0 0 30px #ffd54f,0 0 90px #ff6d00}}"
               "@keyframes bar{from{width:0}to{width:100%}}")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:1080px;height:1920px;overflow:hidden;background:radial-gradient(circle at 50% 35%,#1b2340,#05060c 70%);
font-family:'Arial Black',Arial,sans-serif;color:#fff}}
.beam{{position:absolute;top:-20%;left:0;width:260px;height:140%;background:linear-gradient(90deg,transparent,rgba(255,179,0,.22),transparent);
animation:sweep 5s linear infinite both}}
.beam.b2{{animation-duration:7s;animation-delay:-3s;opacity:.6}}
.s{{position:absolute;left:110px;right:110px;top:520px;height:900px;display:flex;flex-direction:column;justify-content:center;
align-items:center;text-align:center;opacity:0}}
.big{{font-size:118px;line-height:1.05;color:#ffd54f;text-transform:uppercase;animation:glow 2s ease-in-out infinite both;
word-break:break-word}}
.small{{margin-top:44px;font-family:Arial,sans-serif;font-weight:700;font-size:56px;line-height:1.2;color:#fff}}
.brand{{position:absolute;top:150px;left:0;right:0;text-align:center;font-size:44px;letter-spacing:12px;color:#ffb300}}
.bar{{position:absolute;left:0;bottom:0;height:12px;background:#ffb300;animation:bar {dur:.2f}s linear both}}
{''.join(css)}
</style></head><body><div class="beam"></div><div class="beam b2"></div><div class="brand">PLANET PRINT</div>
{''.join(blocks)}<div class="bar"></div></body></html>"""


def code(data: dict) -> tuple[str, str]:
    """Dasturchi animatsiya kodi: (html, manba). AI kodi yaroqsiz bo'lsa - Ali shabloni."""
    from .service import _ask_json
    scenes = " | ".join(f"{s['big']} — {s.get('small', '')}" for s in data["scenes"])
    try:
        got = _ask_json(CODE.format(agent=_agent("dasturchi")[:4000], dur=DURATION, scenes=scenes,
                                    cta=data.get("cta", "")), _ready(), 300)
        page = str(got.get("html", ""))
        if "@keyframes" in page and "<body" in page.lower() and "http" not in page.lower().replace("http-equiv", ""):
            return page, "AI"
    except Exception as e:
        log.info("Animatsiya kodi AI'siz: %s", e)
    return template(data), "shablon"


SEEK = """t => { const all = document.getAnimations(); all.forEach(a => { a.pause(); a.currentTime = t; }); return all.length; }"""


def render(page: str, out: Path, dur: float = DURATION, fps: int = FPS) -> Path:
    """HTML animatsiyani kadrma-kadr (har kadrda vaqt aniq o'rnatiladi - sakrashsiz) videoga aylantiradi."""
    from playwright.sync_api import sync_playwright

    from .browser import CHROME
    from .skills.video_edit import _run
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=CHROME if Path(CHROME).exists() else None)
        try:
            tab = browser.new_page(viewport={"width": 1080, "height": 1920})
            tab.set_content(page, wait_until="load")
            if not tab.evaluate(SEEK, 0):
                raise RuntimeError("Kodda animatsiya yo'q")
            for n in range(int(dur * fps)):
                tab.evaluate(SEEK, n * 1000 / fps)
                tab.screenshot(path=str(Path(tmp) / f"f{n:05d}.jpg"), type="jpeg", quality=92)
        finally:
            browser.close()
        _run(["-framerate", str(fps), "-i", str(Path(tmp) / "f%05d.jpg"), "-c:v", "libx264", "-preset", "medium",
              "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(fps), str(out)])
    return out


def make(slot: str, notify=lambda text: None, topic: str = "") -> dict:
    """Bitta video: g'oya -> kod -> render -> musiqa. {path, idea, sources}."""
    from . import outbox, team_hub
    from .skills.music import for_video
    from .skills.video_pro import video_pro
    data, idea_src = idea(slot, topic)
    team_hub.feed("kontent", f"{slot} Reels g'oyasi", f"🎬 {data.get('title', '')}\n🪝 {data.get('hook', '')}\n"
                  + "\n".join(f"• {s['big']} — {s.get('small', '')}" for s in data["scenes"])
                  + f"\n📣 {data.get('cta', '')}\n💡 {data.get('why', '')}\n(manba: {idea_src})")
    page, code_src = code(data)
    team_hub.feed("dasturchi", f"{slot} Reels animatsiya kodi", f"HTML animatsiya: {len(page) // 1024 + 1} KB ({code_src})")
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "anim.mp4"
        try:
            render(page, raw)
        except Exception as e:  # AI kodi ishlamadi - Ali shabloni bilan qayta
            if code_src == "shablon":
                raise
            log.warning("AI animatsiyasi render bo'lmadi (%s) - shablon", e)
            page, code_src = template(data), "shablon"
            render(page, raw)
        music, music_src = for_video(DURATION + 2, data.get("mood") if data.get("mood") in ("energetic", "cinematic", "calm")
                                     else "energetic")
        start = outbox.mark()
        video_pro(str(raw), music=music, cut_silence=False, subtitles=False, progress_bar=False)
        made = [f for f in outbox.since(start) if f.suffix == ".mp4"]
    if not made:
        raise RuntimeError("Video chiqmadi")
    sources = f"g'oya: {idea_src}, kod: {code_src}, musiqa: {music_src}"
    team_hub.feed("video_montajchi", f"{slot} Reels montaji", f"✅ {made[-1].name} ({DURATION} s, 1080x1920, {sources})")
    return {"path": str(made[-1]), "idea": data, "sources": sources}


def run(slot: str, notify) -> None:
    """Videoni yasaydi va kanalga (yuborilmasa - navbatga) hamda egasiga yuboradi."""
    from . import studio_flow, tg_account
    if not _lock.acquire(blocking=False):
        return
    try:
        res = make(slot, notify)
    except Exception as e:
        log.exception("Kunlik video yasalmadi")
        notify(f"⚠️ {slot} kunlik video yasalmadi: {str(e)[:300]}")
        return
    finally:
        _lock.release()
    data = res["idea"]
    text = f"{data.get('caption', '')}\n\n{data.get('hashtags', '')}".strip()
    st = studio_flow._state()
    try:
        pid = tg_account.send_file(studio_flow.CHANNEL, res["path"], f"{text}\n\n{studio_flow.MARK}"[:1024])
        st.setdefault("posted", []).append(pid)
    except Exception as e:  # internet yo'q - kanal kuzatuvi keyin o'zi joylaydi
        log.info("Kunlik video kanalga hozir joylanmadi: %s", e)
        st.setdefault("pending_post", []).append({"out": res["path"], "caption": text, "src": None})
    studio_flow._save(st)
    studio_flow.send_files(f"🎬 {slot} kunlik Reels tayyor: «{data.get('title', '')}»\n🪝 {data.get('hook', '')}\n"
                           f"💡 {data.get('why', '')}\n({res['sources']})\n\n{text}", [res["path"]])
    hist = _state()
    hist.setdefault("history", []).append({"title": data.get("title", ""), "at": datetime.now().isoformat(timespec="minutes")})
    hist["history"] = hist["history"][-60:]
    _save(hist)


def tick(notify, now: datetime | None = None) -> None:
    """Kontent reja tsiklidan (har 30 s): 11:00 va 16:00 da bir martadan (qayta yoqilganda takrorlanmaydi)."""
    now = now or datetime.now()
    st = _state()
    for slot in TIMES:
        h, m = map(int, slot.split(":"))
        at = now.replace(hour=h, minute=m, second=0, microsecond=0)
        key = f"{now.date().isoformat()} {slot}"
        if at <= now and key not in st.get("done", {}):
            st.setdefault("done", {})[key] = (now - at).total_seconds() <= LATE
            st["done"] = dict(list(st["done"].items())[-20:])
            _save(st)
            if st["done"][key]:
                threading.Thread(target=run, args=(slot, notify), daemon=True, name="daily-video").start()
