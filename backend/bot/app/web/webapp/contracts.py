from __future__ import annotations

from bot.app.web.route_contracts import RouteContract, register_contract

from .account_contracts import ACCOUNT_ROUTE_CONTRACTS
from .assets_contracts import ASSET_ROUTE_CONTRACTS
from .auth_contracts import AUTH_ROUTE_CONTRACTS
from .billing_contracts import BILLING_ROUTE_CONTRACTS
from .devices_contracts import DEVICES_ROUTE_CONTRACTS
from .guides_contracts import GUIDES_ROUTE_CONTRACTS
from .subscription_reissue_contracts import SUBSCRIPTION_REISSUE_ROUTE_CONTRACTS
from .support_contracts import SUPPORT_ROUTE_CONTRACTS
from .telegram_notifications_contracts import TELEGRAM_NOTIFICATIONS_ROUTE_CONTRACTS

WEBAPP_ROUTE_CONTRACTS: dict[str, RouteContract] = {
    **ASSET_ROUTE_CONTRACTS,
    **AUTH_ROUTE_CONTRACTS,
    **ACCOUNT_ROUTE_CONTRACTS,
    **BILLING_ROUTE_CONTRACTS,
    **DEVICES_ROUTE_CONTRACTS,
    **GUIDES_ROUTE_CONTRACTS,
    **SUBSCRIPTION_REISSUE_ROUTE_CONTRACTS,
    **SUPPORT_ROUTE_CONTRACTS,
    **TELEGRAM_NOTIFICATIONS_ROUTE_CONTRACTS,
}


def register_webapp_route_contracts() -> None:
    for handler_name, contract in WEBAPP_ROUTE_CONTRACTS.items():
        register_contract(handler_name, contract)
