from typing import Optional, Tuple

from config.settings import Settings

BOT_MENU_CONTEXT = "bot"
HWID_RENEWAL_TOKEN = "hwid_renewal"


def telegram_bot_menu_enabled_for_user(
    settings: Settings,
    *,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> bool:
    """Return whether the legacy in-bot interface should be available."""
    return not bool(getattr(settings, "TELEGRAM_BOT_MENU_DISABLED", False))


def sale_mode_tokens(sale_mode: Optional[str]) -> Tuple[str, ...]:
    if not sale_mode or "|" not in sale_mode:
        return ()
    return tuple(token.strip() for token in str(sale_mode).split("|")[1:] if token.strip())


def callback_context_from_back_callback(back_callback: Optional[str]) -> Optional[str]:
    if back_callback == "main_action:bot_interface":
        return BOT_MENU_CONTEXT
    return None


def sale_mode_with_callback_context(sale_mode: str, context: Optional[str]) -> str:
    sale_mode = sale_mode or "subscription"
    if not context or context in sale_mode_tokens(sale_mode):
        return sale_mode
    return f"{sale_mode}|{context}"


def sale_mode_with_token(sale_mode: str, token: str) -> str:
    sale_mode = sale_mode or "subscription"
    token = str(token or "").strip()
    if not token or token in sale_mode_tokens(sale_mode):
        return sale_mode
    return f"{sale_mode}|{token}"


def sale_mode_without_token(sale_mode: str, token: str) -> str:
    sale_mode = sale_mode or "subscription"
    token = str(token or "").strip()
    if not token or "|" not in sale_mode:
        return sale_mode
    base, *tokens = sale_mode.split("|")
    kept = [item for item in tokens if item.strip() and item.strip() != token]
    return "|".join([base, *kept])


def sale_mode_has_token(sale_mode: Optional[str], token: str) -> bool:
    return str(token or "").strip() in sale_mode_tokens(sale_mode)


def callback_context_from_sale_mode(sale_mode: Optional[str]) -> Optional[str]:
    tokens = sale_mode_tokens(sale_mode)
    return BOT_MENU_CONTEXT if BOT_MENU_CONTEXT in tokens else None


def callback_suffix_for_context(context: Optional[str]) -> str:
    return f":{context}" if context else ""


def subscription_options_callback(context: Optional[str]) -> str:
    return "main_action:bot_subscribe" if context == BOT_MENU_CONTEXT else "main_action:subscribe"


def tariff_purchase_back_callback(context: Optional[str]) -> str:
    if context == BOT_MENU_CONTEXT:
        return "main_action:bot_interface"
    return subscription_options_callback(context)


def payment_methods_back_callback(
    value: str, sale_mode: str = "subscription", price: Optional[float] = None
) -> str:
    sale_mode = sale_mode or "subscription"
    context = callback_context_from_sale_mode(sale_mode)
    context_suffix = callback_suffix_for_context(context)
    sale_mode_main = sale_mode.split("|", 1)[0]
    sale_base = sale_mode_main.split("@", 1)[0]
    tariff_key = sale_mode_main.split("@", 1)[1] if "@" in sale_mode_main else None

    if sale_base == "subscription" and tariff_key:
        return f"tariff:period:{tariff_key}:{value}{context_suffix}"
    if sale_base == "traffic_package" and tariff_key:
        return f"tariff:package:{tariff_key}:{value}{context_suffix}"
    if sale_base == "topup" and tariff_key:
        return f"tariff:package:{tariff_key}:{value}"
    if sale_base == "premium_topup" and tariff_key:
        return f"tariff:premium_package:{tariff_key}:{value}"
    if sale_base in {"hwid_device", "hwid_devices", "hwid_devices_renewal"} and tariff_key:
        action = "renewal_package" if sale_base == "hwid_devices_renewal" else "package"
        return f"hwid_devices:{action}:{tariff_key}:{value}"
    if sale_base == "tariff_upgrade" and tariff_key:
        amount = str(price) if price is not None else value
        return f"tariff_change:pay:{tariff_key}:{amount}"
    if sale_base in {"subscription", "traffic"}:
        return f"subscribe_period:{value}{context_suffix}"
    return subscription_options_callback(context)


def payment_options_back_callback(sale_mode: str = "subscription") -> str:
    sale_mode = sale_mode or "subscription"
    context = callback_context_from_sale_mode(sale_mode)
    context_suffix = callback_suffix_for_context(context)
    sale_mode_main = sale_mode.split("|", 1)[0]
    sale_base = sale_mode_main.split("@", 1)[0]
    tariff_key = sale_mode_main.split("@", 1)[1] if "@" in sale_mode_main else None

    if sale_base in {"subscription", "traffic_package"} and tariff_key:
        return f"tariff:select:{tariff_key}{context_suffix}"
    if sale_base in {"topup", "premium_topup"}:
        return "tariff_topup:list"
    if sale_base in {"hwid_device", "hwid_devices", "hwid_devices_renewal"}:
        return "hwid_devices:list"
    return subscription_options_callback(context)
