import logging

from db.dal import payment_dal, subscription_dal, tariff_dal, user_dal

from ._typing import SubscriptionServiceMixinContract
from .lifecycle_activation import SubscriptionLifecycleActivationMixin
from .lifecycle_details import SubscriptionLifecycleDetailsMixin
from .lifecycle_extension import SubscriptionLifecycleExtensionMixin
from .lifecycle_panel import SubscriptionLifecyclePanelMixin
from .lifecycle_switch import SubscriptionLifecycleSwitchMixin


class SubscriptionLifecycleMixin(
    SubscriptionLifecycleActivationMixin,
    SubscriptionLifecycleExtensionMixin,
    SubscriptionLifecycleDetailsMixin,
    SubscriptionLifecycleSwitchMixin,
    SubscriptionLifecyclePanelMixin,
    SubscriptionServiceMixinContract,
):
    pass


__all__ = [
    "SubscriptionLifecycleMixin",
    "logging",
    "payment_dal",
    "subscription_dal",
    "tariff_dal",
    "user_dal",
]
