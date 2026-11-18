import unittest

from ali.video_visuals import scene_visual, palette


class VideoVisualTests(unittest.TestCase):
    def test_seeded_scenery_varies_and_is_safe(self):
        scene = {"visual": {"seed": 42, "background": "rings", "graphic": "orbits",
                            "palette": ["#010203", "#abcdef", "#fedcba"]}}
        first = scene_visual(scene, 0, 2, 4)
        self.assertEqual(first, scene_visual(scene, 0, 2, 4))
        self.assertIn('url(#visual0Base)', first)
        self.assertIn('4.000s ease-in-out 2.000s both', first)
        scene["visual"]["seed"] = 43
        self.assertNotEqual(first, scene_visual(scene, 0, 2, 4))
        self.assertIn('url(#visual1Base)', scene_visual(scene, 1, 2, 4))
        scene["visual"]["palette"][0] = '"><script>alert(1)</script>'
        self.assertNotIn('<script>', scene_visual(scene, 0, 0, 3))
        self.assertEqual(palette(scene)[0], "#101b39")
        for background in ("aurora", "grid", "rings", "ribbons"):
            scene["visual"]["background"] = background
            self.assertIn('<svg', scene_visual(scene, 0, 0, 3))
        self.assertIn('3.000s', scene_visual({"visual": []}, 0, float('nan'), float('inf')))


if __name__ == "__main__":
    unittest.main()
