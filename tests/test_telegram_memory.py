import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import test_runtime
from ali import telegram_memory as tm
from ali.memory import Memory
from ali.config import config
from telegram.ext import ExtBot


class TelegramMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'memory.db'
        self.memory = Memory(self.path)
        self.patch = patch.object(tm, 'memory', self.memory)
        self.patch.start()
        self.journal = patch('ali.memory.journal')
        self.journal.start()
        tm._request_chat.set(None)

    def tearDown(self):
        self.patch.stop(); self.journal.stop()
        self.memory.conn.close(); self.temp.cleanup()

    def test_events_survive_restart_and_are_not_duplicated(self):
        tm.record('Multik', 42, 'update:7', 'request', 'Qush haqida multfilm')
        tm.record('Multik', 42, 'update:7', 'request', 'Qush haqida multfilm')
        self.memory.conn.close()
        self.memory = Memory(self.path)
        with patch.object(tm, 'memory', self.memory):
            tm.record('Multik',42,'update:7','request','Qush haqida multfilm')
        rows = self.memory.vault_list('Qush')['items']
        self.assertEqual(len(rows),1)
        self.assertIn('Telegram',self.memory.vault_detail(rows[0]['id'])['content'])

    def test_only_trusted_requests_and_no_login_password(self):
        handler = tm.observe('Ali',lambda:{42})
        update = SimpleNamespace(effective_user=SimpleNamespace(id=42),effective_chat=SimpleNamespace(id=42),
            callback_query=None,update_id=8,effective_message=SimpleNamespace(text='/login my-secret',caption=None))
        asyncio.run(handler.callback(update,None))
        self.assertEqual(self.memory.vault_list('my-secret')['total'],0)
        self.assertEqual(self.memory.vault_list('parol yashirildi')['total'],1)
        update.effective_user.id=999;update.update_id=9;update.effective_message.text='Private public user'
        asyncio.run(handler.callback(update,None))
        self.assertEqual(self.memory.vault_list('Private public user')['total'],0)

    def test_confirmed_video_delivery_and_failure_not_reported_as_success(self):
        bot=tm.MemoryBot('123456:TEST',source='Multik')
        result={'message_id':77,'caption':'Tayyor hikoya','video':{'file_name':'story.mp4'}}
        with patch.object(config,'telegram_owner_id',42), patch.object(ExtBot,'_do_post',AsyncMock(return_value=result)):
            asyncio.run(bot._do_post('sendVideo',{'chat_id':42}))
            asyncio.run(bot._do_post('sendVideo',{'chat_id':42}))
            asyncio.run(bot._do_post('sendVideo',{'chat_id':999}))
        self.assertEqual(self.memory.vault_list('story.mp4')['total'],1)
        with patch.object(config,'telegram_owner_id',42), patch.object(ExtBot,'_do_post',AsyncMock(side_effect=RuntimeError('network'))):
            with self.assertRaises(RuntimeError):asyncio.run(bot._do_post('sendMessage',{'chat_id':42,'text':'not sent'}))
        self.assertEqual(self.memory.vault_list('not sent')['total'],0)

    def test_configured_credentials_and_token_links_are_redacted(self):
        with patch.object(config,'elevenlabs_api_key','secret-eleven-key'):
            text=tm.redact('Key secret-eleven-key https://example.test/login?token=123')
        self.assertNotIn('secret-eleven-key',text)
        self.assertNotIn('token=123',text)

    def test_database_failure_rolls_back_event_marker(self):
        with self.assertRaises(Exception):
            self.memory.log_event('test','session','role',None)
        self.assertTrue(self.memory.log_event('test','session','role','Retry works'))


if __name__ == '__main__':unittest.main()
