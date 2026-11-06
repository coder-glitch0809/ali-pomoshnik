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
import re
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
bugungi {slot} Reels'ining g'oyasini tuz. {topic} Video - animatsiyali matn va grafika (motion design), {dur}-30 soniya (videoda aniq soniyani yozma);
ekranda Planet Print personaji (3D multfilm qahramon) bor va u matnni ovoz chiqarib aytadi, ostida musiqa. Tomoshabin 1-2 soniyada to'xtashi, oxirigacha ko'rishi va direktga yozishi kerak.
Haftalik Instagram audit xulosasi (shunga tayan):
{audit}
Oldingi videolar (TAKRORLAMA): {previous}
FAQAT JSON: {{"title": "...", "hook": "1-sahna - 3-6 so'z, kuchli", "scenes": [{{"big": "3-6 so'z", "small": "qo'shimcha 0-8 so'z",
"visual": "sahna belgisi - mazmuniga mos, FAQAT shulardan biri: {visuals}",
"backdrop": "sahna foni: street (ko'cha, do'konlar, peshlavha) | night (tungi shahar, chiroq) | dash (raqamli reklama, tahlil)",
"diagram": {{"type": "FAQAT biri: {diagrams}", "title": "diagramma sarlavhasi 2-5 so'z", "labels": ["2-3 ta yozuv, har biri 1-2 so'z, SONSIZ"]}}}}],
"cta": "direktga chaqiruv", "caption": "Instagram matni", "hashtags": "#...", "mood": "energetic|cinematic|calm",
"why": "nega bu Instagram'da ishlaydi (1 gap)",
"voice": "personaj OVOZ chiqarib aytadigan matn: 30-40 so'z, sodda o'zbek tilida, foydali maslahat, sahnalar tartibida, oxirida CTA"}}
(scenes: 4-5 ta, hook birinchisi. Diagrammada to'qima son/foiz YOZMA - faqat g'oyani ko'rsatsin)"""

CODE = """{agent}

Sen Dasturchisan. Video montajchi uchun {dur} soniyalik vertikal motion-grafika ANIMATSIYA KODINI yoz - bitta HTML fayl.
Sahnalar - AYNAN shu vaqtlarda ko'rinsin (animation-delay = boshlanish, har lahzada ekranda bitta sahna matni bo'lsin): {scenes}
CTA (oxirgi sahna): {cta}
QOIDALAR (buzilsa video chiqmaydi):
- <body> aniq 1080x1920 px, margin 0, overflow hidden; fon to'q (qora/ko'k), Planet Print uslubi: neon sariq/to'q sariq nur.
- FAQAT CSS @keyframes animatsiyalar (animation-delay bilan sahnalarni almashtir), animation-fill-mode: both.
  JavaScript, setTimeout, tashqi shrift/rasm/URL ISHLATMA (internet yo'q). Shrift: Arial Black, Arial, sans-serif.
- Matn katta (asosiy 90-130px, kichik 48-60px), o'qiladigan; chetdan 110px ichkarida, 1500px dan pastga matn qo'yma (Reels tugmalari).
- Har sahna: kirish (pastdan uchib chiqish / zoom / glow), 1-2 s turadi, chiqish. Fonda sekin harakatlanuvchi nur/chiziqlar.
- Jami davomiylik aniq {dur} s; oxirgi sahna (CTA) oxirigacha ko'rinib turadi.
{extra}
FAQAT JSON: {{"html": "<!doctype html>..."}}"""

CHARACTERS = """- PERSONAJLAR so'ralgan: inline <svg> bilan 1-2 ta multfilm personaj chiz (masalan: kaskali usta - Planet Print
  ustasi, do'kon egasi - mijoz): bosh, ko'z, og'iz, tana, qo'llar alohida <g> guruhlar; CSS bilan jonlantir - ko'z qisish,
  qo'l silkitish, yurib kirish, sakrash, gapirganda og'iz ochilishi. Sahnalar matni personaj yonida nutq pufagi (speech
  bubble) yoki tepasida katta yozuv bo'lsin. Personajlar 1500px dan pastga tushmasin; ranglar yorqin, kontur qalin."""
PERSONA = re.compile(r"personaj|персонаж|qahramon|қаҳрамон|multfilm|мультфильм|cartoon|mascot|maskot", re.I)

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


CHAR_DIR = config.data_dir / "characters"
CHAR_SAVE = re.compile(r"personaj|персонаж|yuzni\s+eslab|юзни\s+эслаб|qahramon|қаҳрамон|maskot|маскот", re.I)


def character() -> Path | None:
    """Egam bergan personaj rasmi (eng oxirgisi) - videolarda shu qahramon gapiradi."""
    files = sorted((f for f in CHAR_DIR.glob("*") if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
                    and not f.stem.endswith("_cut")),
                   key=lambda f: f.stat().st_mtime) if CHAR_DIR.is_dir() else []
    return files[-1] if files else None


def save_character(path: str) -> Path:
    CHAR_DIR.mkdir(parents=True, exist_ok=True)
    for old in CHAR_DIR.glob("personaj*"):  # yangi qahramon - eski rasm, fonsiz nusxa va og'iz koordinatalari o'chadi
        old.unlink()
    dest = CHAR_DIR / f"personaj{Path(path).suffix.lower() or '.jpg'}"
    dest.write_bytes(Path(path).read_bytes())
    return dest


def _data_uri(path: Path) -> str:
    import base64
    mime = {".png": "image/png", ".webp": "image/webp"}.get(path.suffix.lower(), "image/jpeg")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


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
    if topic:  # Kontent-meyker o'z bilimiga ham tayanadi
        from .service import knowledge_block
        audit += knowledge_block(topic, "kontent")[:4000]
    try:
        from .skills.motion_bg import KEYS
        from .skills.stage import KINDS
        got = _ask_json(IDEA.format(agent=_agent("kontent")[:5000], slot=slot, dur=DURATION, audit=audit or "-", visuals=KEYS,
                                    diagrams=KINDS,
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


HERO_CSS = """.s{{top:230px;height:620px}}.big{{font-size:96px}}.small{{font-size:50px;margin-top:28px}}
.hero{{position:absolute;left:150px;width:780px;height:975px;top:880px;object-fit:cover;border-radius:60px;
box-shadow:0 0 0 8px #ffb300,0 0 90px rgba(255,140,0,.55);animation:heroin .9s cubic-bezier(.2,.8,.2,1) both,
talk .32s ease-in-out .9s infinite alternate}}
@keyframes heroin{{0%{{opacity:0;transform:translateY(300px) scale(.85)}}100%{{opacity:1;transform:none}}}}
@keyframes talk{{0%{{transform:scale(1) rotate(-.4deg)}}100%{{transform:scale(1.018) rotate(.4deg) translateY(-6px)}}}}"""


TALK_CSS = """.s{top:190px;height:640px}.big{font-size:92px;text-shadow:0 0 18px #ffb300,0 6px 30px #000}
.small{font-size:48px;margin-top:26px;text-shadow:0 4px 18px #000}
.hero{transform-origin:50% 100%;animation:heroin .9s cubic-bezier(.2,.8,.2,1) both,sway 3.4s ease-in-out .9s infinite alternate both}
@keyframes heroin{0%{opacity:0;transform:translateY(400px)}100%{opacity:1;transform:none}}
@keyframes sway{0%{transform:rotate(-.8deg) translateY(0)}50%{transform:rotate(.3deg) translateY(-8px)}100%{transform:rotate(.9deg) translateY(-2px)}}"""


def template(data: dict, dur: float = DURATION, hero: str | dict = "") -> str:
    """Ali'ning o'z animatsiya kodi (AI'siz): har sahna pastdan uchib chiqadi, neon nur, oxirida CTA.
    hero - personaj: rasm (data URI - kartochkada tebranadi) yoki talking_head.build() natijasi (fonsiz, og'zi ovozga mos
    gapiradi, orqasida sahna mavzusidagi motion-grafika)."""
    scenes = [*data["scenes"], {"big": data.get("cta", "Direktga yozing"), "small": "PLANET PRINT"}]
    if isinstance(hero, dict) and "torso" in hero:  # boshlovchi: bosh, gavda, qo'llar alohida; fon va diagrammalar mavzuga mos
        from .skills import presenter, stage
        back, desk, css = stage.layer(scenes, dur / len(scenes), dur)
        return _base(scenes, dur, css, back + presenter.html(hero) + desk)
    if isinstance(hero, dict):
        from .skills import motion_bg, talking_head
        mg_html, mg_css = motion_bg.layer(scenes, dur / len(scenes), dur)
        face = talking_head.html(hero, (1080 - hero["w"]) / 2, 1920 - hero["h"])
        return _base(scenes, dur, mg_css + TALK_CSS, mg_html + face)
    return _base(scenes, dur, HERO_CSS.format() if hero else "", f'<img class="hero" src="{hero}">' if hero else "")


def _base(scenes: list[dict], dur: float, extra_css: str, extra_html: str) -> str:
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
{extra_css}
</style></head><body><div class="beam"></div><div class="beam b2"></div><div class="brand">PLANET PRINT</div>
{extra_html}{''.join(blocks)}<div class="bar"></div></body></html>"""


def _offline(page: str) -> bool:
    """Kodda tashqi manzil yo'q (SVG nomlar fazosi www.w3.org - manzil emas, ruxsat)."""
    low = re.sub(r"http://www\.w3\.org/[\w/.-]*", "", page.lower()).replace("http-equiv", "")
    return "http" not in low


HERO_RULE = """- PERSONAJ RASMI bor (egamning 3D qahramoni, portret 4:5): <img class="hero" src="HERO_IMAGE"> - src AYNAN «HERO_IMAGE»
  bo'lsin (Ali o'zi rasmga almashtiradi). Pastki yarmida katta (eni ~780px, top ~880px, 1850px dan oshmasin), yumaloq
  burchak, neon sariq hoshiya; kirishda pastdan chiqadi, keyin butun video davomida «gapirayotgandek» yengil tebranadi
  (scale 1-1.02, 0.3 s, alternate). Matn sahnalari TEPADA (230-850px), personaj bilan ustma-ust tushmasin."""


def code(data: dict, topic: str = "", dur: float = DURATION, hero: str = "") -> tuple[str, str]:
    """Dasturchi animatsiya kodi: (html, manba). AI kodi yaroqsiz bo'lsa - Ali shabloni. hero - personaj (data URI)."""
    from .service import _ask_json
    step = dur / (len(data["scenes"]) + 1)  # +1 - oxirgi CTA sahnasi
    scenes = " | ".join(f"{k + 1}) {k * step:.1f}-{(k + 1) * step:.1f} s: {s['big']} — {s.get('small', '')}"
                        for k, s in enumerate(data["scenes"])) + f" | CTA: {len(data['scenes']) * step:.1f}-{dur:.0f} s"
    extra = "\n".join(filter(None, [CHARACTERS if PERSONA.search(topic) and not hero else "", HERO_RULE if hero else ""]))
    try:
        got = _ask_json(CODE.format(agent=_agent("dasturchi")[:4000], dur=round(dur), scenes=scenes, cta=data.get("cta", ""),
                                    extra=extra), _ready(), 420)
        page = str(got.get("html", ""))
        if "@keyframes" in page and "<body" in page.lower() and _offline(page) and (not hero or "HERO_IMAGE" in page):
            return page.replace("HERO_IMAGE", hero), "AI"
    except Exception as e:
        log.info("Animatsiya kodi AI'siz: %s", e)
    return template(data, dur, hero), "shablon"


SEEK = """t => { const all = document.getAnimations(); all.forEach(a => { a.pause(); a.currentTime = t; }); return all.length; }"""


VISIBLE_TEXT = """() => { const out = [];
  document.querySelectorAll('body *').forEach(e => {
    if (![...e.childNodes].some(c => c.nodeType === 3 && c.textContent.trim().length > 1)) return;
    let o = 1;
    for (let x = e; x && x.nodeType === 1; x = x.parentElement) {
      const cs = getComputedStyle(x); o *= parseFloat(cs.opacity);
      if (cs.visibility === 'hidden' || cs.display === 'none') o = 0; }
    const r = e.getBoundingClientRect();
    if (o > 0.3 && r.width > 0 && r.bottom > 0 && r.top < 1920 && r.right > 0 && r.left < 1080) out.push(e.textContent.trim());
  }); return out; }"""


def _check_text(tab, dur: float, samples: int = 10) -> None:
    """Video bo'ylab ekranda sahna matni bo'lishi shart (doim turadigan «PLANET PRINT» kabi yozuvlar hisobga olinmaydi).
    Bo'sh oraliq bo'lsa - AI kodi rad etiladi, Ali shabloni ishlatiladi."""
    seen = []
    for k in range(samples):
        tab.evaluate(SEEK, (0.6 + k * (dur - 1.0) / (samples - 1)) * 1000)
        seen.append(set(tab.evaluate(VISIBLE_TEXT)))
    always = set.intersection(*seen) if seen else set()
    empty = sum(1 for texts in seen if not texts - always)
    if empty > 1:
        raise RuntimeError(f"Animatsiyada {empty}/{samples} lahzada matn yo'q (sahnalar vaqti noto'g'ri)")


FACE = """([t, m, b]) => { document.getAnimations().forEach(a => { a.pause(); a.currentTime = t; });
  if (window.__rig) window.__rig(m); else if (window.__face) window.__face(m, b); }"""


def render(page: str, out: Path, dur: float = DURATION, fps: int = FPS, face: list | None = None) -> Path:
    """HTML animatsiyani kadrma-kadr (har kadrda vaqt aniq o'rnatiladi - sakrashsiz) videoga aylantiradi.
    face - har kadr uchun (og'iz ochilishi, ko'z yumilgan) - personaj ovozga mos gapiradi."""
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
            _check_text(tab, dur)
            for n in range(int(dur * fps)):
                if face:
                    state = face[n] if n < len(face) else face[-1]
                    tab.evaluate(FACE, [n * 1000 / fps, state, False] if isinstance(state, dict)
                                 else [n * 1000 / fps, *state])
                else:
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
    hero_file = character()
    with tempfile.TemporaryDirectory() as tmp:
        voice, dur = _voice(data, Path(tmp)) if hero_file else (None, DURATION)  # personaj bor - u matnni ovozda aytadi
        hero, face = "", None
        if hero_file:  # fonsiz qahramon, og'zi ovozga mos ochiladi, ko'z qisadi; orqasida mavzu motion-grafikasi
            from .skills import presenter, talking_head
            try:
                rig = presenter.build(hero_file) if voice else None
                if rig:
                    hero = rig
                    face = presenter.frames(len(data["scenes"]) + 1, dur / (len(data["scenes"]) + 1), dur, FPS,
                                            talking_head.levels(voice, dur, FPS), talking_head.blinks(dur, FPS))
                else:
                    hero = talking_head.build(hero_file, 900)
                    if voice and hero["mouths"]:
                        face = list(zip(talking_head.levels(voice, dur, FPS), talking_head.blinks(dur, FPS)))
            except Exception as e:
                log.warning("Personaj jonlantirilmadi (%s) - oddiy rasm", e)
                hero = _data_uri(hero_file)
        # personajli video - Ali shabloni (matn har lahzada aniq ko'rinadi; AI kodi personaj bilan matnni xiralashtirib
        # qo'yardi), personajsiz - Dasturchi AI kodi (tekshiruv bilan)
        page, code_src = (template(data, dur, hero), "shablon + boshlovchi personaj (qo'llar) + diagrammalar"
                          if face else "shablon + personaj") if hero else code(data, topic, dur)
        team_hub.feed("dasturchi", f"{slot} Reels animatsiya kodi", f"HTML animatsiya: {len(page) // 1024 + 1} KB ({code_src})")
        raw = Path(tmp) / "anim.mp4"
        try:
            render(page, raw, dur, face=face)
        except Exception as e:  # AI kodi ishlamadi - Ali shabloni bilan qayta
            if code_src.startswith("shablon"):
                raise
            log.warning("AI animatsiyasi render bo'lmadi (%s) - shablon", e)
            page, code_src = template(data, dur, hero), "shablon"
            render(page, raw, dur)
        if voice:  # personaj ovozi videoga (video ovozdan uzunroq - oxirida jimlik bilan to'ldiriladi)
            from .skills.video_edit import _run
            spoken = Path(tmp) / "spoken.mp4"
            # apad aniq video uzunligigacha (cheksiz apad + -shortest + copy - ffmpeg hech qachon tugamasdi)
            _run(["-i", str(raw), "-i", str(voice), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                  "-af", f"apad=whole_dur={dur:.2f}", "-t", f"{dur:.2f}", "-c:a", "aac", "-ar", "48000", str(spoken)])
            raw = spoken
        music, music_src = for_video(dur + 2, data.get("mood") if data.get("mood") in ("energetic", "cinematic", "calm")
                                     else "energetic")
        start = outbox.mark()
        video_pro(str(raw), music=music, cut_silence=False, subtitles=False, progress_bar=False)
        made = [f for f in outbox.since(start) if f.suffix == ".mp4"]
    if not made:
        raise RuntimeError("Video chiqmadi")
    sources = (f"g'oya: {idea_src}, kod: {code_src}, musiqa: {music_src}"
               + (", personaj gapiradi" if voice else ""))
    team_hub.feed("video_montajchi", f"{slot} Reels montaji", f"✅ {made[-1].name} ({dur:.0f} s, 1080x1920, {sources})")
    return {"path": str(made[-1]), "idea": data, "sources": sources}


def _voice(data: dict, tmp: Path) -> tuple[Path | None, float]:
    """Personaj matni o'zbekcha ovozda (raqamlar so'z bilan). (mp3, video davomiyligi) - ovozga moslanadi, 15-45 s."""
    import asyncio

    from . import tts
    from .skills.video_edit import info
    text = str(data.get("voice") or "").strip() or ". ".join(
        f"{s['big']}. {s.get('small', '')}".strip(". ") for s in data["scenes"]) + f". {data.get('cta', '')}"
    try:
        audio = asyncio.run(tts.synthesize(text))
    except Exception as e:
        log.warning("Personaj ovozi yaratilmadi: %s", e)
        return None, DURATION
    path = tmp / "voice.mp3"
    path.write_bytes(audio)
    length = info(path)["duration"]
    return path, max(DURATION, min(45.0, length + 1.5))


def run(slot: str, notify, topic: str = "") -> None:
    """Videoni yasaydi va kanalga (yuborilmasa - navbatga) hamda egasiga yuboradi.
    topic - egam bergan mavzu: u o'zi kanalga so'ragan - kengash bahosi qanday bo'lsa ham joylanadi (baho hisobotda)."""
    from . import studio_flow, tg_account
    if not _lock.acquire(blocking=False):
        return
    try:
        res = make(slot, notify, topic)
    except Exception as e:
        log.exception("Kunlik video yasalmadi")
        notify(f"⚠️ {slot} kunlik video yasalmadi: {str(e)[:300]}")
        return
    finally:
        _lock.release()
    data = res["idea"]
    text = f"{data.get('caption', '')}\n\n{data.get('hashtags', '')}".strip()
    # Maslahat kengashi: video guruhga qo'yiladi, agentlar Instagram uchun baholaydi; 5 dan past - kanalga chiqmaydi
    from . import team_hub
    from .service import brain
    about = (f"«{data.get('title', '')}». Hook: {data.get('hook', '')}. Sahnalar: "
             + "; ".join(s["big"] for s in data["scenes"]) + f". CTA: {data.get('cta', '')}. {DURATION} s animatsiya, musiqa.")
    decision, score = team_hub.review_video(res["path"], about, brain.agents, _ready())
    verdict = f"\n\n🤝 Kengash bahosi: {score:g}/10" if score is not None else ""
    if score is not None and score < 5 and not topic:
        studio_flow.send_files(f"🚫 {slot} kunlik Reels kengashdan o'tmadi ({score:g}/10) - kanalga joylanmadi.\n\n"
                               f"{decision[-2500:]}", [res["path"]])
        return
    st = studio_flow._state()
    try:
        pid = tg_account.send_file(studio_flow.CHANNEL, res["path"], f"{text}\n\n{studio_flow.MARK}"[:1024])
        st.setdefault("posted", []).append(pid)
    except Exception as e:  # internet yo'q - kanal kuzatuvi keyin o'zi joylaydi
        log.info("Kunlik video kanalga hozir joylanmadi: %s", e)
        st.setdefault("pending_post", []).append({"out": res["path"], "caption": text, "src": None})
    studio_flow._save(st)
    studio_flow.send_files(f"🎬 {slot} kunlik Reels tayyor: «{data.get('title', '')}»\n🪝 {data.get('hook', '')}\n"
                           f"💡 {data.get('why', '')}\n({res['sources']}){verdict}\n\n{text}", [res["path"]])
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
