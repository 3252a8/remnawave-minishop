"""Pure builders for partner-program deep links."""

from bot.utils.invite_links import DEFAULT_INVITE_LINK_PREFIX, build_invitation_link


def build_partner_bot_link(
    bot_username: str | None,
    partner_code: str | None,
    prefix: str = DEFAULT_INVITE_LINK_PREFIX,
) -> str | None:
    return build_invitation_link(bot_username, partner_code, kind="p", prefix=prefix, telegram=True)


def build_partner_webapp_link(
    base_url: str | None,
    partner_code: str | None,
    prefix: str = DEFAULT_INVITE_LINK_PREFIX,
) -> str | None:
    return build_invitation_link(base_url, partner_code, kind="p", prefix=prefix, telegram=False)


__all__ = ["build_partner_bot_link", "build_partner_webapp_link"]
