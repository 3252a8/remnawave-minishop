import unittest
from datetime import datetime, timezone

from bot.services import message_audit


class MessageAuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_log_user_message_delivery_adds_targeted_log(self):
        calls = []
        sent_at = datetime(2026, 5, 31, tzinfo=timezone.utc)

        async def fake_create(_session, payload):
            calls.append(payload)

        original = message_audit.message_log_dal.create_message_log_no_commit
        message_audit.message_log_dal.create_message_log_no_commit = fake_create
        self.addCleanup(
            self._restore_create_message_log,
            original,
        )

        await message_audit.log_user_message_delivery(
            object(),
            target_user_id=42,
            event_type="telegram_traffic_warning_sent",
            channel="telegram",
            recipient="100500",
            content="kind=regular level=90",
            timestamp=sent_at,
        )

        self.assertEqual(
            calls,
            [
                {
                    "user_id": None,
                    "event_type": "telegram_traffic_warning_sent",
                    "content": "channel=telegram | recipient=100500 | kind=regular level=90",
                    "is_admin_event": False,
                    "target_user_id": 42,
                    "timestamp": sent_at,
                }
            ],
        )

    def _restore_create_message_log(self, original):
        message_audit.message_log_dal.create_message_log_no_commit = original
