from types import SimpleNamespace

from bot.app.web.webapp.external_identity_state import (
    external_identity_can_unlink,
    external_identity_email_survives,
    external_identity_replacement_email,
)


def _identity(provider: str, email: str):
    return SimpleNamespace(provider=provider, email=email, email_verified=True)


def _address(email: str, source: str, *, primary: bool = False):
    return SimpleNamespace(
        email=email,
        source=source,
        verified_at=object(),
        is_primary=primary,
    )


def _user(email: str):
    return SimpleNamespace(email=email, email_verified_at=object())


def test_provider_owned_email_requires_a_distinct_replacement_even_with_telegram():
    google = _identity("google", "user@example.test")
    addresses = [_address("user@example.test", "google", primary=True)]

    assert external_identity_replacement_email(google, addresses) is None
    assert not external_identity_can_unlink(
        google,
        addresses,
        [google],
        user=_user("user@example.test"),
        has_other_external_identity=False,
        has_passkey_login=False,
        has_telegram_login=True,
        email_login_enabled=False,
    )


def test_verified_alternative_email_allows_safe_provider_unlink():
    google = _identity("google", "google@example.test")
    replacement = _address("other@example.test", "email")
    addresses = [
        _address("google@example.test", "google", primary=True),
        replacement,
    ]

    assert external_identity_replacement_email(google, addresses) is replacement
    assert external_identity_can_unlink(
        google,
        addresses,
        [google],
        user=_user("google@example.test"),
        has_other_external_identity=False,
        has_passkey_login=False,
        has_telegram_login=False,
        email_login_enabled=True,
    )


def test_same_email_survives_when_it_has_an_independent_source():
    google = _identity("google", "shared@example.test")
    manual_address = _address("shared@example.test", "email", primary=True)
    yandex = _identity("yandex", "shared@example.test")

    assert external_identity_email_survives(google, [manual_address], [google])
    assert external_identity_email_survives(
        google,
        [_address("shared@example.test", "google", primary=True)],
        [google, yandex],
    )
