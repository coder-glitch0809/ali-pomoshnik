import tempfile
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_runtime  # Initialize isolated test state before importing Ali.
from ali import account_images, local_ai, providers, story_video
from ali.config import config


class AccountImageTests(unittest.TestCase):
    def test_codex_windows_startup_permission_failure_prepares_home(self):
        failure = SimpleNamespace(returncode=1, stdout="", stderr=(
            "WARNING: failed to clean up stale arg0 temp dirs: (os error 5)\n"
            "WARNING: proceeding, even though we could not create PATH aliases: (os error 5)\n"
            "Error: failed to initialize in-process app-server client: (os error 5)"
        ))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            with (
                patch.object(config, "data_dir", root),
                patch.object(local_ai, "STATE", root / "apps.json"),
                patch.object(local_ai, "WORKDIR", root / "work"),
                patch.object(local_ai, "app_exe", return_value="codex"),
                patch.object(local_ai.subprocess, "run", return_value=failure),
            ):
                ok, message = local_ai.verify("codex")
                self.assertFalse(ok)
                self.assertIn("Kirish", message)
                self.assertTrue((root / "codex-home").is_dir())
                self.assertEqual(local_ai.clean_env("codex")["CODEX_HOME"], str(root / "codex-home"))
                ok, message = local_ai.verify("codex")
                self.assertFalse(ok)
                self.assertIn("ruxsatini", message)

    def test_codex_state_database_open_failure_prepares_a_new_home(self):
        failure = SimpleNamespace(returncode=1, stdout="", stderr=(
            "Failed to initialize state runtime: failed to open state DB at state_5.sqlite: "
            "(code: 14) unable to open database file"
        ))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            with (
                patch.object(config, "data_dir", root),
                patch.object(local_ai, "STATE", root / "apps.json"),
                patch.object(local_ai, "WORKDIR", root / "work"),
                patch.object(local_ai, "app_exe", return_value="codex"),
                patch.object(local_ai.subprocess, "run", return_value=failure),
            ):
                ok, message = local_ai.verify("codex")
                self.assertFalse(ok)
                self.assertIn("«Kirish»", message)
                self.assertEqual(local_ai.clean_env("codex")["CODEX_HOME"], str(root / "codex-home"))

    def test_windows_gemini_login_and_prompt_use_direct_cli(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(local_ai, "WORKDIR", Path(folder)):
            with (
                patch.object(local_ai.os, "name", "nt"),
                patch.object(local_ai.subprocess, "STARTUPINFO", create=True,
                             return_value=SimpleNamespace(dwFlags=0, wShowWindow=0)),
                patch.object(local_ai.subprocess, "STARTF_USESHOWWINDOW", 1, create=True),
                patch.object(local_ai, "app_exe", return_value="gemini.cmd"),
                patch.object(local_ai.subprocess, "Popen") as launch,
                patch.object(local_ai.subprocess, "run", return_value=SimpleNamespace(
                    returncode=0, stdout="OK", stderr=""
                )) as run,
            ):
                local_ai.open_login("gemini")
                self.assertEqual(launch.call_args.kwargs["startupinfo"].wShowWindow, 1)
                self.assertEqual(launch.call_args.kwargs["cwd"], Path(folder))
                self.assertEqual(local_ai.ask_one("gemini", "gemini.cmd", "Verify", account_only=True), "OK")
                self.assertEqual(launch.call_args.kwargs["env"]["GEMINI_CLI_NO_RELAUNCH"], "1")
                self.assertEqual(run.call_args.kwargs["env"]["GEMINI_CLI_NO_RELAUNCH"], "1")

    def test_login_launch_failure_is_reported(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(local_ai, "WORKDIR", Path(folder)),
            patch.object(local_ai, "app_exe", return_value="codex.cmd"),
            patch.object(local_ai.subprocess, "Popen", side_effect=OSError("Access denied")),
        ):
            with self.assertRaisesRegex(RuntimeError, "kirish oynasi ochilmadi"):
                local_ai.open_login("codex")

    def test_readonly_codex_database_switches_login_and_verification_to_writable_home(self):
        failed = SimpleNamespace(returncode=1, stdout="", stderr=(
            "attempt to write a readonly database\n"
            "Error: failed to initialize in-process app-server client: Отказано в доступе. (os error 5)"
        ))
        success = SimpleNamespace(returncode=0, stdout="OK", stderr="")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
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
            session = '01a21614-ee9b-7082-93e2-d440286ea894'
            home = root / 'codex-home'
            artifact = home / 'generated_images' / session / 'exec-image.png'
            def run(args, **kwargs):
                if 'login' in args:
                    return SimpleNamespace(returncode=0, stdout='Logged in using ChatGPT', stderr='')
                self.assertNotIn('OPENAI_API_KEY', kwargs['env'])
                self.assertIn('1:1', kwargs['input'])
                self.assertIn('read-only', args)
                self.assertIn('--json', args)
                artifact.parent.mkdir(parents=True)
                artifact.write_bytes(b'image')
                return SimpleNamespace(returncode=0, stdout=json.dumps({'type':'thread.started','thread_id':session}), stderr='')
            with patch.object(config, 'data_dir', root), patch('ali.local_ai.app_exe', return_value='codex'), patch('ali.local_ai.access', return_value=True), patch.object(local_ai, 'clean_env', return_value={'CODEX_HOME':str(home)}), patch.object(account_images.subprocess, 'run', side_effect=run), patch.object(story_video, 'good', return_value=True):
                self.assertEqual(account_images.generate('subject', (512,512)), b'image')
                self.assertEqual(list((root/'account_images').iterdir()), [])
                self.assertTrue(artifact.is_file())

    def test_image_lookup_rejects_unrelated_and_ambiguous_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            session = '01a21614-ee9b-7082-93e2-d440286ea894'
            folder = home / 'generated_images' / session
            folder.mkdir(parents=True)
            (folder / 'one.png').write_bytes(b'one')
            env = {'CODEX_HOME':str(home)}
            event = json.dumps({'type':'thread.started','thread_id':session})
            self.assertIsNone(account_images.generated_image('not json', env))
            self.assertIsNone(account_images.generated_image(json.dumps({'type':'thread.started','thread_id':'../../other'}), env))
            other = event.replace(session, '01a21614-ee9b-7082-93e2-d440286ea895')
            self.assertIsNone(account_images.generated_image(other, env))
            self.assertIsNone(account_images.generated_image(event+'\n'+other, env))
            self.assertEqual(account_images.generated_image(event, env), (folder / 'one.png').resolve())
            (folder / 'two.png').write_bytes(b'two')
            self.assertIsNone(account_images.generated_image(event, env))

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
