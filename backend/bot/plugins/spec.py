"""Public contract for application plugins.

Plugins are separate Python packages that extend the application without
forking it. A package advertises itself through the ``minishop.plugins``
entry point group; the entry point must resolve to a :class:`Plugin`
subclass or instance.

Every hook is optional: the base class provides no-op defaults, so a plugin
only overrides what it needs. Hooks must not assume a particular call order
beyond the guarantees documented on each method.

The plugin API is a public extension surface. Additive hooks may appear in
minor versions; compatibility-breaking changes require an explicit migration
note.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    cast,
)

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher, Router
    from aiohttp import web
    from sqlalchemy.orm import sessionmaker

    from bot.app.factories.core_services import PanelService
    from bot.middlewares.i18n import JsonI18n
    from bot.services.audience_segmentation import AudienceSegmentationService
    from bot.services.email_auth_service import EmailAuthService
    from bot.services.entitlements import EntitlementsProvider
    from bot.services.lknpd_service import LknpdService
    from bot.services.notification_service import NotificationService
    from bot.services.outbound_messaging import OutboundMessagingService
    from bot.services.panel_webhook_service import PanelWebhookService
    from bot.services.promo_code_service import PromoCodeService
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
    from bot.services.support_service import SupportService
    from config.settings import Settings
    from db.migrator import Migration

ENTRY_POINT_GROUP = "minishop.plugins"

# Scopes passed to Plugin.setup_web: the webhooks app serves health checks
# and payment/panel webhooks, the webapp app serves the Mini App and admin API.
WEB_SCOPE_WEBHOOKS = "webhooks"
WEB_SCOPE_WEBAPP = "webapp"


@dataclass(frozen=True)
class WorkerTaskSpec:
    """A long-running background task contributed to the worker process.

    ``factory`` is called once at worker startup and must return the coroutine
    to run (typically ``SomeWorker(...).run()``). ``enabled`` is an optional
    settings predicate checked before the task is started.
    """

    name: str
    factory: Callable[[PluginContext], Coroutine[Any, Any, None]]
    enabled: Callable[[Settings], bool] | None = None


#: Handler for one webhook-queue event; receives the context and the raw
#: event payload dict popped from the queue.
QueueHandler = Callable[["PluginContext", dict[str, Any]], Awaitable[None]]
T = TypeVar("T")


@dataclass
class PluginContext:
    """Shared core objects handed to every plugin hook.

    Availability depends on the entrypoint: the bot/web process fills all
    fields, while auxiliary entrypoints may leave ``bot`` or ``dispatcher``
    unset. Hooks must tolerate ``None`` for optional fields.
    """

    settings: Settings
    session_factory: sessionmaker | None = None
    bot: Bot | None = None
    i18n: JsonI18n | None = None
    dispatcher: Dispatcher | None = None
    services: dict[str, object] = field(default_factory=dict)

    def require_session_factory(self) -> sessionmaker:
        if self.session_factory is None:
            raise RuntimeError("Plugin context has no session factory")
        return self.session_factory

    def require_bot(self) -> Bot:
        if self.bot is None:
            raise RuntimeError("Plugin context has no bot")
        return self.bot

    def require_i18n(self) -> JsonI18n:
        if self.i18n is None:
            raise RuntimeError("Plugin context has no i18n instance")
        return self.i18n

    def get_service(self, key: str, expected_type: type[T]) -> T | None:
        service = self.services.get(key)
        if service is None:
            return None
        if not isinstance(service, expected_type):
            raise TypeError(
                f"Plugin service {key!r} must be {expected_type.__name__}, "
                f"got {type(service).__name__}"
            )
        return service

    def require_service(self, key: str, expected_type: type[T]) -> T:
        service = self.get_service(key, expected_type)
        if service is None:
            raise KeyError(f"Required plugin service {key!r} is not registered")
        return service

    @property
    def panel_service(self) -> PanelService | None:
        return cast("PanelService | None", self.services.get("panel_service"))

    def require_panel_service(self) -> PanelService:
        return cast("PanelService", self._required_service("panel_service"))

    @property
    def subscription_service(self) -> SubscriptionService | None:
        return cast("SubscriptionService | None", self.services.get("subscription_service"))

    def require_subscription_service(self) -> SubscriptionService:
        return cast("SubscriptionService", self._required_service("subscription_service"))

    @property
    def referral_service(self) -> ReferralService | None:
        return cast("ReferralService | None", self.services.get("referral_service"))

    def require_referral_service(self) -> ReferralService:
        return cast("ReferralService", self._required_service("referral_service"))

    @property
    def promo_code_service(self) -> PromoCodeService | None:
        return cast("PromoCodeService | None", self.services.get("promo_code_service"))

    @property
    def notification_service(self) -> NotificationService | None:
        return cast("NotificationService | None", self.services.get("notification_service"))

    @property
    def email_auth_service(self) -> EmailAuthService | None:
        return cast("EmailAuthService | None", self.services.get("email_auth_service"))

    @property
    def support_service(self) -> SupportService | None:
        return cast("SupportService | None", self.services.get("support_service"))

    @property
    def panel_webhook_service(self) -> PanelWebhookService | None:
        return cast("PanelWebhookService | None", self.services.get("panel_webhook_service"))

    def require_panel_webhook_service(self) -> PanelWebhookService:
        return cast("PanelWebhookService", self._required_service("panel_webhook_service"))

    @property
    def lknpd_service(self) -> LknpdService | None:
        return cast("LknpdService | None", self.services.get("lknpd_service"))

    @property
    def audience_segmentation_service(self) -> AudienceSegmentationService | None:
        return cast(
            "AudienceSegmentationService | None",
            self.services.get("audience_segmentation_service"),
        )

    @property
    def outbound_messaging_service(self) -> OutboundMessagingService | None:
        return cast(
            "OutboundMessagingService | None",
            self.services.get("outbound_messaging_service"),
        )

    def _required_service(self, key: str) -> object:
        service = self.services.get(key)
        if service is None:
            raise KeyError(f"Required plugin service {key!r} is not registered")
        return service


class Plugin:
    """Base class for application plugins; override any subset of hooks."""

    #: Unique plugin identifier (used in logs and diagnostics).
    name: str = "unnamed"
    #: Plugin version string (informational).
    version: str = "0.0.0"

    def setup(self, ctx: PluginContext) -> None:
        """General initialization; called first, once per process.

        This is the right place to contribute services to ``ctx.services``
        and to subscribe to domain events (:mod:`bot.infra.events`). Plugins
        that add payment-backed units can also register purchase resolvers in
        :mod:`bot.infra.payment_events` from this hook.
        """

    def setup_bot(
        self,
        ctx: PluginContext,
        *,
        user_root: Router,
        admin_root: Router,
    ) -> None:
        """Register aiogram routers.

        ``user_root`` is the root router (private chats only); routers included
        here run after the core user handlers. ``admin_root`` is already guarded
        by the admin filter, so routers included there only see admin updates.
        """

    def setup_web(self, ctx: PluginContext, app: web.Application, *, scope: str) -> None:
        """Register aiohttp routes.

        Called once per web application after the core routes are registered.
        ``scope`` is :data:`WEB_SCOPE_WEBHOOKS` or :data:`WEB_SCOPE_WEBAPP`.
        """

    def worker_tasks(self, ctx: PluginContext) -> list[WorkerTaskSpec]:
        """Return background tasks to run in the worker process."""
        return []

    def queue_handlers(self, ctx: PluginContext) -> dict[str, QueueHandler]:
        """Return webhook-queue handlers keyed by event provider name.

        Provider names already handled by the core (or another plugin) are
        rejected; pick names unique to the plugin.
        """
        return {}

    def migrations(self) -> list[Migration]:
        """Return the plugin's database migration chain.

        Every migration id must be prefixed with ``"<plugin name>."`` (e.g.
        ``"myplugin.0001_initial"``); all chains share the core
        ``schema_migrations`` table. By convention plugin tables are named
        with an ``ext_<plugin>_`` prefix to avoid clashes with core tables.
        """
        return []

    def locales_dir(self) -> Path | None:
        """Return a directory with extra locale JSON files (same layout as
        the core ``locales/`` directory). Plugin keys never override keys
        already defined by the core locales."""
        return None

    def entitlements_provider(self) -> EntitlementsProvider | None:
        """Return a feature entitlement provider for this process.

        When several plugins return providers, the last active plugin wins.
        The default core provider exposes an empty feature set.
        """
        return None

    from bot.services.audience_segmentation import AudienceSegmentationService
    from bot.services.outbound_messaging import OutboundMessagingService
