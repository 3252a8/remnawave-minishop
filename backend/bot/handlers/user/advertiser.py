from html import escape

from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from db.dal import ad_dal, user_dal

router = Router(name="advertiser_router")


@router.message(Command("my_ads"))
async def my_ads_command(
    message: types.Message,
    session: AsyncSession,
    i18n_data: dict,
    settings: Settings,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n or not message.from_user:
        return

    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    telegram_user_id = message.from_user.id
    user = await user_dal.get_user_by_telegram_id(
        session, telegram_user_id
    ) or await user_dal.get_user_by_id(session, telegram_user_id)
    lookup_id = int(user.user_id) if user else None

    campaigns = (
        await ad_dal.list_campaigns(session, advertiser_id=lookup_id)
        if lookup_id is not None
        else []
    )

    if not campaigns:
        await message.answer(_("advertiser_no_campaigns"))
        return

    text = _("advertiser_campaigns_header")
    from db.dal.ad_statistics import campaign_statistics

    statistics = await campaign_statistics(session, [int(c.ad_campaign_id) for c in campaigns])
    for camp in campaigns:
        stats = statistics[int(camp.ad_campaign_id)]

        status_text = (
            _("advertiser_status_active") if camp.is_active else _("advertiser_status_inactive")
        )
        item = _(
            "advertiser_campaign_item",
            source=escape(camp.source or ""),
            start_param=escape(camp.start_param or ""),
            status=status_text,
            starts=stats.get("starts", 0),
            trials=stats.get("trials", 0),
            payers=stats.get("payers", 0),
            revenue=f"{float(stats.get('revenue', 0.0)):.2f}",
        )

        if len(text) + len(item) > 3900:
            await message.answer(text, parse_mode="HTML")
            text = ""
        text += item
    if text:
        await message.answer(text, parse_mode="HTML")
