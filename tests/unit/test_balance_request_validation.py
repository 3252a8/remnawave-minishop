from unittest import TestCase

from pydantic import ValidationError

from bot.app.web.admin_api_impl.schemas import (
    AdminUserBalanceAdjustmentBody,
    AdminUserBalanceConversionBody,
)
from bot.app.web.webapp.payloads import WebAppBalanceTopupPayload


class BalanceRequestValidationTests(TestCase):
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
