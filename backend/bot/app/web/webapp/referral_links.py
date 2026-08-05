from config.settings_models import ReferralSettings


def visible_referral_links(
    settings: ReferralSettings,
    *,
    bot_link: str | None,
    webapp_link: str | None,
) -> tuple[str | None, str | None]:
    return (
        bot_link if settings.telegram_link_enabled else None,
        webapp_link if settings.webapp_link_enabled else None,
    )
