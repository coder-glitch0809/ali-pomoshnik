import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_runtime  # noqa: F401
from ali import youtube_render


class YouTubeRenderTests(unittest.TestCase):
    def test_landscape_media_slow_motion_and_safe_timed_subtitles(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"fixture")
            data = {"title": "A < B", "scenes": [
                {"voice": "Birinchi sahna", "big": "<script>bad</script>", "chapter": "Kirish", "speed": .5},
                {"voice": "Ikkinchi sahna", "big": "Natija"}]}
            page, subs = youtube_render.page(data, [0, 3], [3, 4], [(video, ""), (None, "")])
            self.assertIn("width:1920px;height:1080px", page)
            self.assertIn('data-speed="0.5"', page)
            self.assertIn('data:video/mp4;base64', page)
            self.assertIn('Kirish', page)
            self.assertIn('&lt;script&gt;bad&lt;/script&gt;', page)
            self.assertIn('visual1Base', page)
            self.assertEqual(subs[0][0], 0)
            self.assertEqual(subs[-1][1], 7)
            with patch("ali.story_video.render", return_value=video) as render:
                self.assertEqual(youtube_render.render(page, video, 7, subs=subs), video)
                self.assertEqual(render.call_args.kwargs['viewport'], (1920, 1080))

    def test_invalid_timing_rejected(self):
        with self.assertRaises(ValueError):
            youtube_render.page({"scenes": [{}]}, [0], [-1], [(None, "")])


if __name__ == '__main__':
    unittest.main()
