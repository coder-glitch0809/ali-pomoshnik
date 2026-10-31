import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik ALI_STATE_DIR va test sozlamalari ali'dan oldin o'rnatilsin
from ali.skills import video_edit as v
from ali.skills import video_motion as m


class VideoMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.src = cls.tmp / "a.mp4"
        v._run(["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=4", "-f", "lavfi", "-i",
                "sine=frequency=440:duration=4", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(cls.src)])

    def test_ramp_and_dynamic_join(self):
        r = m.ramp_clip(str(self.src), 0, 4, self.tmp / "r.mp4", True)
        self.assertEqual((v.info(r)["width"], v.info(r)["height"]), (1080, 1920))
        j = m.join_dynamic([r, r], self.tmp / "j.mp4", ["zoomin"])
        self.assertTrue(v.info(j)["audio"])
        self.assertGreater(v.info(j)["duration"], v.info(r)["duration"])

    def test_motion_text_helpers(self):
        from ali.skills.video_pro import _ass_time
        hook = m.kinetic_hook("Bo'sh karkasdan yonib turgan belgigacha —", 0, 2.8, _ass_time)
        self.assertIn("\move(", hook)
        self.assertNotIn("—", hook)
        self.assertIn("t/4.00", m.progress_bar(4))

    def test_learn_style_without_ai_uses_measurements(self):
        m.STYLES.parent.mkdir(parents=True, exist_ok=True)
        with patch("ali.local_ai.access", return_value=False), patch("ali.memory.memory.add_knowledge"):
            style = m.analyze_style(str(self.src), "tez ritm yoqdi")
        self.assertIn("avg_shot", style)
        self.assertTrue(style["lessons"])
        self.assertEqual(m.latest_style()["name"], style["name"])
        self.assertIn("O'rgandim", m.style_text(style))


if __name__ == "__main__":
    unittest.main()
