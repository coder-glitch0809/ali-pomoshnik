import copy
import tempfile
import asyncio
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

import test_runtime
from test_youtube_content import example
from ali import youtube_content, youtube_video, video_variety
from ali.skills.video_edit import _run, info


class ShortsAndArchiveTests(unittest.TestCase):
    def test_studio_sync_indexes_media_without_reposting_or_redownloading(self):
        from ali import studio_flow
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(video_variety.config, 'data_dir', Path(folder)), \
                patch.object(video_variety, 'LIBRARY', Path(folder) / 'library.json'), \
                patch('ali.tg_account.authorized', return_value=True), \
                patch('ali.local_ai.access', return_value=False):
            downloads = []
            async def download(file):
                downloads.append(file)
                Path(file).write_bytes(b'fixture')
                return file
            async def messages(*args, **kwargs):
                yield SimpleNamespace(id=1, video=True, photo=False, text='Banner kontrasti', download_media=download)
                yield SimpleNamespace(id=2, video=True, photo=False, text=studio_flow.MARK, download_media=download)
            client = SimpleNamespace(iter_messages=messages)
            with patch('ali.tg_account._run', side_effect=lambda fn: asyncio.run(fn(client))):
                video_variety.sync_studio()
                video_variety.sync_studio()
            self.assertEqual(len(downloads), 1)
            entries = video_variety.library()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]['caption'], 'Banner kontrasti')
            self.assertIsNotNone(video_variety.select_media({'voice': 'Banner tayyorlash'}, set()))

    def test_short_script_and_explicit_order(self):
        data = example()
        data['scenes'] = data['scenes'][:6]
        voice = 'Peshlavhani uzoqdan tekshiring matn katta ranglar kontrastli manzil esa aniq va tushunarli bolsin'
        for scene, section in zip(data['scenes'], ['hook', 'problem', 'solution', 'solution', 'solution', 'cta']):
            scene.update(voice=voice, section=section)
        data['hook'] = voice
        result = youtube_content.validate(data, shorts=True)
        self.assertEqual(result['aspect_ratio'], '9:16')
        self.assertEqual(result['format'], 'youtube_shorts')
        with patch.object(youtube_video.threading, 'Thread') as thread:
            youtube_video.enqueue('YouTube shorts qilib ber', Mock())
        self.assertTrue(thread.call_args.kwargs['kwargs']['shorts'])
        with patch('ali.skills.video_edit.info', return_value=dict(width=1080, height=1920, fps=30, duration=70, audio=True)):
            self.assertTrue(youtube_video.quality_issues('short.mp4', shorts=True))

    def test_real_clip_and_still_preserve_aspect_and_record_selected_moment(self):
        with tempfile.TemporaryDirectory() as folder, patch('ali.local_ai.access', return_value=True), \
                patch('ali.local_ai.ask_pro', return_value=('test', '{"frame":4}')):
            folder = Path(folder)
            source = folder / 'source.mp4'
            _run(['-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=30', '-t', '2', '-c:v', 'libx264', str(source)])
            scene = {'voice': 'Banner matni kontrasti'}
            result = video_variety.prepare_media(source, scene, .5, folder / 'clip', (320, 180))
            meta = info(result)
            self.assertEqual((meta['width'], meta['height']), (320, 180))
            self.assertAlmostEqual(meta['duration'], .5, delta=.05)
            self.assertGreater(scene['media_source']['start'], 0)
            self.assertEqual(scene['media_source']['selection'], 'visual_match')
            scene['media_kind'] = 'still'
            result = video_variety.prepare_media(source, scene, .5, folder / 'still', (180, 320))
            from PIL import Image
            with Image.open(result) as image:
                self.assertEqual(image.size, (180, 320))
            self.assertEqual(scene['media_source']['kind'], 'still')

    def test_missing_images_fail_before_render(self):
        data = {'title': 'Test', 'scenes': [{'voice': 'Advice', 'big': 'Advice'}]}
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(youtube_video, 'STATE', Path(folder) / 'state.json'), \
                patch('ali.youtube_content.script', return_value=data), \
                patch('ali.daily_video._ready', return_value=[]), \
                patch('ali.daily_video.character', return_value=None), \
                patch('ali.skills.presenter.vector_rig', return_value={}), \
                patch('ali.video_variety.direction'), patch('ali.video_variety.sync_studio'), \
                patch('ali.video_variety.select_media', return_value=None), \
                patch('ali.story_video.voices', return_value=(Path('voice.wav'), [30])), \
                patch('ali.story_video.images', return_value=[(None, '')]), \
                patch('ali.story_video.render') as render:
            with self.assertRaisesRegex(RuntimeError, 'rasmlari yetishmayapti'):
                youtube_video.make()
            render.assert_not_called()


if __name__ == '__main__':
    unittest.main()
