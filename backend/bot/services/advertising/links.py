"""Canonical links are built only from configured public destinations."""

from __future__ import annotations

import json
import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.advertising_models import AdLink, AdPromoBinding
from db.models import AdCampaign, PromoCode

from .capture import utc


def link_urls(
    settings: Settings,
    code: str,
    utm: dict[str, str],
    path: str = "/",
    *,
    bot_username: str = "",
    app_name: str = "",
) -> dict[str, str]:
    urls: dict[str, str] = {}
    public = str(settings.public_app_url or "")
    parsed = urlsplit(public)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        target = parsed.path.rstrip("/") + (path if path != "/" else "/")
        landing = urlsplit(target)
        query.update(dict(parse_qsl(landing.query, keep_blank_values=True)))
        query.update(utm)
        query["campaign"] = code
        urls["web"] = urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                landing.path,
                urlencode(query),
                landing.fragment or parsed.fragment,
            )
        )
    username = bot_username.lstrip("@")
    if settings.TELEGRAM_ENABLED and username:
        urls["bot"] = f"https://t.me/{username}?start={code}"
        urls["miniapp"] = f"https://t.me/{username}?startapp={code}"
        if app_name and app_name.replace("_", "").isalnum():
            urls["named_miniapp"] = f"https://t.me/{username}/{app_name}?startapp={code}"
    return urls


async def create_link(
    session: AsyncSession,
    campaign_id: int,
    *,
    label: str,
    destination: str,
    utm: dict[str, str],
    landing_path: str,
) -> AdLink:
    from .locking import lock_advertising

    await lock_advertising(session, "codes")
    while True:
        code = "ad_" + secrets.token_urlsafe(9)
        legacy = (
            await session.execute(
                select(AdCampaign.ad_campaign_id).where(AdCampaign.start_param == code)
            )
        ).first()
        existing = (await session.execute(select(AdLink.id).where(AdLink.code == code))).first()
        if not legacy and not existing:
            break
    link = AdLink(
        campaign_id=campaign_id,
        code=code,
        label=label,
        destination=destination,
        utm_json=json.dumps(utm),
        landing_path=landing_path,
    )
    session.add(link)
    await session.flush()
    await session.refresh(link)
    return link


async def public_offer(
    session: AsyncSession, campaign_id: int, link_id: int | None
) -> tuple[str | None, str, bool]:
    from datetime import UTC, datetime

    from bot.services.promo_effects import PromoEffects

    now = datetime.now(UTC)
    rows = (
        await session.execute(
            select(AdPromoBinding, PromoCode)
            .join(
                PromoCode,
                PromoCode.promo_code_id == AdPromoBinding.promo_code_id,
            )
            .where(
                AdPromoBinding.campaign_id == campaign_id,
                AdPromoBinding.purpose == "offer",
                (AdPromoBinding.link_id.is_(None)) | (AdPromoBinding.link_id == link_id),
                AdPromoBinding.starts_at <= now,
                (AdPromoBinding.ends_at.is_(None)) | (AdPromoBinding.ends_at > now),
            )
            .order_by(AdPromoBinding.link_id.desc().nullslast(), AdPromoBinding.id.desc())
            .limit(1)
        )
    ).first()
    if rows is None:
        return None, "none", False
    _, promo = rows
    active = (
        bool(promo.is_active)
        and promo.archived_at is None
        and (promo.valid_until is None or utc(promo.valid_until) > now)
    )
    active = (
        active
        and promo.user_id is None
        and int(promo.current_activations or 0) < int(promo.max_activations)
    )
    effects = PromoEffects.from_model(promo)
    return (
        str(promo.code),
        "activation" if effects.can_apply_standalone else "checkout",
        active,
    )
