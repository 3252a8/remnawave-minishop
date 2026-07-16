import asyncio

from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis


def test_redis_clients_keep_resp2_with_redis_py_8() -> None:
    direct_client = Redis.from_url("redis://localhost:6379/0", protocol=2)
    aiogram_storage = RedisStorage.from_url(
        "redis://localhost:6379/0",
        connection_kwargs={"protocol": 2},
    )

    try:
        assert direct_client.connection_pool.connection_kwargs["protocol"] == 2
        assert aiogram_storage.redis.connection_pool.connection_kwargs["protocol"] == 2
    finally:
        asyncio.run(direct_client.aclose())
        asyncio.run(aiogram_storage.close())
