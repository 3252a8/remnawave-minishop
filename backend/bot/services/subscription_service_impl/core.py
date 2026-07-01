from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from aiogram import Bot

from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from config.settings import Settings

if TYPE_CHECKING:
    from bot.payment_providers.shared import RecurringProviderService
else:
    RecurringProviderService = object

from .devices import HwidDeviceMixin
from .lifecycle import SubscriptionLifecycleMixin
from .panel_identity import PanelIdentityMixin
from .payments import PaymentContextMixin
from .renewal import RenewalMixin
from .tariffs import TariffMixin
from .topups import TopupMixin
from .traffic import TrafficMixin
from .trial import TrialSubscriptionMixin


class SubscriptionService(
    TrialSubscriptionMixin,
    TopupMixin,
    TrafficMixin,
    HwidDeviceMixin,
    SubscriptionLifecycleMixin,
    RenewalMixin,
    PaymentContextMixin,
    PanelIdentityMixin,
    TariffMixin,
):
    def __init__(
        self,
        settings: Settings,
        panel_service: PanelApiService,
        bot: Optional[Bot] = None,
        i18n: Optional[JsonI18n] = None,
    ):
        self.settings = settings
        self.panel_service = panel_service
        self.bot = bot
        self.i18n = i18n
        self._premium_access_cache: Dict[Tuple[str, ...], Dict[str, Any]] = {}
        self.yookassa_service: RecurringProviderService | None = None
        self.recurring_provider_services: Dict[str, RecurringProviderService] = {}
