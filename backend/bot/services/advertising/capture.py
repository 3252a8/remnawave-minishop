"""Durable contacts, first-party visits and immutable checkout decisions."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.advertising_models import (
    AdAuthContext,
    AdLink,
    AdOfferActivation,
    AdPromoBinding,
    AdPurchaseAttribution,
    AdTouchpoint,
    AdUtmRule,
    AdVisit,
)
from db.models import AdAttribution, AdCampaign, Payment, User

from .validation import RESERVED, currency_scale, normalize_utm

VISIT_COOKIE = "ms_ad_visit"
POLICY = "last_tagged_checkout_v1"


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def insert_once(
    session: AsyncSession, model: Any, values: dict[str, Any], keys: list[Any]
) -> None:
    factory = sqlite_insert if session.get_bind().dialect.name == "sqlite" else pg_insert
    await session.execute(
        factory(model).values(**values).on_conflict_do_nothing(index_elements=keys)
    )


async def resolve_code(session: AsyncSession, code: str) -> tuple[AdCampaign | None, AdLink | None]:
    if not code or RESERVED.search(code):
        return None, None
    # Published legacy aliases win over a newly introduced namespace.
    campaign = (
        await session.execute(select(AdCampaign).where(AdCampaign.start_param == code))
    ).scalar_one_or_none()
    link = None
    if campaign is None:
        link = (
            await session.execute(select(AdLink).where(AdLink.code == code))
        ).scalar_one_or_none()
        if link is not None and link.is_active:
            campaign = await session.get(AdCampaign, link.campaign_id)
    if campaign is None or not campaign.is_active or campaign.archived_at is not None:
        return None, None
    return campaign, link


async def capture_contact(
    session: AsyncSession,
    *,
    code: str = "",
    observed_utm: dict[str, str] | None = None,
    visit_id: str | None = None,
    user_id: int | None = None,
    channel: str = "web",
    event_key: str | None = None,
    occurred_at: datetime | None = None,
    bot_id: str | None = None,
    is_new_user: bool | None = None,
) -> str | None:
    from config.settings import get_settings

    if not get_settings().ADVERTISING_ENABLED:
        campaign = (
            await session.execute(
                select(AdCampaign).where(
                    AdCampaign.start_param == code.strip(),
                    AdCampaign.is_active.is_(True),
                    AdCampaign.archived_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if campaign and user_id:
            await insert_once(
                session,
                AdAttribution,
                {"user_id": user_id, "ad_campaign_id": campaign.ad_campaign_id},
                [AdAttribution.user_id],
            )
        return None
    observed = normalize_utm(observed_utm or {})
    campaign, link = await resolve_code(session, code.strip())
    mapped = False
    published_code = None
    if campaign is None and observed and code.strip():
        published_code = (
            await session.execute(
                select(AdCampaign.ad_campaign_id)
                .where(AdCampaign.start_param == code.strip())
                .union_all(select(AdLink.id).where(AdLink.code == code.strip()))
                .limit(1)
            )
        ).scalar()
    if campaign is None and observed and published_code is None:
        fingerprint = hashlib.sha256(json.dumps(observed, sort_keys=True).encode()).hexdigest()
        rule = await session.get(AdUtmRule, fingerprint)
        if rule:
            candidate = await session.get(AdCampaign, rule.campaign_id)
            if candidate and candidate.is_active and candidate.archived_at is None:
                campaign, mapped = candidate, True
    if campaign is None and not observed and channel != "bot":
        return None
    now = datetime.now(UTC)
    visit = await session.get(AdVisit, visit_id) if visit_id and len(visit_id) == 32 else None
    if (
        visit is None
        or utc(visit.expires_at) <= now
        or (visit.user_id is not None and visit.user_id != user_id)
    ):
        visit = AdVisit(id=uuid.uuid4().hex, user_id=user_id, expires_at=now + timedelta(days=30))
        session.add(visit)
        await session.flush()
    key = (
        event_key
        or f"web:{visit.id}:{link.code if link else code}:{json.dumps(observed, sort_keys=True)}"
    )
    if event_key and channel == "web":
        key = f"{visit.id}:{event_key}"
    # Keys must fit storage and should never contain raw personal information.
    key = f"{channel}:{hashlib.sha256(key.encode()).hexdigest()}"
    await insert_once(
        session,
        AdTouchpoint,
        {
            "event_key": key,
            "visit_id": visit.id,
            "user_id": user_id,
            "original_user_id": user_id,
            "campaign_id": int(campaign.ad_campaign_id) if campaign else None,
            "link_id": link.id if link else None,
            "channel": channel,
            "evidence": "operator_utm_mapping"
            if mapped
            else "tagged_link"
            if campaign
            else "unassigned_utm"
            if observed
            else "unassigned_bot_start",
            "observed_utm_json": json.dumps(observed, sort_keys=True),
            "utm_fingerprint": hashlib.sha256(
                json.dumps(observed, sort_keys=True).encode()
            ).hexdigest(),
            "occurred_at": utc(occurred_at or now),
            "received_at": now,
            "bot_id": bot_id,
            "is_new_user": is_new_user,
        },
        [AdTouchpoint.event_key],
    )
    if user_id is not None:
        await claim_visit(session, visit.id, user_id)
    return visit.id


async def claim_visit(session: AsyncSession, visit_id: str, user_id: int) -> None:
    visit = (
        await session.execute(select(AdVisit).where(AdVisit.id == visit_id).with_for_update())
    ).scalar_one_or_none()
    if visit is None or utc(visit.expires_at) <= datetime.now(UTC):
        return
    if visit.user_id is not None and visit.user_id != user_id:
        return
    # FOR NO KEY UPDATE serializes claims without upgrading the KEY SHARE locks
    # held by contact/visit foreign keys, which can deadlock concurrent captures.
    user = (
        await session.execute(
            select(User).where(User.user_id == user_id).with_for_update(key_share=True)
        )
    ).scalar_one_or_none()
    if user is None or user.is_banned:
        return
    visit.user_id = user_id
    touches = list(
        (
            await session.execute(
                select(AdTouchpoint)
                .where(AdTouchpoint.visit_id == visit_id)
                .order_by(AdTouchpoint.occurred_at, AdTouchpoint.id)
            )
        ).scalars()
    )
    for touch in touches:
        if touch.user_id is not None and touch.user_id != user_id:
            continue
        touch.user_id = user_id
        touch.original_user_id = touch.original_user_id or user_id
        if touch.is_new_user is None:
            touch.is_new_user = utc(user.registration_date) >= utc(touch.occurred_at)
    await session.flush()
    # Compatibility projection. New reports read evidence rather than treating it as a registration.
    attributed = next((touch for touch in touches if touch.campaign_id is not None), None)
    if attributed is not None:
        await insert_once(
            session,
            AdAttribution,
            {
                "user_id": user_id,
                "ad_campaign_id": attributed.campaign_id,
                "first_start_at": attributed.occurred_at,
            },
            [AdAttribution.user_id],
        )


async def project_mapped_contacts(
    session: AsyncSession, campaign_id: int, fingerprint: str
) -> None:
    factory = sqlite_insert if session.get_bind().dialect.name == "sqlite" else pg_insert
    contacts = (
        select(AdTouchpoint.user_id, AdTouchpoint.campaign_id, func.min(AdTouchpoint.occurred_at))
        .where(
            AdTouchpoint.campaign_id == campaign_id,
            AdTouchpoint.utm_fingerprint == fingerprint,
            AdTouchpoint.user_id.is_not(None),
        )
        .group_by(AdTouchpoint.user_id, AdTouchpoint.campaign_id)
    )
    await session.execute(
        factory(AdAttribution)
        .from_select(["user_id", "ad_campaign_id", "first_start_at"], contacts)
        .on_conflict_do_nothing(index_elements=[AdAttribution.user_id])
    )


async def snapshot_purchase(
    session: AsyncSession, payment: Payment, *, checkout_at: datetime | None = None
) -> None:
    if await session.get(AdPurchaseAttribution, int(payment.payment_id)):
        return
    now = utc(checkout_at or payment.created_at or datetime.now(UTC))
    touches = list(
        (
            await session.execute(
                select(AdTouchpoint)
                .where(
                    AdTouchpoint.user_id == payment.user_id,
                    AdTouchpoint.campaign_id.is_not(None),
                    AdTouchpoint.occurred_at <= now,
                    AdTouchpoint.occurred_at >= now - timedelta(days=365),
                )
                .order_by(AdTouchpoint.occurred_at.desc(), AdTouchpoint.id.desc())
            )
        ).scalars()
    )
    chosen = None
    window = 30
    for touch in touches:
        campaign = await session.get(AdCampaign, touch.campaign_id)
        if campaign is None:
            continue
        window = int(campaign.attribution_window_days or 30)
        if utc(touch.occurred_at) >= now - timedelta(days=window):
            chosen = touch
            break
    binding = None
    if payment.promo_code_id is not None:
        bindings = list(
            (
                await session.execute(
                    select(AdPromoBinding).where(
                        AdPromoBinding.promo_code_id == payment.promo_code_id,
                        AdPromoBinding.starts_at <= now,
                        (AdPromoBinding.ends_at.is_(None)) | (AdPromoBinding.ends_at > now),
                    )
                )
            ).scalars()
        )
        eligible = [
            item
            for item in bindings
            if chosen is not None
            and item.campaign_id == chosen.campaign_id
            and (item.link_id is None or item.link_id == chosen.link_id)
        ]
        if eligible:
            binding = max(eligible, key=lambda item: item.id)
        else:
            manual = [item for item in bindings if item.purpose == "manual_code_source"]
            if chosen is None and len({item.campaign_id for item in manual}) == 1 and manual:
                binding = max(manual, key=lambda item: item.id)
    campaign_id = chosen.campaign_id if chosen else binding.campaign_id if binding else None
    legacy = await session.get(AdAttribution, int(payment.user_id)) if campaign_id is None else None
    if legacy is not None and now - timedelta(days=window) <= utc(legacy.first_start_at) <= now:
        campaign_id = int(legacy.ad_campaign_id)
    else:
        legacy = None
    currency = str(payment.currency).upper()
    amount_minor = int(
        (Decimal(str(payment.amount)) * (10 ** currency_scale(currency))).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )
    balances = int(payment.user_balance_amount_minor or 0) + int(
        payment.partner_balance_amount_minor or 0
    )
    external = str(payment.funding_source or "external") == "external"
    await insert_once(
        session,
        AdPurchaseAttribution,
        {
            "payment_id": int(payment.payment_id),
            "user_id": int(payment.user_id),
            "original_user_id": int(payment.user_id),
            "campaign_id": campaign_id,
            "link_id": chosen.link_id if chosen else None,
            "touchpoint_id": chosen.id if chosen else None,
            "binding_id": binding.id if binding else None,
            "evidence": chosen.evidence
            if chosen
            else "promo_code"
            if binding
            else "legacy_bot_start"
            if legacy
            else "unknown",
            "policy_version": POLICY,
            "window_days": window,
            "checkout_at": now,
            "amount_minor": int(
                (Decimal(str(payment.amount)) * (10 ** currency_scale(currency))).quantize(
                    Decimal(1), rounding=ROUND_HALF_UP
                )
            ),
            "currency": currency,
            "currency_scale": currency_scale(currency),
            "product_amount_minor": amount_minor + balances if external else amount_minor,
            "product_order": str(payment.sale_mode or "").split("|")[0] != "balance_topup"
            and (amount_minor > 0 or balances > 0 or payment.promo_code_id is not None),
            "cash_amount_minor": amount_minor if external else 0,
            "funding_source": str(payment.funding_source or "external"),
            "sale_mode": str(payment.sale_mode or ""),
        },
        [AdPurchaseAttribution.payment_id],
    )


async def record_payment_created(session: AsyncSession, payment: Payment) -> None:
    from config.settings import get_settings

    if not get_settings().ADVERTISING_ENABLED:
        return
    # PostgreSQL now() is the transaction start, which may precede a contact in this transaction.
    await snapshot_purchase(session, payment, checkout_at=datetime.now(UTC))
    await record_payment_state(session, payment)


async def record_payment_state(session: AsyncSession, payment: Payment) -> None:
    decision = await session.get(AdPurchaseAttribution, int(payment.payment_id))
    if decision is None:
        from config.settings import get_settings

        if not get_settings().ADVERTISING_ENABLED:
            return
        await snapshot_purchase(session, payment)
        decision = await session.get(AdPurchaseAttribution, int(payment.payment_id))
    if decision is None:
        return
    if payment.status == "succeeded" and decision.succeeded_at is None:
        # Serializing per account makes the first-purchase flag stable under concurrent webhooks.
        await session.execute(
            select(User.user_id).where(User.user_id == payment.user_id).with_for_update()
        )
        await session.refresh(decision)
        if decision.succeeded_at is not None:
            return
        decision.succeeded_at = datetime.now(UTC)
        product = str(payment.sale_mode or "").split("|")[0] != "balance_topup" and (
            float(payment.amount) > 0
            or int(payment.user_balance_amount_minor or 0) > 0
            or int(payment.partner_balance_amount_minor or 0) > 0
            or payment.promo_code_id is not None
        )
        if decision.product_order is not None:
            product = decision.product_order
        previous = (
            await session.execute(
                select(AdPurchaseAttribution.payment_id)
                .join(
                    Payment,
                    Payment.payment_id == AdPurchaseAttribution.payment_id,
                )
                .where(
                    AdPurchaseAttribution.user_id == payment.user_id,
                    AdPurchaseAttribution.payment_id != payment.payment_id,
                    AdPurchaseAttribution.first_product_purchase.is_(True),
                )
            )
        ).first()
        historic = (
            await session.execute(
                select(Payment.payment_id)
                .outerjoin(
                    AdPurchaseAttribution,
                    Payment.payment_id == AdPurchaseAttribution.payment_id,
                )
                .where(
                    Payment.user_id == payment.user_id,
                    Payment.payment_id != payment.payment_id,
                    AdPurchaseAttribution.first_product_purchase.is_(None),
                    Payment.status.in_(["succeeded", "refunded", "reversed"]),
                    (Payment.sale_mode.is_(None)) | (~Payment.sale_mode.like("balance_topup%")),
                    Payment.amount > 0,
                )
                .limit(1)
            )
        ).first()
        decision.first_product_purchase = product and previous is None and historic is None
    if payment.status in {"refunded", "reversed"} and decision.refunded_at is None:
        decision.refunded_at = datetime.now(UTC)
    await session.flush()


async def merge_evidence(session: AsyncSession, source_user_id: int, target_user_id: int) -> None:
    for model in (AdTouchpoint, AdVisit, AdPurchaseAttribution, AdOfferActivation):
        await session.execute(
            update(model).where(model.user_id == source_user_id).values(user_id=target_user_id)
        )
    await session.execute(
        update(AdCampaign)
        .where(AdCampaign.advertiser_id == source_user_id)
        .values(advertiser_id=target_user_id)
    )
    firsts = list(
        (
            await session.execute(
                select(AdPurchaseAttribution)
                .where(
                    AdPurchaseAttribution.user_id == target_user_id,
                    AdPurchaseAttribution.first_product_purchase.is_(True),
                )
                .order_by(AdPurchaseAttribution.succeeded_at, AdPurchaseAttribution.payment_id)
            )
        ).scalars()
    )
    for duplicate in firsts[1:]:
        duplicate.first_product_purchase = False
    source = await session.get(AdAttribution, source_user_id)
    target = await session.get(AdAttribution, target_user_id)
    if source is not None and target is not None:
        if utc(source.first_start_at) < utc(target.first_start_at):
            target.ad_campaign_id = source.ad_campaign_id
            target.first_start_at = source.first_start_at
        dates = [
            item
            for item in (target.trial_activated_at, source.trial_activated_at)
            if item is not None
        ]
        target.trial_activated_at = min(dates, key=utc) if dates else None
        await session.flush()


async def claim_auth_context(
    session: AsyncSession, operation_key: str | None, user_id: int
) -> None:
    if not operation_key:
        return
    context = await session.get(AdAuthContext, operation_key)
    if context and utc(context.expires_at) > datetime.now(UTC):
        await claim_visit(session, context.visit_id, user_id)
