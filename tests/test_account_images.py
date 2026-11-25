import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_runtime  # Initialize isolated test state before importing Ali.
from ali import account_images, local_ai, providers, story_video
from ali.config import config


class AccountImageTests(unittest.TestCase):
    def test_readonly_codex_database_switches_login_and_verification_to_writable_home(self):
        failed = SimpleNamespace(returncode=1, stdout="", stderr=(
            "attempt to write a readonly database\n"
            "Error: failed to initialize in-process app-server client: Отказано в доступе. (os error 5)"
        ))
        success = SimpleNamespace(returncode=0, stdout="OK", stderr="")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = str(root / "existing-codex")
            with (
                patch.object(config, "data_dir", root),
                patch.object(local_ai, "STATE", root / "apps.json"),
                patch.object(local_ai, "LIMITS", root / "limits.json"),
                patch.object(local_ai, "WORKDIR", root / "work"),
                patch.object(local_ai, "app_exe", return_value="codex"),
                patch.dict("os.environ", {"CODEX_HOME": original, "ALI_CODEX_MODEL": ""}),
                patch.object(local_ai.subprocess, "run", side_effect=[failed, success]) as run,
                patch.object(local_ai.subprocess, "Popen") as launch,
            ):
                ok, message = local_ai.verify("codex")
                self.assertFalse(ok)
                self.assertIn("«Kirish»", message)
                self.assertEqual(run.call_args.kwargs["env"]["CODEX_HOME"], original)
                home = root / "codex-home"
                self.assertTrue(home.is_dir())
                local_ai.open_login("codex")
                self.assertEqual(launch.call_args.kwargs["env"]["CODEX_HOME"], str(home))
                self.assertTrue(local_ai.verify("codex")[0])
                self.assertEqual(run.call_args.kwargs["env"]["CODEX_HOME"], str(home))
                self.assertEqual(run.call_args.kwargs["env"]["CODEX_SQLITE_HOME"], str(home))

    def test_inaccessible_codex_model_retries_with_compatible_model(self):
        command = ["codex", "exec", "--sandbox", "read-only", "-"]
        rejected = SimpleNamespace(returncode=1, stdout="", stderr="model_not_in_accessible_catalog")
        accepted = SimpleNamespace(returncode=0, stdout="OK", stderr="")
        with patch.dict("os.environ", {"ALI_CODEX_MODEL": ""}), patch.object(
            local_ai.subprocess, "run", side_effect=[rejected, accepted]
        ) as run:
            self.assertIs(local_ai.run_codex(command, input="test"), accepted)
        self.assertEqual(run.call_args.args[0], ["codex", "exec", "--model", "gpt-6-luna", *command[2:]])
        self.assertEqual(run.call_args.kwargs["input"], "test")

    def test_chatgpt_account_unsupported_model_retries_with_compatible_model(self):
        command = ["codex", "exec", "--sandbox", "read-only", "-"]
        rejected = SimpleNamespace(returncode=1, stdout="", stderr="The 'gpt-6-astra' model is not supported when using Codex with a ChatGPT account")
        accepted = SimpleNamespace(returncode=0, stdout="OK", stderr="")
        with patch.dict("os.environ", {"ALI_CODEX_MODEL": ""}), patch.object(
            local_ai.subprocess, "run", side_effect=[rejected, accepted]
        ) as run:
            self.assertIs(local_ai.run_codex(command, input="test"), accepted)
        self.assertEqual(run.call_args.args[0], ["codex", "exec", "--model", "gpt-6-luna", *command[2:]])

    def test_requires_chatgpt_login_and_local_permission(self):
        with patch('ali.local_ai.app_exe', return_value='codex'), patch('ali.local_ai.access', return_value=False), patch.object(account_images.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                account_images.generate('scene')
            run.assert_not_called()
        with patch('ali.local_ai.app_exe', return_value='codex'), patch('ali.local_ai.access', return_value=True), patch.object(account_images.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='API key', stderr='')):
            with self.assertRaises(RuntimeError):
                account_images.generate('scene')

    def test_native_image_output_and_workspace_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def run(args, **kwargs):
                if 'login' in args:
                    return SimpleNamespace(returncode=0, stdout='Logged in using ChatGPT', stderr='')
                self.assertNotIn('OPENAI_API_KEY', kwargs['env'])
                self.assertIn('1:1', kwargs['input'])
                self.assertIn('workspace-write', args)
                (Path(args[args.index('-C')+1])/'scene.png').write_bytes(b'image')
                return SimpleNamespace(returncode=0, stdout='', stderr='')
            with patch.object(config, 'data_dir', root), patch('ali.local_ai.app_exe', return_value='codex'), patch('ali.local_ai.access', return_value=True), patch.object(account_images.subprocess, 'run', side_effect=run), patch.object(story_video, 'good', return_value=True):
                self.assertEqual(account_images.generate('subject', (512,512)), b'image')
                self.assertEqual(list((root/'account_images').iterdir()), [])

    def test_selected_account_route_preserves_aspect_and_no_fallback(self):
        with patch.object(config, 'image_source', 'chatgpt_account'), patch.object(account_images, 'generate', return_value=b'image') as generate:
            sources = providers.image_sources('pro', size=(1920,1080))
            self.assertEqual(len(sources),1)
            self.assertEqual(sources[0][1]('scene'), b'image')
            generate.assert_called_once_with('scene', (1920,1080))
        with tempfile.TemporaryDirectory() as tmp, patch.object(config, 'image_source', 'chatgpt_account'), patch.object(story_video, 'ART', Path(tmp)), patch.object(providers, 'image_sources', return_value=[]), patch.object(story_video, '_pollinations') as poll, patch('ali.scene_art.illustrate') as art:
            with self.assertRaisesRegex(RuntimeError, 'ChatGPT'):
                story_video.images([{'image':'scene'}], 7)
            poll.assert_not_called()
            art.assert_not_called()
