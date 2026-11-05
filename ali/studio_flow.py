"""Kreativ video oqimi (telefondan): Ali brif beradi -> egasi rasmlarni ChatGPT/Gemini ilovasida yaratadi -> botga yoki
@planetprint_reels kanaliga tashlaydi -> Ali videoni o'zi yig'adi va kanalga joylaydi.

Nega shunday: Pro obuna (ChatGPT/Gemini) faqat ilova ichida ishlaydi; ilovani dastur bilan boshqarish akkauntni xavf
ostiga qo'yadi. Rasmni egasi yaratadi (1 bosish), qolgan hammasi - Ali: brif, promptlar, ovoz, subtitr, montaj, joylash.
Har video uslubi «[video_montajchi] Uslub» bilimi bo'lib saqlanadi va keyingi briflarda ishlatiladi.
"""
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

import httpx

from .config import config

log = logging.getLogger("ali.studio")

STATE = config.data_dir / "studio_briefs.json"
CHANNEL = os.getenv("VIDEO_CHANNEL", "planetprint_reels").lstrip("@")  # «🎬 Planet Print | Reels studiya"
QUERY = re.compile(r"(brif|бриф|kreativ|креатив|rasmli\s+video|расмли\s+видео|virus|вирус)", re.I)
TAG = re.compile(r"#?\s*[BbВв](\d{1,4})")

BRIEF = """Sen Instagram strategi va Reels rejissyorisan. Egang: targetolog va tashqi reklama agentligi egasi (Planet Print,
Beshariq). Maqsad - Instagram tavsiyasiga (Explore/Reels) chiqadigan VIRUSLI, kreativ Reels.
Mavzu / topshiriq: {task}
{styles}
Egang rasmlarni ChatGPT yoki Gemini ilovasida O'ZI yaratadi - har sahna uchun tayyor, batafsil INGLIZCHA rasm prompti yoz
(vertikal 9:16, fotorealistik yoki kinematografik, MATNSIZ - yozuvni Ali qo'yadi, brend ranglari, aniq kompozitsiya).
Egamning darslari kunduzi - Instagram ishlari faqat 13:00 dan keyin.

FAQAT JSON qaytar:
{{"title": "...", "hook": "birinchi 1-2 soniyadagi kuchli yozuv (o'zbekcha)",
  "scenes": [{{"title": "ekrandagi qisqa yozuv (3-6 so'z)", "narration": "diktor matni (o'zbekcha, 1-2 gap)",
              "image_prompt": "English detailed prompt, vertical 9:16, no text", "duration": 3}}],
  "caption": "post matni (CTA bilan)", "hashtags": "#... (8-12 ta)",
  "post_time": "kun va soat (masalan: bugun 19:30) + nega",
  "trial": "Instagram «sinov Reels» (trial reels - faqat obunachi bo'lmaganlarga) qilib joylashmi: ha/yo'q + nega",
  "why_viral": "nega tavsiyaga chiqishi mumkin (2-3 gap)",
  "style": "uslub: ranglar, shrift, ritm, o'tishlar, kayfiyat (1-2 gap)"}}
Sahnalar soni: 4-6."""


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"next": 1, "briefs": {}, "channel_last": 0}


def _save(state: dict) -> None:
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


INSTANT = re.compile(r"rasmsiz|расмсиз|darhol|дарҳол|дархол|gradient|tezkor\s+video", re.I)


def is_query(text: str) -> bool:
    """Brif yo'li: «kreativ/virusli video, brif» yoki oddiy «video yarat» (egasi 2-yo'lni tanlagan - rasmlarni o'zi
    ilovada yaratadi). «rasmsiz / darhol» deyilsa - tezkor (gradient) video, bu yo'l emas."""
    from . import montage
    t = text or ""
    if INSTANT.search(t):
        return False
    brief = bool(QUERY.search(t)) and bool(re.search(r"video|видео|reels|рилс|ролик", t, re.I))
    return brief or montage.is_creation(t)


def waiting() -> dict | None:
    """Rasm kutayotgan oxirgi brif."""
    briefs = [b for b in _state()["briefs"].values() if b["status"] == "waiting"]
    return max(briefs, key=lambda b: b["id"]) if briefs else None


def _styles() -> str:
    from .memory import memory
    rows = memory.relevant_knowledge("video uslub reels", "[video_montajchi] Uslub", 3)
    return ("Oldingi muvaffaqiyatli uslublar (shunga yaqin, lekin takrorlamasdan):\n" +
            "\n".join(f"- {r['content'][:300]}" for r in rows)) if rows else ""


def start(task: str, ready: list[str]) -> list[str]:
    """Brif tuzadi va saqlaydi. Telegram'ga yuboriladigan xabarlar ro'yxatini qaytaradi."""
    from .service import _ask_json
    data = _ask_json(BRIEF.format(task=task[:1500], styles=_styles()), ready, 300)
    scenes = [s for s in data.get("scenes", []) if isinstance(s, dict) and s.get("image_prompt")][:6]
    if not scenes:
        raise RuntimeError("Brif tuzilmadi (sahnalar yo'q) - mavzuni aniqroq yozing")
    state = _state()
    try:  # kanaldagi eski rasmlar yangi brifga aralashmasin - hozirgi oxirgi post belgilanadi
        from . import tg_account

        async def top(client):
            async for m in client.iter_messages(CHANNEL, limit=1):
                return m.id
            return 0
        state["channel_last"] = max(state.get("channel_last", 0), tg_account._run(top) or 0)
    except Exception as e:
        log.warning("Kanal belgilanmadi: %s", e)
    bid = state["next"]
    state["next"] += 1
    state["briefs"][str(bid)] = {"id": bid, "task": task, "status": "waiting", "at": time.time(), "images": [],
                                 **{k: data.get(k, "") for k in ("title", "hook", "caption", "hashtags", "post_time",
                                                                 "trial", "why_viral", "style")}, "scenes": scenes}
    _save(state)
    head = (f"🎬 Brif #B{bid}: {data.get('title', '')}\n\n🪝 Hook: {data.get('hook', '')}\n"
            f"🕒 Joylash: {data.get('post_time', '')}\n🧪 Sinov Reels: {data.get('trial', '')}\n"
            f"🔥 Nega tavsiyaga chiqadi: {data.get('why_viral', '')}\n🎨 Uslub: {data.get('style', '')}\n\n"
            f"📲 QADAMLAR (telefonda):\n1) Pastdagi {len(scenes)} ta promptni ChatGPT yoki Gemini ilovasiga birma-bir "
            f"yuboring.\n2) Chiqqan rasmlarni TARTIB BILAN shu botga yoki @{CHANNEL} kanaliga tashlang.\n"
            f"3) Hammasi kelgach Ali videoni o'zi yig'adi va kanalga joylaydi. Kamroq rasm bilan qilish: «#B{bid} video qil».")
    prompts = [f"🖼 {i}/{len(scenes)} — {s.get('title', '')}\n\n{s['image_prompt']}" for i, s in enumerate(scenes, 1)]
    return [head, *prompts]


def add_image(path: str, caption: str = "") -> tuple[dict | None, str]:
    """Rasmni brifga qo'shadi. (to'lgan brif yoki None, holat matni)."""
    state = _state()
    m = TAG.search(caption or "")
    brief = state["briefs"].get(m.group(1)) if m else None
    brief = brief if brief and brief["status"] == "waiting" else waiting()
    if not brief:
        return None, ""
    b = state["briefs"][str(brief["id"])]
    b["images"].append(str(path))
    _save(state)
    need = len(b["scenes"])
    if len(b["images"]) >= need:
        return b, f"✅ #B{b['id']}: {need}/{need} rasm keldi - videoni yig'yapman…"
    return None, f"🖼 #B{b['id']}: {len(b['images'])}/{need} rasm qabul qilindi"


def build(bid: int, progress=lambda note: None) -> dict:
    """Videoni yig'adi (rasmlar fon, diktor ovozi, subtitr, sahna yozuvlari), kanalga joylaydi, uslubni eslab qoladi."""
    from . import outbox
    from .memory import memory
    from .plugins.video_studio import make_content_video
    state = _state()
    b = state["briefs"][str(bid)]
    b["status"] = "building"
    _save(state)
    scenes = [{"title": (b["hook"] if i == 0 and b.get("hook") else s.get("title", "")), "text": s.get("title", "") if i else "",
               "narration": s.get("narration", ""), "image_prompt": s.get("image_prompt", ""),
               "duration": s.get("duration", 3)} for i, s in enumerate(b["scenes"])]
    start = outbox.mark()
    try:
        result = make_content_video(b.get("title") or b["task"], scenes=scenes, images=b["images"],
                                    ai_images=False, platform="reels")
    except Exception:
        b["status"] = "waiting"
        _save(state)
        raise
    files = outbox.since(start)
    video = next((f for f in files if f.suffix == ".mp4"), None)
    b["status"], b["video"] = "done", str(video) if video else ""
    _save(state)
    posted = ""
    if video:
        caption = f"{b.get('caption', '')}\n\n{b.get('hashtags', '')}\n\n🕒 {b.get('post_time', '')}"[:990] + f"\n{MARK}"
        try:
            from . import tg_account
            pid = tg_account.send_file(CHANNEL, str(video), caption)
            st = _state()
            st.setdefault("posted", []).append(pid)  # o'z videosi - kanal kuzatuvi qayta ishlamaydi
            _save(st)
            posted = f"📢 @{CHANNEL} kanaliga joylandi"
        except Exception as e:
            posted = f"⚠️ Kanalga joylanmadi: {e}"
        memory.add_knowledge(f"[video_montajchi] Uslub: {b.get('title', '')[:60]}",
                             f"Uslub: {b.get('style', '')}\nHook: {b.get('hook', '')}\nMavzu: {b['task'][:200]}\n"
                             f"Nega virusli: {b.get('why_viral', '')}")
    return {"text": f"{result}\n{posted}", "files": [str(f) for f in files]}


# --- @kanal kuzatuvi: kanalga tashlangan VIDEO - Ali o'zi tahlil qilib montaj qiladi; RASM - brifga yoki B-roll so'roviga ---
MARK = "#ali_tayyor"  # Ali o'zi joylagan postlar - qayta ishlanmaydi
EDIT_PLAN = """Sen professional Instagram Reels montajchisi va targetologsan. Egam (targetolog, tashqi reklama agentligi
Planet Print) kanalga video tashladi. Biriktirilgan rasmlar - videodan olingan kadrlar (boshidan oxirigacha).
Davomiylik: {dur:.1f} s, o'lcham: {size}. Egam izohi: {caption}
Nutq (taxminiy): {speech}

{style}
Egam izohi/topshirig'i bo'lsa - unga ANIQ amal qil (sahnalar tartibi, uzunlik, ritm, rang, yozuv yo'qligi, fps, 4K).
"render": premium/kinematografik topshiriqda - grade "cinematic", fade true, progress_bar false, hook/cta faqat so'ralsa;
nutq bo'lmasa subtitles false; 24 fps yoki 4K so'ralsa - fps 24, uhd true. Oddiy Reels - natural, 30 fps, progress_bar true.
Shu videoni Instagram tavsiyasiga chiqadigan Reels qilish uchun montaj rejasini tuz. FAQAT JSON:
{{"hook": "birinchi 2.5 s uchun kuchli yozuv (o'zbekcha, ko'pi bilan 6 so'z)", "cta": "oxirgi yozuv (3-4 so'z)",
  "cut_silence": true, "caption": "post matni (CTA bilan)", "hashtags": "#... (8-12 ta)",
  "render": {{"subtitles": true, "progress_bar": true, "grade": "natural|cinematic", "fade": false, "fps": 30, "uhd": false}},
  "post_time": "qachon joylash + nega", "trial": "sinov Reels qilib joylashmi: ha/yo'q + nega",
  "missing": [{{"why": "nega kerak (o'zbekcha)", "prompt": "English prompt for ChatGPT/Gemini image, vertical 9:16, photorealistic, no text"}}]}}
"missing" - faqat haqiqatan yetishmayotgan kadrlar (masalan: natija, yaqin plan, oldin/keyin, mahsulot): 0-4 ta."""


def _frames(video: Path, tmp: Path, n: int = 6) -> list[str]:
    from .skills.video_edit import _run, info
    dur, out = info(video)["duration"], []
    for k in range(n):
        f = tmp / f"k{k}.jpg"
        try:
            _run(["-ss", f"{dur * (k + 0.5) / n:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=540:-1", str(f)])
            out.append(str(f))
        except RuntimeError:
            pass
    return out


def _plan(video: Path, caption: str) -> dict:
    """AI kadrlarni ko'rib, nutqni o'qib montaj rejasini tuzadi (Claude/Gemini rasm ko'radi)."""
    import tempfile
    from . import local_ai
    from .skills.video_edit import _srt, info
    i = info(video)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        frames = _frames(video, tmp_p)
        try:
            speech = " ".join(l for l in _srt(video, tmp_p).splitlines() if l and "-->" not in l and not l.isdigit())[:3000]
        except Exception:
            speech = "(nutq yo'q yoki tanilmadi)"
        prompt = EDIT_PLAN.format(dur=i["duration"], size=f"{i['width']}x{i['height']}", caption=caption or "-", speech=speech,
                                  style=_style_hint())
        got = local_ai.ask_pro(prompt, 300, None, frames) if local_ai.access() is True else None
    try:
        raw = got[1] if got else ""
        return json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (ValueError, TypeError):
        from .skills.video_motion import RULE_WORDS
        cine = bool(RULE_WORDS["cinematic"].search(caption or ""))  # AI band - topshiriq so'zlaridan
        return {"hook": "", "cta": "" if cine else "Direktga yozing", "cut_silence": not cine, "missing": [],
                "render": {"grade": "cinematic" if cine else "natural", "fade": cine, "progress_bar": not cine,
                           "fps": 24 if cine or RULE_WORDS["fps24"].search(caption or "") else 30,
                           "uhd": bool(RULE_WORDS["uhd"].search(caption or ""))},
                "caption": "Planet Print - tashqi reklama. Direktga yozing.",
                "hashtags": "#planetprint #tashqireklama #reklama #reels #uzbekistan", "offline": True}


ALBUM_PLAN = """Sen professional Reels montajchisisan. Egam kanalga {n} ta klipdan iborat albom tashladi - ulardan BITTA
Reels yasash kerak. Biriktirilgan rasmlar - har klipdan 2 tadan kadr (tartib bilan: 1-klip, 2-klip, ...).
Klipler (raqam: davomiylik): {clips}
Egam izohi: {caption}
{style}
Eng kuchli qismlarni tanla, tartibla va kes: jami 20-60 soniya, boshida eng qiziq kadr (hook), kadrlar 1.5-4 s (dinamik).
Harakatli kadrlarga (o'rnatish, yig'ish, ko'tarish, yonish) SPEED RAMP qo'y: "ramp": true (normal -> tez -> slow-motion).
Har o'tish uchun turini tanla: zoomin, slideleft, slideright, smoothup, fadewhite (flash), circleopen, fade. FAQAT JSON:
Egam izohi/topshirig'i bo'lsa - unga ANIQ amal qil (sahnalar tartibi, uzunlik, ritm, rang, yozuv yo'qligi, fps, 4K).
"render": premium/kinematografik topshiriqda - grade "cinematic", fade true, progress_bar false, hook/cta faqat so'ralsa;
nutq bo'lmasa subtitles false; 24 fps yoki 4K so'ralsa - fps 24, uhd true. Oddiy Reels - natural, 30 fps, progress_bar true.
{{"clips": [{{"n": 1, "start": 0.0, "end": 4.5, "ramp": false}}], "transitions": ["zoomin", "..."],
  "render": {{"subtitles": true, "progress_bar": true, "grade": "natural|cinematic", "fade": false, "fps": 30, "uhd": false}},
  "hook": "...", "cta": "...", "caption": "...", "hashtags": "...",
  "post_time": "...", "trial": "...", "missing": [{{"why": "...", "prompt": "English prompt, vertical 9:16, no text"}}]}}"""


def _style_hint() -> str:
    """/organ bilan o'rganilgan oxirgi uslub - montaj rejasiga qo'shiladi."""
    from .skills.video_motion import latest_style
    st = latest_style()
    if not st:
        return ""
    return ("Egam o'rgatgan uslub (shunga moslab montaj qil): " + json.dumps(
        {k: st.get(k) for k in ("name", "pacing", "hook", "text_style", "transitions", "effects", "avg_shot", "lessons")},
        ensure_ascii=False)[:1500])


def _album(paths: list[str], caption: str, tmp: Path) -> tuple[str, dict]:
    """Albom: AI eng yaxshi qismlarni tanlaydi -> kesib, silliq o'tishlar bilan bitta videoga yig'iladi."""
    from . import local_ai
    from .skills.video_edit import _fit, _run, info
    from .skills.video_motion import join_dynamic, ramp_clip
    infos = [info(Path(p)) for p in paths]
    frames = []
    for k, p in enumerate(paths):
        (tmp / f"c{k}").mkdir()
        frames += _frames(Path(p), tmp / f"c{k}", 2)
    prompt = ALBUM_PLAN.format(n=len(paths), clips=", ".join(f"{k}: {i['duration']:.1f} s" for k, i in enumerate(infos, 1)),
                               caption=(caption or "-")[:6000], style=_style_hint())
    got = local_ai.ask_pro(prompt, 300, None, frames[:16]) if local_ai.access() is True else None
    try:
        raw = got[1] if got else ""
        plan = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (ValueError, TypeError):
        plan = {}
    picks = [c for c in plan.get("clips", []) if isinstance(c, dict) and 1 <= int(c.get("n", 0)) <= len(paths)]
    if not picks:  # AI'lar band (limit) - montajchi o'z qoidalari va o'lchovlari bilan reja tuzadi
        from .skills.video_motion import rule_plan
        plan = rule_plan(paths, caption)
        picks = plan["clips"]
    parts = []
    for j, c in enumerate(picks[:12]):
        src, d = paths[int(c["n"]) - 1], infos[int(c["n"]) - 1]["duration"]
        a = max(0.0, float(c.get("start", 0)))
        b = min(d, float(c.get("end", d)) or d)
        if b - a < 0.8:
            continue
        part = tmp / f"p{j}.mp4"
        has_audio = infos[int(c["n"]) - 1]["audio"]
        if c.get("ramp") and b - a >= 2.0:  # speed ramp: normal -> tez -> slow-motion
            parts.append(ramp_clip(src, a, b, part, has_audio))
            continue
        audio = [] if has_audio else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        _run(["-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-i", src, *audio, "-filter_complex", _fit("blur") + ",format=yuv420p[v]",
              "-map", "[v]", "-map", "1:a" if audio else "0:a", "-shortest", "-c:v", "libx264", "-preset", "veryfast",
              "-crf", "18", "-c:a", "aac", "-ar", "48000", "-ac", "2", str(part)])
        parts.append(part)
    if not parts:
        raise RuntimeError("Albomdan yaroqli qism tanlanmadi")
    joined = tmp / "joined.mp4"
    try:  # motion: kliplar orasida dinamik o'tishlar (zoom, slayd, flash)
        join_dynamic(parts, joined, [str(t) for t in plan.get("transitions", [])])
    except RuntimeError:  # o'tish ishlamasa - oddiy ulash
        (tmp / "list.txt").write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
        _run(["-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", str(joined)], cwd=tmp)
    return str(joined), plan


def auto_edit(video, caption: str, src_id: int, notify, photos: list | None = None, music: str = "") -> None:
    """Kanaldagi video (yoki albom - bir nechta klip) - o'zi montaj qiladi, kanalga (javob qilib) va egasiga yuboradi;
    kadr yetmasa - kanalga prompt yozadi."""
    import tempfile
    from . import outbox, tg_account
    from .skills.video_pro import video_pro
    paths = video if isinstance(video, list) else [video]
    notify(f"🎬 Kanaldagi {'albomni (' + str(len(paths)) + ' ta klip)' if len(paths) > 1 else 'videoni'} oldim - "
           "ko'rib chiqib montaj qilyapman (2-5 daqiqa)…")
    tmpdir = tempfile.TemporaryDirectory()
    try:
        if len(paths) > 1:
            video, plan = _album(paths, caption, Path(tmpdir.name))
        else:
            video, plan = paths[0], _plan(Path(paths[0]), caption)
    except Exception as e:
        tmpdir.cleanup()
        notify(f"⚠️ Montaj bajarilmadi: {str(e)[:400]}")
        return
    start = outbox.mark()
    try:
        r = plan.get("render") if isinstance(plan.get("render"), dict) else {}
        if not music:  # paketda trek yo'q - kutubxonadan yoki sintez (mualliflik huquqi muammosiz)
            from .skills.music import for_video, mood_of
            from .skills.video_edit import info
            mood = "cinematic" if str(r.get("grade")) == "cinematic" else mood_of(caption)
            music, src = for_video(info(Path(video))["duration"] + 2, mood)
            notify(f"🎵 Musiqa: {mood} ({src})")
        result = video_pro(video, hook=plan.get("hook", ""), cta=plan.get("cta", ""), music=music,
                           cut_silence=bool(plan.get("cut_silence", len(paths) == 1)),
                           subtitles=bool(r.get("subtitles", True)), progress_bar=bool(r.get("progress_bar", True)),
                           grade=str(r.get("grade", "natural")), fade=bool(r.get("fade", False)),
                           fps=int(r.get("fps", 30) or 30), uhd=bool(r.get("uhd", False)))
        if photos:  # paketdagi rasmlar - B-roll (asl ovoz davom etadi)
            from .skills.video_pro import video_broll
            made = [f for f in outbox.since(start) if f.suffix == ".mp4"]
            if made:
                result += "\n" + video_broll(str(made[-1]), photos)
                outbox.forget(made[-1])
    except Exception as e:
        notify(f"⚠️ Montaj bajarilmadi: {str(e)[:400]}")
        return
    finally:
        tmpdir.cleanup()
    out = next((f for f in outbox.since(start) if f.suffix == ".mp4"), None)
    text = f"{plan.get('caption', '')}\n\n{plan.get('hashtags', '')}".strip()
    state = _state()
    if out:
        try:
            pid = tg_account.send_file(CHANNEL, str(out), f"{text}\n\n{MARK}"[:1024], reply_to=src_id)
            state.setdefault("posted", []).append(pid)
        except Exception as e:  # internet/Telegram uzilgan - keyinroq o'zi qayta joylaydi
            state.setdefault("pending_post", []).append({"out": str(out), "caption": text, "src": src_id})
            result += f"\n⏳ Kanalga hozir joylanmadi ({str(e)[:80]}) - internet tiklanishi bilan o'zim joylayman."
    missing = [m for m in plan.get("missing", []) if isinstance(m, dict) and m.get("prompt")][:4]
    if missing and out:
        ask = (f"🖼 Videoni kuchaytirish uchun kerakli kadrlar ({len(missing)} ta). ChatGPT yoki Gemini'da yarating va "
               f"SHU XABARGA JAVOB qilib rasmlarni tashlang - Ali ularni videoga qo'shadi:\n\n"
               + "\n\n".join(f"{n}) {m.get('why', '')}\n{m['prompt']}" for n, m in enumerate(missing, 1)) + f"\n\n{MARK}")
        try:
            rid = tg_account.send_text(CHANNEL, ask, reply_to=src_id)
            state.setdefault("posted", []).append(rid)
            state.setdefault("requests", {})[str(rid)] = {"video": str(out), "need": len(missing), "images": [],
                                                          "src": src_id, "caption": text}
        except Exception as e:
            log.warning("Kadr so'rovi joylanmadi: %s", e)
    _save(state)
    advice = f"🕒 {plan.get('post_time', '')}\n🧪 Sinov Reels: {plan.get('trial', '')}"
    send_files(f"{result}\n\n🪝 Hook: {plan.get('hook', '')}\n{advice}"
               + (f"\n\n🖼 {len(missing)} ta qo'shimcha kadr prompti kanalga yozildi." if missing else ""),
               [str(out)] if out else [])


def _broll(req_id: str, notify) -> None:
    """Kadr so'roviga javob rasmlari kelgach - videoga B-roll qilib qo'shadi va qayta joylaydi."""
    from . import outbox, tg_account
    from .skills.video_pro import video_broll
    state = _state()
    req = state.get("requests", {}).pop(req_id, None)
    _save(state)
    if not req:
        return
    start = outbox.mark()
    try:
        result = video_broll(req["video"], req["images"])
    except Exception as e:
        notify(f"⚠️ B-roll qo'shilmadi: {str(e)[:300]}")
        return
    out = next((f for f in outbox.since(start) if f.suffix == ".mp4"), None)
    if out:
        try:
            pid = tg_account.send_file(CHANNEL, str(out), f"{req.get('caption', '')}\n\n{MARK}"[:1024], reply_to=req["src"])
            state = _state()
            state.setdefault("posted", []).append(pid)
            _save(state)
        except Exception as e:
            result += f"\n⚠️ Kanalga joylanmadi: {e}"
    send_files(f"✅ Qo'shimcha kadrlar bilan yangi variant: {result}", [str(out)] if out else [])


LEARN = re.compile(r"/\s*(o['ʻ‘’]?rgan|organ|ўрган|урган|learn)\b", re.I)


def learn(videos: list[str], caption: str, src_id: int, notify) -> None:
    """«/organ» - namuna video(lar)dan montaj uslubini o'rganadi va kanalga/egasiga hisobot beradi."""
    from . import tg_account
    from .skills.video_motion import analyze_style, style_text
    notify(f"🎓 Namuna videoni o'rganyapman ({len(videos)} ta) - kesimlar, ritm, effektlar, yozuvlar…")
    reports = []
    for v in videos:
        try:
            reports.append(style_text(analyze_style(v, LEARN.sub("", caption).strip())))
        except Exception as e:
            reports.append(f"⚠️ O'rganib bo'lmadi: {str(e)[:200]}")
    text = "\n\n".join(reports)
    try:
        pid = tg_account.send_text(CHANNEL, f"{text}\n\n{MARK}", reply_to=src_id)
        st = _state()
        st.setdefault("posted", []).append(pid)
        _save(st)
    except Exception as e:
        log.warning("O'rganish hisoboti kanalga joylanmadi: %s", e)
    send_files(text, [])


QUIET = 90  # kanalda shuncha soniya yangi post bo'lmasa - paket (albom + topshiriq + rasmlar + musiqa) to'liq deb olinadi
BATCH = 600  # albom bilan bir paket: ±10 daqiqa ichidagi matn, rasm va audio


def _poll_channel(notify) -> None:
    from datetime import datetime, timezone
    from . import tg_account
    if not tg_account.authorized():
        return
    state = _state()
    last = state.get("channel_last", 0)
    posted = set(state.get("posted", []))
    folder = config.data_dir / "inbox" / "studio"
    folder.mkdir(parents=True, exist_ok=True)

    async def go(client):
        msgs = [m async for m in client.iter_messages(CHANNEL, limit=40, min_id=last)]
        if not msgs:
            return None
        newest = max(m.date for m in msgs)
        if (datetime.now(timezone.utc) - newest).total_seconds() < QUIET:
            return None  # egasi hali yuboryapti - paket tugashini kutamiz
        got = []
        for m in sorted(msgs, key=lambda x: x.id):
            if m.id in posted or MARK in (m.text or ""):
                continue  # Ali o'zi joylagan
            mime = (m.file.mime_type or "") if m.file else ""
            kind = ("video" if m.video or mime.startswith("video/") else
                    "photo" if m.photo or mime.startswith("image/") else
                    "audio" if m.audio or m.voice or mime.startswith("audio/") else "text" if m.text else "")
            if not kind:
                continue
            path = await m.download_media(file=str(folder)) if kind != "text" else None
            got.append({"kind": kind, "id": m.id, "path": path, "text": m.text or "", "group": m.grouped_id,
                        "reply": m.reply_to_msg_id, "at": m.date.timestamp()})
        return got, max(m.id for m in msgs)
    try:
        res = tg_account._run(go)
    except Exception as e:
        log.warning("Kanal kuzatilmadi: %s", e)
        return
    if res is None:
        return
    items, top = res
    fresh = _state()
    fresh["channel_last"] = max(fresh.get("channel_last", 0), top)
    _save(fresh)

    # Videolar: albom (bir nechta klip) - bitta video; atrofidagi matn - topshiriq, rasm - B-roll, audio - musiqa
    videos = [x for x in items if x["kind"] == "video" and x["path"]]
    albums: dict = {}
    for x in videos:
        albums.setdefault(x["group"] or f"one{x['id']}", []).append(x)
    used: set[int] = set()
    for clips in albums.values():
        clips.sort(key=lambda x: x["id"])
        t0 = clips[0]["at"]
        near = [x for x in items if x["kind"] != "video" and abs(x["at"] - t0) <= BATCH and not x["reply"]]
        used.update(x["id"] for x in near)
        brief = "\n\n".join(t for t in [*(c["text"] for c in clips), *(x["text"] for x in near if x["kind"] == "text")] if t)
        photos = [x["path"] for x in near if x["kind"] == "photo" and x["path"]]
        music = next((x["path"] for x in near if x["kind"] == "audio" and x["path"]), "")
        paths = [c["path"] for c in clips]
        if LEARN.search(brief):  # «/organ» - namuna: montaj emas, uslubni o'rganish
            threading.Thread(target=learn, args=(paths, brief, clips[0]["id"], notify), daemon=True).start()
        else:
            threading.Thread(target=auto_edit, args=(paths, brief, clips[0]["id"], notify, photos, music),
                             daemon=True).start()
    # Alohida tashlangan audio - musiqa kutubxonasiga (izohdagi so'z bo'yicha kayfiyat: cinematic/energetic/calm)
    for x in items:
        if x["kind"] == "audio" and x["path"] and x["id"] not in used:
            from .skills.music import save_track
            dest = save_track(x["path"], x["text"])
            notify(f"🎵 Musiqa kutubxonaga qo'shildi: {dest.parent.name}/{dest.name}")
    # Videosiz rasmlar: kadr so'roviga javob (B-roll) yoki kreativ brif
    for x in items:
        if x["kind"] != "photo" or not x["path"] or x["id"] in used:
            continue
        req = _state().get("requests", {}).get(str(x["reply"])) if x["reply"] else None
        if req is not None:
            st = _state()
            st["requests"][str(x["reply"])]["images"].append(x["path"])
            _save(st)
            got_n = len(st["requests"][str(x["reply"])]["images"])
            notify(f"🖼 Qo'shimcha kadr: {got_n}/{req['need']}")
            if got_n >= req["need"]:
                threading.Thread(target=_broll, args=(str(x["reply"]), notify), daemon=True).start()
            continue
        full, note = add_image(x["path"], x["text"])
        if note:
            notify(note)
        if full:
            threading.Thread(target=_build_and_send, args=(full["id"], notify), daemon=True).start()


def _build_and_send(bid: int, notify) -> None:
    try:
        res = build(bid)
    except Exception as e:
        notify(f"⚠️ #B{bid} video yig'ilmadi: {e}")
        return
    send_files(res["text"], res["files"])


def send_files(text: str, files: list[str], queue: bool = True) -> bool:
    """Natijani egasiga Telegram bot orqali yuboradi (video - video bo'lib, qolgani - fayl).
    Internet uzilgan bo'lsa - navbatga qo'yiladi, kanal kuzatuvi har daqiqada qayta urinadi."""
    api = f"https://api.telegram.org/bot{config.telegram_token}"
    uid = config.telegram_owner_id
    if not (config.telegram_token and uid):
        return False
    original = (text, list(files))
    big = [f for f in files if Path(f).is_file() and Path(f).stat().st_size > 45 * 1024 * 1024]
    if big:  # Telegram bot 50 MB dan katta fayl yubora olmaydi (4K video) - kanaldagi postga havola
        text += f"\n\n🎬 Video katta ({Path(big[0]).stat().st_size // 1048576} MB) - kanalda ko'ring: https://t.me/{CHANNEL}"
        files = [f for f in files if f not in big]
    try:
        httpx.post(api + "/sendMessage", data={"chat_id": uid, "text": text[:4000]}, timeout=30).raise_for_status()
        for f in files:
            kind, field = ("sendVideo", "video") if f.endswith(".mp4") else ("sendDocument", "document")
            with open(f, "rb") as fh:
                httpx.post(f"{api}/{kind}", data={"chat_id": uid}, files={field: (Path(f).name, fh)},
                           timeout=300).raise_for_status()
        return True
    except (httpx.HTTPError, OSError) as e:
        log.warning("Studio natijasi yuborilmadi: %s", e)
        if queue:
            state = _state()
            state.setdefault("pending_send", []).append({"text": original[0], "files": original[1]})
            _save(state)
        return False


def flush_pending() -> None:
    """Internet uzilganda yuborilmay qolgan natijalar: kanalga joylash va egasiga yuborish (navbat tartibida)."""
    from . import tg_account
    state = _state()
    posts, sends = state.get("pending_post", []), state.get("pending_send", [])
    if not posts and not sends:
        return
    left_posts = []
    for p in posts:
        if not Path(p["out"]).is_file():
            continue
        try:
            pid = tg_account.send_file(CHANNEL, p["out"], f"{p.get('caption', '')}\n\n{MARK}"[:1024], reply_to=p.get("src"))
            state.setdefault("posted", []).append(pid)
            log.info("Kechikkan montaj kanalga joylandi: %s", Path(p["out"]).name)
        except Exception as e:
            log.info("Kechikkan montaj hali joylanmadi: %s", e)
            left_posts.append(p)
    state["pending_post"] = left_posts
    _save(state)
    left_sends = []
    for item in sends:
        if left_sends or not send_files("📬 (internet uzilganda yuborilmay qolgan edi)\n" + item["text"],
                                        [f for f in item["files"] if Path(f).is_file()], queue=False):
            left_sends.append(item)
    state = _state()
    state["pending_send"] = left_sends
    _save(state)


EDIT_ASK = re.compile(r"(kanal|канал)\S*.{0,80}(video|видео|klip|клип|reels|рилс).{0,80}(montaj|монтаж|ko['ʻ‘’]?r|кор|кўр)|"
                      r"(video|видео)\S*.{0,40}(montaj|монтаж)\S*.{0,40}(kanal|канал)", re.I | re.S)


def is_edit_request(text: str) -> bool:
    """«Kanalga video tashladim, ko'r va montaj qil» - kanaldagi oxirgi videoni montaj qilish so'rovi."""
    return bool(EDIT_ASK.search(text or ""))


def edit_latest(notify) -> str:
    """Egasi so'raganda: yuborilmay qolgan montaj bo'lsa - uni yuboradi, bo'lmasa kanaldagi oxirgi video(albom)ni
    (yonidagi topshiriq matni, rasm va musiqa bilan) qayta montaj qiladi."""
    from . import tg_account
    state = _state()
    if state.get("pending_post") or state.get("pending_send"):
        threading.Thread(target=flush_pending, daemon=True).start()
        return ("🎬 Montaj tayyor edi, lekin internet uzilgani uchun yuborilmay qolgan - hozir kanalga (videoga javob "
                "qilib) va sizga yuboryapman.")
    if not tg_account.authorized():
        return "⚠️ Kanalni o'qish uchun Telegram akkaunt ulanmagan (/tg-login)."
    folder = config.data_dir / "inbox" / "studio"
    folder.mkdir(parents=True, exist_ok=True)

    async def go(client):
        msgs = [m async for m in client.iter_messages(CHANNEL, limit=40) if MARK not in (m.text or "")]
        vids = [m for m in msgs if m.video or (m.file and (m.file.mime_type or "").startswith("video/"))]
        if not vids:
            return None
        last = vids[0]
        clips = [m for m in vids if last.grouped_id and m.grouped_id == last.grouped_id] or [last]
        t0 = min(m.date.timestamp() for m in clips)
        near = [m for m in msgs if m not in clips and abs(m.date.timestamp() - t0) <= BATCH and not m.reply_to_msg_id]
        paths = [await m.download_media(file=str(folder)) for m in sorted(clips, key=lambda m: m.id)]
        photos = [await m.download_media(file=str(folder)) for m in near if m.photo]
        audio = next((m for m in near if m.audio or m.voice), None)
        music = await audio.download_media(file=str(folder)) if audio else ""
        brief = "\n\n".join(t for t in [*(m.text for m in clips), *(m.text for m in near if not m.media)] if t)
        return paths, brief, min(m.id for m in clips), photos, music
    try:
        got = tg_account._run(go)
    except Exception as e:
        return f"⚠️ Kanal o'qilmadi: {str(e)[:300]}"
    if not got:
        return f"Kanalda (@{CHANNEL}) video topilmadi - videoni kanalga tashlang, men o'zim montaj qilaman."
    paths, brief, src, photos, music = got
    threading.Thread(target=auto_edit, args=(paths, brief, src, notify, photos, music), daemon=True).start()
    return (f"🎬 Kanaldagi oxirgi videoni oldim ({len(paths)} ta klip"
            + (f", {len(photos)} ta rasm" if photos else "") + (", musiqa" if music else "") + ") - montaj qilyapman. "
            "Tayyor bo'lgach kanalga (videoga javob qilib) va sizga yuboraman.")


def loop(notify) -> None:
    while True:
        time.sleep(60)
        try:
            flush_pending()
            _poll_channel(notify)
        except Exception:
            log.exception("Studio kanal kuzatuvi xatosi")


def start_watch(notify) -> None:
    threading.Thread(target=loop, args=(notify,), daemon=True, name="studio").start()
