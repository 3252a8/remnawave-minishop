"""Version offer bindings and record activation evidence without granting rights."""

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.promo_effects import PromoEffects
from db.advertising_models import (
    AdOfferActivation,
    AdPromoBinding,
    AdPurchaseAttribution,
    AdTouchpoint,
)
from db.models import AdCampaign, Payment, PromoCode, PromoCodeActivation

from .capture import insert_once, utc


async def offer_statistics(session: AsyncSession, campaign_id: int) -> dict[int, dict[str, int]]:
    output: dict[int, dict[str, int]] = {}
    activations = (
        await session.execute(
            select(AdOfferActivation.binding_id, func.count())
            .where(
                AdOfferActivation.campaign_id == campaign_id,
            )
            .group_by(AdOfferActivation.binding_id)
        )
    ).all()
    for ident, count in activations:
        output[ident] = {"activations": int(count)}
    purchases = (
        await session.execute(
            select(
                AdPurchaseAttribution.binding_id,
                func.sum(
                    case((Payment.status.in_(["succeeded", "refunded", "reversed"]), 1), else_=0)
                ),
                func.sum(case((Payment.status.like("pending%"), 1), else_=0)),
                func.sum(case((Payment.status.in_(["refunded", "reversed"]), 1), else_=0)),
            )
            .join(Payment, Payment.payment_id == AdPurchaseAttribution.payment_id)
            .where(
                AdPurchaseAttribution.campaign_id == campaign_id,
                AdPurchaseAttribution.binding_id.is_not(None),
            )
            .group_by(AdPurchaseAttribution.binding_id)
        )
    ).all()
    for ident, count, pending, refunds in purchases:
        output.setdefault(ident, {}).update(
            purchases=int(count), pending=int(pending), refunded=int(refunds)
        )
    return output


def binding_terms(promo: PromoCode) -> dict[str, str]:
    effects = PromoEffects.from_model(promo)
    return {
        "code_snapshot": str(promo.archived_code or promo.code),
        "effects_json": json.dumps(asdict(effects), sort_keys=True),
    }


async def version_bindings(session: AsyncSession, promo: PromoCode) -> None:
    from .locking import lock_advertising

    await lock_advertising(session, "offers")
    active = list(
        (
            await session.execute(
                select(AdPromoBinding)
                .where(
                    AdPromoBinding.promo_code_id == promo.promo_code_id,
                    AdPromoBinding.ends_at.is_(None),
                )
                .with_for_update()
            )
        ).scalars()
    )
    now = datetime.now(UTC)
    terms = binding_terms(promo)
    for binding in active:
        if (
            binding.code_snapshot == terms["code_snapshot"]
            and binding.effects_json == terms["effects_json"]
            and promo.is_active
            and promo.archived_at is None
        ):
            continue
        binding.ends_at = now
        if promo.is_active and promo.archived_at is None:
            session.add(
                AdPromoBinding(
                    campaign_id=binding.campaign_id,
                    link_id=binding.link_id,
                    promo_code_id=binding.promo_code_id,
                    purpose=binding.purpose,
                    starts_at=now,
                    version=binding.version + 1,
                    **terms,
                )
            )
    await session.flush()


async def record_offer_activation(session: AsyncSession, activation: PromoCodeActivation) -> None:
    now = utc(activation.activated_at)
    binding = None
    evidence = "manual_code"
    if activation.payment_id:
        purchase = await session.get(AdPurchaseAttribution, int(activation.payment_id))
        if purchase and purchase.binding_id:
            binding = await session.get(AdPromoBinding, purchase.binding_id)
            evidence = purchase.evidence
    else:
        bindings = list(
            (
                await session.execute(
                    select(AdPromoBinding).where(
                        AdPromoBinding.promo_code_id == activation.promo_code_id,
                        AdPromoBinding.starts_at <= now,
                        (AdPromoBinding.ends_at.is_(None)) | (AdPromoBinding.ends_at > now),
                    )
                )
            ).scalars()
        )
        touches = (
            await session.execute(
                select(AdTouchpoint, AdCampaign)
                .join(AdCampaign, AdCampaign.ad_campaign_id == AdTouchpoint.campaign_id)
                .where(
                    AdTouchpoint.user_id == activation.user_id,
                    AdTouchpoint.occurred_at <= now,
                    AdTouchpoint.occurred_at >= now - timedelta(days=365),
                )
                .order_by(AdTouchpoint.occurred_at.desc(), AdTouchpoint.id.desc())
            )
        ).all()
        chosen = next(
            (
                touch
                for touch, campaign in touches
                if utc(touch.occurred_at)
                >= now - timedelta(days=int(campaign.attribution_window_days))
            ),
            None,
        )
        if chosen:
            matching = [
                b
                for b in bindings
                if b.campaign_id == chosen.campaign_id
                and (b.link_id is None or b.link_id == chosen.link_id)
            ]
            if matching:
                binding = max(matching, key=lambda b: (b.link_id is not None, b.id))
                evidence = chosen.evidence
        if binding is None and chosen is None:
            manual = [b for b in bindings if b.purpose == "manual_code_source"]
            if manual and len({b.campaign_id for b in manual}) == 1:
                binding = max(manual, key=lambda b: b.id)
    if binding:
        await insert_once(
            session,
            AdOfferActivation,
            {
                "activation_id": int(activation.activation_id),
                "campaign_id": binding.campaign_id,
                "binding_id": binding.id,
                "user_id": int(activation.user_id),
                "original_user_id": int(activation.user_id),
                "evidence": evidence,
                "occurred_at": now,
            },
            [AdOfferActivation.activation_id],
        )
