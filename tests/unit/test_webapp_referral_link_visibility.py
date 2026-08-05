from bot.app.web.webapp.referral_links import visible_referral_links
from config.settings import Settings
from config.settings_models import ReferralSettings


def _referral_settings(*, webapp: bool, telegram: bool) -> ReferralSettings:
    return Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        REFERRAL_WEBAPP_LINK_ENABLED=webapp,
        REFERRAL_TELEGRAM_LINK_ENABLED=telegram,
    ).referral_settings


def test_visible_referral_links_keep_both_enabled_links() -> None:
    links = visible_referral_links(
        _referral_settings(webapp=True, telegram=True),
        bot_link="https://t.me/bot?start=ref_abc",
        webapp_link="https://app.example/ref/abc",
    )

    assert links == (
        "https://t.me/bot?start=ref_abc",
        "https://app.example/ref/abc",
    )


def test_visible_referral_links_hide_each_disabled_channel() -> None:
    bot_only = visible_referral_links(
        _referral_settings(webapp=False, telegram=True),
        bot_link="https://t.me/bot?start=ref_abc",
        webapp_link="https://app.example/ref/abc",
    )
    webapp_only = visible_referral_links(
        _referral_settings(webapp=True, telegram=False),
        bot_link="https://t.me/bot?start=ref_abc",
        webapp_link="https://app.example/ref/abc",
    )

    assert bot_only == ("https://t.me/bot?start=ref_abc", None)
    assert webapp_only == (None, "https://app.example/ref/abc")
