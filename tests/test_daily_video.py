import json
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik ALI_STATE_DIR va test sozlamalari ali'dan oldin o'rnatilsin
from ali import chat_import, daily_video


class DailyVideoTests(unittest.TestCase):
    def test_runs_at_11_and_16_once_and_skips_stale_slots(self):
        started = []
        with tempfile.TemporaryDirectory() as d, patch.object(daily_video, "STATE", Path(d) / "dv.json"), \
                patch.object(daily_video.threading, "Thread") as thread:
            thread.side_effect = lambda target, args, **kw: started.append(args[0]) or unittest.mock.MagicMock()
            daily_video.tick(print, datetime(2026, 11, 5, 10, 59))
            daily_video.tick(print, datetime(2026, 11, 5, 11, 0, 30))
            daily_video.tick(print, datetime(2026, 11, 5, 11, 5))  # qayta yoqilgandek - takrorlanmaydi
            self.assertEqual(started, ["11:00"])
            daily_video.tick(print, datetime(2026, 11, 6, 20, 0))  # kompyuter kun bo'yi o'chiq edi - eskisi o'tkaziladi
            self.assertEqual(started, ["11:00"])

    def test_template_without_ai_has_all_scenes_and_cta(self):
        data = {**daily_video.IDEAS[1], "scenes": daily_video.IDEAS[1]["scenes"]}
        page = daily_video.template(data)
        self.assertIn("@keyframes", page)
        self.assertIn("HAJMLI HARFLAR", page)
        self.assertIn("Bepul o&#x27;lchov", page)
        self.assertNotIn("<script", page)

    def test_idea_without_ai_rotates_topics(self):
        with tempfile.TemporaryDirectory() as d, patch.object(daily_video, "STATE", Path(d) / "dv.json"), \
                patch("ali.service._ask_json", side_effect=RuntimeError("limit")):
            first, src = daily_video.idea("11:00")
            daily_video._save({"history": [{"title": first["title"]}]})
            second, _ = daily_video.idea("16:00")
        self.assertEqual(src, "bilim")
        self.assertNotEqual(first["title"], second["title"])
        self.assertGreaterEqual(len(first["scenes"]), 3)


class CouncilGateTests(unittest.TestCase):
    def _run(self, score):
        from ali import studio_flow
        res = {"path": "v.mp4", "sources": "g'oya: AI", "idea": {**daily_video.IDEAS[0], "caption": "c", "hashtags": "#h",
                                                                 "scenes": daily_video.IDEAS[0]["scenes"]}}
        with tempfile.TemporaryDirectory() as d, patch.object(daily_video, "STATE", Path(d) / "dv.json"), \
                patch.object(studio_flow, "STATE", Path(d) / "st.json"), \
                patch.object(daily_video, "make", return_value=res), \
                patch("ali.team_hub.review_video", return_value=("qaror", score)), \
                patch("ali.tg_account.send_file", return_value=7) as post, \
                patch.object(studio_flow, "send_files") as owner:
            daily_video.run("11:00", print)
        return post.call_count, owner.call_args[0][0]

    def test_video_goes_to_channel_only_after_council_approves(self):
        posted, text = self._run(8.0)
        self.assertEqual(posted, 1)
        self.assertIn("Kengash bahosi: 8/10", text)
        posted, text = self._run(3.0)
        self.assertEqual(posted, 0)
        self.assertIn("kengashdan o'tmadi", text)

    def test_score_parsed_from_decision(self):
        from ali.team_hub import score_of
        self.assertEqual(score_of("📊 Instagram uchun BAHO: 7/10 - hook kuchli"), 7.0)
        self.assertEqual(score_of("Baho: 6.5 — o'rtacha"), 6.5)
        self.assertIsNone(score_of("baho berilmadi"))


class ChatImportTests(unittest.TestCase):
    def test_parses_chatgpt_and_claude_exports(self):
        gpt = [{"title": "Pilon narxi", "mapping": {
            "a": {"message": {"author": {"role": "user"}, "content": {"parts": ["Pilon qancha turadi?"]}, "create_time": 1}},
            "b": {"message": {"author": {"role": "assistant"}, "content": {"parts": ["Taxminan 8-15 mln so'm."]},
                              "create_time": 2}},
            "c": {"message": None}}}]
        claude = [{"name": "Reels hook", "chat_messages": [{"sender": "human", "text": "Hook yoz"},
                                                           {"sender": "assistant", "text": "Tunda ham kunduzdek!"}]}]
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "export.zip"
            with zipfile.ZipFile(z, "w") as f:
                f.writestr("conversations.json", json.dumps(gpt))
            convs = chat_import.load(z)
            self.assertEqual(convs[0]["source"], "ChatGPT")
            self.assertEqual([r for r, _ in convs[0]["messages"]], ["user", "assistant"])
            self.assertIn("8-15 mln", chat_import.digest(convs[0]))
            j = Path(d) / "conversations.json"
            j.write_text(json.dumps(claude), encoding="utf-8")
            self.assertEqual(chat_import.load(j)[0]["source"], "Claude")


if __name__ == "__main__":
    unittest.main()
