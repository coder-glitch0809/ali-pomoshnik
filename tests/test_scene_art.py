import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import test_runtime
from ali import scene_art, story_video, video_variety


class SceneArtTests(unittest.TestCase):
    def setUp(self):
        story_video._image_cooldowns.clear()
        self.addCleanup(story_video._image_cooldowns.clear)

    def test_payment_failure_is_not_repeated_for_each_scene(self):
        provider = Mock(side_effect=RuntimeError("429 quota"))
        with tempfile.TemporaryDirectory() as tmp, patch.object(story_video, "ART", Path(tmp)), \
                patch("ali.providers.image_sources", return_value=[("Gemini", provider)]), \
                patch.object(story_video, "_pollinations", side_effect=HTTPError("test", 402, "payment", {}, None)) as poll:
            self.assertEqual(story_video.image("banner", 1), (None, ""))
            self.assertEqual(story_video.image("lightbox", 2), (None, ""))
        provider.assert_called_once()
        poll.assert_called_once()

    def test_missing_images_are_illustrated_without_replacing_good_photos(self):
        photo, drawing = Path("photo.jpg"), Path("drawing.jpg")
        scenes = [{"big": "Banner"}, {"big": "Telefon"}]
        with patch.object(story_video, "image", side_effect=lambda prompt, seed: (photo, "AI") if prompt == "Banner" else (None, "")), \
                patch.object(scene_art, "illustrate", return_value=[drawing]) as fallback:
            result = story_video.images(scenes, 7)
        self.assertEqual(result[0], (photo, "AI"))
        self.assertEqual(result[1][0], drawing)
        self.assertEqual(fallback.call_args.args[0], [scenes[1]])

    def test_art_is_topic_specific_and_escapes_untrusted_headings(self):
        banner = scene_art.page({"big": "Banner <script>", "voice": "Peshlavha"}, (1920, 1080))
        phone = scene_art.page({"big": "Telefon"}, (1080, 1920))
        self.assertIn("&lt;script&gt;", banner)
        self.assertNotIn("<script>", banner)
        self.assertIn("ILLUSTRATSIYA", banner)
        self.assertNotEqual(banner, phone)

    def test_new_reels_directions_have_concrete_spoken_advice(self):
        for topic in video_variety.TOPICS[4:]:
            data = story_video.fallback(topic)
            self.assertGreaterEqual(len(data["scenes"]), 5)
            self.assertTrue(all(s.get("image") and s.get("voice") for s in data["scenes"]))
