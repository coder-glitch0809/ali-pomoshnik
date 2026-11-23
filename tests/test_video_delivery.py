import json
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from unittest.mock import AsyncMock
from datetime import datetime

import test_runtime
from ali import video_delivery as delivery, daily_video, autopilot


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for obj, name, value in ((delivery, 'DB', self.root/'deliveries.db'),
                                 (delivery.config, 'telegram_token', 'fixture'),
                                 (delivery.config, 'telegram_owner_id', 123)):
            p = patch.object(obj, name, value); p.start(); self.addCleanup(p.stop)
        self.file = self.root/'video.mp4'
        self.file.write_bytes(b'fixture')

    def test_partial_send_resumes_and_records_file_receipt(self):
        with patch.object(delivery, '_post', side_effect=[101, RuntimeError('offline')]), \
                patch('ali.skills.video_edit.info', return_value={'width':1920,'height':1080,'duration':30}):
            self.assertFalse(delivery.send_files('Video', [self.file]))
        with delivery._db() as db:
            row = db.execute('SELECT * FROM deliveries').fetchone()
            self.assertEqual(json.loads(row['receipts']), [101])
            self.assertFalse(row['sent'])
            db.execute('UPDATE deliveries SET retry=0')
        with patch.object(delivery, '_post', return_value=102) as post, \
                patch('ali.skills.video_edit.info', return_value={'width':1920,'height':1080,'duration':30}):
            delivery.flush_pending()
            self.assertEqual(post.call_args.args[0], 'sendVideo')
            self.assertTrue(delivery.send_files('Video', [self.file]))
            post.assert_called_once()

    def test_missing_and_oversized_files_never_count_as_sent(self):
        with patch.object(delivery, '_post') as post:
            self.assertFalse(delivery.send_files('Missing', [self.root/'missing.mp4']))
            with self.file.open('wb') as f:
                f.truncate(46*1024*1024)
            self.assertFalse(delivery.send_files('Too large', [self.file]))
            post.assert_not_called()
        with delivery._db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM deliveries WHERE sent=0').fetchone()[0], 2)

    def test_http_ok_without_telegram_receipt_is_not_success(self):
        with patch.object(delivery.httpx, 'post', return_value=Mock(status_code=200, json=lambda:{'ok':False})):
            with self.assertRaisesRegex(RuntimeError, 'receipt missing'):
                delivery._post('sendMessage')

    def test_large_valid_video_gets_transport_copy_without_changing_original(self):
        with self.file.open('wb') as stream:
            stream.truncate(46 * 1024 * 1024)
        meta = {'duration': 200, 'width': 1920, 'height': 1080, 'fps': 30, 'audio': True}
        with patch('ali.skills.video_edit.info', return_value=meta), \
                patch('ali.skills.video_edit._run', side_effect=lambda args: Path(args[-1]).write_bytes(b'encoded')) as encode:
            output = delivery.telegram_video(self.file)
            self.assertEqual(output.read_bytes(), b'encoded')
            self.assertEqual(self.file.stat().st_size, 46 * 1024 * 1024)
            self.assertEqual(delivery.telegram_video(self.file), output)
            encode.assert_called_once()

    def test_reels_failure_is_retryable_not_done(self):
        with patch.object(daily_video, 'STATE', self.root/'daily.json'), \
                patch.object(daily_video, 'run', return_value=None):
            daily_video._scheduled_run('11:00', Mock(), '2026-11-20 11:00')
            state = daily_video._state()
            self.assertNotIn('2026-11-20 11:00', state['done'])
            self.assertIn('2026-11-20 11:00', state['retry'])
            with patch.object(daily_video, 'run', return_value=str(self.file)):
                daily_video._scheduled_run('11:00', Mock(), '2026-11-20 11:00')
            self.assertEqual(daily_video._state()['done']['2026-11-20 11:00'], str(self.file))

    def test_six_hour_channel_learning_is_manual_only(self):
        with patch('ali.tg_account.configured', return_value=True), \
                patch('ali.tg_account.learn_all_channels') as learn, \
                patch('ali.tg_account.review_chats', return_value={'reminders':[], 'summary':'', 'facts':0}), \
                patch('ali.tg_watch.tick'), patch.object(autopilot, '_save'):
            autopilot._telegram_tick({}, 9999999999)
        learn.assert_not_called()

    def test_failed_slots_survive_midnight_and_resume_after_ai_recovery(self):
        from ali import youtube_video, ai_status
        now = datetime(2026, 11, 20, 9, tzinfo=daily_video.TZ)
        for module in (daily_video, youtube_video):
            with patch.object(module, 'STATE', self.root/(module.__name__+'.json')), \
                    patch.object(module, '_scheduled', set()), patch.object(module.threading, 'Thread') as thread:
                key = '2026-11-19 17:00' if module is youtube_video else '2026-11-19 16:00'
                module._save({'retry': {key: now.timestamp()+100}})
                with patch.object(ai_status, 'recovered_at', return_value=0):
                    module.tick(Mock(), now)
                    thread.assert_not_called()
                with patch.object(ai_status, 'recovered_at', return_value=now.timestamp()):
                    module.tick(Mock(), now)
                    thread.assert_called_once()

    def test_telegram_button_runs_channel_reader(self):
        from ali.telegram_bot import TelegramBot
        bot = TelegramBot.__new__(TelegramBot)
        bot._guard = AsyncMock(return_value=True)
        bot.safe_answer = AsyncMock()
        bot.app = Mock()
        bot.app.bot.send_message = AsyncMock()
        update = Mock()
        update.effective_message.reply_text = AsyncMock()
        async def run():
            await bot.on_learn_channels(update, Mock())
            await asyncio.gather(*bot.learn_tasks)
            await asyncio.sleep(0)
        with patch('ali.tg_account.learn_all_channels', return_value=[]) as learn:
            asyncio.run(run())
        learn.assert_called_once()
        self.assertFalse(bot._channel_learning)
