from ._runtime import (
    Any,
    Bot,
    Dict,
    JsonI18n,
    Optional,
    PanelApiService,
    RecurringProviderService,
    Settings,
    Tuple,
)
from .devices import HwidDeviceMixin
from .lifecycle import SubscriptionLifecycleMixin
from .panel_identity import PanelIdentityMixin
from .payments import PaymentContextMixin
from .renewal import RenewalMixin
from .tariffs import TariffMixin
from .traffic import TrafficMixin
from .trial import TrialSubscriptionMixin


class SubscriptionService(
    TrialSubscriptionMixin,
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
