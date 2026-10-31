"""Video uchun fon musiqasi: 1) paketdagi trek; 2) kutubxona (data/music - kanalga tashlangan audiolar, kayfiyat bo'yicha);
3) kutubxona bo'sh bo'lsa - FFmpeg bilan sintez qilingan musiqa (mualliflik huquqi muammosi yo'q, internetsiz).

Kayfiyatlar: cinematic (premium, sekin pad + chuqur bass, ~100 BPM), energetic (jarayon/oldin-keyin, zarba + bass, ~120 BPM),
calm (maslahat/gapiruvchi video ostida, yumshoq pad).
"""
import random
import re
import shutil
from pathlib import Path

from ..config import config
from . import skill
from .video_edit import _run

LIB = config.data_dir / "music"
MOODS = ("cinematic", "energetic", "calm")
_MOOD_WORDS = {"cinematic": r"cinemat|kinemat|premium|luxury|epic|hashamat", "energetic": r"energ|tez|dinamik|beat|drive|upbeat",
               "calm": r"calm|tinch|sokin|lofi|lo-fi|yumshoq|chill"}


def mood_of(text: str) -> str:
    for mood, pat in _MOOD_WORDS.items():
        if re.search(pat, text or "", re.I):
            return mood
    return "energetic"


def save_track(path: str, caption: str = "") -> Path:
    """Kanalga tashlangan audioni kutubxonaga saqlaydi (izohdagi so'zlar bo'yicha kayfiyat papkasiga)."""
    folder = LIB / mood_of(caption)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / Path(path).name
    shutil.copy(path, dest)
    return dest


def pick(mood: str) -> str:
    """Kutubxonadan shu kayfiyatdagi (bo'lmasa istalgan) trek."""
    files = [p for p in (LIB / mood).glob("*") if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac")]
    if not files:
        files = [p for p in LIB.rglob("*") if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac")]
    return str(random.choice(files)) if files else ""


# Akkord ketma-ketliklari (Hz): Am - F - C - G (premium/kinematografik), Em - C - G - D (energik)
_CHORDS = {"cinematic": [(110.0, 130.81, 164.81), (87.31, 110.0, 130.81), (130.81, 164.81, 196.0), (98.0, 123.47, 146.83)],
           "energetic": [(82.41, 98.0, 123.47), (130.81, 164.81, 196.0), (98.0, 123.47, 146.83), (146.83, 185.0, 220.0)],
           "calm": [(130.81, 164.81, 196.0), (110.0, 130.81, 164.81), (87.31, 110.0, 130.81), (98.0, 123.47, 146.83)]}


def generate(duration: float, mood: str = "cinematic", out: Path | None = None) -> str:
    """Sintez musiqa: akkord pad (har 4 takt almashadi) + bass + (energik/kinematografik) zarba, reverb va fade."""
    mood = mood if mood in MOODS else "cinematic"
    bpm = {"cinematic": 100, "energetic": 120, "calm": 85}[mood]
    bar = 4 * 60 / bpm  # bitta takt (soniya)
    chords = _CHORDS[mood]
    # pad: har akkord 2 takt; t ga qarab akkord tanlanadi (if zanjiri), yumshoq "nafas" (LFO)
    def chord_expr(k: int) -> str:
        return "+".join(f"sin(2*PI*{f}*t)+0.5*sin(2*PI*{f * 2}*t)" for f in chords[k])
    period = 2 * bar * len(chords)
    pad = chord_expr(len(chords) - 1)
    for k in range(len(chords) - 2, -1, -1):
        pad = f"if(lt(mod(t,{period:.4f}),{(k + 1) * 2 * bar:.4f}),{chord_expr(k)},{pad})"
    pad = f"0.045*({pad})*(0.75+0.25*sin(2*PI*t/{bar:.4f}))"
    beat = 60 / bpm
    kick = f"0.55*sin(2*PI*52*t)*exp(-9*mod(t,{beat:.4f}))" if mood != "calm" else "0"
    bass_root = f"0.18*sin(2*PI*{chords[0][0] / 2}*t)*(0.6+0.4*exp(-4*mod(t,{beat:.4f})))"
    expr = f"{pad}+{kick}+{bass_root}"
    out = out or (config.data_dir / "music_gen" / f"{mood}_{int(duration)}s.m4a")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        return str(out)
    _run(["-f", "lavfi", "-i", f"aevalsrc='{expr}':s=48000:d={duration + 1:.1f}",
          "-af", f"lowpass=f=5200,aecho=0.8:0.6:60|120:0.25|0.15,afade=t=in:d=1.5,"
                 f"afade=t=out:st={max(0.0, duration - 2):.2f}:d=2,loudnorm=I=-16:TP=-1.5,aformat=channel_layouts=stereo",
          "-c:a", "aac", "-b:a", "192k", str(out)])
    return str(out)


def for_video(duration: float, mood: str) -> tuple[str, str]:
    """(trek yo'li, manba): kutubxona bo'lsa - undan, bo'lmasa sintez."""
    track = pick(mood)
    if track:
        return track, "kutubxona"
    return generate(duration, mood), "sintez"


FIND = ("Chrome'da Pixabay Music (https://pixabay.com/music/search/{q}/) saytidan '{mood}' kayfiyatdagi, so'zsiz "
        "instrumental, 30-120 soniyalik bitta trekni tanla va yuklab ol (Download tugmasi). Kirish so'ralsa - to'xta va "
        "egasiga «Ali'ning Chrome'ida pixabay.com ga kiring» de.")
QUERIES = {"cinematic": "cinematic%20corporate", "energetic": "upbeat%20energetic", "calm": "calm%20ambient"}


def find_online(mood: str, ready: list[str], confirm=None) -> str:
    """Internetdan (Pixabay Music - reklamada bepul ishlatish mumkin) trek topib kutubxonaga yuklaydi."""
    from .. import browser
    mood = mood if mood in MOODS else "cinematic"
    return browser.agent(FIND.format(q=QUERIES[mood], mood=mood), ready, confirm, steps=10, download_to=LIB / mood)


@skill(
    description="Video uchun fon musiqasi tayyorlaydi: kutubxonadan (kanalga tashlangan treklar) yoki o'zi sintez qiladi "
                "(mualliflik huquqi muammosiz). mood: cinematic / energetic / calm.",
    params={"duration": {"type": "number", "description": "Davomiylik (soniya)"},
            "mood": {"type": "string", "enum": list(MOODS), "description": "Kayfiyat"}},
    required=["duration"],
)
def make_music(duration: float, mood: str = "cinematic") -> str:
    track, src = for_video(float(duration), mood)
    from .. import outbox
    out = outbox.new_path(f"musiqa {mood}", Path(track).suffix.lstrip(".") or "m4a")
    shutil.copy(track, out)
    outbox.register(out)
    return f"Musiqa tayyor ({src}, {mood}): {out.name}"
