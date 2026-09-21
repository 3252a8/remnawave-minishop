"""Raw subscription delivery, independent of instruction documents and panel APIs."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DeliveryRequest:
    client_type: str | None
    headers: dict[str, str]
    client_ip: str
    is_disconnected: Callable[[], bool] | None = None


@dataclass(frozen=True)
class DeliveryResult:
    status: int
    headers: dict[str, str]
    body: bytes


class SubscriptionSource(Protocol):
    async def fetch(self, binding: object, request: DeliveryRequest) -> DeliveryResult: ...


class SubscriptionDeliveryService:
    def __init__(self, source: SubscriptionSource) -> None:
        self.source = source

    async def deliver(self, binding: object, request: DeliveryRequest) -> DeliveryResult:
        return await self.source.fetch(binding, request)
