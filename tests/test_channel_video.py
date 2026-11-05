import unittest
from pathlib import Path
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik ALI_STATE_DIR ali'dan oldin o'rnatilsin
from ali.skills import load_all


class ChannelVideoTests(unittest.TestCase):
    def test_skill_registered(self):
        s = load_all()["channel_video_edit"]
        self.assertEqual(s.required, ["channel"])
        self.assertFalse(s.dangerous)

    def test_downloads_then_edits(self):
        s = load_all()["channel_video_edit"]
        with patch("ali.tg_account.download_latest_video", return_value=(Path("v.mp4"), "Kanal")) as dl, \
                patch("ali.local_ai.access", return_value=False), \
                patch("ali.montage.run", return_value="🎬 Montaj tayyor") as run:
            out = s.func(channel="Kanal", task="subtitr qo'sh")
        dl.assert_called_once_with("Kanal")
        self.assertEqual(run.call_args.args[:2], ("subtitr qo'sh", "v.mp4"))
        self.assertIn("Montaj tayyor", out)


if __name__ == "__main__":
    unittest.main()
