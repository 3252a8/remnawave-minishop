"""Keep public subscription credentials out of HTTP diagnostics."""

import re

_SUBSCRIPTION_URL = re.compile(
    r"(/(?:s|api/subscription-guides/public)/)[^/?#\s\"'<>]+", re.IGNORECASE
)


def redact_subscription_urls(value: str) -> str:
    return _SUBSCRIPTION_URL.sub(r"\1[redacted]", value)
