import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.services.referral_service import ReferralService


class PartnerReferralPaymentRestrictionTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_referral_links_obey_partner_restriction_at_payment(self):
        cases = (
            # program, restriction, profile, client benefit, attribution, recipients
            (True, True, "active", False, True, []),
            (True, True, "paused", True, True, []),
            (True, True, "closed", True, True, []),
            (True, True, "active", True, True, [42]),
            (True, True, "active", True, False, []),
            (True, True, None, False, True, [7, 42]),
            (True, False, "active", False, True, [7, 42]),
            (False, True, "active", False, True, [7, 42]),
        )
        for enabled, disabled, status, client_benefit, attributed, expected in cases:
            with self.subTest(
                enabled=enabled,
                disabled=disabled,
                status=status,
                client_benefit=client_benefit,
                attributed=attributed,
            ):
                settings = SimpleNamespace(
                    DEFAULT_LANGUAGE="en",
                    REFERRAL_PROGRAM_ENABLED=True,
                    REFERRAL_ONE_BONUS_PER_REFEREE=False,
                    referral_bonus_inviter={1: 7},
                    referral_bonus_referee={1: 3},
                    partner_settings=SimpleNamespace(
                        enabled=enabled,
                        referral_program_disabled=disabled,
                        client_payment_bonus_enabled=client_benefit,
                        one_bonus_per_client=False,
                    ),
                )
                service = ReferralService(
                    settings,
                    AsyncMock(),
                    None,
                    SimpleNamespace(gettext=lambda *_args, **_kwargs: "friend"),
                )
                profile = SimpleNamespace(status=status) if status else None
                referee = SimpleNamespace(user_id=42, referred_by_id=7, first_name="Client")
                inviter = SimpleNamespace(user_id=7, first_name="Inviter")
                accrual = AsyncMock()
                with (
                    patch(
                        "bot.services.referral_service.user_dal.get_user_by_id",
                        AsyncMock(
                            side_effect=lambda _session, uid, client=referee, owner=inviter: (
                                client if uid == 42 else owner
                            )
                        ),
                    ),
                    patch(
                        "bot.services.partner_program_service.partner_dal.get_profile_by_user_id",
                        AsyncMock(return_value=profile),
                    ),
                    patch(
                        "bot.services.partner_program_service.partner_dal.get_client_with_profile_for_user",
                        AsyncMock(
                            return_value=(SimpleNamespace(partner_client_id=3), profile)
                            if attributed and profile
                            else None
                        ),
                    ),
                    patch(
                        "bot.services.referral_service.payment_dal.get_payment_by_db_id",
                        AsyncMock(return_value=None),
                    ),
                    patch("bot.services.referral_service.enqueue_period_accrual", accrual),
                ):
                    await service.apply_referral_bonuses_for_payment(
                        AsyncMock(),
                        42,
                        1,
                        current_payment_db_id=91,
                        skip_if_active_before_payment=False,
                        defer=True,
                    )
                self.assertEqual(
                    [call.kwargs["user_id"] for call in accrual.await_args_list], expected
                )
                self.assertEqual(referee.referred_by_id, 7)
                for call in accrual.await_args_list:
                    self.assertEqual(call.kwargs["days"], 7 if call.kwargs["user_id"] == 7 else 3)
