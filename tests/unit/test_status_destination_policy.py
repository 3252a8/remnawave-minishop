import asyncio

import pytest

from bot.services.server_status.service import ProviderFetchError, ServerStatusService
from config.settings import Settings


@pytest.mark.parametrize("provider", ["uptime-kuma", "xray-checker"])
def test_status_override_cannot_probe_an_unapproved_loopback(provider: str) -> None:
    async def run() -> None:
        settings = Settings(
            _env_file=None, BOT_TOKEN="token", POSTGRES_USER="test", POSTGRES_PASSWORD="test"
        )
        service = ServerStatusService(settings)
        try:
            with pytest.raises(ProviderFetchError, match="invalid_response"):
                await service._fetch_json(provider, "http://127.0.0.1:9/api/status-page/a")
        finally:
            await service.close()

    asyncio.run(run())


def test_operator_status_origin_is_frozen_before_database_overrides() -> None:
    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="test",
        POSTGRES_PASSWORD="test",
        SERVER_STATUS_KUMA_URL="http://10.0.0.2/status/a",
    )
    settings.SERVER_STATUS_KUMA_URL = "http://10.0.0.3/status/a"
    policy = ServerStatusService(settings)._outbound_policy
    policy.check_url("http://10.0.0.2/api/status-page/a")
    with pytest.raises(ValueError):
        policy.check_url("http://10.0.0.3/api/status-page/a")
