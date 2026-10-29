import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik ALI_STATE_DIR va test sozlamalari ali'dan oldin o'rnatilsin
from ali import montage, outbox
from ali.skills import video_edit as v


class VideoEditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.src = cls.tmp / "a.mp4"
        v._run(["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=2", "-f", "lavfi", "-i",
                "sine=frequency=440:duration=2", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(cls.src)])

    def test_reels_and_text(self):
        res = v.video_reels(str(self.src))
        out = outbox.since(max(0, outbox.mark() - 1))[-1]
        self.assertIn("1080x1920", res)
        self.assertEqual((v.info(out)["width"], v.info(out)["height"]), (1080, 1920))
        self.assertIn("Tayyor", v.video_text(str(self.src), "Hook -30% 👇", "top", 0, 1))

    def test_montage_without_ai_uses_default_and_sends_only_final(self):
        self.assertTrue(montage.is_query("oxirgi videoni reels qil va subtitr qo'sh"))
        self.assertFalse(montage.is_query("bugun ob-havo qanday"))
        from ali.service import brain
        start = outbox.mark()
        with patch.object(v, "_srt", return_value="1\n00:00:00,000 --> 00:00:01,500\nSalom\n"):
            report = montage.run("", str(self.src), brain.registry, [])
        made = [p for p in outbox.since(start) if p.suffix == ".mp4"]
        self.assertIn("video_reels", str(montage.DEFAULT))
        self.assertEqual(len(made), 1)  # oraliq 9:16 fayli o'chirildi - faqat yakuniy video
        self.assertIn("subtitr", report.lower())


if __name__ == "__main__":
    unittest.main()
