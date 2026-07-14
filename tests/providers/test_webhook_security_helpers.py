from types import SimpleNamespace

from bot.payment_providers.shared.webhook_security import (
    check_webhook_source_ip,
    constant_time_compare,
)


def _request(*, remote="127.0.0.1", headers=None):
    return SimpleNamespace(remote=remote, headers=headers or {})


def test_webhook_source_ip_allows_empty_allowlist_when_optional():
    result = check_webhook_source_ip(
        _request(remote="198.51.100.10"),
        trusted_ips=[],
        trusted_proxies=[],
        allow_empty=True,
    )

    assert result.client_ip == "198.51.100.10"
    assert result.allowed is True


def test_webhook_source_ip_denies_empty_allowlist_when_required():
    result = check_webhook_source_ip(
        _request(remote="198.51.100.10"),
        trusted_ips=[],
        trusted_proxies=[],
        allow_empty=False,
    )

    assert result.client_ip == "198.51.100.10"
    assert result.allowed is False


def test_webhook_source_ip_honors_trusted_proxy_forwarded_for():
    result = check_webhook_source_ip(
        _request(
            remote="10.0.0.10",
            headers={"X-Forwarded-For": "203.0.113.44, 10.0.0.10"},
        ),
        trusted_ips=["203.0.113.0/24"],
        trusted_proxies=["10.0.0.0/24"],
        allow_empty=False,
    )

    assert result.client_ip == "203.0.113.44"
    assert result.allowed is True


def test_webhook_source_ip_honors_verified_cloudflare_forwarding():
    result = check_webhook_source_ip(
        _request(
            remote="10.0.0.10",
            headers={
                "X-Forwarded-For": "172.64.1.10",
                "CF-Connecting-IP": "203.0.113.44",
            },
        ),
        trusted_ips=["203.0.113.0/24"],
        trusted_proxies=["10.0.0.0/24"],
        allow_empty=False,
    )

    assert result.client_ip == "203.0.113.44"
    assert result.allowed is True


def test_constant_time_compare_keeps_case_policy_explicit():
    assert constant_time_compare("ABC", "ABC") is True
    assert constant_time_compare("ABC", "abc") is False
    assert constant_time_compare("ABC", "abc", case_sensitive=False) is True
