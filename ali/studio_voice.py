"""Explicit, per-character narration for the creative studio; no silent fallback."""
import re
import httpx
from . import tts
from .config import config

EMOTIONS = {"neutral": "", "happy": "[happy]", "excited": "[excited]",
            "sad": "[sad]", "angry": "[angry]", "whisper": "[whispers]", "surprised": "[surprised]"}


def options():
    return [{"id": "expressive", "name": "Ifodali aktyor · ElevenLabs"},
            {"id": "sardor", "name": "Sardor · o‘zbekcha erkak"},
            {"id": "madina", "name": "Madina · o‘zbekcha ayol"}]


def prepare(text):
    text = tts.clean(text)
    text = re.sub(r"\[[^\]]*\]", "", text)  # performance tags come from validated direction only
    text = re.sub(r"([oOgG])[‘’ʻʼ`']", r"\1‘", text)
    return re.sub(r"\s+", " ", text).strip()


async def speak(text, voice="expressive", emotion="neutral"):
    text = prepare(text)
    if not text:
        raise ValueError("Ovoz matni bo‘sh")
    if voice == "expressive":
        voice_id = tts.current_voice().get("voice_id") or config.elevenlabs_voice_id
        if not config.elevenlabs_api_key or not voice_id:
            raise ValueError("Ruxsatlar → Ovoz: ElevenLabs kaliti va ovoz ID sini sozlang")
        tag = EMOTIONS.get(emotion, "")
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{tts.ELEVEN}/text-to-speech/{voice_id}",
                headers={"xi-api-key": config.elevenlabs_api_key}, params={"output_format": "mp3_44100_128"},
                json={"text": f"{tag} {text}".strip(), "model_id": "eleven_v3",
                      "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}})
        if not response.is_success:
            try:
                detail = response.json().get("detail", {})
            except ValueError:
                detail = {}
            if isinstance(detail, dict) and detail.get("status") == "missing_permissions":
                raise ValueError("ElevenLabs kalitida Text to Speech ruxsati yo‘q. ElevenLabs → API Keys’da shu ruxsatni yoqing, keyin qayta sinang.")
            raise ValueError("ElevenLabs ovoz bermadi. Ruxsatlar → Ovoz bo‘limida haqiqiy API kaliti, ovoz ID va limitni tekshiring. Oddiy ovozga avtomatik o‘tilmadi.")
        if not response.content:
            raise ValueError("ElevenLabs bo‘sh audio qaytardi")
        return response.content
    voices = {"sardor": "uz-UZ-SardorNeural", "madina": "uz-UZ-MadinaNeural"}
    if voice not in voices:
        raise ValueError("Noma’lum ovoz")
    import edge_tts
    rate, pitch = {"excited": ("+6%", "+2Hz"), "sad": ("-8%", "-2Hz"),
                   "whisper": ("-8%", "-1Hz"), "surprised": ("+3%", "+3Hz")}.get(emotion, ("-3%", "+0Hz"))
    data = bytearray()
    async for chunk in edge_tts.Communicate(text, voices[voice], rate=rate, pitch=pitch).stream():
        if chunk["type"] == "audio":
            data.extend(chunk["data"])
    if not data:
        raise ValueError("O‘zbekcha ovoz tayyorlanmadi")
    return bytes(data)
