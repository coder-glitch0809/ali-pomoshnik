import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_runtime  # noqa: F401 - testlar vaqtinchalik muhitda ishlaydi
from ali import tg_account, tg_watch
from ali.skills.tg_channels import tg_reminder_permission


class TelegramReminderTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        for module in (tg_account, tg_watch):
            p = patch.object(module, "STATE", Path(self.folder.name) / (module.__name__ + ".json"))
            p.start()
            self.addCleanup(p.stop)

    def test_permission_saved_and_revoked_without_connection(self):
        self.assertEqual(tg_account.reminder_sources(), {})
        with patch.object(tg_account, "channels", return_value=[{"id": -10, "title": "Maktab"}]) as channels:
            tg_reminder_permission(-10, True)
            self.assertEqual(tg_account.reminder_sources(), {"-10": "Maktab"})
            channels.reset_mock()
            tg_reminder_permission(-10, False)
            channels.assert_not_called()
        self.assertEqual(tg_account.reminder_sources(), {})

    def test_empty_permission_skips_collection_and_analysis(self):
        with patch.object(tg_account, "_run") as run, patch("ali.service._ask_json") as ask:
            self.assertEqual(tg_account.review_chats()["reminders"], [])
            run.assert_not_called()
            ask.assert_not_called()

    def test_collects_only_allowed_groups_and_channels(self):
        now = datetime.now(timezone.utc)
        dialogs = [SimpleNamespace(id=cid, name=str(cid), date=now,
                                   is_group=kind == "group", is_channel=kind == "channel",
                                   is_user=kind == "user", entity=SimpleNamespace(bot=False))
                   for cid, kind in [(-10, "group"), (-20, "channel"), (-30, "group"), (40, "user")]]
        read = []

        async def iter_dialogs():
            for d in dialogs:
                yield d

        async def iter_messages(cid, **kwargs):
            read.append(cid)
            yield SimpleNamespace(date=now, text="Ertaga soat 10 da yig'ilish", out=False)

        client = SimpleNamespace(iter_dialogs=iter_dialogs, iter_messages=iter_messages)
        for cid in (-10, -20, 40):
            tg_account.set_reminder_source(cid, str(cid), True)
        with patch.object(tg_account, "_run", side_effect=lambda go: asyncio.run(go(client))):
            result = tg_account.recent_chats(reminders_only=True)
        self.assertEqual(read, [-10, -20, 40])  # shaxsiy chat ham - faqat egam belgilagan bo'lsa
        self.assertIn("### -20", result)
        self.assertNotIn("### -30", result)

    def test_class_review_ignores_unapproved_group(self):
        notify, remind, ask = Mock(), Mock(), Mock()
        groups = [{"id": -10, "group": "5-D sinf", "messages": [
            {"id": 1, "text": "Dars jadvali", "photo": None}]}]
        with patch("ali.team_hub.post") as post:
            result = tg_watch.review_class(notify=notify, remind=remind, ask_json=ask, groups=groups)
        self.assertEqual(result["schedules"], [])
        for callback in (notify, remind, ask, post):
            callback.assert_not_called()

    def test_approved_plan_creates_reminder_only_once(self):
        from ali.memory import memory
        plan = {"plans": [{"what": "Yig'ilishga borish", "with": "Maktab",
                           "when": datetime.now().strftime("%Y-%m-%d")}]}
        with patch.object(tg_account, "recent_chats", return_value="Maktab: yig'ilish") as chats, \
                patch("ali.local_ai.access", return_value=False), \
                patch("ali.service._ask_json", return_value=plan), \
                patch.object(memory, "add_reminder") as add:
            first = tg_account.review_chats()
            second = tg_account.review_chats()
        chats.assert_called_with(36, reminders_only=True)
        add.assert_called_once()
        self.assertIn("Maktab", first["reminders"][0])
        self.assertEqual(second["reminders"], [])


if __name__ == "__main__":
    unittest.main()
