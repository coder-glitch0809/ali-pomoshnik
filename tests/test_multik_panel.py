import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
from test_runtime import config
from ali.multik_bot import MultikBot
from ali import creative_video


class PanelTests(unittest.IsolatedAsyncioTestCase):
    def test_failed_redraw_preserves_original_and_unlocks(self):
        job_id = 'd'*32
        with TemporaryDirectory() as folder, patch.object(config, 'data_dir', Path(folder)), \
             patch.dict(creative_video._jobs, {job_id: {'status':'ready','story':{'scenes':[{'image':'bird'}]}}}), \
             patch('ali.account_images.generate', side_effect=RuntimeError('offline')):
            target = Path(folder) / 'creative_videos' / job_id / 'scene-1.png'
            target.parent.mkdir(parents=True)
            target.write_bytes(b'original')
            with self.assertRaises(RuntimeError):
                creative_video.redraw_scene(job_id, 1)
            self.assertEqual(target.read_bytes(), b'original')
            self.assertEqual(creative_video.get(job_id)['status'], 'ready')

    def test_settings_survive_new_instance(self):
        with TemporaryDirectory() as folder, patch.object(config, 'data_dir', Path(folder)):
            MultikBot()._remember(42, voice='madina', format='16:9', job='a'*32)
            self.assertEqual(MultikBot()._state()['42']['voice'], 'madina')

    async def test_other_user_cannot_render_job(self):
        bot = MultikBot()
        bot.allowed = {42}
        message = NS(chat_id=42, reply_text=AsyncMock())
        query = NS(data='studio:render:'+'a'*32, message=message, answer=AsyncMock())
        update = NS(effective_user=NS(id=42), callback_query=query)
        with patch.object(creative_video, 'get', return_value={'bot_user':43,'bot_chat':42}), \
             patch.object(creative_video, 'start_render') as render:
            await bot.studio_action(update, NS())
        render.assert_not_called()
        message.reply_text.assert_awaited_once()

    async def test_render_uses_saved_voice_and_starts_monitor(self):
        bot = MultikBot()
        bot.allowed = {42}
        message = NS(chat_id=42, reply_text=AsyncMock())
        query = NS(data='studio:render:'+'a'*32, message=message, answer=AsyncMock())
        update = NS(effective_user=NS(id=42), callback_query=query)
        tasks = []
        context = NS(application=NS(create_task=tasks.append))
        job = {'bot_user':42,'bot_chat':42,'bot_voice':'madina','story':{'scenes':[{'speaker':'Ali'}]}}
        with patch.object(creative_video, 'get', return_value=job), \
             patch.object(creative_video, 'start_render') as render:
            await bot.studio_action(update, context)
        render.assert_called_once_with('a'*32, {'Ali':'madina'})
        self.assertEqual(len(tasks), 1)
        tasks[0].close()
