"""Gapirish (TTS).

edge    - Microsoft Edge ovozlari, o'zbekcha bor (uz-UZ-SardorNeural / uz-UZ-MadinaNeural). Internet kerak.
pyttsx3 - oflayn, lekin o'zbekcha ovoz yo'q.
none    - ovozsiz.
"""
import asyncio
import logging
import os
import re
import tempfile
import threading

from ..config import config

log = logging.getLogger("ali.speaker")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")


def _clean(text: str) -> str:
    # Markdown belgilarini olib tashlaymiz, aks holda ular ham o'qiladi
    return re.sub(r"[*_#`>|]+", "", text).strip()


class Speaker:
    def __init__(self, backend: str = config.tts_backend):
        self.backend = backend
        self._lock = threading.Lock()
        self._engine = None
        if backend == "pyttsx3":
            import pyttsx3
            self._engine = pyttsx3.init()
        elif backend == "edge":
            import edge_tts  # noqa: F401  - o'rnatilganini tekshirish
            import pygame
            pygame.mixer.init()

    def say(self, text: str) -> None:
        text = _clean(text)
        if not text or self.backend == "none":
            return
        with self._lock:
            try:
                if self.backend == "edge":
                    self._say_edge(text)
                elif self._engine:
                    self._engine.say(text)
                    self._engine.runAndWait()
            except Exception:
                log.exception("Gapirishda xato")

    def _say_edge(self, text: str) -> None:
        import edge_tts
        import pygame

        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        try:
            asyncio.run(edge_tts.Communicate(text, config.tts_voice).save(path))
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(50)
            pygame.mixer.music.unload()
        finally:
            os.remove(path)
