import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.services import subscription_reissue_access as access_service
from tests.support.settings_stub import settings_stub


class SubscriptionReissueAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_reissue_commits_old_revocation_before_panel_and_binds_new_link(self) -> None:
        events: list[str] = []

        async def commit() -> None:
            events.append("commit")

        async def revoke(_session: object, _panel_uuid: str) -> None:
            events.append("revoke")

        async def panel_revoke(_panel_uuid: str) -> dict[str, str]:
            events.append("panel")
            assert events[:2] == ["revoke", "commit"]
            return {"shortUuid": "new-short", "subscriptionUrl": "https://panel.test/new-short"}

        subscription = SimpleNamespace(panel_subscription_uuid="old-short")
        panel = SimpleNamespace(revoke_user_subscription=panel_revoke)
        session = SimpleNamespace(commit=commit)
        with (
            patch.object(
                access_service.subscription_dal,
                "revoke_install_share_tokens_for_panel_user",
                side_effect=revoke,
            ),
            patch.object(
                access_service.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=subscription),
            ),
            patch.object(
                access_service.subscription_dal,
                "ensure_install_share_token",
                AsyncMock(return_value="a" * 32),
            ),
        ):
            updated, url = await access_service.reissue_subscription_access(
                session,
                panel,
                user_id=42,
                panel_user_uuid="panel-user",
                settings=settings_stub(
                    SUBSCRIPTION_GATEWAY_ENABLED=True,
                    SUBSCRIPTION_LINK_MODE="minishop",
                    SUBSCRIPTION_MINI_APP_URL="https://shop.test/",
                ),
            )
        assert updated and updated["shortUuid"] == "new-short"
        assert subscription.panel_subscription_uuid == "new-short"
        assert url == f"https://shop.test/s/{'a' * 32}"
        assert events == ["revoke", "commit", "panel", "commit"]
