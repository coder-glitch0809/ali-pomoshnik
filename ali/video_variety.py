"""Topic rotation, visual direction and the owner's reusable media library."""
import json
import re
import threading
from pathlib import Path

from .config import config

LIBRARY = config.data_dir / "video_media.json"
LOCK = threading.RLock()
STYLES = (
    "photorealistic editorial photography, natural daylight, teal and cream palette",
    "isometric 3D product illustration, cobalt and coral palette, clean studio lighting",
    "cinematic documentary photography, warm amber and charcoal palette",
    "paper cut editorial illustration, emerald and ivory palette, layered depth",
)
TOPICS = (
    "Lightbox: tungi ko'rinishni tekshirish; yorug'lik bir tekis tarqalsin; yozuv uzoqdan o'qilsin; elektr ulanishini mutaxassis tekshirsin",
    "Banner: bitta asosiy taklif; uzoqdan o'qiladigan katta yozuv; fon bilan kuchli kontrast; aloqa raqamini aniq joylashtiring",
    "Target: auditoriyani tanlash; mahsulot kimga kerakligini yozing; alohida auditoriyalarni sinang; natijani murojaatlar bilan solishtiring",
    "Hajmli harflar: material tanlash; tashqi muhitni hisobga oling; bino rangiga mos kontrast tanlang; o'rnatish joyini o'lchang",
    "Reels: birinchi kadr; mahsulotni darhol ko'rsating; bitta muammoni tushuntiring; keyingi harakatni aniq ayting",
    "Vizitka: kerakli ma'lumotlar; ism va xizmatni aniq yozing; telefon raqamini tekshiring; bosmadan oldin maketni ko'ring",
    "Peshlavha: joylashuv; piyoda yo'lidan ko'rinishni tekshiring; daraxt to'sib qolmasin; kunduzgi va tungi ko'rinishni solishtiring",
    "Reklama byudjeti: sinov rejasi; kichik sinovdan boshlang; xarajat va murojaatni yozib boring; natijaga qarab rejani yangilang",
)


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
    for scene in data["scenes"]:
        scene["image"] = f"Visual direction: {style}. {scene.get('image', '')}"


def register(path, caption=""):
    path = Path(path).resolve()
    root = (config.data_dir / "inbox").resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"}:
        return
    with LOCK:
        entries = library()
        entries = [e for e in entries if e["path"] != str(path)]
        entries.append({"path": str(path), "caption": str(caption)[:2000]})
        LIBRARY.parent.mkdir(parents=True, exist_ok=True)
        tmp = LIBRARY.with_suffix(".tmp")
        tmp.write_text(json.dumps(entries[-500:], ensure_ascii=False), encoding="utf-8")
        tmp.replace(LIBRARY)


def library():
    try:
        entries = json.loads(LIBRARY.read_text(encoding="utf-8"))
        return entries if isinstance(entries, list) else []
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
        path = Path(entry["path"]).resolve()
        hit = len(query & words(entry.get("caption", "")))
        if hit >= 2 and path.is_relative_to(root) and path.is_file() and str(path) not in used:
            candidates.append((hit, str(path)))
    if not candidates:
        return None
    path = max(candidates)[1]
    used.add(path)
    return Path(path)
