import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_runtime  # Configure isolated state before importing Ali.
from ali import video_variety as variety


class VisualPlanTests(unittest.TestCase):
    def test_every_rotating_topic_has_a_usable_fallback(self):
        from ali.story_video import fallback
        for topic in variety.TOPICS:
            with self.subTest(topic=topic):
                data = fallback(topic)
                self.assertGreaterEqual(len(data["scenes"]), 5)
                self.assertNotIn("[cite:", str(data))

    def test_fresh_plans_are_persisted_and_media_remains_selectable(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(variety, "LIBRARY", Path(tmp) / "video_media.json"), \
                patch.object(variety.config, "data_dir", Path(tmp)), \
                patch.object(variety.time, "time_ns", return_value=1800000000000000000):
            inbox = Path(tmp) / "inbox"
            inbox.mkdir()
            asset = inbox / "banner.png"
            asset.write_bytes(b"fixture")
            variety.register(asset, "Banner matni kontrast")
            template = {"title": "Banner", "scenes": [
                {"voice": "Banner matni kontrast", "image": "A shop sign", "big": "Banner"}
                for _ in range(8)]}
            first, second = copy.deepcopy(template), copy.deepcopy(template)
            variety.direction(first, [])
            variety.direction(second, [])
            self.assertNotEqual(first["visual_id"], second["visual_id"])
            visuals = [s["visual"] for d in (first, second) for s in d["scenes"]]
            self.assertEqual(len({v["seed"] for v in visuals}), 16)
            for a, b in zip(visuals, visuals[1:]):
                self.assertNotEqual(a["background"], b["background"])
                self.assertNotEqual(a["graphic"], b["graphic"])
                self.assertNotEqual(a["palette"], b["palette"])
            for visual in visuals:
                self.assertEqual(len(visual["palette"]), 3)
                self.assertLess(visual["seed"], 2 ** 53)
                for color in visual["palette"]:
                    self.assertRegex(color, r"^#[0-9a-f]{6}$")
                for key in ("background_prompt", "graphic_prompt", "palette_prompt"):
                    self.assertTrue(visual[key])
            records = json.loads(variety.LIBRARY.read_text(encoding="utf-8"))
            self.assertEqual(records[-1]["scenes"][0]["visual"], second["scenes"][0]["visual"])
            variety.register(asset, "Banner matni kontrast")
            self.assertEqual(len(variety.library()), 3)
            self.assertEqual(variety.select_media(template["scenes"][0], set()), asset.resolve())

    def test_prompt_retention_does_not_evict_uploaded_media(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(variety, "LIBRARY", Path(tmp) / "video_media.json"):
            media = {"path": str(Path(tmp) / "portfolio.png"), "caption": "Owner portfolio"}
            variety._save([media] + [{"type": "visual_plan", "id": str(n)} for n in range(205)])
            records = variety.library()
            self.assertEqual(records[0], media)
            self.assertEqual(len(records), 201)
            self.assertEqual(records[1]["id"], "5")


if __name__ == "__main__":
    unittest.main()
