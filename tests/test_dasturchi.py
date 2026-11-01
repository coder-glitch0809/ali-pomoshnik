import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik ALI_STATE_DIR va test sozlamalari ali'dan oldin o'rnatilsin
from ali import self_upgrade as su


class DasturchiTests(unittest.TestCase):
    def test_owner_orders_to_dasturchi_start_upgrade(self):
        self.assertTrue(su.is_request("Али дастурчига айт pr media гурухидан менга нарса ташламасин, шуни тогирласин"))
        self.assertTrue(su.is_request("dasturchi, /ob_havo ga 3 kunlik prognoz qo'sh"))
        self.assertTrue(su.is_request("Ali o'zingni kuchaytir: tugmalarni tuzat"))
        self.assertFalse(su.is_request("Али нега дастурчи халихам тогирламади"))
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


if __name__ == "__main__":
    unittest.main()
