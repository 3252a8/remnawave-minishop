from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.payment_providers.shared import webhooks
from db.dal import payment_dal


class PaymentLookupTests(IsolatedAsyncioTestCase):
    async def test_rejects_internal_id_owned_by_another_provider(self) -> None:
        payment = SimpleNamespace(payment_id=7, provider="stripe")

        with (
            patch.object(
                payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                payment_dal,
                "get_payment_by_provider_payment_id",
                AsyncMock(),
            ) as get_by_provider_id,
        ):
            result = await webhooks.lookup_payment_by_order_or_provider_id(
                AsyncMock(),
                providers="lava",
                order_id_raw="7",
            )

        self.assertIsNone(result)
        get_by_provider_id.assert_not_awaited()

    async def test_scopes_external_id_lookup_to_provider(self) -> None:
        payment = SimpleNamespace(payment_id=8, provider="lava")
        session = AsyncMock()

        with (
            patch.object(payment_dal, "get_payment_by_db_id", AsyncMock()) as get_by_db_id,
            patch.object(
                payment_dal,
                "get_payment_by_provider_payment_id",
                AsyncMock(return_value=payment),
            ) as get_by_provider_id,
        ):
            result = await webhooks.lookup_payment_by_order_or_provider_id(
                session,
                providers="lava",
                provider_payment_id="invoice-42",
            )

        self.assertIs(result, payment)
        get_by_db_id.assert_not_awaited()
        get_by_provider_id.assert_awaited_once_with(session, "lava", "invoice-42")

    async def test_rejects_ambiguous_external_id_across_allowed_providers(self) -> None:
        payments = {
            "wata": SimpleNamespace(payment_id=9, provider="wata"),
            "wata_crypto": SimpleNamespace(payment_id=10, provider="wata_crypto"),
        }

        async def get_by_provider_id(_session, provider, _provider_payment_id):
            return payments[provider]

        with patch.object(
            payment_dal,
            "get_payment_by_provider_payment_id",
            get_by_provider_id,
        ):
            result = await webhooks.lookup_payment_by_order_or_provider_id(
                AsyncMock(),
                providers=("wata", "wata_crypto"),
                provider_payment_id="shared-id",
            )

        self.assertIsNone(result)
