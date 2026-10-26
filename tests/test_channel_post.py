import unittest
from unittest.mock import MagicMock, patch


def setUpModule():
    # ali.config'ni kech import qilamiz: test_runtime avval o'z muhitini (ALI_STATE_DIR va h.k.) o'rnatsin
    global providers, config, channel_post
    from ali import providers
    from ali.config import config
    from ali.skills import channel_post


class ImageSourcesTest(unittest.TestCase):
    def test_pro_tries_pro_models_first_and_falls_back(self):
        with patch.object(config, "openai_api_key", "k"), patch.object(config, "gemini_api_key", "k"):
            names = [n for n, _ in providers.image_sources("pro")]
            self.assertTrue(names[0].startswith("ChatGPT pro"))
            self.assertTrue(names[1].startswith("Gemini pro"))
            std = [n for n, _ in providers.image_sources("standard")]
            self.assertTrue(std[0].startswith("Gemini ("))
            with patch.object(providers, "_openai_image", side_effect=RuntimeError("limit")), \
                    patch.object(providers, "generate_image", return_value=b"png") as gen:
                data, source = providers.generate_image_best("cat", "pro")
            self.assertEqual(data, b"png")
            self.assertTrue(source.startswith("Gemini pro"))
            gen.assert_called_once_with("cat", config.gemini_image_pro_model)

    def test_no_keys_raises(self):
        with patch.object(config, "openai_api_key", ""), patch.object(config, "gemini_api_key", ""):
            with self.assertRaises(RuntimeError):
                providers.generate_image_best("cat")


class ChannelPostTest(unittest.TestCase):
    def test_chat_id_normalized(self):
        self.assertEqual(channel_post._chat_id("mykanal"), "@mykanal")
        self.assertEqual(channel_post._chat_id("https://t.me/mykanal"), "@mykanal")
        self.assertEqual(channel_post._chat_id("-1001234"), "-1001234")
        with patch.object(config, "telegram_channel", ""), self.assertRaises(RuntimeError):
            channel_post._chat_id("")

    def test_post_sends_photo_to_channel(self):
        response = MagicMock(status_code=200, content=b"1")
        response.json.return_value = {"ok": True, "result": {"message_id": 7}}
        with patch.object(config, "telegram_token", "t"), \
                patch("ali.providers.generate_image_best", return_value=(b"png", "Gemini pro")), \
                patch("ali.skills.channel_post.httpx.post", return_value=response) as post:
            out = channel_post.post_image_to_channel("Bahor", "spring", "Bahor keldi", "@kanal")
        self.assertIn("@kanal", out)
        self.assertIn("#7", out)
        self.assertEqual(post.call_args.kwargs["data"]["chat_id"], "@kanal")
