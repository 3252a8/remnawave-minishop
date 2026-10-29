import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from bot.app.web.admin_settings_manifest import coerce_value, get_field_by_key
from bot.services.registration_invite_gate import (
    RegistrationInviteStatus,
    evaluate_registration_invite,
)
from bot.utils.invite_links import decode_invitation_payload
from bot.utils.partner_links import build_partner_bot_link, build_partner_webapp_link
from bot.utils.referral_links import build_bot_referral_link, build_webapp_referral_link
from config.settings import Settings
from config.settings_invites import InvitationSettings


@pytest.mark.parametrize("prefix", ["discount", "join", ""])
def test_builders_share_prefix_and_keep_programs_distinct(prefix: str) -> None:
    base = "https://app.example/path?lang=ru&ref=OLD&partner=OLD&discount=r_OLD#section"
    query = f"{prefix}=r_ABC123XYZ" if prefix else "ref=uABC123XYZ"
    partner_query = f"{prefix}=p_ABC123XYZ" if prefix else "partner=ABC123XYZ"
    referral_payload = f"{prefix}_r_ABC123XYZ" if prefix else "ref_uABC123XYZ"
    partner_payload = f"{prefix}_p_ABC123XYZ" if prefix else "p_ABC123XYZ"
    assert build_webapp_referral_link(base, "ABC123XYZ", prefix) == (
        f"https://app.example/path?lang=ru&{query}#section"
    )
    assert build_partner_webapp_link(base, "ABC123XYZ", prefix) == (
        f"https://app.example/path?lang=ru&{partner_query}#section"
    )
    assert build_bot_referral_link("@shop_bot", "ABC123XYZ", prefix) == (
        f"https://t.me/shop_bot?start={referral_payload}"
    )
    assert build_partner_bot_link("@shop_bot", "ABC123XYZ", prefix) == (
        f"https://t.me/shop_bot?start={partner_payload}"
    )


@pytest.mark.parametrize("prefix", ["ref", "partner", "promo", "gift", "start", "lang", "p"])
def test_reserved_prefixes_are_rejected(prefix: str) -> None:
    with pytest.raises(ValidationError):
        InvitationSettings(INVITE_LINK_PREFIX=prefix)
    field = get_field_by_key("INVITE_LINK_PREFIX")
    assert field is not None
    with pytest.raises(ValueError):
        coerce_value(field, prefix)


@pytest.mark.parametrize("prefix", ["HasCaps", "two_words", "bad&key", "a" * 17])
def test_unsafe_or_overlong_prefixes_are_rejected(prefix: str) -> None:
    with pytest.raises(ValidationError):
        InvitationSettings(INVITE_LINK_PREFIX=prefix)


def test_default_and_legacy_generation_settings() -> None:
    assert InvitationSettings().INVITE_LINK_PREFIX == "discount"
    assert InvitationSettings(INVITE_LINK_PREFIX="").INVITE_LINK_PREFIX == ""
    field = get_field_by_key("INVITE_LINK_PREFIX")
    assert field is not None
    assert coerce_value(field, "") == ""
    assert coerce_value(field, " join ") == "join"
    payload = "join_p_" + "A" * 32
    assert decode_invitation_payload(payload, "join") == "p_" + "A" * 32
    assert decode_invitation_payload("gift_" + "A" * 43, "join") == "gift_" + "A" * 43
    assert decode_invitation_payload("ref_uABC123XYZ", "join") == "ref_uABC123XYZ"


@pytest.mark.parametrize("source", ["webapp", "telegram_start"])
@pytest.mark.parametrize("prefix", ["discount", "join"])
def test_registration_resolves_only_the_selected_program(source: str, prefix: str) -> None:
    asyncio.run(_check_registration_program(source, prefix))


async def _check_registration_program(source: str, prefix: str) -> None:
    from bot.services.registration_invite_gate import ReferralLookupSource

    settings = cast(
        Settings,
        SimpleNamespace(
            INVITE_LINK_PREFIX=prefix,
            REGISTRATION_INVITE_ONLY_ENABLED=True,
            REFERRAL_PROGRAM_ENABLED=True,
            LEGACY_REFS=False,
            compatibility_settings=SimpleNamespace(remnashop_referral_code_compat_enabled=False),
            partner_settings=SimpleNamespace(enabled=True, referral_program_disabled=False),
        ),
    )
    session = AsyncMock()
    referral_lookup = AsyncMock(return_value=SimpleNamespace(user_id=7))
    partner_lookup = AsyncMock(
        return_value=SimpleNamespace(
            partner_id=11, user_id=8, partner_code="ABC123XYZ", status="active"
        )
    )
    with (
        patch(
            "bot.services.registration_invite_gate.user_dal.get_user_by_referral_code",
            referral_lookup,
        ),
        patch(
            "bot.services.registration_invite_gate.partner_dal.get_profile_by_code", partner_lookup
        ),
    ):
        for kind in ("r", "p"):
            referral_lookup.reset_mock()
            partner_lookup.reset_mock()
            invite = await evaluate_registration_invite(
                session,
                f"{prefix}_{kind}_ABC123XYZ",
                settings=settings,
                current_user_id=42,
                source=cast(ReferralLookupSource, source),
            )
            assert invite.status == RegistrationInviteStatus.VALID
            if kind == "r":
                assert invite.referrer_user_id == 7
                assert invite.partner_id is None
                referral_lookup.assert_awaited_once()
                partner_lookup.assert_not_awaited()
            else:
                assert invite.partner_id == 11
                assert invite.referrer_user_id is None
                partner_lookup.assert_awaited_once_with(session, "ABC123XYZ")
                referral_lookup.assert_not_awaited()
