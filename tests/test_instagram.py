import asyncio
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik sozlamalar ali'dan oldin o'rnatilsin
from ali.config import config
from ali import connections
from ali.skills import instagram


class InstagramAccountTests(unittest.TestCase):
    def test_multiple_profiles_require_explicit_selection(self):
        accounts = {"planetprint": "id-1", "personal": "id-2"}
        with patch.object(config, "ig_accounts", accounts):
            with self.assertRaisesRegex(RuntimeError, "@planetprint, @personal"):
                instagram._account_id("")
            self.assertEqual(instagram._account_id("@personal"), "id-2")
            with patch("ali.skills.instagram._post") as post:
                with self.assertRaisesRegex(RuntimeError, "bittasini tanlang"):
                    instagram.instagram_publish("reel", ["video.mp4"])
            post.assert_not_called()

    def test_single_profile_remains_the_default(self):
        with patch.object(config, "ig_accounts", {"planetprint": "id-1"}):
            self.assertEqual(instagram._account_id(""), "id-1")

    def test_meta_connection_saves_all_discovered_profiles(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(connections, "ENV_FILE", Path(folder) / ".env"), \
                patch.object(config, "ig_accounts", {}), \
                patch.object(config, "ig_access_token", ""), \
                patch.dict(os.environ, {}, clear=False), \
                patch.object(instagram, "discover", return_value={"planetprint": "id-1", "personal": "id-2"}):
            result = asyncio.run(connections.connect_instagram("EAA" + "x" * 20))
            self.assertEqual(config.ig_accounts, {"planetprint": "id-1", "personal": "id-2"})
            self.assertIn("2 profil", result["message"])
            self.assertIn("@personal", result["message"])


if __name__ == "__main__":
    unittest.main()
