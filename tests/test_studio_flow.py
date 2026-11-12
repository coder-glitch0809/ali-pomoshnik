from pathlib import Path
import unittest
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik ALI_STATE_DIR va test sozlamalari ali'dan oldin o'rnatilsin
from ali import studio_flow as s


def _brief(bid, n=2, status="waiting"):
    return {"id": bid, "task": "t", "status": status, "at": 0, "images": [], "title": "T", "hook": "H",
            "scenes": [{"title": f"s{i}", "narration": "n", "image_prompt": "p"} for i in range(n)]}


class StudioFlowTests(unittest.TestCase):
    def setUp(self):
        s.STATE.parent.mkdir(parents=True, exist_ok=True)  # boshqa test vaqtinchalik papkani o'chirgan bo'lishi mumkin
        s._save({"next": 3, "channel_last": 0, "briefs": {"1": _brief(1), "2": _brief(2)}})

    def test_routing(self):
        self.assertFalse(s.is_query("Targetolog haqida reels qilib ber"))  # endi tayyor video (daily_video), brif emas
        self.assertTrue(s.is_query("virusli kreativ video: tashqi reklama"))
        self.assertFalse(s.is_query("rasmsiz video yarat: SMM"))
        self.assertFalse(s.is_query("bugun ob-havo"))

    def test_images_go_to_tagged_or_latest_brief(self):
        self.assertEqual(s.waiting()["id"], 2)
        full, note = s.add_image("a.jpg", "#B1")
        self.assertIsNone(full)
        self.assertIn("#B1: 1/2", note)
        s.add_image("b.jpg", "")                       # izohsiz - oxirgi brif (#B2)
        full, note = s.add_image("c.jpg", "#B1")
        self.assertEqual((full["id"], full["images"]), (1, ["a.jpg", "c.jpg"]))

    def test_no_waiting_brief_ignores_image(self):
        s._save({"next": 2, "channel_last": 0, "briefs": {"1": _brief(1, status="done")}})
        self.assertEqual(s.add_image("x.jpg", ""), (None, ""))

    def test_edit_plan_uses_local_rules_when_ai_access_is_not_enabled(self):
        from ali import local_ai

        with patch.object(local_ai, "access", return_value=False), \
                patch("ali.skills.video_edit.info", return_value={"duration": 12, "width": 720, "height": 1280}) as info, \
                patch.object(s, "_frames") as frames:
            plan = s._plan(Path("video.mp4"), "cinematic montaj")
        self.assertTrue(plan["offline"])
        self.assertEqual(plan["render"]["grade"], "cinematic")
        info.assert_called_once()
        frames.assert_not_called()

    def test_edit_plan_falls_back_when_ai_limit_returns_no_plan(self):
        from ali import local_ai

        with patch.object(local_ai, "access", return_value=True), \
                patch.object(local_ai, "ask_pro", return_value=None), \
                patch("ali.skills.video_edit.info", return_value={"duration": 12, "width": 720, "height": 1280}), \
                patch.object(s, "_frames", return_value=[]), \
                patch("ali.skills.video_edit._srt", return_value=""), \
                patch.object(s, "_style_hint", return_value=""):
            plan = s._plan(Path("video.mp4"), "oddiy reels")
        self.assertTrue(plan["offline"])
        self.assertTrue(plan["render"]["progress_bar"])


if __name__ == "__main__":
    unittest.main()
