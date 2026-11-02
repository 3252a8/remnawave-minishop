"""Pure builders for referral deep links."""

from bot.utils.invite_links import DEFAULT_INVITE_LINK_PREFIX, build_invitation_link


def build_bot_referral_link(
    bot_username: str | None,
    referral_code: str | None,
    prefix: str = DEFAULT_INVITE_LINK_PREFIX,
) -> str | None:
    return build_invitation_link(
        bot_username, referral_code, kind="r", prefix=prefix, telegram=True
    )


def build_webapp_referral_link(
    base_url: str | None,
    referral_code: str | None,
    prefix: str = DEFAULT_INVITE_LINK_PREFIX,
) -> str | None:
    return build_invitation_link(base_url, referral_code, kind="r", prefix=prefix, telegram=False)
