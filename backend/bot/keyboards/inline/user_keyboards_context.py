from config.settings import Settings
from config.subscription_periods import sale_mode_duration_days

BOT_MENU_CONTEXT = "bot"
HWID_SUBSCRIPTION_ORIGIN = "s"
TARIFF_SWITCH_ORIGIN = "sw"
SUBSCRIPTION_CATALOG_ORIGIN = "cs"
TELEGRAM_SUBSCRIPTION_CHECKOUT = "t"
HWID_RENEWAL_TOKEN = "hwid_renewal"
# Telegram limits callback payloads to 64 bytes, so checkout-only tokens stay compact.
PROMO_DISABLED_TOKEN = "pd"
PROMO_ID_TOKEN_PREFIX = "p"


def telegram_bot_menu_enabled_for_user(
    settings: Settings,
    *,
    user_id: int | None = None,
    is_admin: bool = False,
) -> bool:
    """Return whether the legacy in-bot interface should be available."""
    return not bool(settings.TELEGRAM_BOT_MENU_DISABLED)


def sale_mode_tokens(sale_mode: str | None) -> tuple[str, ...]:
    if not sale_mode or "|" not in sale_mode:
        return ()
    return tuple(token.strip() for token in str(sale_mode).split("|")[1:] if token.strip())


def callback_context_from_back_callback(back_callback: str | None) -> str | None:
    if back_callback in {
        "main_action:bot_interface",
        subscription_status_callback(BOT_MENU_CONTEXT),
    }:
        return BOT_MENU_CONTEXT
    return None


def split_callback_context(data: str) -> tuple[str, str | None]:
    base, _, suffix = data.rpartition(":")
    return (base, BOT_MENU_CONTEXT) if suffix == BOT_MENU_CONTEXT else (data, None)


def subscription_status_callback(context: str | None = None) -> str:
    return (
        "main_action:bot_my_subscription"
        if context == BOT_MENU_CONTEXT
        else "main_action:my_subscription"
    )


def subscription_menu_back_callback(context: str | None) -> str:
    return (
        "main_action:bot_interface" if context == BOT_MENU_CONTEXT else "main_action:back_to_main"
    )


def hwid_origin_suffix(context: str | None, *, from_subscription: bool = False) -> str:
    origin = f":{HWID_SUBSCRIPTION_ORIGIN}" if from_subscription else ""
    return f"{origin}{callback_suffix_for_context(context)}"


def payment_receipt_back_callback(sale_mode: str) -> str | None:
    context = callback_context_from_sale_mode(sale_mode)
    if (
        sale_mode_has_token(sale_mode, HWID_SUBSCRIPTION_ORIGIN)
        or sale_mode_has_token(sale_mode, TARIFF_SWITCH_ORIGIN)
        or sale_mode_has_token(sale_mode, SUBSCRIPTION_CATALOG_ORIGIN)
    ):
        return f"{subscription_status_callback(context)}:keep"
    if not sale_mode_has_token(sale_mode, TELEGRAM_SUBSCRIPTION_CHECKOUT):
        return None
    base = sale_mode.split("|", 1)[0].split("@", 1)[0]
    if base in {"hwid_device", "hwid_devices", "hwid_devices_renewal"}:
        return f"main_action:my_devices:keep{callback_suffix_for_context(context)}"
    return f"{subscription_status_callback(context)}:keep"


def sale_mode_with_callback_context(sale_mode: str, context: str | None) -> str:
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


def sale_mode_has_token(sale_mode: str | None, token: str) -> bool:
    return str(token or "").strip() in sale_mode_tokens(sale_mode)


def promo_id_token(promo_code_id: int) -> str:
    return f"{PROMO_ID_TOKEN_PREFIX}{int(promo_code_id)}"


def sale_mode_promo_code_id(sale_mode: str | None) -> int | None:
    for token in sale_mode_tokens(sale_mode):
        if not token.startswith(PROMO_ID_TOKEN_PREFIX):
            continue
        raw_id = token.removeprefix(PROMO_ID_TOKEN_PREFIX)
        if raw_id.isdigit() and int(raw_id) > 0:
            return int(raw_id)
    return None


def callback_context_from_sale_mode(sale_mode: str | None) -> str | None:
    tokens = sale_mode_tokens(sale_mode)
    return BOT_MENU_CONTEXT if BOT_MENU_CONTEXT in tokens else None


def callback_suffix_for_context(context: str | None) -> str:
    return f":{context}" if context else ""


def callback_suffix_for_checkout(context: str | None, *, promo_enabled: bool = True) -> str:
    tokens = [context] if context else []
    if not promo_enabled:
        tokens.append(PROMO_DISABLED_TOKEN)
    return "".join(f":{token}" for token in tokens)


def subscription_options_callback(
    context: str | None, *, promo_enabled: bool = True, from_subscription: bool = False
) -> str:
    action = "main_action:bot_subscribe" if context == BOT_MENU_CONTEXT else "main_action:subscribe"
    if from_subscription:
        action += f":{SUBSCRIPTION_CATALOG_ORIGIN}"
    return action if promo_enabled else f"{action}:{PROMO_DISABLED_TOKEN}"


def tariff_purchase_back_callback(context: str | None) -> str:
    if context == BOT_MENU_CONTEXT:
        return "main_action:bot_interface"
    return subscription_options_callback(context)


def payment_methods_back_callback(
    value: str, sale_mode: str = "subscription", price: float | None = None
) -> str:
    sale_mode = sale_mode or "subscription"
    context = callback_context_from_sale_mode(sale_mode)
    promo_enabled = not sale_mode_has_token(sale_mode, PROMO_DISABLED_TOKEN)
    from_subscription = sale_mode_has_token(sale_mode, SUBSCRIPTION_CATALOG_ORIGIN)
    context_suffix = callback_suffix_for_checkout(context, promo_enabled=promo_enabled)
    if from_subscription:
        context_suffix += f":{SUBSCRIPTION_CATALOG_ORIGIN}"
    sale_mode_main = sale_mode.split("|", 1)[0]
    sale_base = sale_mode_main.split("@", 1)[0]
    tariff_key = sale_mode_main.split("@", 1)[1] if "@" in sale_mode_main else None

    if sale_base == "subscription" and tariff_key:
        days = sale_mode_duration_days(sale_mode)
        if days is not None:
            value = f"d{days}"
        return (
            f"tariff:period:{tariff_key}:{value}{context_suffix}{tariff_switch_suffix(sale_mode)}"
        )
    if sale_base == "traffic_package" and tariff_key:
        return (
            f"tariff:package:{tariff_key}:{value}{context_suffix}{tariff_switch_suffix(sale_mode)}"
        )
    if sale_base == "topup" and tariff_key:
        return f"tariff:package:{tariff_key}:{value}{callback_suffix_for_context(context)}"
    if sale_base == "premium_topup" and tariff_key:
        return f"tariff:premium_package:{tariff_key}:{value}{callback_suffix_for_context(context)}"
    if sale_base in {"hwid_device", "hwid_devices", "hwid_devices_renewal"} and tariff_key:
        action = "renewal_package" if sale_base == "hwid_devices_renewal" else "package"
        suffix = hwid_origin_suffix(
            context, from_subscription=sale_mode_has_token(sale_mode, HWID_SUBSCRIPTION_ORIGIN)
        )
        return f"hwid_devices:{action}:{tariff_key}:{value}{suffix}"
    if sale_base == "tariff_upgrade" and tariff_key:
        amount = str(price) if price is not None else value
        return f"tariff_change:pay:{tariff_key}:{amount}{callback_suffix_for_context(context)}"
    if sale_base in {"subscription", "traffic"}:
        return f"subscribe_period:{value}{context_suffix}"
    return subscription_options_callback(
        context, promo_enabled=promo_enabled, from_subscription=from_subscription
    )


def payment_options_back_callback(sale_mode: str = "subscription") -> str:
    sale_mode = sale_mode or "subscription"
    context = callback_context_from_sale_mode(sale_mode)
    promo_enabled = not sale_mode_has_token(sale_mode, PROMO_DISABLED_TOKEN)
    from_subscription = sale_mode_has_token(sale_mode, SUBSCRIPTION_CATALOG_ORIGIN)
    context_suffix = callback_suffix_for_checkout(context, promo_enabled=promo_enabled)
    if from_subscription:
        context_suffix += f":{SUBSCRIPTION_CATALOG_ORIGIN}"
    sale_mode_main = sale_mode.split("|", 1)[0]
    sale_base = sale_mode_main.split("@", 1)[0]
    tariff_key = sale_mode_main.split("@", 1)[1] if "@" in sale_mode_main else None

    if sale_base in {"subscription", "traffic_package"} and tariff_key:
        if sale_mode_has_token(sale_mode, TARIFF_SWITCH_ORIGIN):
            return f"tariff_change:select:{tariff_key}{callback_suffix_for_context(context)}"
        return f"tariff:select:{tariff_key}{context_suffix}"
    if sale_base in {"topup", "premium_topup"}:
        return f"tariff_topup:list{callback_suffix_for_context(context)}"
    if sale_base in {"hwid_device", "hwid_devices", "hwid_devices_renewal"}:
        suffix = hwid_origin_suffix(
            context, from_subscription=sale_mode_has_token(sale_mode, HWID_SUBSCRIPTION_ORIGIN)
        )
        return f"hwid_devices:list{suffix}"
    return subscription_options_callback(
        context, promo_enabled=promo_enabled, from_subscription=from_subscription
    )


def tariff_switch_suffix(sale_mode: str) -> str:
    return (
        f":{TARIFF_SWITCH_ORIGIN}" if sale_mode_has_token(sale_mode, TARIFF_SWITCH_ORIGIN) else ""
    )
