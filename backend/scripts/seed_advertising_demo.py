"""Explicit, repeatable synthetic advertising fixtures for the local mock profile."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from bot.services.advertising.imports import build_candidates, confirm_import, preview_import
from bot.services.advertising.offers import binding_terms
from config.settings import get_settings
from db.advertising_models import (
    AdAudit,
    AdLink,
    AdPromoBinding,
    AdPurchaseAttribution,
    AdSpendEntry,
    AdTouchpoint,
)
from db.database_setup import init_db_connection
from db.models import AdAttribution, AdCampaign, Payment, PromoCode, User


async def main() -> None:
    factory = init_db_connection(get_settings())
    async with factory() as session:
        if await session.get(AdCampaign, 940000001):
            print("Advertising QA fixtures already exist; operator changes preserved")
            return
        now = datetime.now(UTC)
        acquired = now - timedelta(days=100)
        for index in range(1, 4):
            session.add(
                User(
                    user_id=930000000 + index,
                    username=f"ads_qa_{index}",
                    first_name="Advertising QA",
                    registration_date=acquired if index == 1 else now - timedelta(days=3),
                )
            )
        await session.flush()
        for index, name, active, archived in [
            (1, "Web and Mini App", True, False),
            (2, "Telegram Ads import", True, False),
            (3, "Paused", False, False),
            (4, "Archive", False, True),
        ]:
            session.add(
                AdCampaign(
                    ad_campaign_id=940000000 + index,
                    name=f"QA · {name}",
                    source="qa_advertising",
                    start_param=f"ads_qa_campaign_{index}",
                    cost=4500,
                    is_active=active,
                    archived_at=now if archived else None,
                    report_currency="RUB",
                    spend_source="manual",
                    advertiser_id=910000001,
                    description="Synthetic local QA data; no platform identity evidence",
                )
            )
        await session.flush()
        links = []
        for destination in ("web", "bot", "miniapp"):
            link = AdLink(
                campaign_id=940000001,
                code=f"ad_qa_{destination}",
                label=f"QA · {destination}",
                destination=destination,
                utm_json=json.dumps(
                    {"utm_source": "qa", "utm_medium": "paid", "utm_campaign": "advertising"}
                ),
                landing_path="/",
            )
            session.add(link)
            links.append(link)
        await session.flush()
        promos = []
        for code, days, discount, expires in [
            ("ADS_QA_CHECKOUT", 0, 50, None),
            ("ADS_QA_WELCOME", 7, None, None),
            ("ADS_QA_EXPIRED", 7, None, now - timedelta(days=1)),
        ]:
            promo = (
                await session.execute(select(PromoCode).where(PromoCode.code == code))
            ).scalar_one_or_none()
            if promo is None:
                promo = PromoCode(
                    code=code,
                    bonus_days=days,
                    discount_percent=discount,
                    max_activations=100000,
                    valid_until=expires,
                )
                session.add(promo)
            promos.append(promo)
        await session.flush()
        binding = AdPromoBinding(
            campaign_id=940000001,
            link_id=links[0].id,
            promo_code_id=promos[0].promo_code_id,
            starts_at=acquired,
            **binding_terms(promos[0]),
        )
        session.add(binding)
        session.add(
            AdPromoBinding(
                campaign_id=940000001,
                link_id=links[2].id,
                promo_code_id=promos[1].promo_code_id,
                starts_at=acquired,
                **binding_terms(promos[1]),
            )
        )
        touches = []
        for index, channel, uid, occurred, new in [
            (1, "web", 930000001, acquired, True),
            (2, "miniapp", 930000002, now - timedelta(days=3), True),
            (3, "bot", 930000001, now - timedelta(hours=1), False),
            (4, "bot", 930000003, now - timedelta(hours=1, seconds=2), False),
            (5, "web", None, now, None),
            (6, "web", 930000001, now - timedelta(days=5), False),
            (7, "web", None, now - timedelta(minutes=5), None),
        ]:
            touch = AdTouchpoint(
                event_key=f"qa-advertising:{index}",
                campaign_id=940000001 if index not in {4, 7} else None,
                link_id=links[0].id if index not in {4, 7} else None,
                user_id=uid,
                original_user_id=uid,
                channel=channel,
                occurred_at=occurred,
                received_at=occurred + timedelta(seconds=1),
                evidence="unassigned_utm"
                if index == 7
                else "unassigned_bot_start"
                if index == 4
                else "tagged_link",
                is_new_user=new,
                bot_id="qa_bot" if channel == "bot" else None,
                observed_utm_json=json.dumps({"utm_source": "qa_unassigned"})
                if index == 7
                else "{}",
                utm_fingerprint=hashlib.sha256(
                    json.dumps({"utm_source": "qa_unassigned"}, sort_keys=True).encode()
                ).hexdigest()
                if index == 7
                else None,
            )
            session.add(touch)
            touches.append(touch)
        for uid, moment in [(930000001, acquired), (930000002, now - timedelta(days=3))]:
            session.add(
                AdAttribution(
                    user_id=uid,
                    ad_campaign_id=940000001,
                    first_start_at=moment,
                    trial_activated_at=moment + timedelta(minutes=2),
                )
            )
        session.add(
            AdSpendEntry(
                campaign_id=940000001,
                amount_minor=450000,
                currency="RUB",
                currency_scale=2,
                occurred_at=acquired,
                created_by=910000001,
                note="QA · Synthetic expense",
            )
        )
        await session.flush()
        for index, uid, amount, currency, status, mode, first, moment in [
            (
                1,
                930000001,
                900,
                "RUB",
                "succeeded",
                "subscription",
                True,
                acquired + timedelta(days=1),
            ),
            (2, 930000001, 700, "RUB", "refunded", "subscription", False, now - timedelta(days=2)),
            (3, 930000002, 49, "XTR", "succeeded", "gift", True, now - timedelta(days=2)),
            (
                4,
                930000001,
                1000,
                "RUB",
                "succeeded",
                "balance_topup",
                False,
                now - timedelta(days=1),
            ),
            (5, 930000002, 500, "RUB", "pending", "subscription", None, now),
        ]:
            payment = Payment(
                user_id=uid,
                amount=amount,
                currency=currency,
                status=status,
                provider="qa_advertising",
                idempotence_key=f"qa-advertising-payment:{index}",
                sale_mode=mode,
                funding_source="external",
                description="QA · Synthetic advertising order",
                created_at=moment,
                fulfilled_at=moment if status != "pending" else None,
            )
            session.add(payment)
            await session.flush()
            minor = amount * (1 if currency == "XTR" else 100)
            session.add(
                AdPurchaseAttribution(
                    payment_id=payment.payment_id,
                    user_id=uid,
                    original_user_id=uid,
                    campaign_id=940000001,
                    link_id=links[0].id,
                    touchpoint_id=touches[0 if index == 1 else 1 if uid == 930000002 else 5].id,
                    binding_id=binding.id,
                    evidence="tagged_link",
                    checkout_at=moment,
                    succeeded_at=moment if status != "pending" else None,
                    refunded_at=now - timedelta(days=1) if status == "refunded" else None,
                    first_product_purchase=first,
                    amount_minor=minor,
                    product_amount_minor=minor if mode != "balance_topup" else 0,
                    product_order=mode != "balance_topup",
                    cash_amount_minor=minor,
                    currency=currency,
                    currency_scale=0 if currency == "XTR" else 2,
                    sale_mode=mode,
                    funding_source="external",
                )
            )
        batch = await preview_import(
            session,
            campaign_id=940000002,
            user_id=910000001,
            source=f"time,ad,starts\n{(now - timedelta(hours=1)).isoformat()},qa-synthetic,1\n",
            mapping={"start": "time", "advertisement": "ad", "starts": "starts"},
            timezone_name="UTC",
            account="QA · Synthetic export",
            granularity="event",
            currency=None,
            delimiter=",",
        )
        await confirm_import(session, batch, replace=False)
        await build_candidates(session, batch, bot_id="qa_bot", window_seconds=30)
        session.add(
            AdAudit(
                campaign_id=940000001,
                action="campaign.updated",
                actor_id=910000001,
                details_json='{"fixture":"synthetic"}',
            )
        )
        await session.commit()
        print("Seeded advertising QA campaigns, accounts, orders and an ambiguous import")


if __name__ == "__main__":
    asyncio.run(main())
