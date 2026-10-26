import unittest
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik ALI_STATE_DIR va test sozlamalari ali'dan oldin o'rnatilsin
from ali import remote_pc
from ali.telegram_bot import TelegramBot


class RemotePcTests(unittest.TestCase):
    def test_parse_cell(self):
        self.assertEqual(remote_pc.parse_cell("B3"), (1, 2))
        self.assertEqual(remote_pc.parse_cell(" h 6 "), (7, 5))
        self.assertIsNone(remote_pc.parse_cell("I1"))
        self.assertIsNone(remote_pc.parse_cell("salom"))

    def test_cell_center_and_zoom_stay_on_screen(self):
        s = remote_pc.Session(screen=(1600, 1200))
        self.assertEqual(remote_pc.cell_center(s, 0, 0), (100, 100))
        s.zoom = True
        self.assertIn("kattalashtirildi", remote_pc.click_cell(s, 7, 5))
        self.assertEqual(s.region, (1000, 600, 600, 600))  # pastki o'ng burchak - ekrandan chiqmaydi
        self.assertFalse(s.zoom)
        self.assertEqual(remote_pc.cell_center(s, 0, 0), (1038, 650))

    def test_handle_text_routes_click_keys_and_typing(self):
        s = remote_pc.Session(screen=(800, 600))
        with patch.object(remote_pc, "click_cell", return_value="c") as click, \
                patch.object(remote_pc, "keys", return_value="k") as keys, \
                patch.object(remote_pc, "type_text", return_value="t") as typed:
            remote_pc.handle_text(s, "a1")
            remote_pc.handle_text(s, "+ctrl+s")
            remote_pc.handle_text(s, "Salom dunyo")
        click.assert_called_once_with(s, 0, 0)
        keys.assert_called_once_with("ctrl+s")
        typed.assert_called_once_with("Salom dunyo")

    def test_draw_grid_and_keyboard(self):
        from PIL import Image
        img = remote_pc.draw_grid(Image.new("RGB", (800, 600), "white"))
        self.assertEqual(img.size, (800, 600))
        markup = TelegramBot.pc_keyboard(None, remote_pc.Session())
        buttons = [b for row in markup.inline_keyboard for b in row]
        self.assertIn("pc:c:75", [b.callback_data for b in buttons])
        self.assertLessEqual(len(buttons), 100)  # Telegram cheklovi


if __name__ == "__main__":
    unittest.main()
