from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik ALI_STATE_DIR va test sozlamalari ali'dan oldin o'rnatilsin
from ali import outbox, plugins, skills
from ali.plugins import coreldraw, photoshop


class PluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        skills.load_all()

    def test_all_plugins_load_with_tools(self):
        self.assertEqual(set(plugins.PLUGINS), {"gemini", "chatgpt", "photoshop", "coreldraw", "autocad", "max3ds",
                                                "video_studio"})
        for p in plugins.PLUGINS.values():
            self.assertTrue(p.tools, p.key)
            self.assertTrue(all(t in skills.REGISTRY for t in p.tools))

    def test_unavailable_plugin_tools_are_hidden(self):
        p = plugins.PLUGINS["chatgpt"]
        with patch.object(p, "start", return_value=(False, "kalit yo'q")):
            plugins.restart("chatgpt")
        self.assertTrue(set(p.tools) <= plugins.hidden_tools())
        with patch.object(p, "start", return_value=(True, "Ulangan")):
            plugins.restart("chatgpt")
        self.assertFalse(set(p.tools) & plugins.hidden_tools())

    def test_photoshop_design_builds_script_and_registers_files(self):
        with tempfile.TemporaryDirectory() as d:
            psd = Path(d) / "Aksiya.psd"

            def fake_run(script, timeout):
                psd.write_bytes(b"x")
                psd.with_suffix(".png").write_bytes(b"x")
                return ""
            with patch.object(photoshop, "_progid", "Photoshop.Application"),                     patch.object(outbox, "new_path", return_value=psd), patch.object(outbox, "register"),                     patch.object(photoshop, "run_ps", side_effect=fake_run) as run:
                result = photoshop.photoshop_design("Aksiya", 1080, 1080, "#112233",
                                                    [{"text": "Chegirma 50%", "x": 100, "y": 500, "size": 90}])
            self.assertIn("Aksiya.png", result)
            self.assertIn("DoJavaScript", run.call_args.args[0])

    def test_corel_design_script_uses_mm_and_flipped_y(self):
        with tempfile.TemporaryDirectory() as d, patch.object(outbox, "DIR", Path(d)), \
                patch.object(coreldraw, "_progid", "CorelDRAW.Application.27"), \
                patch.object(coreldraw, "run_ps", return_value="") as run:
            with self.assertRaises(RuntimeError):  # soxta run_ps fayl yaratmaydi
                coreldraw.corel_design("Vizitka", 90, 50, texts=[{"text": "Ali's", "x": 10, "y": 20, "size": 14}])
            script = run.call_args.args[0]
            self.assertIn("$doc.Unit = 3", script)
            self.assertIn("CreateArtisticText(10.0, 30.0, 'Ali''s')", script)
            self.assertIn("ExportBitmap", script)


if __name__ == "__main__":
    unittest.main()
