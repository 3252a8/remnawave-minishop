from typing import Any, Callable, Optional, Tuple


def _format_value(val: float) -> str:
    return str(int(val)) if float(val).is_integer() else f"{val:g}"


def _parse_offer_payload(payload: str) -> Optional[Tuple[float, float, str]]:
    try:
        parts = payload.split(":")
        value = float(parts[0])
        price = float(parts[1])
        sale_mode = parts[2] if len(parts) > 2 else "subscription"
        return value, price, sale_mode
    except (ValueError, IndexError):
        return None


def _parse_saved_list_payload(payload: str) -> Optional[Tuple[float, float, int, str]]:
    parts = payload.split(":")
    if len(parts) < 2:
        return None
    try:
        months = float(parts[0])
        price = float(parts[1])
    except (ValueError, IndexError):
        return None

    page = 0
    sale_mode = "subscription"
    if len(parts) > 2:
        try:
            page = int(parts[2])
            sale_mode = parts[3] if len(parts) > 3 else "subscription"
        except ValueError:
            sale_mode = parts[2]
    return months, price, page, sale_mode


def _metadata_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    text = str(value).strip()
    return text or None


def _format_saved_payment_method_title(
    get_text: Callable[..., str], network: Optional[str], last4: Optional[str], is_default: bool
) -> str:
    def _is_yoomoney_network(name: Optional[str]) -> bool:
        s = (name or "").lower()
        return "yoomoney" in s or "yoo money" in s or "yoo-money" in s

    def _extract_last4(text: str) -> Optional[str]:
        digits = "".join(ch for ch in text if ch.isdigit())
        return digits[-4:] if len(digits) >= 4 else None

    if _is_yoomoney_network(network):
        inferred_last4 = last4 or (_extract_last4(network or "") or "****")
        title = get_text("payment_method_wallet_title", last4=inferred_last4)
    elif last4:
        network_name = network or get_text("payment_network_card")
        title = get_text("payment_method_card_title", network=network_name, last4=last4)
    else:
        network_name = network or get_text("payment_network_generic")
        title = get_text("payment_method_generic_title", network=network_name)
    return f"⭐ {title}" if is_default else title
