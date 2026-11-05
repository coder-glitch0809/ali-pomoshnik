import tempfile
import unittest
from pathlib import Path
import unittest.mock
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik ALI_STATE_DIR va test sozlamalari ali'dan oldin o'rnatilsin
from ali import self_upgrade as su


class DasturchiTests(unittest.TestCase):
    def test_owner_orders_to_dasturchi_start_upgrade(self):
        self.assertTrue(su.is_request("Али дастурчига айт pr media гурухидан менга нарса ташламасин, шуни тогирласин"))
        self.assertTrue(su.is_request("dasturchi, /ob_havo ga 3 kunlik prognoz qo'sh"))
        self.assertTrue(su.is_request("Ali o'zingni kuchaytir: tugmalarni tuzat"))
        self.assertTrue(su.is_request("Али дастурчига айт телеграмда pr media гурухи бор мени белгиламаса хабар келмасин "
                                      "хар бир агентга алохида буйрук гурухларда бера олай"))
        self.assertFalse(su.is_request("Али нега дастурчи халихам тогирламади"))
        self.assertFalse(su.is_request("Нега дастурчи жавоб бермаябти, дастурчига буйруклар бердим"))
        self.assertFalse(su.is_request("dasturchi nima qila oladi?"))

    def test_api_coder_applies_exact_edits_and_skips_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "ali").mkdir()
            (root / "ali" / "x.py").write_text('"""Sinov moduli."""\nGREETING = "salom"\n', encoding="utf-8")
            answers = [{"files": ["ali/x.py"]},
                       {"edits": [{"file": "ali/x.py", "old": 'GREETING = "salom"', "new": 'GREETING = "assalomu alaykum"'},
                                  {"file": ".env", "old": "", "new": "TOKEN=1"},
                                  {"file": "ali/x.py", "old": "yo'q parcha", "new": "x"}],
                        "report": "Salomlashuv o'zgardi"}]
            with patch("ali.service._ask_json", side_effect=answers), patch.object(su, "_dasturchi", return_value=""):
                ok, report = su._api_code("vazifa", "salomni o'zgartir", root)
            self.assertTrue(ok)
            self.assertIn("assalomu alaykum", (root / "ali" / "x.py").read_text(encoding="utf-8"))
            self.assertFalse((root / ".env").exists())
            self.assertIn("ali/x.py", report)


class TeamAddressTests(unittest.TestCase):
    def test_group_message_goes_straight_to_named_agent(self):
        from types import SimpleNamespace
        from ali import team_hub
        agents = {"kontent": SimpleNamespace(name="Kontent-meyker"), "dasturchi": SimpleNamespace(name="Dasturchi"),
                  "video_montajchi": SimpleNamespace(name="Video montajchi")}
        with patch.object(team_hub, "name_of", side_effect=lambda k: team_hub.NAMES.get(k, k)):
            self.assertEqual(team_hub.addressed("Контент мейкер, эртага учун пост ёз", agents), "kontent")
            self.assertEqual(team_hub.addressed("Sevara, reels g'oya ber", agents), "kontent")
            self.assertEqual(team_hub.addressed("Ali dasturchiga ayt: tugmani tuzat", agents), "dasturchi")
            self.assertEqual(team_hub.addressed("Али монтажчи видео кил", agents), "video_montajchi")
            self.assertIsNone(team_hub.addressed("bugun ob-havo qanday", agents))

    def test_instagram_daily_report_not_repeated_after_restart(self):
        from datetime import datetime
        from ali import instagram_audit as ig
        sent = []
        with tempfile.TemporaryDirectory() as d, patch.object(ig, "SENT", Path(d) / "ig_sent.json"), \
                patch.object(ig, "snapshot", return_value=["obunachi +3"]), \
                patch.object(ig, "datetime", wraps=datetime) as dt:
            dt.now.return_value = datetime(2026, 11, 5, 20, 5)  # payshanba
            ig.tick(sent.append)
            ig.tick(sent.append)  # qayta ishga tushgandek - fayldan o'qiydi
            dt.now.return_value = datetime(2026, 11, 5, 19, 0)
        self.assertEqual(len(sent), 1)


class StudioDeliveryTests(unittest.TestCase):
    def test_montage_request_detected(self):
        from ali import studio_flow as sf
        self.assertTrue(sf.is_edit_request("Каналга видео ташладим кор ва видео монтаж килиб бер"))
        self.assertTrue(sf.is_edit_request("kanaldagi videoni montaj qil"))
        self.assertFalse(sf.is_edit_request("kanal nomini o'zgartir"))

    def test_result_queued_when_offline_and_sent_later(self):
        import httpx
        from ali import studio_flow as sf
        with tempfile.TemporaryDirectory() as d:
            video = Path(d) / "r.mp4"
            video.write_bytes(b"0")
            with patch.object(sf, "STATE", Path(d) / "st.json"), \
                    patch.object(sf.config, "telegram_token", "t"), patch.object(sf.config, "telegram_owner_id", 1):
                with patch.object(sf.httpx, "post", side_effect=httpx.ConnectError("offline")):
                    self.assertFalse(sf.send_files("tayyor", [str(video)]))
                self.assertEqual(len(sf._state()["pending_send"]), 1)
                ok = unittest.mock.MagicMock()
                with patch.object(sf.httpx, "post", return_value=ok) as post, \
                        patch("ali.tg_account.send_file", return_value=5):
                    sf.flush_pending()
                self.assertEqual(sf._state()["pending_send"], [])
                self.assertEqual(post.call_count, 2)  # matn + video


if __name__ == "__main__":
    unittest.main()
