"""Ovoz (TTS): Ali qaysi ovozda gapirishini boshqaradi.

Standart: Microsoft Edge ovozi (uz-UZ-SardorNeural), bepul.
Shaxsiy ovoz: voices/samples/ papkasidagi yozuvlardan (yoki Telegram'ga yuborilgan
ovozli xabarlardan) ElevenLabs orqali klon yaratiladi va Ali shu ovozda gapiradi.
"""
import json
import logging
import re
from pathlib import Path

import httpx

from .config import STATE_ROOT, config

log = logging.getLogger("ali.tts")

SAMPLES_DIR = STATE_ROOT / "voices" / "samples"
VOICE_FILE = config.data_dir / "voice.json"
ELEVEN = "https://api.elevenlabs.io/v1"
AUDIO_EXT = {".ogg", ".oga", ".mp3", ".wav", ".m4a", ".webm", ".flac"}

SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def clean(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)       # kod bloklari o'qilmaydi
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)    # havolalar -> faqat matni
    return re.sub(r"[*_#`>|]+", "", text).strip()[:3000]


def current_voice() -> dict:
    if VOICE_FILE.exists():
        try:
            return json.loads(VOICE_FILE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    if config.elevenlabs_voice_id:
        return {"provider": "elevenlabs", "voice_id": config.elevenlabs_voice_id, "name": "env"}
    return {"provider": "edge", "voice": config.tts_voice}


def use_default_voice() -> None:
    VOICE_FILE.unlink(missing_ok=True)


def samples() -> list[Path]:
    return sorted(p for p in SAMPLES_DIR.iterdir() if p.suffix.lower() in AUDIO_EXT)


async def synthesize(text: str) -> bytes:
    """Matnni MP3 ovozga aylantiradi."""
    text = clean(text)
    if not text:
        return b""
    voice = current_voice()
    if voice["provider"] == "elevenlabs" and config.elevenlabs_api_key:
        try:
            return await _eleven_tts(text, voice["voice_id"])
        except Exception:
            log.exception("ElevenLabs xatosi, Edge ovoziga o'tildi")
    return await _edge_tts(text)


FALLBACK_VOICE = "uz-UZ-SardorNeural"  # tanlangan ovoz mavjud bo'lmasa (masalan noto'g'ri nom) - o'zbekcha erkak ovozi


async def _edge_tts(text: str) -> bytes:
    import edge_tts

    for voice in dict.fromkeys([config.tts_voice, FALLBACK_VOICE]):
        audio = bytearray()
        try:
            async for chunk in edge_tts.Communicate(text, voice).stream():
                if chunk["type"] == "audio":
                    audio.extend(chunk["data"])
        except edge_tts.exceptions.NoAudioReceived:
            log.warning("Edge ovozi %s ishlamadi (bunday ovoz yo'q?) - %s ga o'tildi", voice, FALLBACK_VOICE)
            continue
        return bytes(audio)
    raise RuntimeError("Edge ovozi javob bermadi")


async def _eleven_tts(text: str, voice_id: str) -> bytes:
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{ELEVEN}/text-to-speech/{voice_id}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": config.elevenlabs_api_key},
            json={"text": text, "model_id": config.elevenlabs_model},
        )
        r.raise_for_status()
        return r.content


async def clone_voice(name: str = "Ali") -> str:
    """voices/samples/ dagi yozuvlardan shaxsiy ovoz yaratadi va uni faollashtiradi."""
    if not config.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY yo'q (.env). Ovoz klonlash uchun elevenlabs.io dan kalit oling.")
    files = samples()
    if not files:
        raise RuntimeError("Namunalar yo'q. voices/samples/ ga yozuv qo'ying yoki Telegram'da /ovoz orqali yuboring.")
    multipart = [("name", (None, name)), ("remove_background_noise", (None, "true"))]
    multipart += [("files", (f.name, f.read_bytes())) for f in files[:25]]
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{ELEVEN}/voices/add", headers={"xi-api-key": config.elevenlabs_api_key}, files=multipart)
        if r.status_code >= 400:
            raise RuntimeError(f"ElevenLabs: {r.status_code} {r.text[:300]}")
        voice_id = r.json()["voice_id"]
    VOICE_FILE.write_text(
        json.dumps({"provider": "elevenlabs", "voice_id": voice_id, "name": name, "samples": len(files)}),
        encoding="utf-8",
    )
    return voice_id
