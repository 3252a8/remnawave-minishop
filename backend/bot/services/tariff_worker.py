import asyncio
import logging

from db.dal import subscription_dal, tariff_dal, user_dal

from .tariff_worker_core import TariffWorkerCoreMixin
from .tariff_worker_legacy import TariffWorkerLegacyMixin
from .tariff_worker_premium import TariffWorkerPremiumMixin
from .tariff_worker_regular import TariffWorkerRegularMixin

PREMIUM_WARNING_LEVEL_OFFSET = 1000
# Single warning per premium billing period when usage reached or exceeded the quota.
PREMIUM_WARNING_DEPLETED_LEVEL = PREMIUM_WARNING_LEVEL_OFFSET + 100

# Process active subscriptions in chunks and prefetch panel data concurrently
# to avoid an N+1 serial chain to the Remnawave panel each tick.
TARIFF_WORKER_BATCH_SIZE = 50
TARIFF_WORKER_PANEL_CONCURRENCY = 10
TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD = 50
TARIFF_WORKER_SQUAD_CONFIRMATION_CACHE_TTL_SECONDS = 900
TARIFF_WORKER_DB_RETRY_ATTEMPTS = 3
TARIFF_WORKER_DB_RETRY_BASE_SLEEP_SECONDS = 0.5
POSTGRES_RETRYABLE_SQLSTATES = {"40001", "40P01"}
POSTGRES_RETRYABLE_ERROR_NAMES = {"DeadlockDetectedError", "SerializationError"}


class TariffTrafficWorker(
    TariffWorkerRegularMixin,
    TariffWorkerPremiumMixin,
    TariffWorkerLegacyMixin,
    TariffWorkerCoreMixin,
):
    pass


__all__ = [
    "POSTGRES_RETRYABLE_ERROR_NAMES",
    "POSTGRES_RETRYABLE_SQLSTATES",
    "PREMIUM_WARNING_DEPLETED_LEVEL",
    "PREMIUM_WARNING_LEVEL_OFFSET",
    "TARIFF_WORKER_BATCH_SIZE",
    "TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD",
    "TARIFF_WORKER_DB_RETRY_ATTEMPTS",
    "TARIFF_WORKER_DB_RETRY_BASE_SLEEP_SECONDS",
    "TARIFF_WORKER_PANEL_CONCURRENCY",
    "TARIFF_WORKER_SQUAD_CONFIRMATION_CACHE_TTL_SECONDS",
    "TariffTrafficWorker",
    "asyncio",
    "logging",
    "subscription_dal",
    "tariff_dal",
    "user_dal",
]
