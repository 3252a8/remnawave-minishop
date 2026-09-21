"""Append-only core migration chain, assembled from the chain modules."""

from .chain_0001_0021 import CHAIN_0001_0021
from .chain_0022_0041 import CHAIN_0022_0041
from .chain_0046_0060 import CHAIN_0046_0060
from .chain_0056_0070 import CHAIN_0056_0070
from .chain_0069_0083 import CHAIN_0069_0083
from .chain_0075_period_days import CHAIN_0075_PERIOD_DAYS
from .chain_0076_tariff_squad_sync import CHAIN_0076_TARIFF_SQUAD_SYNC
from .chain_0077_subscription_gifts import CHAIN_0077_SUBSCRIPTION_GIFTS
from .chain_0078_gift_entitlements import CHAIN_0078_GIFT_ENTITLEMENTS
from .chain_0084_gift_refunds import CHAIN_0084_GIFT_REFUNDS
from .chain_0085_user_notification_preferences import CHAIN_0085_USER_NOTIFICATION_PREFERENCES
from .chain_0086_panel_tariff_tag import CHAIN_0086_PANEL_TARIFF_TAG
from .chain_0087_wata_subscriptions import CHAIN_0087_WATA_SUBSCRIPTIONS
from .chain_0088_install_share_binding import CHAIN_0088_INSTALL_SHARE_BINDING
from .engine import Migration

MIGRATIONS: list[Migration] = [
    *CHAIN_0001_0021,
    *CHAIN_0022_0041,
    *CHAIN_0046_0060,
    *CHAIN_0056_0070,
    *CHAIN_0069_0083,
    *CHAIN_0075_PERIOD_DAYS,
    *CHAIN_0076_TARIFF_SQUAD_SYNC,
    *CHAIN_0077_SUBSCRIPTION_GIFTS,
    *CHAIN_0078_GIFT_ENTITLEMENTS,
    *CHAIN_0084_GIFT_REFUNDS,
    *CHAIN_0085_USER_NOTIFICATION_PREFERENCES,
    *CHAIN_0086_PANEL_TARIFF_TAG,
    *CHAIN_0087_WATA_SUBSCRIPTIONS,
    *CHAIN_0088_INSTALL_SHARE_BINDING,
]
