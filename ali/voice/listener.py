"""Eshitish (STT): mikrofondan nutqni yozib, matnga aylantiradi (Google Speech, o'zbek tili).

Mikrofon sounddevice orqali o'qiladi (PyAudio Python 3.14 da o'rnatilmaydi).
Gap boshi/oxiri ovoz balandligi (energiya) bo'yicha aniqlanadi.
"""
import collections
import logging
import time

import numpy as np
import sounddevice as sd
import speech_recognition as sr

from ..config import config

log = logging.getLogger("ali.listener")

RATE = 16000
BLOCK = 1600          # 0.1 soniya
PAUSE_BLOCKS = 8      # 0.8 s sukunat = gap tugadi
PREROLL_BLOCKS = 3    # gap boshidan oldingi 0.3 s ham olinadi


def _rms(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(block.astype(np.float32) ** 2)))


class Listener:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.threshold = self._calibrate()
        log.info("Mikrofon chegarasi: %.0f", self.threshold)

    def _calibrate(self, seconds: float = 1.0) -> float:
        noise = sd.rec(int(RATE * seconds), samplerate=RATE, channels=1, dtype="int16")
        sd.wait()
        return max(_rms(noise) * 2.5, 300.0)

    def _record_phrase(self, timeout: float | None, phrase_limit: float) -> bytes | None:
        preroll = collections.deque(maxlen=PREROLL_BLOCKS)
        frames: list[bytes] = []
        silent = 0
        started_at = time.monotonic()
        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK) as stream:
            while True:
                block, _ = stream.read(BLOCK)
                loud = _rms(block) > self.threshold
                if not frames:
                    preroll.append(block.tobytes())
                    if loud:
                        frames.extend(preroll)
                    elif timeout is not None and time.monotonic() - started_at > timeout:
                        return None
                    continue
                frames.append(block.tobytes())
                silent = 0 if loud else silent + 1
                if silent >= PAUSE_BLOCKS or len(frames) * BLOCK / RATE >= phrase_limit:
                    return b"".join(frames)

    def listen(self, timeout: float | None = None, phrase_limit: float = 15) -> str | None:
        """Bitta gapni eshitadi. Hech narsa tushunilmasa None."""
        raw = self._record_phrase(timeout, phrase_limit)
        if not raw:
            return None
        try:
            return self.recognizer.recognize_google(sr.AudioData(raw, RATE, 2), language=config.stt_language)
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            log.error("Nutqni aniqlash xizmati xatosi: %s", e)
            return None


def strip_wake_word(text: str) -> str | None:
    """Matn uyg'otish so'zi bilan boshlansa, qolgan qismini qaytaradi ('' - faqat chaqirildi).
    Uyg'otish so'zi bo'lmasa None."""
    lowered = text.lower().strip()
    for word in config.wake_words:
        if lowered.startswith(word):
            return text.strip()[len(word):].lstrip(" ,.!?")
    return None
