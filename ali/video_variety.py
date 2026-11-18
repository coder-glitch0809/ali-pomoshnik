"""Topic rotation, visual direction and the owner's reusable media library."""
import colorsys
import json
import random
import re
import threading
import time
import uuid
from pathlib import Path

from .config import config

LIBRARY = config.data_dir / "video_media.json"
LOCK = threading.RLock()
STYLES = (
    "cinematic commercial with character focus, shallow depth of field, dramatic moody lighting, professional color grading, motion blur",
    "high-end Instagram Reels style, fast-paced hook in first 2 seconds, vibrant colors, sharp focus, mobile-optimized framing",
    "outdoor LED billboard cinematic style, ultra-sharp resolution, massive visual impact, bright daylight visibility, clear character expressions",
    "dynamic cinematic slow-motion, smooth camera movement, film grain, professional lighting setup, engaging narrative pacing"
)
TOPICS = (
    "Character Hook: Birinchi kadrda mijoz muammosini ko'rsating; hayotiy vaziyat orqali qiziqtiring; xizmat foydasini aniq ayting",
    "Cinematic Slow-Motion: Mahsulot detalini yaqin kadrda ko'rsating; ustaning ish jarayonini sekinlashtiring; tayyor natijani yorug'likda namoyish eting",
    "Outdoor & Social Media Hybrid: Ko'chada peshlavha uzoqdan o'qilsin; telefonda asosiy yozuv yirik ko'rinsin; ikkala formatda aloqa manzilini ko'rsating",
    "Dynamic Storytelling: Tadbirkorning muammosidan boshlang; reklama yechimini jarayonda ko'rsating; yakunda mijozga keyingi qadamni ayting"
)
BACKGROUNDS = ("aurora", "grid", "rings", "ribbons")
GRAPHICS = ("orbits", "lines", "dots")


def _save(entries):
    """Keep prompt history separate from the uploaded-media retention limit."""
    media = [e for e in entries if e.get("path")][-500:]
    plans = [e for e in entries if e.get("type") == "visual_plan"][-200:]
    LIBRARY.parent.mkdir(parents=True, exist_ok=True)
    tmp = LIBRARY.with_suffix(".tmp")
    tmp.write_text(json.dumps(media + plans, ensure_ascii=False), encoding="utf-8")
    tmp.replace(LIBRARY)


def words(text):
    return set(re.findall(r"[\w]{4,}", str(text).lower())) - {"uchun", "bilan", "qanday", "video", "reklama"}


def repeated(data, history):
    title = words(data.get("title", ""))
    voice = words(" ".join(s.get("voice", "") for s in data.get("scenes", [])))
    for old in history:
        if data.get("topic") and words(data["topic"]) == words(old.get("topic", "")):
            return True
        for new, prior in ((title, words(old.get("title", ""))), (voice, words(old.get("script", "")))):
            if new and prior and len(new & prior) / len(new | prior) >= .65:
                return True
    return False


def fresh_topic(history):
    for topic in TOPICS:
        subject = topic.split(":")[0].lower()
        if not any(subject in (str(h.get("title", "")) + " " + str(h.get("topic", ""))).lower() for h in history):
            return topic
    raise ValueError("Yangi mavzular tugadi: kontent rejasiga yangi mavzu qo'shish kerak")


def direction(data, history):
    previous = history[-1].get("style") if history else None
    style = STYLES[len(history) % len(STYLES)]
    if style == previous:
        style = STYLES[(STYLES.index(style) + 1) % len(STYLES)]
    data["style"] = style
    with LOCK:
        entries = library()
        plans = [e for e in entries if e.get("type") == "visual_plan"]
        # Microsecond seeds stay exactly representable in JavaScript; persisted
        # scene counters also prevent collisions when two jobs start together.
        seed = max(time.time_ns() // 1000, max(
            (e.get("seed", 0) + max(1, len(e.get("scenes", []))) for e in plans), default=0))
        rng = random.Random(seed)
        data["visual_id"], data["seed"] = uuid.uuid4().hex, seed
        last = plans[-1]["scenes"][-1].get("visual", {}) if plans and plans[-1].get("scenes") else {}
        hue = rng.random()
        for index, scene in enumerate(data["scenes"]):
            background = rng.choice([b for b in BACKGROUNDS if b != last.get("background")])
            graphic = rng.choice([g for g in GRAPHICS if g != last.get("graphic")])
            scene_hue = (hue + index * .083 + rng.uniform(-.025, .025)) % 1
            palette = ["#%02x%02x%02x" % tuple(round(c * 255) for c in colorsys.hsv_to_rgb(
                (scene_hue + offset) % 1, saturation, value))
                for offset, saturation, value in ((0, .65, .18), (.08, .7, .65), (.5, .4, 1))]
            subject = str(scene.get("image") or scene.get("voice") or data.get("title", ""))[:600]
            visual = {"background": background, "graphic": graphic, "palette": palette, "seed": seed + index,
                      "background_prompt": f"{subject}. Layered {background} background, composition seed {seed + index}; no text.",
                      "graphic_prompt": f"Subtle animated {graphic} framing {scene.get('big', '')}; leave title and subtitle safe zones clear.",
                      "palette_prompt": f"Use {', '.join(palette)} for shadows, midtones and accents; maintain readable contrast."}
            scene["visual"] = visual
            scene["image"] = f"Visual direction: {style}. {background} backdrop; palette {', '.join(palette)}. {subject}."
            last = visual
        entries.append({"type": "visual_plan", "id": data["visual_id"], "seed": seed,
                        "title": data.get("title", ""), "style": style,
                        "format": data.get("format", "reels"), "hook": data.get("hook", ""),
                        "character": data.get("character", ""), "topic_sources": data.get("topic_sources", []),
                        "scenes": [{"image": s["image"], "visual": s["visual"], "voice": s.get("voice", ""),
                                    "big": s.get("big", ""), "section": s.get("section", "")}
                                   for s in data["scenes"]]})
        _save(entries)


def register(path, caption=""):
    path = Path(path).resolve()
    root = (config.data_dir / "inbox").resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"}:
        return
    with LOCK:
        entries = library()
        entries = [e for e in entries if e.get("path") != str(path)]
        entries.append({"path": str(path), "caption": str(caption)[:2000]})
        _save(entries)


def library():
    try:
        entries = json.loads(LIBRARY.read_text(encoding="utf-8"))
        return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []
    except (OSError, ValueError):
        return []


def select_media(scene, used):
    query = words(scene.get("voice", "") + " " + scene.get("big", ""))
    candidates = []
    root = (config.data_dir / "inbox").resolve()
    # Older uploads with descriptive filenames remain discoverable without an index.
    entries = library() + [{"path": str(p), "caption": p.stem} for p in root.rglob("*")
                           if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"}]
    for entry in entries:
        if not isinstance(entry.get("path"), str) or not entry["path"]:
            continue
        path = Path(entry["path"]).resolve()
        hit = len(query & words(entry.get("caption", "")))
        if hit >= 2 and path.is_relative_to(root) and path.is_file() and str(path) not in used:
            candidates.append((hit, str(path)))
    if not candidates:
        return None
    path = max(candidates)[1]
    used.add(path)
    return Path(path)
