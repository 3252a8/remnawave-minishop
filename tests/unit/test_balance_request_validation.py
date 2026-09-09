from unittest import TestCase

from pydantic import ValidationError

from bot.app.web.admin_api_impl.schemas import (
    AdminUserBalanceAdjustmentBody,
    AdminUserBalanceConversionBody,
)
from bot.app.web.webapp.payloads import WebAppBalanceTopupPayload


class BalanceRequestValidationTests(TestCase):
    def test_admin_adjustment_defaults_to_main_balance_and_validates_target(self) -> None:
        body = AdminUserBalanceAdjustmentBody(mode="add", amount=10)
        self.assertEqual(body.target, "user")

        with self.assertRaises(ValidationError):
            AdminUserBalanceAdjustmentBody(target="unknown", mode="add", amount=10)

    def test_balance_amounts_reject_non_finite_values(self) -> None:
        cases = (
            (WebAppBalanceTopupPayload, {"method": "qa", "amount": float("inf")}),
            (AdminUserBalanceAdjustmentBody, {"mode": "add", "amount": float("inf")}),
            (
                AdminUserBalanceConversionBody,
                {"direction": "partner_to_user", "amount": float("inf")},
            ),
        )

        for model, payload in cases:
            with self.subTest(model=model.__name__), self.assertRaises(ValidationError):
                model(**payload)
