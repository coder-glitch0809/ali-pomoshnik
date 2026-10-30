"""Video montaj - API kalitisiz: Pro ilova (Claude/ChatGPT/OmniRoute/Gemini) montaj REJASINI JSON qilib beradi,
Ali uni video_* vositalari bilan qadam-baqadam o'zi bajaradi (har qadam oldingi natija ustida).

Telegram'ga video yuborilsa: izohi (caption) - montaj topshirig'i; izohsiz bo'lsa - standart Reels ishlovi
(9:16 + avtomatik subtitr). Matnda "videoni montaj qil / reels qil / subtitr qo'sh..." deyilsa - oxirgi video olinadi.
"""
import json
import logging
import re
from pathlib import Path

from . import outbox

log = logging.getLogger("ali.montage")

TOOLS = ("video_reels", "video_join", "video_text", "video_subtitles", "video_music", "video_voiceover", "video_speed",
         "video_cover")
QUERY = re.compile(r"(video|видео|reels|рилс|ролик)\S*.{0,60}(montaj|монтаж|qirq|қирқ|kes|subtitr|субтитр|yozuv|ёзув|"
                   r"matn|матн|musiqa|мусиқа|ovoz|овоз|tezla|reels|рилс|birlashtir|бирлаштир|muqova|муқова|9:16)", re.I | re.S)
DEFAULT = [{"tool": "video_reels", "args": {"fit": "blur"}}, {"tool": "video_subtitles", "args": {}}]

PLAN = """Sen tajribali video montajchisan (Instagram Reels, targetolog va tashqi reklama kontenti).
Foydalanuvchi videosi: {video}
Topshiriq: {task}

Mavjud vositalar (har qadam OLDINGI qadam natijasi ustida ishlaydi, "path" ni yozma - Ali o'zi qo'yadi):
{tools}

Reels qoidalari: 9:16 (video_reels birinchi), birinchi 1-3 soniyada kuchli hook matni (video_text, top), nutq bo'lsa
subtitr (video_subtitles), oxirida CTA matni, musiqa past. Faqat topshiriqqa kerakli qadamlarni tanla (1-6 ta).
FAQAT JSON qaytar: {{"steps": [{{"tool": "video_reels", "args": {{...}}}}, ...], "note": "1 gapda nima qilinadi"}}"""


CREATE = re.compile(r"(video|видео|reels|рилс|ролик)\S*.{0,50}(yarat|яrat|ярат|qilib\s+ber|қилиб\s+бер|килиб\s+бер|"
                    r"tayyorla|тайёрла|генерац|generatsiya|ясаб|yasab|chiqar|чиқар)|"
                    r"(yarat|ярат|tayyorla|тайёрла|qilib\s+ber|қилиб\s+бер)\S*.{0,30}(video|видео|reels|рилс|ролик)", re.I | re.S)
EXISTING = re.compile(r"(oxirgi|охирги|yuborgan|юборган|shu|шу)\s+(video|видео)", re.I)


def is_query(text: str) -> bool:
    """Mavjud (yuborilgan) videoni montaj qilish so'rovi."""
    return bool(QUERY.search(text or "")) and not is_creation(text)


def is_creation(text: str) -> bool:
    """Video berilmagan - noldan yaratish so'rovi («targetolog haqida reels qilib ber»)."""
    return bool(CREATE.search(text or "")) and not EXISTING.search(text or "")


def create(task: str, registry, ready: list[str], progress=lambda note: None) -> str:
    """Ssenariy -> sahnalar, diktor ovozi, (bo'lsa) AI fon rasmlari, subtitr -> tayyor .mp4 (Video montajchi)."""
    skill = registry.get("make_content_video")
    if skill is None:
        raise RuntimeError("Video studiya plagini o'chirilgan (make_content_video yo'q)")
    m = re.search(r"(\d{2,3})\s*(s|soniya|сония|sek|сек)", task)
    duration = int(m.group(1)) if m else 30
    progress("🎞️ Video montajchi: ssenariy yozyapman, ovoz va sahnalarni tayyorlayapman (1-3 daqiqa)…")
    return skill.func(topic=task, duration_s=min(max(duration, 10), 90))


def _tools_text(registry) -> str:
    rows = []
    for name in TOOLS:
        s = registry.get(name)
        if s:
            params = {k: v for k, v in s.params.items() if k not in ("path", "paths")}
            rows.append(f"- {name}: {s.description[:220]} | args: {json.dumps(params, ensure_ascii=False)[:400]}")
    return "\n".join(rows)


def plan(task: str, video: str, registry, ready: list[str]) -> tuple[list[dict], str]:
    """AI montaj rejasi; AI bo'lmasa yoki rejani bera olmasa - standart (9:16 + subtitr)."""
    from .service import _ask_json
    if not task.strip() or not ready:
        return DEFAULT, "Standart Reels ishlovi: 9:16 + avtomatik subtitr"
    try:
        data = _ask_json(PLAN.format(video=video, task=task, tools=_tools_text(registry)), ready, 300)
        steps = [s for s in data.get("steps", []) if isinstance(s, dict) and s.get("tool") in TOOLS][:6]
        if steps:
            return steps, str(data.get("note", ""))[:300]
    except (ValueError, RuntimeError) as e:
        log.warning("Montaj rejasi olinmadi: %s", e)
    return DEFAULT, "Standart Reels ishlovi: 9:16 + avtomatik subtitr"


def run(task: str, path: str, registry, ready: list[str], progress=lambda note: None) -> str:
    """Rejani bajaradi. Natija fayllari outbox orqali avtomatik yuboriladi. Qaytaradi: hisobot matni."""
    from .skills import video_edit
    src = str(video_edit._src(path))
    i = video_edit.info(video_edit._src(src))
    steps, note = plan(task, f"{src} ({i['width']}x{i['height']}, {i['duration']:.1f} s, ovoz: {'bor' if i['audio'] else 'yo‘q'})",
                       registry, ready)
    progress(f"🎬 Montaj rejasi: {note or ', '.join(s['tool'] for s in steps)}")
    current, done = src, []
    for n, step in enumerate(steps, 1):
        skill = registry[step["tool"]]
        args = {k: v for k, v in (step.get("args") or {}).items() if k in skill.params and k not in ("path", "paths")}
        if step["tool"] == "video_join":
            continue  # birlashtirish - bir nechta video kerak, bitta video rejasida o'tkaziladi
        args["path"] = current
        if error := skill.validate(args):
            done.append(f"⚠️ {step['tool']}: {error}")
            continue
        progress(f"🎬 {n}/{len(steps)}: {step['tool']}…")
        before = outbox.mark()
        try:
            result = skill.func(**args)
        except Exception as e:
            done.append(f"⚠️ {step['tool']}: {str(e)[:200]}")
            continue
        made = [p for p in outbox.since(before) if p.suffix == ".mp4"]
        if made:
            if current != src:  # oldingi oraliq natija - faqat yakuniy video yuboriladi
                outbox.forget(Path(current))
            current = str(made[-1])
        done.append(f"✅ {result}")
    return (f"🎬 Montaj tayyor{(': ' + note) if note else ''}\n\n" + "\n".join(done) +
            "\n\nOxirgi fayl - tayyor video. O'zgartirish kerak bo'lsa yozing (masalan: «boshiga hook qo'sh: …»).")
