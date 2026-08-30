from types import SimpleNamespace

from bot.services.email_auth_service import is_disposable_email
from config.settings_defaults import DEFAULT_DISPOSABLE_EMAIL_DOMAINS


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        DISPOSABLE_EMAIL_DOMAINS=DEFAULT_DISPOSABLE_EMAIL_DOMAINS,
        disposable_email_domains=None,
    )


def test_default_blocklist_contains_current_high_risk_domains() -> None:
    settings = _settings()

    assert is_disposable_email("person@prorises.com", settings)
    assert is_disposable_email("person@subdomain.prorises.com", settings)
    assert is_disposable_email("person@ogzmail.com", settings)


def test_default_blocklist_does_not_include_common_mailbox_providers() -> None:
    settings = _settings()

    assert not is_disposable_email("person@gmail.com", settings)
    assert not is_disposable_email("person@yandex.ru", settings)
