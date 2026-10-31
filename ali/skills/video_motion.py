"""Motion graphics, speed ramp, dinamik o'tishlar va namunadan uslub o'rganish (/organ) - Video montajchi uchun.

- ramp_clip: speed ramp - normal -> tez (2.5x) -> slow-motion (0.5x) - harakatli kadrlar (o'rnatish, yig'ish, yonish).
- join_dynamic: bo'laklarni dinamik o'tishlar bilan ulash (zoomin, slideleft, fadewhite, smoothup...).
- progress_bar: ekran pastida video davomida o'sib boruvchi chiziq (tomosha oxirigacha ushlab turadi).
- kinetic_hook: hook so'zlari navbat bilan pastdan "uchib" chiqadi (ASS animatsiya).
- analyze_style: namuna videoni o'lchaydi (kesimlar, kadr uzunligi, harakat, ovoz) + AI kadrlarni ko'radi ->
  qayta ishlatiladigan uslub "retsepti" (data/video_styles.json + Video montajchi bilimi).
"""
import json
import re
import time
from pathlib import Path

from ..config import config
from . import skill
from .video_edit import FPS, H, W, _fit, _run, _src, info

STYLES = config.data_dir / "video_styles.json"
TRANSITIONS = ("zoomin", "slideleft", "smoothup", "fadewhite", "circleopen", "slideright", "fade")
ACCENT_BAR = "0xFFE500"


def ramp_clip(src: str, a: float, b: float, out: Path, has_audio: bool = True) -> Path:
    """Speed ramp: [a,b] bo'lagi 3 qismga: 35% normal, 30% tez (2.5x), 35% slow-motion (0.5x)."""
    d = b - a
    cuts = [(a, a + d * 0.35, 1.0), (a + d * 0.35, a + d * 0.65, 2.5), (a + d * 0.65, b, 0.5)]
    chains, labels = [], []
    for k, (x, y, sp) in enumerate(cuts):
        chains.append(f"[0:v]trim={x:.3f}:{y:.3f},setpts=(PTS-STARTPTS)/{sp},{_fit('crop')},setsar=1,"
                      f"{'minterpolate=fps=30:mi_mode=blend,' if sp < 1 else ''}format=yuv420p[v{k}]")
        if has_audio:
            tempo = ",".join(["atempo=2.0", "atempo=1.25"]) if sp == 2.5 else f"atempo={sp}"
            chains.append(f"[0:a]atrim={x:.3f}:{y:.3f},asetpts=PTS-STARTPTS,{tempo}[a{k}]")
        labels.append(f"[v{k}]" + (f"[a{k}]" if has_audio else ""))
    chains.append(f"{''.join(labels)}concat=n=3:v=1:a={int(has_audio)}[v]" + ("[a]" if has_audio else ""))
    silent = [] if has_audio else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]  # o'tishlar uchun ovoz yo'li shart
    _run(["-i", src, *silent, "-filter_complex", ";".join(chains), "-map", "[v]",
          "-map", "[a]" if has_audio else "1:a", "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
          "-c:a", "aac", "-ar", "48000", "-ac", "2", str(out)])
    return out


def join_dynamic(parts: list[Path], out: Path, transitions: list[str] | None = None, dur: float = 0.3) -> Path:
    """Bo'laklarni xfade o'tishlari bilan ulaydi (ovoz - acrossfade). Barcha bo'laklar bir xil o'lcham/fps/ovozli."""
    if len(parts) == 1:
        return parts[0]
    lens = [info(p)["duration"] for p in parts]
    inputs = [x for p in parts for x in ("-i", str(p))]
    v, a, chain, offset = "[0:v]", "[0:a]", [], 0.0
    for n in range(1, len(parts)):
        kind = (transitions or [])[n - 1] if transitions and n - 1 < len(transitions) else TRANSITIONS[(n - 1) % len(TRANSITIONS)]
        kind = kind if kind in TRANSITIONS else "fade"
        offset += lens[n - 1] - dur
        chain.append(f"{v}[{n}:v]xfade=transition={kind}:duration={dur}:offset={offset:.3f}[v{n}]")
        chain.append(f"{a}[{n}:a]acrossfade=d={dur}[a{n}]")
        v, a = f"[v{n}]", f"[a{n}]"
    _run([*inputs, "-filter_complex", ";".join(chain), "-map", v, "-map", a, "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", str(out)])
    return out


def progress_bar(duration: float, height: int = 10) -> str:
    """drawbox filtri: pastda sariq chiziq 0 dan to'liq kenglikkacha o'sadi."""
    return f"drawbox=x=0:y=ih-{height}:w='iw*min(t/{max(duration, 0.1):.2f},1)':h={height}:color={ACCENT_BAR}@0.95:t=fill"


def kinetic_hook(text: str, start: float, end: float, ass_time) -> str:
    """Hook so'zlari navbat bilan pastdan ko'tarilib chiqadi (har so'z 0.12 s kechikish), oxirida birga yo'qoladi."""
    emoji = re.compile("[\U00010000-\U0010FFFF\u2600-\u27BF\uFE0F\u200D]")
    words = emoji.sub("", " ".join((text or "").split())).split()[:7]
    if not words or end - start < 0.6:
        return ""
    words[-1] = words[-1].rstrip(" —–-,:;")
    rows, line = [], []
    for w in words:  # 2-3 so'zli qatorlar
        line.append(w)
        if len(" ".join(line)) >= 14:
            rows.append(line)
            line = []
    if line:
        rows.append(line)
    out = []
    for r, row in enumerate(rows):  # har qator 0.2 s kechikib, pastdan ko'tarilib chiqadi
        y, text_row = 300 + r * 105, " ".join(row).upper()
        out.append(f"Dialogue: 2,{ass_time(start + r * 0.2)},{ass_time(end)},Title,,0,0,0,,"
                   f"{{\\an8\\move(540,{y + 60},540,{y},0,220)\\fad(120,150)\\t(0,140,\\fscx112\\fscy112)"
                   f"\\t(140,260,\\fscx100\\fscy100)}}{text_row}")
    return "\n".join(out) + "\n"


# ---------------- /organ: namuna videodan uslub o'rganish ----------------
STYLE_TASK = """Sen tajribali Reels montaj rejissyorisan. Egam namuna sifatida video tashladi - shu montaj USLUBINI o'rgan.
Biriktirilgan rasmlar - videodan kadrlar (boshidan oxirigacha). O'lchovlar: {metrics}
Egam izohi: {caption}

Aniq, qayta ishlatiladigan "retsept" yoz (umumiy gap emas). FAQAT JSON:
{{"name": "uslub nomi (2-4 so'z)", "pacing": "ritm (kadr uzunligi, kesimlar/daqiqa)",
  "hook": "birinchi 3 soniyada nima qilingan", "text_style": "yozuvlar: joyi, shrift, rang, animatsiya",
  "transitions": ["xfade turlaridan: zoomin, slideleft, smoothup, fadewhite, circleopen, slideright, fade"],
  "effects": ["speed ramp / zoom / shake / flash / progress bar / B-roll ..."],
  "color": "rang korreksiyasi", "music": "musiqa va ovoz", "speed_ramp": true,
  "progress_bar": false, "avg_shot": 1.5, "lessons": ["Ali montajda takrorlashi kerak bo'lgan 3-5 aniq qoida"]}}"""


def measure(video: Path) -> dict:
    """Ob'ektiv o'lchovlar: kesimlar (sahna almashishi), o'rtacha kadr uzunligi, ovoz balandligi."""
    i = info(video)
    log = _run(["-i", str(video), "-vf", "select='gt(scene,0.32)',showinfo", "-an", "-f", "null", "-"])
    cuts = [float(x) for x in re.findall(r"pts_time:([\d.]+)", log)]
    loud = re.search(r"I:\s+(-?[\d.]+) LUFS", _run(["-i", str(video), "-af", "ebur128", "-f", "null", "-"])) if i["audio"] else None
    shots = len(cuts) + 1
    return {"duration": round(i["duration"], 1), "size": f"{i['width']}x{i['height']}", "cuts": len(cuts),
            "avg_shot": round(i["duration"] / shots, 2), "cuts_per_min": round(len(cuts) / max(i["duration"], 1) * 60, 1),
            "loudness_lufs": float(loud.group(1)) if loud else None, "audio": i["audio"]}


def load_styles() -> list[dict]:
    try:
        return json.loads(STYLES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def latest_style() -> dict | None:
    styles = load_styles()
    return styles[-1] if styles else None


def analyze_style(video: str, caption: str = "") -> dict:
    """Namuna videoni o'rganadi: o'lchovlar + AI kadrlarni ko'radi -> retsept saqlanadi va Video montajchi bilimiga yoziladi."""
    import tempfile
    from .. import local_ai
    from ..memory import memory
    src = _src(video)
    metrics = measure(src)
    with tempfile.TemporaryDirectory() as tmp:
        frames = []
        for k in range(8):
            f = Path(tmp) / f"s{k}.jpg"
            try:
                _run(["-ss", f"{metrics['duration'] * (k + 0.5) / 8:.2f}", "-i", str(src), "-frames:v", "1",
                      "-vf", "scale=540:-1", str(f)])
                frames.append(str(f))
            except RuntimeError:
                pass
        got = local_ai.ask_pro(STYLE_TASK.format(metrics=json.dumps(metrics, ensure_ascii=False), caption=caption or "-"),
                               300, None, frames) if local_ai.access() is True else None
    try:
        raw = got[1] if got else ""
        style = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (ValueError, TypeError):  # AI band - o'lchovlardan aniq qoidalar (AI qaytgach to'liqroq tahlil)
        shot, cpm = metrics["avg_shot"], metrics["cuts_per_min"]
        pace = "juda tez" if shot < 1.5 else "tez" if shot < 3 else "o'rtacha" if shot < 5 else "sekin"
        style = {"name": (caption or "Namuna")[:40], "pacing": f"{pace}: o'rtacha kadr {shot} s, {cpm} kesim/daqiqa",
                 "avg_shot": shot, "transitions": [], "effects": [],
                 "lessons": [f"Kadrlarni o'rtacha {shot} s atrofida ushla ({pace} ritm)",
                             f"Daqiqasiga ~{cpm:.0f} ta kesim qil",
                             "Video uzunligi namunaga yaqin bo'lsin: ~" + str(metrics["duration"]) + " s"],
                 "note": "AI tahlili hozir band edi - qoidalar o'lchovlardan chiqarildi"}
    style.update(metrics=metrics, at=time.strftime("%Y-%m-%d %H:%M"))
    style["avg_shot"] = style.get("avg_shot") or metrics["avg_shot"]
    styles = (load_styles() + [style])[-20:]
    STYLES.write_text(json.dumps(styles, ensure_ascii=False, indent=1), encoding="utf-8")
    memory.add_knowledge(f"[video_montajchi] Namuna uslub: {style.get('name', 'Namuna')}",
                         json.dumps({k: v for k, v in style.items() if k != "metrics"}, ensure_ascii=False)
                         + f"\nO'lchovlar: {json.dumps(metrics, ensure_ascii=False)}")
    return style


def style_text(style: dict) -> str:
    m = style.get("metrics", {})
    return (f"🎓 O'rgandim: «{style.get('name', '')}»\n"
            f"📊 {m.get('duration')} s, {m.get('cuts')} ta kesim, o'rtacha kadr {m.get('avg_shot')} s "
            f"({m.get('cuts_per_min')} kesim/daqiqa), ovoz {m.get('loudness_lufs')} LUFS\n"
            f"⚡ Ritm: {style.get('pacing', '')}\n🪝 Hook: {style.get('hook', '')}\n🔤 Yozuvlar: {style.get('text_style', '')}\n"
            f"🔀 O'tishlar: {', '.join(style.get('transitions', []))}\n✨ Effektlar: {', '.join(style.get('effects', []))}\n"
            f"🎨 Rang: {style.get('color', '')}\n🎵 Ovoz: {style.get('music', '')}\n\n📌 Qoidalar:\n"
            + "\n".join(f"• {x}" for x in style.get("lessons", [])[:5])
            + "\n\nKeyingi montajlarda shu uslubni qo'llayman.")


@skill(
    description="Namuna videodan montaj uslubini o'rganadi (kesimlar, ritm, o'tishlar, yozuvlar, effektlar, rang) va keyingi "
                "montajlarda qo'llaydi. Kanalga video «/organ» izohi bilan tashlansa avtomatik ishlaydi.",
    params={"path": {"type": "string", "description": "Namuna video yo'li yoki 'oxirgi'"},
            "caption": {"type": "string", "description": "Egasining izohi (nimasi yoqqani)"}},
    required=[],
)
def video_learn_style(path: str = "oxirgi", caption: str = "") -> str:
    return style_text(analyze_style(path, caption))
