from pathlib import Path

DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_RU = (
    "By buying or renewing a subscription, you get access to a VPN/proxy service "
    "that helps protect your connection and keep your access stable."
)
DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_EN = (
    "By buying or renewing a subscription, you get access to a VPN/proxy service "
    "that helps protect your connection and keep your access stable."
)


def _load_disposable_email_domains() -> str:
    blocklist_path = Path(__file__).with_name("disposable_email_blocklist.conf")
    domains = (
        line.strip().lower() for line in blocklist_path.read_text(encoding="utf-8").splitlines()
    )
    return "\n".join(domain for domain in domains if domain and not domain.startswith("#"))


DEFAULT_DISPOSABLE_EMAIL_DOMAINS = _load_disposable_email_domains()

DEFAULT_TRUSTED_PROXIES = ",".join(
    [
        "127.0.0.1",
        "::1",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
    ]
)
