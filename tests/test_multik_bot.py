import asyncio
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image

from test_video_studio import _silence
from ali import creative_video, local_ai, outbox, providers, service, story_video, team_hub
from ali.config import config
from ali.multik_bot import MultikBot
from ali.plugins import video_studio
from ali.skills.video_edit import info


class MultikBotTests(unittest.IsolatedAsyncioTestCase):
    def test_connected_chatgpt_takes_priority_over_openai_key(self):
        with (
            patch.object(config, "openai_api_key", "fixture-key"),
            patch.object(local_ai, "access", return_value=True),
            patch.object(local_ai, "connected", return_value=["codex"]),
            patch.object(creative_video.threading, "Thread") as worker,
        ):
            creative_video.create("Qush va bog‘", "2D serial", "9:16")
        self.assertIs(worker.call_args.kwargs["args"][-1], False)

    def test_explicit_account_mode_requires_connected_chatgpt(self):
        with (
            patch.object(config, "openai_api_key", "fixture-key"),
            patch.object(config, "image_source", "chatgpt_account"),
            patch.object(local_ai, "access", return_value=False),
        ):
            with self.assertRaisesRegex(ValueError, "ChatGPT akkauntini ulang"):
                creative_video.create("Qush va bog‘", "2D serial", "9:16")

    def test_account_storyboard_does_not_fall_back_to_api(self):
        job_id = "account-test"
        with (
            patch.dict(creative_video._jobs, {job_id: {}}),
            patch.object(local_ai, "ask_pro", return_value=None) as ask,
            patch.object(service, "_ask_json") as api,
        ):
            creative_video._run(job_id, "Qush va bog‘", "2D serial", "9:16", use_openai=False)
            self.assertEqual(creative_video.get(job_id)["status"], "error")
        self.assertEqual(ask.call_args.kwargs["only"], "codex")
        api.assert_not_called()

    async def test_cloud_job_renders_and_sends_mp4_without_team_group(self):
        image = io.BytesIO()
        Image.new("RGB", (90, 160), "#72a0c0").save(image, "PNG")
        story = {"title": "Qush va bog‘", "scenes": [
            {"voice": "Qush bog‘ga uchdi.", "big": "Bog‘ga parvoz", "image": "A bird"},
            {"voice": "Davomini kuting!", "big": "Davomini kuting", "image": "A garden"},
        ]}
        uploads = []

        async def send_video(**kwargs):
            self.assertEqual(kwargs["chat_id"], 42)
            self.assertEqual(kwargs["video"].read(8)[4:], b"ftyp")
            uploads.append(kwargs["video"].name)

        with TemporaryDirectory() as folder:
            state = Path(folder)
            with (
                patch.object(config, "data_dir", state),
                patch.object(outbox, "DIR", state / "outbox"),
                patch.object(config, "openai_api_key", "fixture-key"),
                patch.object(config, "image_source", "auto"),
                patch.object(service, "_ask_json", return_value=story) as plan,
                patch.object(story_video, "design_plan"),
                patch.object(providers, "_openai_image", return_value=image.getvalue()) as generate,
                patch.object(video_studio, "_tts", return_value=_silence()),
                patch.object(team_hub, "chat_id", return_value=None),
            ):
                job_id = creative_video.create("Qush va bog‘", "2D serial", "9:16")
                bot = SimpleNamespace(send_video=AsyncMock(side_effect=send_video), send_message=AsyncMock())
                await asyncio.wait_for(MultikBot()._deliver(job_id, 42, SimpleNamespace(bot=bot)), timeout=90)
                job = creative_video.get(job_id)
                self.assertEqual(job["status"], "done", job["message"])
                self.assertEqual(job["source"], "OpenAI API")
                self.assertEqual(plan.call_args.args[1], [])
                self.assertEqual(generate.call_count, 3)
                self.assertEqual(generate.call_args.args[-1], (1080, 1920))
                video = outbox.resolve(job["video"])
                self.assertEqual(uploads, [str(video)])
                self.assertTrue(info(video)["audio"])
                self.assertIn("Davomini kuting!", video.with_suffix(".srt").read_text(encoding="utf-8"))
                bot.send_message.assert_not_awaited()
