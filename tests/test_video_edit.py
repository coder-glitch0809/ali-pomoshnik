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

    def test_montage_without_ai_uses_pro_and_sends_only_final(self):
        self.assertTrue(montage.is_query("oxirgi videoni reels qil va subtitr qo'sh"))
        self.assertFalse(montage.is_query("bugun ob-havo qanday"))
        from ali.service import brain
        start = outbox.mark()
        with patch("ali.skills.video_pro._srt", return_value="1\n00:00:00,000 --> 00:00:01,500\nSalom dunyo\n"):
            report = montage.run("", str(self.src), brain.registry, [])
        made = [p for p in outbox.since(start) if p.suffix == ".mp4"]
        self.assertEqual(montage.DEFAULT[0]["tool"], "video_pro")
        self.assertEqual(len(made), 1)
        self.assertEqual((v.info(made[0])["width"], v.info(made[0])["height"]), (1080, 1920))
        self.assertIn("subtitr", report.lower())

    def test_pro_helpers(self):
        from ali.skills import video_pro
        ass = video_pro.karaoke_ass("1\n00:00:01,000 --> 00:00:03,000\nMen targetologman, reklama 👇\n")
        self.assertIn("Dialogue: 0,0:00:01.00", ass)
        self.assertIn("\\k", ass)                 # so'zma-so'z karaoke
        self.assertIn("TARGETOLOGMAN,", ass)       # katta harflar, emoji yo'q
        self.assertNotIn("👇", ass)
        self.assertEqual(video_pro.speech_parts(self.src)[0][0], 0.0)


class VideoCreateAndUpgradeTests(unittest.TestCase):
    def test_creation_vs_edit_and_create_calls_studio(self):
        from types import SimpleNamespace
        self.assertTrue(montage.is_creation("Targetolog haqida 20 soniyalik reels qilib ber"))
        self.assertFalse(montage.is_creation("oxirgi videoni reels qil"))
        self.assertTrue(montage.is_query("oxirgi videoni reels qil va subtitr qo'sh"))
        calls = []
        reg = {"make_content_video": SimpleNamespace(func=lambda **kw: calls.append(kw) or "✅ Video tayyor")}
        self.assertIn("tayyor", montage.create("Tashqi reklama haqida 20 soniyalik video yarat", reg, []))
        self.assertEqual(calls[0]["duration_s"], 20)

    def test_interrupted_upgrade_is_cleaned_and_reported(self):
        from ali import self_upgrade
        self_upgrade._save({"x1": {"task": "video qo'sh", "running": True}, "x2": {"task": "tayyor", "branch": "b"}})
        notes = []
        with patch.object(self_upgrade, "_git", return_value=""):
            lost = self_upgrade.interrupted(notes.append)
        self.assertEqual(lost, ["video qo'sh"])
        self.assertIn("video qo'sh", notes[0])
        self.assertEqual(list(self_upgrade._state()), ["x2"])  # tayyor (tasdiq kutayotgan) saqlanadi
        self_upgrade._save({})

    def test_content_plan_word(self):
        from ali import content_plan
        plan = {"created": "2026-10-30", "analysis": "Strategiya", "items": [
            {"id": 1, "date": "2026-10-31", "time": "13:00", "brand": "target", "format": "Reels", "topic": "CPL",
             "hook": "Reklama pul yeyaptimi?", "script": "1) ...", "caption": "c", "hashtags": "#t"}]}
        self.assertIn("Word tayyor", content_plan.word(plan))
        self.assertIn("13:00", content_plan.voice_summary(plan))
