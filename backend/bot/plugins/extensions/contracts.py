"""Public extension contracts v1. Callbacks never receive browser authority."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from bot.plugins.spec import PluginContext


class ExtensionError(ValueError):
    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProductQuote(ContractModel):
    title: str = Field(min_length=1, max_length=200)
    amount_minor: int = Field(ge=0, le=1_000_000_000_000, strict=True)
    currency: str = Field(pattern=r"^[A-Z]{3,8}$")
    terms: dict[str, JsonValue] = Field(default_factory=dict)
    version: int = Field(default=1, ge=1)
    expires_at: datetime


class OrderSnapshot(ContractModel):
    id: str
    product: str
    user_id: int
    quote: ProductQuote
    reference: str | None = None


class FulfillmentResult(ContractModel):
    reference: str = Field(min_length=1, max_length=256)
    # Public display data only. Private keys belong in the resource provider.
    data: dict[str, JsonValue] = Field(default_factory=dict)


@dataclass(frozen=True)
class UserContext:
    session: AsyncSession
    user_id: int
    language: str


@dataclass(frozen=True)
class OperationContext:
    """Use operation_id as the external idempotency key on every attempt."""

    operation_id: str
    owner: str
    user_id: int | None
    runtime: PluginContext
    lease_token: str = ""

    def assert_current(self) -> None:
        from bot.plugins.packages import generation_is_current

        if not generation_is_current():
            raise ExtensionError("extension_generation_changed", 503)


@dataclass(frozen=True)
class GuideContribution:
    """A complete validated v1 guide fragment; platform IDs are namespaced by Core."""

    config: dict[str, JsonValue]
    order: int = 100


@dataclass(frozen=True)
class ResourceResult:
    body: bytes
    content_type: str = "application/octet-stream"
    filename: str = "configuration.txt"


GuideResolver = Callable[[UserContext], Awaitable[GuideContribution | None]]
ResourceResolver = Callable[[UserContext, str], Awaitable[ResourceResult]]
QuoteResolver = Callable[[UserContext, dict[str, JsonValue]], Awaitable[ProductQuote]]
FulfillResolver = Callable[[OperationContext, OrderSnapshot], Awaitable[FulfillmentResult]]
RevokeResolver = Callable[[OperationContext, OrderSnapshot], Awaitable[None]]
StatusResolver = Callable[[UserContext, OrderSnapshot], Awaitable[dict[str, JsonValue]]]
JobResolver = Callable[[OperationContext, dict[str, JsonValue]], Awaitable[dict[str, JsonValue]]]
ViewPolicy = Callable[[UserContext, str], Awaitable[bool]]


@dataclass(frozen=True)
class GuideProvider:
    id: str
    resolve: GuideResolver


@dataclass(frozen=True)
class ResourceProvider:
    id: str
    # The resolver MUST check ownership of its opaque resource key on every call.
    resolve: ResourceResolver


@dataclass(frozen=True)
class ProductProvider:
    id: str
    quote: QuoteResolver
    fulfill: FulfillResolver
    revoke: RevokeResolver
    status: StatusResolver | None = None
    terms_versions: tuple[int, ...] = (1,)


@dataclass(frozen=True)
class JobHandler:
    id: str
    run: JobResolver
    timeout_seconds: int = 60
    max_attempts: int = 10
    interval_seconds: int | None = None


@dataclass(frozen=True)
class DurableSubscription:
    event: str
    job: str


BackupCollect = Callable[[Path], dict[str, JsonValue]]
BackupValidate = Callable[[Path, dict[str, JsonValue]], None]
BackupRestore = Callable[[Path, dict[str, JsonValue]], None]


@dataclass(frozen=True)
class BackupContributor:
    id: str
    version: int
    collect: BackupCollect
    validate: BackupValidate
    restore: BackupRestore


@dataclass(frozen=True)
class BackupStorageProvider:
    id: str
    upload: Callable[[Path, str], Awaitable[None]]
    download: Callable[[str, Path], Awaitable[None]]
    list_archives: Callable[[], Awaitable[list[str]]]
    delete: Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class ExtensionContributions:
    guides: tuple[GuideProvider, ...] = ()
    resources: tuple[ResourceProvider, ...] = ()
    products: tuple[ProductProvider, ...] = ()
    jobs: tuple[JobHandler, ...] = ()
    events: tuple[DurableSubscription, ...] = ()
    backups: tuple[BackupContributor, ...] = ()
    storage: tuple[BackupStorageProvider, ...] = ()
    view_policy: ViewPolicy | None = None
    # Supported core commands, explicitly requested by the trusted plugin.
    permissions: frozenset[str] = field(default_factory=frozenset)
