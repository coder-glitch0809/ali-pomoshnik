"""Professional Reels montaji - bitta buyruqda (gapiruvchi yoki xom video uchun).

1) Jump-cut: pauzalar kesiladi (silencedetect), har ikkinchi bo'lak 8% yaqinroq (punch-in) - "ikki kamera" effekti.
2) CapCut uslubidagi subtitr: 3-4 so'zli bloklar, aytilayotgan so'z sariq bo'ladi (ASS karaoke), "pop" animatsiya.
3) Ovoz: shovqin tozalash (afftdn) + Instagram standarti -14 LUFS (loudnorm). Musiqa - gapirganda o'zi pasayadi.
4) Rang: kontrast/to'yinganlik/aniqlik. Hook (boshida) va CTA (oxirida). Eksport: 1080x1920, 30 fps, CRF 18.
"""
import re
import tempfile
import textwrap
from pathlib import Path

from . import skill
from .video_edit import FPS, H, W, _done, _fit, _out, _run, _src, _srt, _text_file, info

PRO_FONT = "C\\:/Windows/Fonts/ariblk.ttf"  # hook/CTA uchun qalin shrift
ACCENT = "&H0000E5FF"  # aytilayotgan so'z rangi (ASS BGR: sariq)
_TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")
_EMOJI = re.compile("[\U00010000-\U0010FFFF☀-➿️‍]")


def _sec(ts: str) -> float:
    h, m, s, ms = _TS.match(ts.strip()).groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000


def _ass_time(t: float) -> str:
    cs = int(round(max(t, 0) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def speech_parts(path: Path, noise: str = "-33dB", min_silence: float = 0.45, pad: float = 0.08) -> list[tuple[float, float]]:
    """Gapirilgan qismlar (pauzalar kesiladi): [(boshlanish, tugash), ...]."""
    i = info(path)
    if not i["audio"] or i["duration"] < 2:
        return [(0.0, i["duration"])]
    log = _run(["-i", str(path), "-af", f"silencedetect=noise={noise}:d={min_silence}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    ends += [i["duration"]] * (len(starts) - len(ends))
    parts, cur = [], 0.0
    for s, e in zip(starts, ends):
        if s - cur > 0.25:
            parts.append((max(0.0, cur - pad), min(i["duration"], s + pad)))
        cur = e
    if i["duration"] - cur > 0.25:
        parts.append((max(0.0, cur - pad), i["duration"]))
    merged: list[list[float]] = []  # yaqin/juda ko'p bo'laklar birlashtiriladi (filtr grafi oshib ketmasin)
    for a, b in parts:
        if merged and (a - merged[-1][1] < 0.15 or len(merged) >= 60):
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged] or [(0.0, i["duration"])]


def karaoke_ass(srt: str) -> str:
    """SRT -> CapCut uslubidagi ASS: qisqa bloklar, so'z aytilganda sariq bo'ladi, kichik "pop"."""
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding\n"
            f"Style: Sub,Arial Black,76,{ACCENT},&H00FFFFFF,&H00000000,&H78000000,-1,0,0,0,100,100,0,0,1,7,3,2,70,70,560,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    lines = []
    for block in re.split(r"\n\s*\n", srt.strip()):
        m = re.search(r"([\d:,.]+)\s*-->\s*([\d:,.]+)\s*\n(.+)", block, re.S)
        if not m:
            continue
        start, end = _sec(m.group(1)), _sec(m.group(2))
        words = _EMOJI.sub("", " ".join(m.group(3).split())).split()
        if not words or end <= start:
            continue
        total = sum(len(w) + 2 for w in words)
        t = start
        for g in (words[i:i + 4] for i in range(0, len(words), 4)):
            weight = sum(len(w) + 2 for w in g)
            dur = (end - start) * weight / total
            ks = " ".join(f"{{\\k{max(1, round(dur * 100 * (len(w) + 2) / weight))}}}{w.upper()}" for w in g)
            pop = "{\\fad(40,40)\\t(0,90,\\fscx112\\fscy112)\\t(90,180,\\fscx100\\fscy100)}"
            lines.append(f"Dialogue: 0,{_ass_time(t)},{_ass_time(t + dur)},Sub,,0,0,0,,{pop}{ks}")
            t += dur
    return head + "\n".join(lines) + "\n"


@skill(
    description=(
        "PROFESSIONAL MONTAJ bitta buyruqda (gapiruvchi/xom video uchun eng yaxshisi): pauzalarni kesish (jump-cut), har "
        "kesimda punch-in zoom, CapCut uslubidagi animatsiyali subtitr (aytilayotgan so'z sariq), shovqin tozalash va "
        "Instagram ovoz standarti (-14 LUFS), rang korreksiyasi, ixtiyoriy hook/CTA va musiqa (gapirganda pasayadi), "
        "1080x1920 yuqori sifat."
    ),
    params={"path": {"type": "string", "description": "Video yo'li yoki 'oxirgi'"},
            "hook": {"type": "string", "description": "Boshidagi kuchli yozuv (0-2.5 s), ixtiyoriy"},
            "cta": {"type": "string", "description": "Oxiridagi chaqiriq (oxirgi 2.5 s), ixtiyoriy"},
            "music": {"type": "string", "description": "Fon musiqasi fayli (ixtiyoriy) - gapirganda o'zi pasayadi"},
            "cut_silence": {"type": "boolean", "description": "Pauzalarni kesish (standart ha)"},
            "subtitles": {"type": "boolean", "description": "Animatsiyali subtitr (standart ha)"}},
    required=[],
)
def video_pro(path: str = "oxirgi", hook: str = "", cta: str = "", music: str = "", cut_silence: bool = True,
              subtitles: bool = True) -> str:
    src, out, notes = _src(path), _out("pro montaj reels"), []
    i = info(src)
    vertical = i["height"] > i["width"]

    def base(n: int) -> str:
        """9:16 ga moslash; gorizontal video - xira fon bilan (har bo'lakda alohida nomlar - graf to'qnashmasin)."""
        if vertical:
            return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"
        return (f"split[s{n}a][s{n}b];[s{n}a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"boxblur=25:2[bg{n}];[s{n}b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg{n}];"
                f"[bg{n}][fg{n}]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={FPS}")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        # 1) Jump-cut + punch-in (har ikkinchi bo'lak 8% yaqinroq)
        parts = speech_parts(src) if cut_silence else [(0.0, i["duration"])]
        chains, labels = [], []
        for n, (a, b) in enumerate(parts):
            zoom = f",scale=iw*1.08:ih*1.08,crop={W}:{H}" if n % 2 else ""
            chains.append(f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS,{base(n)}{zoom},setsar=1,format=yuv420p[v{n}]")
            if i["audio"]:
                chains.append(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.02,"
                              f"afade=t=out:st={max(0.0, b - a - 0.03):.3f}:d=0.03[a{n}]")
            labels.append(f"[v{n}]" + (f"[a{n}]" if i["audio"] else ""))
        graph = chains + [f"{''.join(labels)}concat=n={len(parts)}:v=1:a={int(i['audio'])}[cv]" + ("[ca]" if i["audio"] else ""),
                          "[cv]eq=contrast=1.06:saturation=1.12:brightness=0.01,unsharp=5:5:0.5[v]"]
        if i["audio"]:
            graph.append("[ca]afftdn=nf=-25,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        cut = tmp_p / "cut.mp4"
        _run(["-i", str(src), "-filter_complex", ";".join(graph), "-map", "[v]", *(["-map", "[a]"] if i["audio"] else []),
              "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
              "-ar", "48000", str(cut)])
        ci = info(cut)
        if cut_silence and i["duration"] - ci["duration"] > 0.3:
            notes.append(f"{i['duration'] - ci['duration']:.1f} s pauza kesildi ({len(parts)} bo'lak, punch-in zoom)")
        # 2) Animatsiyali subtitr + hook/CTA + (bo'lsa) musiqa
        vf = []
        if subtitles and ci["audio"]:
            try:
                (tmp_p / "s.ass").write_text(karaoke_ass(_srt(cut, tmp_p)), encoding="utf-8")
                vf.append("subtitles=s.ass")
                notes.append("animatsiyali subtitr")
            except Exception as e:
                notes.append(f"subtitr qo'shilmadi ({str(e)[:80]})")
        for text, name, y, window in ((hook, "h.txt", "h*0.14", "lte(t,2.5)"),
                                      (cta, "c.txt", "h*0.68", f"gte(t,{max(0.0, ci['duration'] - 2.5):.2f})")):
            if text and text.strip():  # ekranga sig'sin: ~16 belgidan qatorlarga bo'linadi
                _text_file(textwrap.fill(" ".join(text.split()), 16), tmp_p, name)
                vf.append(f"drawtext=fontfile='{PRO_FONT}':textfile={name}:fontsize=70:fontcolor=white:expansion=none:line_spacing=10:"
                          f"borderw=7:bordercolor=black:x=(w-text_w)/2:y={y}:enable='{window}'")
        m = Path(music) if music else None
        if m and m.is_file() and ci["audio"]:
            graph2 = (f"[0:v]{','.join(vf) or 'null'}[v];[1:a]volume=0.35[m];[0:a]asplit[a1][a2];"
                      "[m][a2]sidechaincompress=threshold=0.04:ratio=10:attack=15:release=350[md];"
                      "[a1][md]amix=inputs=2:duration=first:dropout_transition=0,loudnorm=I=-14:TP=-1.5[a]")
            args = ["-i", "cut.mp4", "-stream_loop", "-1", "-i", str(m), "-filter_complex", graph2, "-map", "[v]",
                    "-map", "[a]", "-shortest", "-c:a", "aac", "-b:a", "192k"]
            notes.append("musiqa (gapirganda pasayadi)")
        else:
            args = ["-i", "cut.mp4", *(["-vf", ",".join(vf)] if vf else []), "-c:a", "copy"]
        _run([*args, "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p",
              "-r", str(FPS), "-movflags", "+faststart", str(out)], cwd=tmp_p)
    return _done(out, "Professional montaj: " + ", ".join(notes + ["rang va ovoz tozalandi", "1080x1920"]) + ".")
