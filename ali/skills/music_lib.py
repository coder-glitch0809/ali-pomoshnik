"""Musiqa xotirasi: egam tashlagan har videodan fon musiqasi ajratib olinadi va keyingi videolarda o'zi qo'yiladi.

1) Videoda nutq bo'lsa - ajratuvchi model (MDX-Net, ONNX, CPU) nutqni olib tashlaydi, musiqa qoladi.
2) Tekshiruv: ko'cha shovqini yoki sukunat musiqa deb olinmaydi (ritm va ohang o'lchanadi).
3) Bir xil trek ikki marta saqlanmaydi; kayfiyati (energetic/cinematic/calm) va tempi yoziladi.
Tanlash: mos kayfiyat, kam ishlatilgan va uzunroq trek birinchi.
"""
import hashlib
import json
import logging
import subprocess
import threading
from pathlib import Path

import numpy as np

from ..config import config
from .video_edit import ffmpeg

log = logging.getLogger("ali.music_lib")

LIB = config.data_dir / "music"
STATE = LIB / "tracks.json"
MODEL = config.data_dir / "models" / "mdx_inst.onnx"
MODEL_URL = "https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR-MDX-NET-Inst_HQ_3.onnx"
RATE = 44100
MIN_SECONDS = 10.0
_lock = threading.Lock()
N_FFT, HOP = 6144, 1024  # model parametrlari


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"tracks": {}, "seen": {}}


def _save(st: dict) -> None:
    LIB.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def _load_audio(path: Path) -> np.ndarray:
    """Stereo float (2, n), 44.1 kHz. Ovozi yo'q fayl - bo'sh."""
    raw = subprocess.run([ffmpeg(), "-v", "error", "-i", str(path), "-vn", "-ac", "2", "-ar", str(RATE), "-f", "f32le", "-"],
                         capture_output=True, timeout=600).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).T.copy() if raw else np.zeros((2, 0), np.float32)


def speech_share(mono: np.ndarray, rate: int = RATE) -> float:
    """Audioning qancha qismi nutq (0..1)."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    step = rate // 16000 or 1
    pcm = mono[::step].astype(np.float32)
    if not len(pcm):
        return 0.0
    spoken = get_speech_timestamps(pcm, VadOptions(threshold=.5))
    return sum(x["end"] - x["start"] for x in spoken) / len(pcm)


def _ensure_model() -> Path:
    if not MODEL.exists():
        import urllib.request
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        tmp = MODEL.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.replace(MODEL)
    return MODEL


def separate(audio: np.ndarray) -> np.ndarray:
    """Nutqni olib tashlaydi - faqat musiqa qoladi (2, n)."""
    import onnxruntime as ort
    sess = ort.InferenceSession(str(_ensure_model()), providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0]
    dim_f, dim_t = inp.shape[2], inp.shape[3]
    window = np.hanning(N_FFT + 1)[:-1].astype(np.float32)
    seg = HOP * (dim_t - 1)
    trim = N_FFT // 2
    chunk = seg - 2 * trim  # har bo'lakning ishonchli o'rtasi
    n = audio.shape[1]
    pad = np.concatenate([np.zeros((2, trim), np.float32), audio, np.zeros((2, seg), np.float32)], axis=1)
    out = np.zeros((2, n + seg), np.float32)
    for start in range(0, n, chunk):
        part = pad[:, start:start + seg]
        spec = np.zeros((1, 4, dim_f, dim_t), np.float32)
        specs = []
        for c in range(2):
            frames = np.stack([np.fft.rfft(np.pad(part[c], (trim, trim))[i * HOP:i * HOP + N_FFT] * window)
                               for i in range(dim_t)], axis=1)
            specs.append(frames)
            spec[0, c * 2] = frames[:dim_f].real
            spec[0, c * 2 + 1] = frames[:dim_f].imag
        pred = sess.run(None, {inp.name: spec})[0][0]
        for c in range(2):
            full = np.zeros((N_FFT // 2 + 1, dim_t), np.complex64)
            full[:dim_f] = pred[c * 2] + 1j * pred[c * 2 + 1]
            wave = np.zeros(HOP * (dim_t - 1) + N_FFT, np.float32)
            norm = np.zeros_like(wave)
            for i in range(dim_t):
                wave[i * HOP:i * HOP + N_FFT] += np.fft.irfft(full[:, i], N_FFT).astype(np.float32) * window
                norm[i * HOP:i * HOP + N_FFT] += window * window
            wave = wave[trim:-trim] / np.maximum(norm[trim:-trim], 1e-6)
            body = wave[trim:trim + chunk]
            out[c, start:start + len(body)] = body
    return out[:, :n]


def features(mono: np.ndarray, rate: int = RATE) -> dict:
    """Musiqa belgilari: tempo (BPM), ritm kuchi, ohangdorlik, balandlik."""
    step = rate // 11025 or 1
    x = mono[::step]
    sr = rate / step
    win, hop = 1024, 256
    if len(x) < win * 4:
        return {"bpm": 0.0, "beat": 0.0, "tonal": 0.0, "rms": 0.0, "stable": 0.0}
    frames = np.lib.stride_tricks.sliding_window_view(x, win)[::hop] * np.hanning(win)
    mag = np.abs(np.fft.rfft(frames, axis=1))
    flux = np.maximum(np.diff(mag, axis=0), 0).sum(axis=1)
    flux = flux - flux.mean()
    ac = np.correlate(flux, flux, "full")[len(flux) - 1:]
    ac = ac / max(ac[0], 1e-9)
    rate_f = sr / hop
    lo, hi = int(rate_f * 60 / 180), int(rate_f * 60 / 70)  # 70-180 BPM
    lag = lo + int(np.argmax(ac[lo:hi])) if hi > lo else 1
    band = mag[:, 8:370]  # ~90-4000 Hz
    tonal = float(np.mean(band.max(axis=1) / np.maximum(np.median(band, axis=1), 1e-9)))
    energy = np.sqrt((frames ** 2).mean(axis=1))
    return {"bpm": round(60 * rate_f / lag, 1), "beat": round(float(ac[lag]), 3), "tonal": round(tonal, 1),
            "rms": round(float(np.sqrt((x ** 2).mean())), 4),
            "stable": round(float(1 - min(1, energy.std() / max(energy.mean(), 1e-9))), 3)}


def is_music(f: dict) -> bool:
    """Shovqin va sukunat emas: musiqada ohang keskin ajralib turadi (o'lchovlarda musiqa 160+, ko'cha shovqini 20-30)."""
    return f["rms"] >= .012 and f["tonal"] >= 60


def mood_of(f: dict) -> str:
    if f["rms"] >= .06 or (f["beat"] >= .25 and f["bpm"] >= 100):
        return "energetic"
    return "calm" if f["rms"] < .03 else "cinematic"


def _sign(mono: np.ndarray) -> list[float]:
    """Trek izi: bir xil musiqani ikki marta saqlamaslik uchun."""
    n = 128
    if len(mono) < n * 2048:
        return []
    mid = mono[len(mono) // 2 - n * 1024:len(mono) // 2 + n * 1024].reshape(n, 2048)
    sp = np.abs(np.fft.rfft(mid * np.hanning(2048), axis=1))[:, 4:200]
    sig = sp.mean(axis=0)
    return [round(float(v), 4) for v in sig / max(np.linalg.norm(sig), 1e-9)]


def harvest(video: str | Path, force: bool = False) -> dict | None:
    """Videodan musiqani oladi va xotiraga saqlaydi. Musiqa yo'q yoki allaqachon bor bo'lsa - None."""
    path = Path(video)
    with _lock:
        size = path.stat().st_size
        with path.open("rb") as fh:
            key = hashlib.sha256(fh.read(1 << 20) + str(size).encode()).hexdigest()[:16]
        st = _state()
        if key in st["seen"] and not force:
            return None
        audio = _load_audio(path)
        info = {"name": path.name, "result": "qisqa yoki ovozsiz"}
        track = None
        if audio.shape[1] >= MIN_SECONDS * RATE:
            mono = audio.mean(axis=0)
            spoken = speech_share(mono)
            clean = separate(audio) if spoken > .08 else audio
            one = clean.mean(axis=0)
            feats = features(one)
            info.update(speech=round(spoken, 2), **feats)
            if not is_music(feats):
                info["result"] = "musiqa emas (shovqin yoki sukunat)"
            else:
                sig = _sign(one)
                twin = next((t for t in st["tracks"].values() if sig and t.get("sign")
                             and float(np.dot(sig, t["sign"])) > .985), None)
                if twin:
                    info["result"] = f"bu trek bor: {twin['file']}"
                else:
                    mood = mood_of(feats)
                    folder = LIB / mood
                    folder.mkdir(parents=True, exist_ok=True)
                    dest = folder / f"video_{key}.m4a"
                    peak = max(float(np.abs(clean).max()), 1e-6)
                    pcm = (clean / peak * .95).T.astype(np.float32).tobytes()
                    subprocess.run([ffmpeg(), "-v", "error", "-y", "-f", "f32le", "-ar", str(RATE), "-ac", "2", "-i", "-",
                                    "-c:a", "aac", "-b:a", "192k", str(dest)], input=pcm, check=True, timeout=600)
                    track = {"file": str(dest.relative_to(LIB)), "mood": mood, "seconds": round(audio.shape[1] / RATE, 1),
                             "src": path.name, "used": 0, "sign": sig, **feats, "speech": round(spoken, 2)}
                    st["tracks"][key] = track
                    info["result"] = f"saqlandi: {mood}, {feats['bpm']:.0f} BPM"
        st["seen"][key] = info
        _save(st)
    log.info("Musiqa xotirasi: %s - %s", path.name, info["result"])
    return track


def harvest_later(video: str | Path) -> None:
    """Videoni qabul qilish to'xtab qolmasin - fonda."""
    def run():
        try:
            harvest(video)
        except Exception as e:
            log.warning("Musiqa olinmadi %s: %s", video, e)
    threading.Thread(target=run, daemon=True).start()


def choose(mood: str = "", want: float = 0, recent: list[str] | None = None) -> str:
    """Eng mos trek: kayfiyati to'g'ri, kam ishlatilgan, videodan uzun. Foydalanish soni oshiriladi."""
    with _lock:
        st = _state()
        best, top = None, -1e9
        for key, t in st["tracks"].items():
            if not (LIB / t["file"]).is_file():
                continue
            score = (5 if t["mood"] == mood else 0) - 3 * t.get("used", 0) + (2 if t["seconds"] >= want else 0)
            score += min(t["seconds"], 60) / 60 + t.get("beat", 0)
            if recent and t["file"] in recent:
                score -= 8
            if score > top:
                best, top = key, score
        if not best:
            return ""
        st["tracks"][best]["used"] = st["tracks"][best].get("used", 0) + 1
        _save(st)
        return str(LIB / st["tracks"][best]["file"])


def summary() -> str:
    st = _state()
    rows = [f"• {t['mood']}, {t['bpm']:.0f} BPM, {t['seconds']:.0f} s - {t['src'][:40]} (ishlatildi: {t.get('used', 0)})"
            for t in st["tracks"].values()]
    return f"🎵 Musiqa xotirasi: {len(rows)} ta trek, {len(st['seen'])} ta video ko'rildi\n" + "\n".join(rows)


def scan(folder: Path | None = None) -> list[dict]:
    """Egam avval tashlagan videolar (inbox va studio) - bir marta ko'rib chiqiladi."""
    root = config.data_dir / "inbox"
    files = [f for d in ([folder] if folder else [root, root / "studio"]) for f in sorted(d.glob("*"))
             if f.suffix.lower() in (".mp4", ".mov", ".m4v", ".webm")]
    out = []
    for f in files:
        try:
            t = harvest(f)
            if t:
                out.append(t)
        except Exception as e:
            log.warning("Musiqa olinmadi %s: %s", f.name, e)
    return out
