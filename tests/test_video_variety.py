import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_runtime
from ali import video_variety as variety, story_video, daily_video


class VarietyTests(unittest.TestCase):
    def test_reworded_title_cannot_hide_identical_script(self):
        old = [{"title": "Old topic", "script": "Banner matni katta kontrast aniq telefon manzil"}]
        self.assertTrue(variety.repeated({"title": "Brand new title", "scenes": [
            {"voice": "Banner matni katta kontrast aniq telefon manzil"}]}, old))
        self.assertFalse(variety.repeated({"title": "Target auditoriyasi", "scenes": [
            {"voice": "Auditoriyani alohida segmentlarga ajrating"}]}, old))

    def test_fallback_topics_and_art_change(self):
        first = story_video.fallback(variety.fresh_topic([]))
        history = [{"title": first["title"]}]
        second = story_video.fallback(variety.fresh_topic(history))
        self.assertNotEqual(first["title"], second["title"])
        self.assertNotEqual(first["scenes"][0]["image"], second["scenes"][0]["image"])
        variety.direction(first, [])
        variety.direction(second, [{"style": first["style"]}])
        self.assertNotEqual(first["style"], second["style"])
        self.assertNotIn("Pixar", story_video.refine(second["scenes"][0]["image"]))

    def test_unrelated_generic_script_is_not_used_on_failure(self):
        with self.assertRaises(ValueError):
            story_video.fallback("Mutlaqo boshqa mavzu")
        with patch("ali.story_video.make", side_effect=ValueError("Takroriy")), \
                patch.object(daily_video, "_make_classic") as classic:
            with self.assertRaises(ValueError):
                daily_video.make("test")
            classic.assert_not_called()

    def test_caption_matching_and_no_duplicate_or_outside_media(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(variety.config, "data_dir", Path(tmp)), \
                patch.object(variety, "LIBRARY", Path(tmp) / "media.json"):
            inbox = Path(tmp) / "inbox"
            inbox.mkdir()
            asset = inbox / "old.mp4"
            asset.write_bytes(b"fixture")
            outside = Path(tmp) / "private.jpg"
            outside.write_bytes(b"private")
            variety.register(asset, "Banner matni kontrast")
            variety.register(outside, "Banner matni kontrast")
            self.assertEqual(len(variety.library()), 1)
            used = set()
            scene = {"voice": "Banner matni katta kontrast", "big": "Banner"}
            self.assertEqual(variety.select_media(scene, used), asset.resolve())
            self.assertIsNone(variety.select_media(scene, used))
            self.assertIsNone(variety.select_media({"voice": "Target auditoriyasi"}, set()))

    def test_graphics_and_video_are_part_of_rendered_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"fixture")
            scenes = [{"voice": "Mijoz yo'lini tushuntiramiz", "big": "Mijoz yo'li", "layout": "full",
                       "diagram": {"type": "funnel", "labels": ["Ko'rdi", "Yozdi"]}}]
            page, _ = story_video.page({"title": "t", "scenes": scenes}, [0], [3], [(video, "archive")], None, lambda s, k: "")
            self.assertIn('data:video/mp4;base64', page)
            self.assertIn('data-start="0"', page)
            self.assertIn('story-graphic', page)
            self.assertIn('url(#gb0)', page)
            self.assertIn('Yozdi', page)
            self.assertIn('v.onseeked', story_video.STEP)
