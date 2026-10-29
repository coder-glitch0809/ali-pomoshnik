import io
import json
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik ALI_STATE_DIR va test sozlamalari ali'dan oldin o'rnatilsin
from ali import outbox, plugins, skills
from ali.plugins import video_studio

SCRIPT = {"title": "Banner sirlari", "hooks": ["Banneringiz ishlamayaptimi?"],
          "scenes": [{"title": "Banner sirlari", "narration": "Uch soniyada e'tiborni tortadigan banner", "duration": 1},
                     {"title": "Biz bilan bog'laning", "text": "Beshariq", "narration": "Hoziroq yozing", "duration": 1}],
          "caption": "Banneringiz sotsin!", "hashtags": ["#banner", "#reklama"]}


def _silence(seconds=0.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(b"\0\0" * int(16000 * seconds))
    return buf.getvalue()


class VideoStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        skills.load_all()

    def test_tools_registered(self):
        self.assertIn("video_studio", plugins.PLUGINS)
        self.assertTrue({"make_content_video", "write_video_script"} <= set(skills.REGISTRY))

    def test_parse_script_from_fenced_json(self):
        s = video_studio._parse_script("```json\n" + json.dumps(SCRIPT, ensure_ascii=False) + "\n```")
        self.assertEqual(len(s["scenes"]), 2)
        with self.assertRaises(ValueError):
            video_studio._parse_script("ssenariy yo'q")

    def test_write_video_script_uses_ai(self):
        with patch.object(video_studio.providers, "chat", return_value=("AI", json.dumps(SCRIPT))):
            text = video_studio.write_video_script("banner reklama")
        self.assertIn("Banneringiz ishlamayaptimi?", text)
        self.assertIn("#banner", text)

    def test_srt_timings(self):
        srt = video_studio._srt([{"duration": 2, "speak": 2, "subs": ["bir", "ikki"]}])
        self.assertIn("00:00:00,000 --> 00:00:01,000\nbir", srt)
        self.assertIn("00:00:01,000 --> 00:00:02,000\nikki", srt)

    def test_make_content_video_writes_script_voice_and_files(self):
        with tempfile.TemporaryDirectory() as d, patch.object(outbox, "DIR", Path(d)), \
                patch.dict(video_studio.FORMATS, {"9:16": (144, 256)}), \
                patch.object(video_studio.providers, "chat", return_value=("AI", json.dumps(SCRIPT))), \
                patch.object(video_studio.providers, "image_sources", return_value=[]), \
                patch.object(video_studio, "_tts", return_value=_silence()):
            result = video_studio.make_content_video("banner reklama")
            files = {p.suffix for p in Path(d).iterdir()}
            self.assertIn("ovozli", result)
            self.assertEqual(files, {".mp4", ".srt", ".txt"})  # vaqtinchalik ovoz fayllari o'chirilgan
            srt = next(Path(d).glob("*.srt")).read_text(encoding="utf-8")
            self.assertIn("Hoziroq yozing", srt)


if __name__ == "__main__":
    unittest.main()
