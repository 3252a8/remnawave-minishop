import asyncio

from aiogram.fsm.storage.redis import RedisStorage

from bot.infra.redis import close_redis, get_redis
from tests.support.settings_stub import settings_stub


def test_redis_clients_keep_compatibility_with_redis_py_8() -> None:
    direct_client = asyncio.run(get_redis(settings_stub(REDIS_URL="redis://localhost:6379/0")))
    aiogram_storage = RedisStorage.from_url(
        "redis://localhost:6379/0",
        connection_kwargs={"protocol": 2},
    )

    try:
        assert direct_client is not None
        assert direct_client.connection_pool.connection_kwargs["protocol"] == 2
        assert direct_client.connection_pool.connection_kwargs["socket_timeout"] is None
        assert aiogram_storage.redis.connection_pool.connection_kwargs["protocol"] == 2
    finally:
        asyncio.run(close_redis())
        asyncio.run(aiogram_storage.close())
