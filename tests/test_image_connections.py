import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_runtime
from fastapi.testclient import TestClient
from PIL import Image
from ali import connections, image_connections as images, local_ai, outbox, providers
from ali.config import config
from runtime import app


class ImageConnectionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for obj, name, value in [(images, 'STATE', self.root/'images.json'),
                                 (connections, 'ENV_FILE', self.root/'.env'),
                                 (outbox, 'DIR', self.root/'outbox'),
                                 (config, 'openai_api_key', 'fixture-secret-key'),
                                 (config, 'image_quality', 'pro')]:
            patcher = patch.object(obj, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_image_proof_is_real_and_expires_when_key_changes(self):
        buffer = io.BytesIO()
        Image.new('RGB', (512, 512), 'blue').save(buffer, 'PNG')
        with patch.object(providers, '_openai_image', return_value=buffer.getvalue()), patch.object(images, 'reset'):
            result = images.test_image('chatgpt')
        self.assertTrue(result['ok'])
        self.assertTrue((outbox.DIR/result['file']).is_file())
        self.assertNotIn('fixture-secret-key', images.STATE.read_text())
        self.assertTrue(images.status('chatgpt')['ok'])
        with patch.object(config, 'openai_api_key', 'replacement'):
            self.assertIsNone(images.status('chatgpt')['ok'])

    def test_error_is_useful_but_never_echoes_provider_secret(self):
        with patch.object(providers, '_openai_image', side_effect=RuntimeError('429 fixture-secret-key')):
            result = images.test_image('chatgpt')
        self.assertFalse(result['ok'])
        self.assertIn('kvotasi', result['message'])
        self.assertNotIn('fixture-secret-key', json.dumps(result))
        with patch.object(providers, '_openai_image', return_value=b'not an image'):
            self.assertFalse(images.test_image('chatgpt')['ok'])

    def test_model_settings_validate_before_writing_and_reset_old_client(self):
        with patch.object(config, 'openai_image_model', 'old'), patch.object(images, 'reset') as reset:
            asyncio.run(images.configure('chatgpt', {'model': 'gpt-image-1', 'quality': 'standard'}))
            self.assertEqual(config.openai_image_model, 'gpt-image-1')
            self.assertEqual(config.image_quality, 'standard')
            reset.assert_called_once_with('chatgpt')
            saved = connections.ENV_FILE.read_text()
            with self.assertRaises(ValueError):
                asyncio.run(images.configure('chatgpt', {'model': 'bad\nTOKEN=secret'}))
            self.assertEqual(connections.ENV_FILE.read_text(), saved)

    def test_image_routes_require_owner_and_reject_foreign_origin(self):
        client = TestClient(app)
        endpoint = '/api/image-connections/chatgpt/test'
        self.assertEqual(client.post(endpoint).status_code, 401)
        client.post('/api/login', json={'password': 'test-password'})
        self.assertEqual(client.post(endpoint, headers={'Origin': 'https://evil.example'}).status_code, 403)
        with patch.object(images, 'test_image', return_value={'ok': True, 'file': 'test.png'}) as test:
            self.assertEqual(client.post(endpoint).status_code, 200)
            test.assert_called_once_with('chatgpt')
        self.assertEqual(client.post('/api/image-connections/other/test').status_code, 400)

    def test_catalog_has_separate_account_and_image_status_without_credentials(self):
        entries = {p['id']: p for p in connections.catalog()}
        for name in ('gemini', 'chatgpt'):
            self.assertIn('account_url', entries[name]['ai'])
            self.assertIsNone(entries[name]['ai']['image_status']['ok'])
        self.assertNotIn('fixture-secret-key', json.dumps(entries))

    def test_gemini_login_verification_never_uses_api_key(self):
        result = SimpleNamespace(returncode=0, stdout='OK', stderr='')
        with patch.object(local_ai, 'WORKDIR', self.root/'cli'), \
                patch.object(local_ai, 'paused_until', return_value=0), \
                patch.object(local_ai.subprocess, 'run', return_value=result) as cli, \
                patch.object(providers, 'gemini_ask') as api:
            self.assertEqual(local_ai.ask_one('gemini', 'gemini.cmd', 'OK', account_only=True), 'OK')
            self.assertNotIn('GEMINI_API_KEY', cli.call_args.kwargs['env'])
            api.assert_not_called()
        self.assertIn('gemini', local_ai.APPS)

    def test_account_and_api_do_not_duplicate_gemini(self):
        with patch.object(config, 'gemini_api_key', 'fixture'), \
                patch.object(local_ai, 'app_state', return_value={'gemini': {'connected': True}}), \
                patch.object(local_ai, 'app_exe', return_value='gemini.cmd'), \
                patch.object(local_ai, 'paused_until', return_value=0), \
                patch('ali.omniroute.available', return_value=False):
            self.assertEqual(local_ai.connected().count('gemini'), 1)
