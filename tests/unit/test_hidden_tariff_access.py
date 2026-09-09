import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.app.web.webapp import billing_tariff_access
from bot.services.subscription_service_impl import renewal as renewal_module
from bot.services.subscription_service_impl.renewal import RenewalMixin
from bot.services.subscription_service_impl.tariffs import TariffMixin
from config.tariffs_config import TariffsConfig


class _TariffsConfig:
    def require(self, key):
        if key == "visible":
            return SimpleNamespace(key=key)
        raise KeyError(key)

    def require_for_user(self, key, assigned_key):
        if key == "hidden" and assigned_key == "hidden":
            return SimpleNamespace(key=key)
        raise KeyError(key)


class _RenewalService(RenewalMixin, TariffMixin):
    def __init__(self, settings):
        self.settings = settings


class HiddenTariffAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_expired_assigned_hidden_tariff_remains_available(self):
        with (
            patch.object(
                billing_tariff_access.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                billing_tariff_access.subscription_dal,
                "get_latest_subscription_by_user_id",
                AsyncMock(return_value=SimpleNamespace(tariff_key="hidden")),
            ),
        ):
            tariff = await billing_tariff_access.require_user_available_tariff(
                AsyncMock(),
                _TariffsConfig(),
                user_id=42,
                tariff_key="hidden",
            )

        self.assertEqual(tariff.key, "hidden")

    async def test_hidden_tariff_is_rejected_after_switching_away(self):
        with (
            patch.object(
                billing_tariff_access.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=SimpleNamespace(tariff_key="visible")),
            ),
            self.assertRaises(KeyError),
        ):
            await billing_tariff_access.require_user_available_tariff(
                AsyncMock(),
                _TariffsConfig(),
                user_id=42,
                tariff_key="hidden",
            )

    async def test_hidden_period_tariff_can_auto_renew(self):
        tariffs = TariffsConfig.model_validate(
            {
                "default_tariff": "standard",
                "tariffs": [
                    {
                        "key": "standard",
                        "names": {"en": "Standard"},
                        "squad_uuids": ["standard-squad"],
                        "billing_model": "period",
                        "monthly_gb": 100,
                        "prices_rub": {"1": 100},
                        "enabled_periods": [1],
                        "enabled": True,
                    },
                    {
                        "key": "hidden",
                        "names": {"en": "Hidden"},
                        "squad_uuids": ["hidden-squad"],
                        "billing_model": "period",
                        "monthly_gb": 200,
                        "prices_rub": {"1": 250},
                        "enabled_periods": [1],
                        "enabled": False,
                    },
                ],
            }
        )
        service = _RenewalService(SimpleNamespace(tariffs_config=tariffs, subscription_options={}))
        subscription = SimpleNamespace(
            subscription_id=7,
            user_id=42,
            tariff_key="hidden",
            duration_months=1,
            duration_days=None,
            end_date=datetime(2026, 10, 1, tzinfo=UTC),
        )

        with patch.object(
            renewal_module.tariff_dal,
            "get_active_flexible_traffic_limit_records",
            AsyncMock(return_value={}),
        ):
            quote = await service.quote_subscription_renewal(AsyncMock(), subscription)

        assert quote is not None
        self.assertEqual(quote.amount, 250)
        self.assertEqual(quote.sale_mode, "subscription@hidden")
