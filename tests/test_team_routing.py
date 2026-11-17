import unittest
from types import SimpleNamespace
from unittest.mock import patch

import test_runtime  # isolated application state
from ali import daily_video, story_video, team_hub


class TeamRoutingTests(unittest.TestCase):
    def setUp(self):
        self.agents = {key: SimpleNamespace(name=name, icon="X") for key, name in
                       (("kontent", "Kontent"), ("dasturchi", "Dasturchi"))}

    def test_explicit_address_overrides_topic_and_ali_stays_ali(self):
        self.assertEqual(team_hub.reply_agent("Ali, kamchilik bor", "kontent", self.agents), "ali")
        self.assertEqual(team_hub.reply_agent("Sevara, yoz", "ali", self.agents), "kontent")
        self.assertEqual(team_hub.reply_agent("davom et", "kontent", self.agents), "kontent")
        self.assertIsNone(team_hub.addressed("Jasurning ishi yaxshi", self.agents))

    def test_reply_in_general_chat_keeps_agent_identity(self):
        signed = team_hub.label("kontent", self.agents) + ":\nNatija"
        self.assertEqual(team_hub.reply_agent("buni tuzat", None, self.agents, signed), "kontent")
        self.assertIsNone(team_hub.reply_agent("salom", None, self.agents))

    def test_background_posts_have_agent_signature(self):
        with patch.object(team_hub, "chat_id", return_value=-123), \
                patch.object(team_hub, "ensure_topic", return_value=5), patch.object(team_hub, "_api") as api:
            team_hub._send("kontent", "Ish tayyor", self.agents)
        self.assertTrue(api.call_args.kwargs["text"].startswith(team_hub.label("kontent", self.agents) + ":"))

    def test_export_requires_resolution_fps_and_audio(self):
        good = dict(width=1080, height=1920, fps=30, duration=15, audio=True)
        with patch("ali.skills.video_edit.info", return_value=good):
            self.assertEqual(daily_video.quality_issues("clip.mp4"), [])
        with patch("ali.skills.video_edit.info", return_value={**good, "audio": False, "fps": 24}):
            self.assertEqual(len(daily_video.quality_issues("clip.mp4")), 2)

    def test_designer_updates_artwork_without_changing_script(self):
        data = {"scenes": [{"voice": "original", "image": "old"}]}
        with patch("ali.daily_video._agent", return_value="designer"), \
                patch("ali.service._ask_json", return_value={"scenes": [{"image": "Consistent cinematic scene with warm lighting"}]}):
            story_video.design_plan(data, [])
        self.assertEqual(data["scenes"][0]["voice"], "original")
        self.assertIn("cinematic", data["scenes"][0]["image"])

    def test_incomplete_design_does_not_partially_mutate_scenes(self):
        data = {"scenes": [{"voice": "original", "image": "old"}]}
        with patch("ali.daily_video._agent", return_value="designer"), \
                patch("ali.service._ask_json", return_value={"scenes": []}), \
                patch.object(story_video.log, "warning"):
            self.assertIn("olinmadi", story_video.design_plan(data, []))
        self.assertEqual(data["scenes"][0]["image"], "old")
