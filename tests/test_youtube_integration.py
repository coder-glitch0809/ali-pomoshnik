import io
import unittest
from unittest.mock import patch

import test_runtime
from PIL import Image
from ali import story_video, daily_video
from ali.skills import motion_code


class YouTubeIntegrationTests(unittest.TestCase):
    def test_landscape_art_and_existing_portrait(self):
        source = io.BytesIO()
        Image.new('RGB', (400, 300), 'red').save(source, 'PNG')
        for size in ((1920, 1080), (1080, 1920)):
            fitted = Image.open(io.BytesIO(story_video._fit(source.getvalue(), size=size)))
            self.assertEqual(fitted.size, size)
        prompt = story_video.refine('A shop owner demonstrating a sign', (1920, 1080))
        self.assertIn('landscape 16:9', prompt)
        self.assertNotIn('vertical', prompt)

    def test_landscape_seed_and_size_reach_image_provider(self):
        scene = {'image': 'Shop sign', 'visual': {'seed': 123}}
        with patch.object(story_video, 'image', return_value=(None, '')) as image:
            story_video.images([scene], 7, size=(1920, 1080))
        image.assert_called_once_with('Shop sign', 123, size=(1920, 1080))

    def test_youtube_routes_before_reels_and_skill_queues(self):
        with patch('ali.youtube_video.handle_text', return_value='YouTube queued') as route:
            self.assertEqual(daily_video.handle_text('YouTube video qil', print), 'YouTube queued')
            route.assert_called_once()
        with patch('ali.youtube_video.enqueue', return_value='queued') as enqueue:
            self.assertEqual(motion_code.make_youtube_video('Banner'), 'queued')
            self.assertEqual(enqueue.call_args.args[0], 'Banner')
