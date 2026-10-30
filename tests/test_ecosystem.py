import unittest
from types import SimpleNamespace
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik ALI_STATE_DIR va test sozlamalari ali'dan oldin o'rnatilsin
from ali import ecosystem


def _brain(*keys):
    agents = {k: SimpleNamespace(key=k, name=k.title(), icon="🤖") for k in keys}
    return SimpleNamespace(agents=agents, registry={"web_search": SimpleNamespace(dangerous=False), "video_reels": SimpleNamespace(dangerous=False)},
                           reload_agents=lambda: None)


class EcosystemTests(unittest.TestCase):
    def setUp(self):
        ecosystem.STATE.unlink(missing_ok=True)

    def test_hire_detection_and_create(self):
        self.assertTrue(ecosystem.is_hire("yangi agent kerak: SMM menejer"))
        self.assertTrue(ecosystem.is_hire("targetolog uchun agent ol"))
        self.assertFalse(ecosystem.is_hire("kontent reja tuz"))
        spec = {"key": "smm", "name": "SMM menejer", "icon": "📣", "description": "Instagramni yuritadi",
                "tools": ["video_reels", "yoq_vosita"], "learn": ["Reels trendlari"], "prompt": "Sen SMM..."}
        with patch("ali.service._ask_json", return_value=spec), \
                patch("ali.skills.agent_admin.create_agent", return_value="Agent yaratildi: 📣 SMM menejer (smm).") as create:
            out = ecosystem.hire("yangi agent kerak: SMM", _brain("kontent"), ["gemini"])
        self.assertIn("SMM", out)
        self.assertEqual(create.call_args.args[4], ["video_reels"])  # mavjud bo'lmagan vosita olib tashlandi

    def test_punishment_ladder_and_firing_needs_confirmation(self):
        brain = _brain("yomon")
        low = {"score": 30, "issues": ["Ko'p xato"]}
        with patch("ali.evolution.health", return_value=low), patch("ali.evolution.improve") as warn, \
                patch("ali.evolution.run_cycle_for") as retrain, patch("ali.evolution.backup"), \
                patch("ali.agents.delete") as fire:
            ecosystem.review(brain)                      # 1 - ogohlantirish
            warn.assert_called_once()
            ecosystem.review(brain)                      # 2 - majburiy qayta o'qitish
            retrain.assert_called_once()
            ecosystem.review(brain, confirm=lambda n, a: False)  # 3 - taklif, egasi rad etdi
            fire.assert_not_called()
            self.assertEqual(ecosystem._state()["agents"]["yomon"]["strikes"], 2)
            ecosystem.review(brain, confirm=lambda n, a: True)   # yana past - egasi tasdiqladi
            fire.assert_called_once_with("yomon")

    def test_good_score_reduces_strikes(self):
        brain = _brain("yaxshi")
        ecosystem._save({"agents": {"yaxshi": {"strikes": 2, "history": []}}, "last_review": ""})
        with patch("ali.evolution.health", return_value={"score": 90, "issues": []}):
            ecosystem.review(brain)
        self.assertEqual(ecosystem._state()["agents"]["yaxshi"]["strikes"], 1)


if __name__ == "__main__":
    unittest.main()
