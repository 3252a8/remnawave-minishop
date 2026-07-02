def _sale_mode_base(sale_mode: str) -> str:
    return str(sale_mode or "subscription").split("@", 1)[0].split("|", 1)[0]


def _sale_mode_tariff_key(sale_mode: str) -> str | None:
    if "@" not in str(sale_mode or ""):
        return None
    return str(sale_mode).split("@", 1)[1].split("|", 1)[0] or None


def _sale_mode_is_traffic(sale_mode: str) -> bool:
    return _sale_mode_base(sale_mode) in {"traffic", "traffic_package", "topup", "premium_topup"}


def _sale_mode_is_hwid_devices(sale_mode: str) -> bool:
    return _sale_mode_base(sale_mode) in {
        "hwid_device",
        "hwid_devices",
        "hwid_devices_renewal",
    }
