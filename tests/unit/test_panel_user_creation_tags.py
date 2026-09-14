import asyncio
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.services.subscription_service_impl import panel_identity
from bot.services.subscription_service_impl.panel_identity import (
    PanelIdentityMixin,
    PanelUserCreateOptions,
)


@pytest.mark.parametrize("user_id", [-42, 42], ids=["email", "telegram"])
@pytest.mark.parametrize("previous_panel_id", [None, "deleted-panel-user"])
@pytest.mark.parametrize("with_catalog", [False, True])
@pytest.mark.parametrize("is_trial", [False, True])
@pytest.mark.parametrize(
    "tariff_key",
    [
        "standard",
        "trial",
        "TRIAL",
        "  standard  ",
        "plan-a",
        "plan_a",
        "legacy-plan",
        "premium-plan-for-friends",
        "ABCDEFGHIJKLMNOP",
        "abcdefghijklmnopq",
        "\u043f\u043b\u0430\u043d",
        "\U0001f680",
        "___",
        "",
        " \t\n ",
        None,
    ],
)
def test_create_and_recreate_users_use_valid_reconcilable_tariff_tags(
    monkeypatch, user_id, previous_panel_id, with_catalog, is_trial, tariff_key
):
    catalog_keys = (
        "standard",
        "trial",
        "TRIAL",
        "plan-a",
        "plan_a",
        "premium-plan-for-friends",
        "ABCDEFGHIJKLMNOP",
        "abcdefghijklmnopq",
        "\u043f\u043b\u0430\u043d",
        "\U0001f680",
        "___",
    )
    mixin = PanelIdentityMixin()
    mixin.settings = SimpleNamespace(
        tariffs_config=(
            SimpleNamespace(
                tariffs=tuple(
                    SimpleNamespace(
                        key=key, legacy_keys=("legacy-plan",) if key == "standard" else ()
                    )
                    for key in catalog_keys
                )
            )
            if with_catalog
            else None
        ),
    )
    db_user = SimpleNamespace(
        user_id=user_id,
        telegram_id=user_id if user_id > 0 else None,
        email="account@example.test" if user_id < 0 else None,
        panel_user_uuid=previous_panel_id,
        username=None,
        first_name=None,
        last_name=None,
        managed_panel_tariff_tag=None,
    )

    async def create_user(**kwargs):
        tag = kwargs["tag"]
        # Emulate the panel's acceptance rules, independently of the mapper.
        assert tag is None or (len(tag) <= 16 and re.fullmatch(r"[A-Z0-9_]+", tag))
        if is_trial:
            assert tag == "TRIAL"
        elif tariff_key and tariff_key.strip() == "standard":
            assert tag == "STANDARD"
        return {
            "response": {
                "uuid": "created-panel-user",
                "shortUuid": "subscription-link",
                "telegramId": kwargs["telegram_id"],
                "tag": tag,
            }
        }

    mixin.panel_service = SimpleNamespace(
        get_users_by_filter=AsyncMock(return_value=[]),
        get_user_by_uuid_lookup=AsyncMock(return_value={"ok": False, "not_found": True}),
        create_panel_user=AsyncMock(side_effect=create_user),
    )
    monkeypatch.setattr(
        panel_identity.user_dal, "ensure_referral_code", AsyncMock(return_value="ABC")
    )
    monkeypatch.setattr(
        panel_identity.user_dal, "get_user_by_panel_uuid", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(panel_identity.user_dal, "update_user", AsyncMock())
    monkeypatch.setattr(
        panel_identity.user_panel_squad_override_dal,
        "merge_panel_user_uuid",
        AsyncMock(return_value=0),
    )
    options = PanelUserCreateOptions(
        default_expire_days=30,
        default_traffic_limit_bytes=0,
        default_traffic_limit_strategy="NO_RESET",
        tag=tariff_key,
        is_trial=is_trial,
    )

    link = asyncio.run(
        mixin._get_or_create_panel_user_link(AsyncMock(), user_id, db_user, create_options=options)
    )

    assert link.panel_user_created_now
    assert link.panel_user_uuid == "created-panel-user"
    assert link.panel_subscription_uuid == "subscription-link"
    mixin.panel_service.create_panel_user.assert_awaited_once()
    assert options.tag == tariff_key
    plan = mixin._plan_panel_tariff_tag(
        db_user, link.panel_user, tariff_key, source="test", is_trial=is_trial
    )
    assert not plan.needs_patch
    # A confirmed CREATE owns its tag even when the tariff is no longer in the catalog.
    assert plan.allowed
    mixin._remember_confirmed_panel_tariff_tag(db_user, plan, link.panel_user)
    assert db_user.managed_panel_tariff_tag == (plan.desired_tag if plan.allowed else None)
