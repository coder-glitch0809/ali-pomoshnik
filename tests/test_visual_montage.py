import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_runtime  # Configure an isolated state directory before importing ali.
from ali import story_video


class VisualMontageTests(unittest.TestCase):
    def scene(self, **extra):
        return {"voice": "Sahna matni", "big": "Aniq fikr", "layout": "full", "visual": {
            "seed": 123, "background": "rings", "graphic": "dots",
            "palette": ["#102030", "#aabbcc", "#ddeeff"]}, **extra}

    def test_procedural_background_and_palette_survive_style(self):
        from ali.video_variety import STYLES
        scene = self.scene()
        fallback = lambda *args: self.fail("Procedural scenes must use their visual plan")
        page, subs = story_video.page({"title": "t", "style": STYLES[0], "scenes": [scene]},
                                     [0], [3], [(None, "")], None, fallback)
        self.assertIn('class="procedural-visual"', page)
        self.assertIn('stop-color="#aabbcc"', page)
        self.assertIn('background:#102030e6', page)
        self.assertIn('cinema-vignette', page)
        self.assertTrue(subs)
        self.assertLessEqual(subs[-1][1], 3)

    def test_footage_has_overlay_and_bounded_slow_motion(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "clip.mp4"
            clip.write_bytes(b"fixture")
            for speed, expected in [(0, .35), (.6, .6), (10, 1.), ("bad", 1), (float("nan"), 1)]:
                scene = self.scene(speed=speed)
                page, _ = story_video.page({"title": "t", "scenes": [scene]}, [0], [3],
                                          [(clip, "archive")], None, lambda *args: "")
                self.assertEqual(float(re.search(r'data-speed="([^"]+)"', page).group(1)), expected)
                self.assertIn('class="visual-overlay"', page)
        self.assertIn('v.duration - .001', story_video.STEP)
        self.assertIn('* speed', story_video.STEP)
        self.assertNotIn('% v.duration', story_video.STEP)

    def test_actual_scene_seed_reaches_image_provider(self):
        with patch.object(story_video, "image", return_value=(None, "")) as image:
            story_video.images([self.scene(image="a shop owner")], 5)
            image.assert_called_once_with("a shop owner", 123)

    def test_refine_preserves_subject_after_direction(self):
        prompt = "Visual direction: " + "cinematic " * 55 + ". A blue shop sign at night"
        self.assertIn("A blue shop sign at night", story_video.refine(prompt))


if __name__ == "__main__":
    unittest.main()
