import copy
import unittest
from unittest.mock import patch

import test_runtime  # Isolate Ali state before imports.
from ali import youtube_content as youtube


def example():
    voice = "Do'koningiz peshlavhasini mijoz ko'chadan bemalol o'qiy oladimi bugun buni oddiy amaliy misol orqali birga tekshirib ko'ramiz"
    return {"title": "Peshlavha", "topic": "Peshlavha kontrasti", "hook": voice,
            "character": "Uzbek shop owner in his forties wearing a blue apron and white shirt",
            "cta": "Planet Print bilan bog'laning", "scenes": [
                {"voice": voice, "big": "Aniq yozuv", "image": "Wide shot of a shop sign in daylight",
                 "section": "hook" if i == 0 else "cta" if i == 19 else "problem" if i < 10 else "solution"}
                for i in range(20)]}


class YouTubeContentTests(unittest.TestCase):
    def test_used_topics_rotate_even_when_model_renames_topic(self):
        with patch.object(youtube, "research", return_value={}) as research, \
                patch("ali.daily_video._agent", return_value=""), \
                patch("ali.service._ask_json", return_value=example()):
            data = youtube.script([{"topic": youtube.TOPICS[0]}], [])
        research.assert_called_once_with(youtube.TOPICS[1], list(youtube.TOPICS[1:]))
        self.assertEqual(data["topic"], youtube.TOPICS[1])

    def test_research_can_select_supported_candidate_and_preserve_character(self):
        with patch.object(youtube, "research", return_value={"selected_topic": youtube.TOPICS[3]}), \
                patch("ali.daily_video._agent", return_value=""), \
                patch("ali.service._ask_json", return_value=example()):
            data = youtube.script([], [])
        self.assertEqual(data["topic"], youtube.TOPICS[3])
        for scene in data["scenes"]:
            self.assertLess(len(scene["image"]), 600)
            self.assertIn(data["character"], scene["image"][:600])
            self.assertIn("shop sign in daylight", scene["image"][:600])
        too_long = example()
        too_long["character"] = "person " * 40
        with self.assertRaisesRegex(ValueError, "Personaj"):
            youtube.validate(too_long)

    def test_valid_script_is_landscape_and_keeps_research_metadata(self):
        evidence = {"topic_sources": ["https://example.com/article"], "trend_evidence": "Research context",
                    "trend_status": "research_context", "popularity_verified": False}
        with patch.object(youtube, "research", return_value=evidence), \
                patch("ali.daily_video._agent", return_value=""), \
                patch("ali.service._ask_json", return_value=example()):
            data = youtube.script([], [])
        self.assertEqual(data["aspect_ratio"], "16:9")
        self.assertTrue(120 <= data["estimated_duration"] <= 240)
        self.assertFalse(data["popularity_verified"])
        self.assertEqual(data["topic_sources"], evidence["topic_sources"])
        self.assertTrue(all(data["character"] in s["image"] for s in data["scenes"]))

    def test_invalid_scripts_retry_and_duplicates_fail_honestly(self):
        original = example()
        history = [{"title": "Different title", "script": " ".join(s["voice"] for s in original["scenes"])}]
        with patch.object(youtube, "research", return_value={}), \
                patch("ali.daily_video._agent", return_value=""), \
                patch("ali.service._ask_json", side_effect=[{}, copy.deepcopy(original), copy.deepcopy(original)]) as ask:
            with self.assertRaisesRegex(ValueError, "Takroriy"):
                youtube.script(history, [])
            self.assertEqual(ask.call_count, 3)

    def test_rejects_short_or_missing_hook_and_accepts_corrected_retry(self):
        invalid = example()
        invalid["scenes"][0]["voice"] = "Too short"
        with self.assertRaisesRegex(ValueError, "12–25"):
            youtube.validate(invalid)
        invalid = example()
        invalid["hook"] = "Different hook"
        with self.assertRaisesRegex(ValueError, "Hook"):
            youtube.validate(invalid)
        with patch.object(youtube, "research", return_value={}), \
                patch("ali.daily_video._agent", return_value=""), \
                patch("ali.service._ask_json", side_effect=[invalid, example()]) as ask:
            self.assertEqual(len(youtube.script([], [])["scenes"]), 20)
            self.assertEqual(ask.call_count, 2)

    def test_research_disabled_or_unavailable_is_not_called_popular(self):
        with patch.object(youtube.config, "web_search", False), \
                patch("ali.skills.web_research.google_research") as search:
            result = youtube.research("Topic")
            search.assert_not_called()
        self.assertEqual(result["trend_status"], "knowledge_fallback")
        self.assertFalse(result["popularity_verified"])
        with patch.object(youtube.config, "web_search", True), \
                patch("ali.skills.web_research.google_research", side_effect=RuntimeError("offline")):
            self.assertEqual(youtube.research("Topic")["topic_sources"], [])


if __name__ == "__main__":
    unittest.main()
