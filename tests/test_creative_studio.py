import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import test_runtime
from fastapi.testclient import TestClient
from ali import creative_video as studio, studio_voice, local_ai, outbox
from ali.config import config
from ali.plugins import video_studio
from runtime import app

JOB = 'a' * 32
STORY = {'title': 'Hikoya', 'scenes': [{'voice': 'Salom!', 'big': 'Boshladik', 'speaker': 'Jasur', 'emotion': 'excited', 'image': 'A boy'}]}


class CreativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch.object(config, 'data_dir', self.root), patch.dict(studio._jobs, {}, clear=True)]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def prepared(self):
        studio._jobs[JOB] = {'id': JOB, 'review': True, 'story': STORY, 'status': 'ready', 'format': '9:16'}
        studio._update(JOB, progress=60)

    def test_review_stops_after_images_and_saves_previews(self):
        studio._jobs[JOB] = {'id':JOB,'review':True,'format':'9:16'}
        with patch.object(local_ai,'ask_pro',return_value=('ChatGPT',json.dumps(STORY))), patch('ali.account_images.generate',return_value=b'image'), patch.object(studio,'_render') as render:
            studio._run(JOB,'Idea','Anime','9:16',False)
        job=studio.get(JOB)
        self.assertEqual(job['status'],'ready')
        self.assertEqual(len(job['scene_images']),len(job['story']['scenes']))
        self.assertTrue(studio.scene_path(JOB,1).is_file())
        render.assert_not_called()

    def test_render_is_atomic_and_validates_cast(self):
        self.prepared()
        with self.assertRaises(ValueError): studio.start_render(JOB,{'Jasur':[]})
        with patch.object(studio.threading,'Thread') as thread:
            studio.start_render(JOB,{'Jasur':'madina'})
            with self.assertRaises(ValueError): studio.start_render(JOB,{})
            self.assertEqual(thread.call_count,1)
        self.assertEqual(studio.get(JOB)['voices'],{'Jasur':'madina'})

    def test_job_survives_restart_and_read_does_not_mutate_state(self):
        self.prepared()
        snapshot=studio.get(JOB);snapshot['story']['title']='wrong'
        self.assertEqual(studio.get(JOB)['story']['title'],'Hikoya')
        studio._jobs.clear()
        self.assertEqual(studio.get(JOB)['status'],'ready')
        studio._update(JOB,status='rendering')
        studio._jobs.clear()
        self.assertEqual(studio.get(JOB)['status'],'error')
        self.assertIsNone(studio.get('../outside'))
        self.assertIsNone(studio.scene_path('../outside',1))

    def test_failed_voice_can_retry_without_regenerating_images(self):
        self.prepared()
        with patch.object(video_studio,'make_content_video',side_effect=RuntimeError('voice unavailable')), patch.object(outbox,'DIR',self.root/'outbox'):
            studio._render(JOB)
        self.assertEqual(studio.get(JOB)['status'],'ready')
        self.assertIn('voice unavailable',studio.get(JOB)['message'])

    def test_routes_require_login_and_reject_foreign_origin(self):
        self.prepared()
        client=TestClient(app)
        self.assertEqual(client.get('/api/creative-voices').status_code,401)
        self.assertEqual(client.post(f'/api/creative-video/{JOB}/telegram').status_code,401)
        with patch('runtime.is_authed',return_value=True), patch('runtime.foreign_origin',return_value=True):
            self.assertEqual(client.post(f'/api/creative-video/{JOB}/render',json={}).status_code,403)
        with patch('runtime.is_authed',return_value=True), patch('runtime.foreign_origin',return_value=False), patch.object(studio_voice,'speak',AsyncMock(return_value=b'audio')) as speak:
            r=client.post(f'/api/creative-video/{JOB}/preview',json={'speaker':'Jasur','voice':'madina'})
            self.assertEqual(r.content,b'audio')
            speak.assert_awaited_once_with('Salom!','madina','excited')

    def test_telegram_delivery_is_not_duplicated(self):
        self.prepared()
        path=self.root/'clip.mp4';path.write_bytes(b'mp4')
        studio._update(JOB,status='done',video='clip.mp4')
        bot=AsyncMock()
        bot.__aenter__.return_value=bot
        with patch('ali.telegram_memory.MemoryBot',return_value=bot), patch.object(outbox,'resolve',return_value=path), patch.object(config,'telegram_token','test'), patch.object(config,'telegram_owner_id',42):
            asyncio.run(studio.send_telegram(JOB))
            asyncio.run(studio.send_telegram(JOB))
        bot.send_video.assert_awaited_once()
        self.assertEqual(bot.send_video.call_args.kwargs['chat_id'],42)
        self.assertEqual(studio.get(JOB)['telegram_status'],'sent')

    def test_voice_direction_and_no_silent_fallback(self):
        response=unittest.mock.Mock(is_success=True,content=b'mp3')
        client=AsyncMock();client.__aenter__.return_value=client;client.post.return_value=response
        with patch.object(studio_voice.httpx,'AsyncClient',return_value=client), patch.object(config,'elevenlabs_api_key','test'), patch.object(studio_voice.tts,'current_voice',return_value={'voice_id':'voice'}):
            self.assertEqual(asyncio.run(studio_voice.speak('Salom!','expressive','happy')),b'mp3')
            payload=client.post.call_args.kwargs['json']
            self.assertEqual(payload['text'],'[happy] Salom!')
            self.assertEqual(payload['model_id'],'eleven_v3')
            response.is_success=False
            with self.assertRaises(ValueError): asyncio.run(studio_voice.speak('Salom!'))


if __name__ == '__main__': unittest.main()
