import asyncio
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image

from test_video_studio import _silence
from ali import creative_video, outbox, providers, service, story_video, team_hub
from ali.config import config
from ali.multik_bot import MultikBot
from ali.plugins import video_studio
from ali.skills.video_edit import info


class MultikBotTests(unittest.IsolatedAsyncioTestCase):
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
