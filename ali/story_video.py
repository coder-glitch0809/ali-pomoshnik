"""Hikoya Reels (egam bergan namunalar uslubida): har sahna - gapga mos ALOHIDA rasm, kamera harakati, turli o'tishlar,
personaj joyi almashadi (chapda, o'ngda, markazda, burchakda yoki umuman yo'q), pastda so'zma-so'z subtitr, boshida hook.

  1) Kontent-meyker ssenariy yozadi: har sahna - aytiladigan gap, ekrandagi qisqa yozuv, rasm tavsifi, joylashuv;
  2) har sahna ovozi alohida yoziladi - sahna aynan gap tugaganda almashadi;
  3) rasmlar: Gemini/ChatGPT (limit bo'lsa) -> bepul Pollinations -> Ali'ning chizilgan foni;
  4) render (Chrome, kadrma-kadr) -> ovoz -> egam videolaridan musiqa.
"""
import hashlib
import html as html_lib
import io
import logging
import math
import random
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .config import config

log = logging.getLogger("ali.story_video")

ART = config.data_dir / "scene_art"
FPS = 30
LAYOUTS = ("full", "host_left", "host_right", "host_center", "host_corner")
STYLE = ("3D Pixar-style cartoon illustration, cinematic lighting, rich colors with warm golden accents, vertical 9:16 "
         "composition, detailed environment, Central Asian (Uzbek) small town setting, no text, no letters, no logos, no watermark")

SCRIPT = """{agent}

Sen Kontent-meykersan. Planet Print (Beshariq: tashqi reklama - pilon, lightbox, hajmli harflar, banner; target reklama xizmati)
uchun Instagram Reels SSENARIYSINI yoz. {topic}
Namuna uslub: har 2-4 soniyada gapga mos YANGI rasm (joy, odamlar, buyumlar), hikoya qilib tushuntiradi, pastda subtitr.
Qoidalar:
- 1-sahna HOOK: 1-2 soniyada to'xtatadigan gap (savol, raqam, kutilmagan fakt yoki og'riq). «Assalomu alaykum» YO'Q.
- 7-10 sahna, jami 30-45 soniya. Har sahna «voice» - 1 gap, 6-14 so'z, sodda o'zbek tilida (raqamlarni so'z bilan yoz).
- Hikoya: muammo (aniq tadbirkor misoli) -> sabablar -> yechim -> natija -> CTA (oxirgi sahna, direktga yozishga chaqiradi).
- «image» - INGLIZCHA, aniq sahna: kim, qayerda, nima qilyapti, kayfiyat (masalan: "an Uzbek shop owner in his 40s looking
  sadly at his empty store at night, dark unreadable shop sign"). Bir hikoyadagi qahramon har sahnada bir xil tasvirlansin.
- «layout»: full (faqat rasm), host_left / host_right / host_center (boshlovchi personaj rasm oldida gapiradi),
  host_corner (personaj burchakda kichik). Ketma-ket ikki sahnada bir xil bo'lmasin, kamida 3 ta «full».
- «big» - ekrandagi 2-4 so'zli asosiy yozuv (hook sahnasida kuchli). To'qima statistika ishlatma.
Oldingi videolar (TAKRORLAMA): {previous}
FAQAT JSON: {{"title": "...", "hook": "...", "scenes": [{{"voice": "...", "big": "...", "image": "...", "layout": "full"}}],
"cta": "...", "caption": "Instagram matni", "hashtags": "#...", "mood": "energetic|cinematic|calm", "why": "1 gap"}}"""


def script(topic: str, previous: str, ready: list[str]) -> tuple[dict, str]:
    """Kontent-meyker ssenariysi: (ssenariy, manba). AI band bo'lsa - mavzu va bilimdan sodda ssenariy."""
    from .daily_video import _agent
    from .service import _ask_json
    try:
        got = _ask_json(SCRIPT.format(agent=_agent("kontent")[:4000], topic=f"Mavzu: {topic}" if topic else
                                      "Mavzuni o'zing tanla (target yoki tashqi reklama).", previous=previous or "-"), ready, 300)
        scenes = [s for s in got.get("scenes", []) if isinstance(s, dict) and str(s.get("voice", "")).strip()][:11]
        if len(scenes) >= 5:
            fix_layouts(scenes)
            return {**got, "scenes": scenes}, "AI"
    except Exception as e:
        log.info("Ssenariy AI'siz: %s", e)
    return fallback(topic), "bilim"


def fallback(topic: str) -> dict:
    """AI'siz: mavzu gaplaridan sahnalar, rasm tavsifi - umumiy hikoya sahnalari."""
    head = re.split(r"[:.\n]", topic or "Reklamangiz mijoz olib kelyaptimi?")[0].strip()[:70]
    parts = [p.strip(" -•") for p in re.split(r"[,;:\n]", topic or "")[1:] if 6 < len(p.strip()) < 90][:5]
    if len(parts) < 3:
        parts = ["Ko'pchilik bu xatoni bilmaydi", "Mijoz sizni ko'rmasa, sotuv ham bo'lmaydi",
                 "To'g'ri reklama bir oyda natija beradi"]
    pics = ["an Uzbek shop owner in his 40s worried, looking at an empty store",
            "a busy Uzbek street with many shops, people walking past one dark shop",
            "a smartphone screen showing an Instagram ad, a hand scrolling past it",
            "a bright illuminated shop sign at night attracting customers",
            "customers entering a cozy shop, the owner smiling",
            "a designer and a client planning an advertisement on a laptop"]
    scenes = [{"voice": head, "big": head[:30], "image": pics[0], "layout": "host_center"}]
    for k, p in enumerate(parts):
        scenes.append({"voice": p, "big": " ".join(p.split()[:3]), "image": pics[(k + 1) % len(pics)], "layout": "full"})
    scenes.append({"voice": "Batafsil bilish uchun direktga yozing", "big": "Direktga yozing", "image": pics[4], "layout": "host_right"})
    fix_layouts(scenes)
    return {"title": head, "hook": head, "scenes": scenes, "cta": "Direktga yozing", "mood": "energetic",
            "caption": f"{head} - Planet Print.", "hashtags": "#planetprint #reklama #target #reels", "why": "mavzu aniq"}


def fix_layouts(scenes: list[dict]) -> None:
    """Joylashuv: noma'lumi tuzatiladi, ketma-ket takror bo'lmaydi, kamida bitta «full» va bitta boshlovchili sahna."""
    prev = ""
    for k, s in enumerate(scenes):
        lay = s.get("layout") if s.get("layout") in LAYOUTS else ("host_center" if k == 0 else "full")
        if lay == prev:
            lay = "full" if prev != "full" else ("host_left", "host_right", "host_corner")[k % 3]
        s["layout"], prev = lay, lay
    if all(s["layout"] == "full" for s in scenes):
        scenes[0]["layout"] = "host_center"
    scenes[-1]["layout"] = "host_center" if scenes[-1]["layout"] == "full" else scenes[-1]["layout"]


# ---------- rasmlar ----------
def _pollinations(prompt: str, seed: int) -> bytes:
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt[:900])
           + f"?width=1080&height=1920&nologo=true&model=flux&seed={seed}")
    req = urllib.request.Request(url, headers={"User-Agent": "AliAssistant/1.0"})
    with urllib.request.urlopen(req, timeout=150) as r:
        data = r.read()
    if len(data) < 5000:
        raise RuntimeError("rasm kelmadi")
    return data


def _fit(data: bytes) -> bytes:
    """1080x1920 ga to'ldirib kesadi (pastdagi xizmat belgisi kesiladi)."""
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size
    im = im.crop((0, 0, w, int(h * .93)))  # bepul xizmat belgisi pastki o'ngda
    w, h = im.size
    scale = max(1080 / w, 1920 / h)
    im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    left, top = (im.width - 1080) // 2, (im.height - 1920) // 2
    buf = io.BytesIO()
    im.crop((left, top, left + 1080, top + 1920)).save(buf, "JPEG", quality=88)
    return buf.getvalue()


def image(prompt: str, seed: int = 7) -> tuple[Path | None, str]:
    """Sahna rasmi (kesh bilan): (fayl, manba). Hech biri ishlamasa (None, '')."""
    full = f"{prompt.strip()}. {STYLE}"
    ART.mkdir(parents=True, exist_ok=True)
    path = ART / (hashlib.sha1(f"{full}|{seed}".encode()).hexdigest()[:16] + ".jpg")
    if path.exists():
        return path, "kesh"
    from . import providers
    sources = []
    try:
        sources = providers.image_sources("standard")
    except Exception:
        pass
    for name, fn in sources:
        try:
            path.write_bytes(_fit(fn(full + " Vertical 9:16.")))
            return path, name
        except Exception as e:
            log.info("Rasm %s: %s", name, str(e)[:120])
    for attempt in range(5):
        try:
            path.write_bytes(_fit(_pollinations(full, seed)))
            return path, "Pollinations"
        except Exception as e:  # 402/429 - navbat band, biroz kutadi
            log.info("Pollinations (%s): %s", attempt + 1, e)
            time.sleep(6 * (attempt + 1))
    return None, ""


def images(scenes: list[dict], seed: int) -> list[tuple[Path | None, str]]:
    """Hamma sahna rasmlari parallel (3 tadan)."""
    out: list = [None] * len(scenes)
    sem = threading.Semaphore(1)  # bepul xizmat bir vaqtda bitta so'rov qabul qiladi

    def one(k):
        with sem:
            out[k] = image(str(scenes[k].get("image") or scenes[k].get("big") or "Uzbek small business street"), seed + k)
            time.sleep(1.5)
    threads = [threading.Thread(target=one, args=(k,), daemon=True) for k in range(len(scenes))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(400)
    return [o or (None, "") for o in out]


# ---------- ovoz: har sahna alohida (sahna gap bilan birga almashadi) ----------
def voices(scenes: list[dict], tmp: Path) -> tuple[Path, list[float]]:
    """(birlashtirilgan ovoz, sahnalar davomiyligi). Internet uzilsa qayta urinadi, bo'lmasa xato."""
    import asyncio

    from . import tts
    from .skills.video_edit import _run, info
    parts, lengths = [], []
    for k, s in enumerate(scenes):
        audio = None
        for attempt in range(4):
            try:
                audio = asyncio.run(tts.synthesize(str(s["voice"])))
                break
            except Exception as e:
                log.warning("Sahna ovozi (%s, %s-urinish): %s", k + 1, attempt + 1, e)
                time.sleep(15 * (attempt + 1))
        if not audio:
            raise RuntimeError("Ovoz yaratilmadi (internet?) - ovozsiz video chiqarilmadi")
        p = tmp / f"v{k:02d}.mp3"
        p.write_bytes(audio)
        wav = tmp / f"v{k:02d}.wav"
        _run(["-i", str(p), "-ar", "48000", "-ac", "1", "-af", "apad=pad_dur=0.25", str(wav)])
        parts.append(wav)
        lengths.append(info(wav)["duration"])
    listing = tmp / "list.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    out = tmp / "voice.wav"
    _run(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(out)])
    return out, lengths


# ---------- sahifa ----------
CSS = """html,body{margin:0;width:1080px;height:1920px;overflow:hidden;background:#05060c;font-family:'Arial Black',Arial,sans-serif}
.sc{position:absolute;left:0;top:0;width:1080px;height:1920px;overflow:hidden;opacity:0}
.sc img.bg{position:absolute;left:-6%;top:-6%;width:112%;height:112%;object-fit:cover}
.sc .dim{position:absolute;inset:0;background:linear-gradient(#05081488,transparent 28%,transparent 55%,#050814cc)}
.hook{position:absolute;left:60px;right:60px;top:210px;text-align:center;font-size:104px;line-height:1.02;color:#ffd54f;
text-transform:uppercase;text-shadow:0 0 30px #ff8f00,0 8px 24px #000;opacity:0}
.tag{position:absolute;left:50px;top:120px;max-width:760px;padding:16px 30px;border-radius:22px;background:#ffb300;color:#07102a;
font-size:46px;line-height:1.08;text-transform:uppercase;box-shadow:0 10px 30px #0008;opacity:0}
.sub{position:absolute;left:70px;right:70px;top:1215px;text-align:center;opacity:0}
.sub span{display:inline-block;margin:6px 4px;padding:8px 16px;border-radius:14px;background:#000000c4;color:#fff;
font:900 50px Arial,sans-serif}
.sub span.on{color:#ffd54f;background:#000000e6;transform:scale(1.08)}
.flash{position:absolute;inset:0;background:#fff;opacity:0;pointer-events:none}
.brand{position:absolute;right:40px;top:44px;font:900 30px 'Arial Black',Arial;letter-spacing:6px;color:#ffd54fcc;z-index:9}
.bar{position:absolute;left:0;bottom:0;height:10px;background:#ffb300;z-index:9}
.sc .bd{position:absolute;left:0;top:0;width:1080px;height:1920px;opacity:1!important;background:radial-gradient(circle at 50% 35%,#1b2340,#05060c 70%)}
"""

MOVES = ("kb_in", "kb_out", "kb_left", "kb_right", "kb_up")
KEYS = """@keyframes kb_in{from{transform:scale(1)}to{transform:scale(1.16)}}
@keyframes kb_out{from{transform:scale(1.18)}to{transform:scale(1.02)}}
@keyframes kb_left{from{transform:scale(1.12) translateX(40px)}to{transform:scale(1.12) translateX(-40px)}}
@keyframes kb_right{from{transform:scale(1.12) translateX(-40px)}to{transform:scale(1.12) translateX(40px)}}
@keyframes kb_up{from{transform:scale(1.14) translateY(40px)}to{transform:scale(1.14) translateY(-40px)}}
@keyframes t_fade{0%{opacity:0}100%{opacity:1}}
@keyframes t_slide{0%{opacity:1;transform:translateX(1080px)}100%{opacity:1;transform:none}}
@keyframes t_up{0%{opacity:1;transform:translateY(1920px)}100%{opacity:1;transform:none}}
@keyframes t_zoom{0%{opacity:0;transform:scale(1.6)}100%{opacity:1;transform:none}}
@keyframes hold{0%,100%{opacity:1}}
@keyframes hookin{0%{opacity:0;transform:scale(2.2) rotate(-4deg)}14%{opacity:1;transform:scale(.94)}20%{transform:scale(1.03)}
26%,88%{opacity:1;transform:none}100%{opacity:0;transform:scale(.9)}}
@keyframes tagin{0%{opacity:0;transform:translateX(-120px)}10%{opacity:1;transform:none}90%{opacity:1}100%{opacity:0}}
@keyframes subin{0%{opacity:0;transform:translateY(30px)}6%{opacity:1;transform:none}94%{opacity:1}100%{opacity:0}}
@keyframes flash{0%{opacity:.75}100%{opacity:0}}
@keyframes bar{from{width:0}to{width:100%}}
"""
TRANS = ("t_fade", "t_slide", "t_zoom", "t_up")


def chunks(text: str, size: int = 4) -> list[str]:
    words = str(text).split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)] or [""]


def page(data: dict, starts: list[float], lengths: list[float], pics: list[tuple], rig: dict | None, fallback_bg) -> tuple[str, list]:
    """(html, subtitr jadvali [(boshlanish, tugash, sahna, bo'lak, so'z)]) - so'zlar ovoz davomida tekis taqsimlanadi."""
    from .skills import presenter
    esc = html_lib.escape
    dur = starts[-1] + lengths[-1]
    rnd = random.Random(len(data.get("title", "")))
    parts, subs = [], []
    for k, s in enumerate(data["scenes"]):
        st, ln = starts[k], lengths[k]
        trans = "t_fade" if k == 0 else TRANS[(k + rnd.randint(0, 3)) % len(TRANS)]
        move = MOVES[(k * 2 + rnd.randint(0, 4)) % len(MOVES)]
        pic = pics[k][0]
        if pic:
            import base64
            bg = f'<img class="bg" src="data:image/jpeg;base64,{base64.b64encode(Path(pic).read_bytes()).decode()}" ' \
                 f'style="animation:{move} {ln + .6:.2f}s linear {st - .3:.2f}s both">'
        else:
            bg = f'<div style="position:absolute;inset:0;animation:{move} {ln + .6:.2f}s linear {st - .3:.2f}s both">{fallback_bg(s, k)}</div>'
        end = dur if k == len(data["scenes"]) - 1 else st + ln + .35
        parts.append(f'<div class="sc" style="z-index:{k + 1};animation:{trans} .35s cubic-bezier(.2,.8,.2,1) {st - .15:.2f}s both,'
                     f'hold {max(.1, end - st - .2):.2f}s {st + .2:.2f}s forwards">{bg}<div class="dim"></div></div>')
        if k:
            parts.append(f'<div class="flash" style="z-index:{k + 1};animation:flash .22s {st - .05:.2f}s forwards"></div>')
        big = str(s.get("big") or "").strip()
        if k == 0 and big:  # HOOK - katta, sakrab chiqadi
            parts.append(f'<div class="hook" style="z-index:40;animation:hookin {ln:.2f}s {st:.2f}s both">{esc(big)}</div>')
        elif big:
            parts.append(f'<div class="tag" style="z-index:40;animation:tagin {ln:.2f}s {st:.2f}s both">{esc(big)}</div>')
        pieces = chunks(s["voice"])
        total = sum(len(p) for p in pieces) or 1
        t = st
        for j, piece in enumerate(pieces):
            span = (ln - .25) * len(piece) / total
            words = piece.split()
            parts.append(f'<div class="sub" id="sb{k}_{j}" style="z-index:45;animation:subin {span:.2f}s {t:.2f}s both">'
                         + "".join(f'<span id="w{k}_{j}_{i}">{esc(w)}</span>' for i, w in enumerate(words)) + "</div>")
            wt = t
            for i, w in enumerate(words):
                wl = span * len(w) / max(1, sum(len(x) for x in words))
                subs.append((wt, wt + wl, f"w{k}_{j}_{i}"))
                wt += wl
            t += span
    host = presenter.html(rig).replace('<div id="pr"', '<div id="pr" class="host"', 1) if rig else ""
    body = (f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}{KEYS}#pr{{z-index:30}}#arms{{z-index:31}}</style></head><body>'
            + "".join(parts) + f'<div style="position:absolute;inset:0;z-index:30">{host}</div>'
            + f'<div class="brand">PLANET PRINT</div><div class="bar" style="animation:bar {dur:.2f}s linear both"></div>'
            + """<script>window.__subs=function(on){var a=document.querySelectorAll('.sub span.on');
for(var i=0;i<a.length;i++)a[i].className='';for(var j=0;j<on.length;j++){var e=document.getElementById(on[j]);if(e)e.className='on';}};</script>"""
            + "</body></html>")
    return body, subs


# ---------- personaj: sahna joylashuviga qarab ----------
SPOTS = {"host_left": (300, 1.0), "host_right": (780, 1.0), "host_center": (540, 1.0), "host_corner": (880, .5), "full": (540, 1.0)}


def host_frames(scenes: list[dict], starts: list[float], lengths: list[float], fps: int, mouth: list[int],
                blink: list[bool]) -> list[dict]:
    """Har kadr: personaj joyi (sahna joylashuvi), yashirinishi, qo'l harakatlari, og'iz, ko'z."""
    from .skills import presenter as pr
    from .skills import talking_head as th
    dur = starts[-1] + lengths[-1]
    n = int(dur * fps)
    out = []

    def state(k):
        lay = scenes[k]["layout"]
        x, sc = SPOTS[lay]
        return x, sc, 1500.0 if lay == "full" else 0.0  # full - pastga yashirinadi

    def gestures(k, t, nx, lvl, toward):
        """Sahna ichidagi qo'l: boshida ko'rsatadi, keyin kaft ochib tushuntiradi, oxirida sanaydi / bosh barmoq."""
        since = (t - starts[k]) / max(.1, lengths[k])
        last = k == len(scenes) - 1
        names = (("open", "point", "open", "thumb") if last else ("point", "open", pr.COUNT[min(k, 4)], "open")
                 if k else ("open", "open", "point", "open"))
        idx = min(3, int(since * 4))
        mix = pr._ease((since * 4 - idx) / .35) if idx else 1.0
        prev = names[idx - 1] if idx else names[0]
        return prev, names[idx], mix

    def spot(name, d, nx, t, lvl):
        beat = lvl * 16 * math.sin(t * 7.3 + d)
        if name == "rest":
            return nx + d * 235, 2050, d * 4.0, pr.HANDS["relax"]
        if name == "point":
            return nx + d * 330, 1450 + beat * .4, d * 58.0, pr.HANDS["point"]
        if name == "open":
            return nx + d * (320 + 18 * math.sin(t * 2.3)), 1530 + beat, d * (20 + 7 * math.sin(t * 3.1)), pr.HANDS["open"]
        if name == "thumb":
            return nx + d * 265, 1480 + beat * .5, d * 6.0, pr.HANDS["thumb"]
        return nx + d * 275, 1460 + beat * .5, d * 10.0, pr.HANDS[name]

    for f in range(n):
        t = f / fps
        k = max(i for i in range(len(scenes)) if starts[i] <= t + 1e-6)
        x1, s1, y1 = state(k)
        x0, s0, y0 = state(k - 1) if k else (x1, s1, 1500.0)
        mix = pr._ease((t - starts[k]) / .55)
        nx, sc, hide = x0 + (x1 - x0) * mix, s0 + (s1 - s0) * mix, y0 + (y1 - y0) * mix
        lvl = (mouth[f] if f < len(mouth) else 0) / (len(th.LEVELS) - 1)
        toward = -1 if nx > 540 else 1
        arms = ""
        if sc > .9 and hide < 200:
            parts = []
            for d, keys in ((toward, True), (-toward, False)):
                p0, p1, m = gestures(k, t, nx, lvl, toward) if keys else ("rest", "open" if .3 < (t - starts[k]) / lengths[k] < .7
                                                                       else "rest", 1.0)
                a0, b0, c0, d0 = spot(p0, d, nx, t, lvl)
                a1, b1, c1, d1 = spot(p1, d, nx, t, lvl)
                curls = tuple(u + (v - u) * m for u, v in zip(d0, d1))
                parts.append(pr.arm(nx + d * 300, 2010 + hide, a0 + (a1 - a0) * m, b0 + (b1 - b0) * m + hide,
                                    c0 + (c1 - c0) * m, curls, 1 if d < 0 else -1))
            arms = "".join(parts)
        out.append({"x": round(nx - pr.NECK_X * pr.SCALE, 2), "tr": round(.6 * math.sin(t * 1.1), 3),
                    "ty": round(4 * math.sin(t * 1.5) + hide, 2), "sc": round(sc, 3),
                    "h": round(1.7 * math.sin(t * 1.9) + 1.0 * math.sin(t * .67 + 1) + toward * 1.4, 3),
                    "n": round(3.2 * lvl * math.sin(t * 8.1) + 2 * math.sin(t * 1.3), 2),
                    "m": mouth[f] if f < len(mouth) else 0, "b": bool(blink[f]) if f < len(blink) else False, "a": arms})
    return out


STEP = """([t, s, on]) => { document.getAnimations().forEach(a => { a.pause(); a.currentTime = t; });
  if (window.__rig) window.__rig(s); if (window.__subs) window.__subs(on); }"""


def render(html: str, out: Path, dur: float, frames: list[dict], subs: list, fps: int = FPS) -> Path:
    import tempfile

    from playwright.sync_api import sync_playwright

    from .browser import CHROME
    from .skills.video_edit import _run
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=CHROME if Path(CHROME).exists() else None)
        try:
            tab = browser.new_page(viewport={"width": 1080, "height": 1920})
            tab.set_content(html, wait_until="load")
            for n in range(int(dur * fps)):
                t = n / fps
                on = [w for a, b, w in subs if a <= t < b]
                tab.evaluate(STEP, [t * 1000, frames[n] if n < len(frames) else frames[-1], on])
                tab.screenshot(path=str(Path(tmp) / f"f{n:05d}.jpg"), type="jpeg", quality=90)
        finally:
            browser.close()
        _run(["-framerate", str(fps), "-i", str(Path(tmp) / "f%05d.jpg"), "-c:v", "libx264", "-preset", "medium",
              "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(fps), str(out)])
    return out


def make(slot: str, notify=lambda text: None, topic: str = "") -> dict:
    """Hikoya Reels: ssenariy -> ovoz (sahnama-sahna) -> rasmlar -> render -> musiqa. {path, idea, sources}."""
    import tempfile

    from . import daily_video, outbox, team_hub
    from .skills import motion_bg, presenter, stage, talking_head
    from .skills.music import for_video
    from .skills.video_edit import _run
    from .skills.video_pro import video_pro
    st = daily_video._state()
    previous = "; ".join(h["title"] for h in st.get("history", [])[-12:])
    data, src = script(topic, previous, daily_video._ready())
    scenes = data["scenes"]
    team_hub.feed("kontent", f"{slot} Reels ssenariysi", f"🎬 {data.get('title', '')}\n"
                  + "\n".join(f"{k + 1}. [{s['layout']}] {s['voice']}  🖼 {s.get('image', '')[:90]}" for k, s in enumerate(scenes))
                  + f"\n(manba: {src})")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        voice, lengths = voices(scenes, tmp)
        starts = [sum(lengths[:k]) for k in range(len(lengths))]
        dur = starts[-1] + lengths[-1]
        pics = images(scenes, int(hashlib.sha1(data.get("title", "").encode()).hexdigest()[:6], 16))
        got = sum(1 for p in pics if p[0])
        art = sorted({s for _, s in pics if s} - {"kesh"}) or (["kesh"] if got else [])

        def drawn(sc, k):  # rasm kelmasa - Ali'ning chizilgan foni
            icon = motion_bg.pick(sc, [])
            return stage._backdrop(stage.backdrop_of(icon), "none")
        rig = presenter.build(daily_video.character()) if daily_video.character() else None
        rig = rig or presenter.vector_rig()
        mouth = talking_head.levels(voice, dur, FPS)
        frames = host_frames(scenes, starts, lengths, FPS, mouth, talking_head.blinks(dur, FPS))
        html, subs = page(data, starts, lengths, pics, rig, drawn)
        team_hub.feed("dasturchi", f"{slot} Reels sahifasi", f"{len(scenes)} sahna, {dur:.0f} s, rasm: {got}/{len(scenes)} "
                      f"({', '.join(art) or 'chizilgan fon'})")
        raw = tmp / "anim.mp4"
        render(html, raw, dur, frames, subs)
        spoken = tmp / "spoken.mp4"
        _run(["-i", str(raw), "-i", str(voice), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
              "-af", f"apad=whole_dur={dur:.2f}", "-t", f"{dur:.2f}", "-c:a", "aac", "-ar", "48000", str(spoken)])
        mood = data.get("mood") if data.get("mood") in ("energetic", "cinematic", "calm") else "energetic"
        music, music_src = for_video(dur + 2, mood)
        start = outbox.mark()
        video_pro(str(spoken), music=music, cut_silence=False, subtitles=False, progress_bar=False)
        made = [f for f in outbox.since(start) if f.suffix == ".mp4"]
    if not made:
        raise RuntimeError("Video chiqmadi")
    sources = (f"ssenariy: {src}, {len(scenes)} sahna, rasmlar: {got}/{len(scenes)} ({', '.join(art) or 'chizilgan'}), "
               f"musiqa: {music_src}, personaj gapiradi")
    team_hub.feed("video_montajchi", f"{slot} Reels montaji", f"✅ {made[-1].name} ({dur:.0f} s, {sources})")
    data = {**data, "scenes": [{**s, "big": s.get("big") or s["voice"][:40], "small": s["voice"]} for s in scenes]}
    return {"path": str(made[-1]), "idea": data, "sources": sources}
