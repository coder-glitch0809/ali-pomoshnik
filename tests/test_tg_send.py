import unittest
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik ALI_STATE_DIR va test sozlamalari ali'dan oldin o'rnatilsin
from ali import tg_send


class TgSendTests(unittest.TestCase):
    def test_detects_requests(self):
        for t in ("Telegramda Akmalga yoz: ertaga 10 da uchrashamiz", "телеграмда Акмалга ёз эртага келаман",
                  "Akmalga yozib qo'y, kechikaman", "Sardorga xabar yubor: hisobot tayyor"):
            self.assertTrue(tg_send.is_request(t), t)
        for t in ("bugun ob-havo qanday", "kontent reja tuz", "Telegram kanallarim ro'yxati"):
            self.assertFalse(tg_send.is_request(t), t)

    def test_parse_without_ai(self):
        self.assertEqual(tg_send.parse("Telegramda Akmalga yoz: ertaga 10 da uchrashamiz", []),
                         ("Akmal", "ertaga 10 da uchrashamiz"))

    def test_sends_only_after_confirmation(self):
        person = [{"id": 5, "title": "Akmal", "username": "akmal", "exact": True, "kind": "shaxs"}]
        with patch("ali.tg_account.credentials", return_value=(1, "x")), \
                patch("ali.tg_account.people", return_value=person), \
                patch("ali.tg_account.send_message") as send, \
                patch("ali.hub.hub.confirm", return_value=False) as confirm, patch.object(tg_send, "log"):
            out = tg_send.handle("Telegramda Akmalga yoz: salom", [])
            send.assert_not_called()
            self.assertIn("Yuborilmadi", out)
            confirm.return_value = True
            out = tg_send.handle("Telegramda Akmalga yoz: salom", [])
        send.assert_called_once_with(5, "salom")
        self.assertEqual(confirm.call_args.args[1], {"Kimga": "Akmal (@akmal)", "Matn": "salom"})
        self.assertIn("Yuborildi", out)

    def test_ambiguous_name_asks_to_clarify(self):
        many = [{"id": 1, "title": "Akmal aka", "username": "", "exact": False, "kind": "shaxs"},
                {"id": 2, "title": "Akmal Usta", "username": "", "exact": False, "kind": "shaxs"}]
        with patch("ali.tg_account.credentials", return_value=(1, "x")), \
                patch("ali.tg_account.people", return_value=many), \
                patch("ali.tg_account.send_message") as send, patch("ali.hub.hub.confirm") as confirm:
            out = tg_send.handle("Telegramda Akmalga yoz: salom", [])
        send.assert_not_called(); confirm.assert_not_called()
        self.assertIn("bir nechta", out)


if __name__ == "__main__":
    unittest.main()
