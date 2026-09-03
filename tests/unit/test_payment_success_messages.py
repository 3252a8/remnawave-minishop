from datetime import UTC, datetime

from bot.payment_providers.shared.success import SuccessMessage, build_success_message


def _translation_key(key: str, **_params: object) -> str:
    return key


def test_partner_client_payment_bonus_uses_dedicated_success_copy() -> None:
    end_date = datetime(2026, 1, 10, tzinfo=UTC)

    message = build_success_message(
        SuccessMessage(
            translator=_translation_key,
            sale_mode="subscription",
            months=1,
            base_end_date=datetime(2026, 1, 7, tzinfo=UTC),
            final_end_date=end_date,
            applied_referee_bonus_days=3,
            referee_bonus_source="partner",
        )
    )

    assert message == "payment_successful_with_partner_client_bonus_full"


def test_ordinary_referral_payment_bonus_keeps_inviter_copy() -> None:
    end_date = datetime(2026, 1, 10, tzinfo=UTC)

    message = build_success_message(
        SuccessMessage(
            translator=_translation_key,
            sale_mode="subscription",
            months=1,
            base_end_date=datetime(2026, 1, 7, tzinfo=UTC),
            final_end_date=end_date,
            applied_referee_bonus_days=3,
            inviter_name="Alex",
        )
    )

    assert message == "payment_successful_with_referral_bonus_full"


def test_paid_trial_uses_trial_success_copy() -> None:
    message = build_success_message(
        SuccessMessage(
            translator=_translation_key,
            sale_mode="trial",
            months=5,
            base_end_date=None,
            final_end_date=datetime(2026, 1, 10, tzinfo=UTC),
        )
    )

    assert message == "payment_successful_trial_full"
