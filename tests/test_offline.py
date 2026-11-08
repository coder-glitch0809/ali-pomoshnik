import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik ALI_STATE_DIR va test sozlamalari ali'dan oldin o'rnatilsin
from ali import service

ROWS = [{"topic": "[video_montajchi] Hook to'plami: tashqi reklama", "created_at": "2026-10-31",
         "content": "TASHQI REKLAMA HOOKLARI:\n- «Kechasi mijozlaringiz sizni topa oladimi?»\nQOIDA: hook 7 so'zdan oshmasin."},
        {"topic": "[kontent] Reels", "created_at": "2026-10-30",
         "content": "Reels hook birinchi uch soniyada tomoshabinni ushlab qolishi kerak. Qisqa."}]


class OfflineTests(unittest.TestCase):
    def test_knowledge_answer_uses_matching_block_and_sentences(self):
        a = SimpleNamespace(icon="🎞️", name="Video montajchi")
        with patch.object(service.memory, "relevant_knowledge", return_value=ROWS):
            out = service.knowledge_answer("tashqi reklama hook to'plami kerak", "video_montajchi", a)
        self.assertIn("o'z bilimlaridan", out)
        self.assertIn("Kechasi mijozlaringiz", out)      # mavzusi mos - butun bo'lim
        self.assertIn("uch soniyada", out)               # boshqa bilimdan mos to'liq gap
        self.assertNotIn("Qisqa.", out.split("Manba:")[0].strip().splitlines()[-1])

    def test_team_reply_falls_back_to_knowledge_when_all_ai_fail(self):
        with patch.object(service, "route", return_value=None), \
                patch("ali.providers.chat", side_effect=RuntimeError("limit")), \
                patch.object(service, "knowledge_answer", return_value="⚙️ bilimdan javob") as ka:
            out = asyncio.run(service.team_reply("tashqi reklama hook", None, []))
        self.assertEqual(out, "⚙️ bilimdan javob")
        ka.assert_called_once()

    def test_rule_plan_reads_brief(self):
        from ali.skills import video_motion as m
        prof = {"duration": 8.0, "audio": True, "motion": [1, 2, 9, 9, 9, 2, 1, 1] * 2, "brightness": 120}
        with patch.object(m, "clip_profile", return_value=prof):
            cine = m.rule_plan(["a.mp4", "b.mp4"], "4K CINEMATIC premium, 24 FPS")
            plain = m.rule_plan(["a.mp4", "b.mp4", "c.mp4"], "Hook: Reklamangiz pul yeyaptimi?")
        self.assertEqual((cine["render"]["uhd"], cine["render"]["fps"], cine["render"]["fade"]), (True, 24, True))
        self.assertEqual(cine["hook"], "")
        self.assertEqual(plain["hook"], "Reklamangiz pul yeyaptimi?")
        self.assertTrue(plain["render"]["progress_bar"])


if __name__ == "__main__":
    unittest.main()


class BrowserTests(unittest.TestCase):
    def test_requests_and_risky_click_needs_confirmation(self):
        from ali import browser
        self.assertTrue(browser.is_request("Chrome'da Ads Manager'ni och va natijalarni ko'r"))
        self.assertTrue(browser.is_request("brauzerda pixabay.com ga kir"))
        self.assertFalse(browser.is_request("kontent reja tuz"))
        with patch.object(browser, "_call", return_value={"ok": 1}) as call:
            with self.assertRaises(RuntimeError):
                browser.click(3, "Buyurtma berish", confirm=lambda n, a: False)
            call.assert_not_called()                      # tasdiqsiz xavfli tugma bosilmaydi
            browser.click(3, "Buyurtma berish", confirm=lambda n, a: True)
            browser.click(4, "Keyingi sahifa")             # oddiy tugma - tasdiqsiz
        self.assertEqual(call.call_count, 2)
