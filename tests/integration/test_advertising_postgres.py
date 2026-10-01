"""Advertising accounting transitions on isolated, disposable PostgreSQL schemas."""

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.services.advertising.capture import (
    capture_contact,
    claim_visit,
    merge_evidence,
    record_payment_state,
)
from bot.services.advertising.imports import (
    build_candidates,
    confirm_import,
    preview_import,
    revert_import,
)
from bot.services.advertising.reporting import campaign_report
from db.advertising_models import (
    AdExternalMetric,
    AdMatchCandidate,
    AdPurchaseAttribution,
    AdTouchpoint,
)
from db.dal import ad_dal, payment_dal
from db.models import AdAttribution, AdCampaign, Base, Payment, User

DATABASE_URL = os.environ.get("CORE_PERFORMANCE_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="Disposable PostgreSQL URL is required")


def scenario(run: Callable[[Any], Awaitable[None]]) -> None:
    async def execute() -> None:
        schema = "advertising_test_" + uuid.uuid4().hex
        admin = create_async_engine(DATABASE_URL)
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            DATABASE_URL, connect_args={"server_settings": {"search_path": schema}}
        )
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
            async with factory() as session:
                session.add_all(
                    [
                        User(user_id=1, registration_date=datetime.now(UTC) - timedelta(days=180)),
                        User(user_id=2),
                    ]
                )
                await session.flush()
                await ad_dal.create_campaign(
                    session, source="Channel A", start_param="channel_a", cost=100
                )
                await ad_dal.create_campaign(
                    session, source="Channel B", start_param="channel_b", cost=200
                )
                await session.commit()
            await run(factory)
        finally:
            await engine.dispose()
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()

    asyncio.run(execute())


async def order(
    session: Any,
    key: str,
    *,
    amount: float = 500,
    currency: str = "RUB",
    sale_mode: str = "subscription",
    user_id: int = 1,
) -> Payment:
    return await payment_dal.create_payment_record(
        session,
        {
            "user_id": user_id,
            "amount": amount,
            "currency": currency,
            "provider": "dev_ads_mock",
            "idempotence_key": key,
            "status": "pending",
            "sale_mode": sale_mode,
        },
    )


def test_checkout_source_is_fixed_before_late_contact_and_success() -> None:
    async def run(factory: Any) -> None:
        async with factory() as session:
            before = await order(session, "before-contact")
            await capture_contact(session, code="channel_a", user_id=1, event_key="a")
            after = await order(session, "after-contact")
            await capture_contact(session, code="channel_b", user_id=1, event_key="b")
            before.status = after.status = "succeeded"
            await record_payment_state(session, before)
            await record_payment_state(session, after)
            await record_payment_state(session, after)
            await session.commit()
            unknown = await session.get(AdPurchaseAttribution, before.payment_id)
            attributed = await session.get(AdPurchaseAttribution, after.payment_id)
            assert unknown.campaign_id is None and unknown.evidence == "unknown"
            assert attributed.campaign_id == 1 and attributed.evidence == "tagged_link"
            assert (
                await session.execute(select(func.count()).select_from(AdPurchaseAttribution))
            ).scalar() == 2
            report = await campaign_report(session, await session.get(AdCampaign, 1))
            assert report["purchases"] == 1
            filtered = await campaign_report(
                session, await session.get(AdCampaign, 1), evidence="tagged_link"
            )
            assert all(
                row["spend_minor"] is None and row["roas"] is None for row in filtered["currencies"]
            )

    scenario(run)


def test_first_product_purchase_uses_success_order_excludes_topups_and_survives_refund() -> None:
    async def run(factory: Any) -> None:
        async with factory() as session:
            await capture_contact(session, code="channel_a", user_id=1)
            topup = await order(session, "topup", amount=1000, sale_mode="balance_topup")
            slow = await order(session, "slow", amount=700)
            fast = await order(session, "fast", amount=900)
            topup.status = fast.status = "succeeded"
            await record_payment_state(session, topup)
            await record_payment_state(session, fast)
            slow.status = "succeeded"
            await record_payment_state(session, slow)
            fast.status = "refunded"
            await record_payment_state(session, fast)
            stars = await order(session, "stars", amount=49, currency="XTR", user_id=2)
            await capture_contact(session, code="channel_a", user_id=2)
            stars.status = "succeeded"
            await record_payment_state(session, stars)
            await session.flush()
            assert (
                await session.get(AdPurchaseAttribution, topup.payment_id)
            ).first_product_purchase is False
            assert (
                await session.get(AdPurchaseAttribution, fast.payment_id)
            ).first_product_purchase is True
            assert (
                await session.get(AdPurchaseAttribution, slow.payment_id)
            ).first_product_purchase is False
            report = await campaign_report(session, await session.get(AdCampaign, 1))
            rub = next(row for row in report["currencies"] if row["currency"] == "RUB")
            assert rub["cash_minor"] == 260000
            assert rub["product_minor"] == 160000
            assert rub["refund_minor"] == 90000
            assert rub["net_minor"] == 70000
            assert report["purchases"] == 2 and report["first_payers"] == 1
            assert all(row["currency"] != "XTR" for row in report["currencies"])

    scenario(run)


def test_anonymous_visit_claim_is_idempotent_and_cannot_move_to_another_account() -> None:
    async def run(factory: Any) -> None:
        async with factory() as session:
            visit = await capture_contact(session, code="channel_a", event_key="visit")
            await claim_visit(session, visit, 1)
            await claim_visit(session, visit, 2)
            await capture_contact(
                session, code="channel_a", visit_id=visit, user_id=1, event_key="visit"
            )
            await session.flush()
            touch = (await session.execute(select(AdTouchpoint))).scalar_one()
            assert touch.user_id == 1 and touch.is_new_user is False
            assert await session.get(AdAttribution, 2) is None

    scenario(run)


def test_concurrent_attribution_and_campaign_creation_do_not_poison_transactions() -> None:
    async def run(factory: Any) -> None:
        async def attribute(code: str) -> None:
            async with factory() as session:
                await capture_contact(session, code=code, user_id=1, event_key=code)
                await session.commit()

        await asyncio.gather(attribute("channel_a"), attribute("channel_b"))

        async def create() -> bool:
            async with factory() as session:
                try:
                    await ad_dal.create_campaign(
                        session, source="Concurrent", start_param="same_code", cost=0
                    )
                except ValueError:
                    await session.rollback()
                    return False
                await session.commit()
                return True

        assert sorted(await asyncio.gather(create(), create())) == [False, True]
        async with factory() as session:
            assert (
                await session.execute(select(func.count()).select_from(AdAttribution))
            ).scalar() == 1
            assert (
                await session.execute(select(func.count()).select_from(AdTouchpoint))
            ).scalar() == 2

    scenario(run)


def test_merge_keeps_earliest_source_original_ids_and_one_first_purchase() -> None:
    async def run(factory: Any) -> None:
        async with factory() as session:
            now = datetime.now(UTC)
            await capture_contact(
                session, code="channel_a", user_id=1, occurred_at=now - timedelta(days=2)
            )
            await capture_contact(
                session, code="channel_b", user_id=2, occurred_at=now - timedelta(days=1)
            )
            first = await order(session, "one")
            second = await order(session, "two", user_id=2)
            first.status = second.status = "succeeded"
            await record_payment_state(session, first)
            await record_payment_state(session, second)
            await session.execute(update(Payment).where(Payment.user_id == 1).values(user_id=2))
            await merge_evidence(session, 1, 2)
            await session.flush()
            attribution = await session.get(AdAttribution, 2)
            assert attribution.ad_campaign_id == 1
            rows = list((await session.execute(select(AdPurchaseAttribution))).scalars())
            assert {row.original_user_id for row in rows} == {1, 2}
            assert sum(row.first_product_purchase is True for row in rows) == 1

    scenario(run)


async def imported(
    session: Any, cost: int, *, campaign_id: int = 1, granularity: str = "daily"
) -> Any:
    return await preview_import(
        session,
        campaign_id=campaign_id,
        user_id=1,
        source=(
            "date,ad,views,clicks,starts,cost\n"
            f"2026-09-01T00:00:00Z,advert-1,100,5,"
            f"{1 if granularity == 'event' else 3},{cost}\n"
        ),
        mapping={
            "start": "date",
            "advertisement": "ad",
            "impressions": "views",
            "clicks": "clicks",
            "starts": "starts",
            "cost": "cost",
        },
        timezone_name="UTC",
        account="test-account",
        granularity=granularity,
        currency="RUB",
        delimiter=",",
    )


def test_import_revision_duplicate_overlap_and_revert_use_current_metrics_once() -> None:
    async def run(factory: Any) -> None:
        async with factory() as session:
            first = await imported(session, 20)
            await confirm_import(session, first, replace=False)
            assert await confirm_import(session, first, replace=False) == "already_confirmed"
            second = await imported(session, 30)
            await confirm_import(session, second, replace=True)
            current = (
                await session.execute(
                    select(AdExternalMetric).where(AdExternalMetric.is_current.is_(True))
                )
            ).scalar_one()
            assert current.cost_minor == 3000
            await revert_import(session, second)
            await session.flush()
            restored = (
                await session.execute(
                    select(AdExternalMetric).where(AdExternalMetric.is_current.is_(True))
                )
            ).scalar_one()
            assert restored.cost_minor == 2000
            duplicate = await imported(session, 20)
            with pytest.raises(ValueError, match="duplicate_import"):
                await confirm_import(session, duplicate, replace=True)
            minute = await imported(session, 10, granularity="minute")
            with pytest.raises(ValueError, match="incompatible_import_overlap"):
                await confirm_import(session, minute, replace=True)

    scenario(run)


def test_temporal_candidates_include_organic_competing_starts_without_attributing_orders() -> None:
    async def run(factory: Any) -> None:
        async with factory() as session:
            moment = datetime(2026, 9, 1, tzinfo=UTC)
            await capture_contact(
                session,
                user_id=1,
                channel="bot",
                bot_id="123",
                occurred_at=moment,
                event_key="organic",
            )
            await capture_contact(
                session,
                code="channel_b",
                user_id=2,
                channel="bot",
                bot_id="123",
                occurred_at=moment,
                event_key="other",
            )
            batch = await imported(session, 0, granularity="event")
            await confirm_import(session, batch, replace=False)
            await build_candidates(session, batch, bot_id="123", window_seconds=30)
            matches = list((await session.execute(select(AdMatchCandidate))).scalars())
            assert len(matches) == 2 and all(item.status == "ambiguous" for item in matches)
            assert await session.get(AdAttribution, 1) is None
            assert (
                await session.execute(select(func.count()).select_from(AdPurchaseAttribution))
            ).scalar() == 0

    scenario(run)


def test_magic_link_carries_server_visit_between_browsers_once() -> None:
    async def run(factory: Any) -> None:
        from urllib.parse import parse_qs, urlsplit

        from bot.services.advertising.capture import claim_auth_context
        from bot.services.email_auth_service import EmailAuthService
        from config.settings import get_settings

        settings = get_settings().model_copy(
            update={
                "APP_RUNTIME_MODE": "test",
                "QA_AUTH_ENABLED": True,
                "EMAIL_LOGIN_ENABLED": True,
                "PUBLIC_APP_URL": "https://example.test/shop",
            }
        )
        service = EmailAuthService(settings)
        async with factory() as browser_one:
            visit = await capture_contact(browser_one, code="channel_a")
            requested = await service.request_code(
                browser_one,
                email="ads-magic@example.test",
                purpose="login",
                language_code="en",
                advertising_visit_id=visit,
            )
            assert requested.ok and requested.magic_link
            token = parse_qs(urlsplit(requested.magic_link).query)["login_token"][0]
            await browser_one.commit()
        async with factory() as browser_two:
            verified = await service.verify_magic_token(browser_two, token=token, purpose="login")
            assert verified.ok
            await claim_auth_context(browser_two, verified.operation_key, 2)
            await browser_two.commit()
            source = await browser_two.get(AdAttribution, 2)
            assert source.ad_campaign_id == 1
            assert not (
                await service.verify_magic_token(browser_two, token=token, purpose="login")
            ).ok
            await claim_auth_context(browser_two, verified.operation_key, 1)
            assert await browser_two.get(AdAttribution, 1) is None

    scenario(run)


def test_offer_versions_keep_checkout_terms_and_free_product_identity() -> None:
    async def run(factory: Any) -> None:
        from bot.services.advertising.capture import snapshot_purchase
        from bot.services.advertising.offers import binding_terms, version_bindings
        from db.advertising_models import AdPromoBinding
        from db.models import PromoCode

        async with factory() as session:
            await capture_contact(session, code="channel_a", user_id=1)
            promo = PromoCode(
                code="ADS_FREE", bonus_days=0, discount_percent=100, max_activations=100
            )
            session.add(promo)
            await session.flush()
            original = AdPromoBinding(
                campaign_id=1, promo_code_id=promo.promo_code_id, **binding_terms(promo)
            )
            session.add(original)
            await session.flush()
            payment = Payment(
                user_id=1,
                provider="dev_ads_mock",
                amount=0,
                currency="RUB",
                status="pending",
                sale_mode="subscription",
                promo_code_id=promo.promo_code_id,
            )
            session.add(payment)
            await session.flush()
            await snapshot_purchase(session, payment, checkout_at=datetime.now(UTC))
            promo.discount_percent = 50
            await version_bindings(session, promo)
            versions = list(
                (
                    await session.execute(select(AdPromoBinding).order_by(AdPromoBinding.id))
                ).scalars()
            )
            assert len(versions) == 2 and versions[0].ends_at and versions[1].version == 2
            payment.status = "succeeded"
            await record_payment_state(session, payment)
            decision = await session.get(AdPurchaseAttribution, payment.payment_id)
            assert decision.binding_id == original.id and decision.product_order
            assert decision.first_product_purchase and decision.cash_amount_minor == 0
            assert "100" in original.effects_json and "50" in versions[1].effects_json
            from db.models import UserBalanceLedgerEntry

            assert (
                await session.execute(select(func.count()).select_from(UserBalanceLedgerEntry))
            ).scalar() == 0

    scenario(run)


def test_mature_cohort_refund_window_and_unknown_currency_spend() -> None:
    async def run(factory: Any) -> None:
        async with factory() as session:
            acquired = datetime.now(UTC) - timedelta(days=100)
            await capture_contact(session, code="channel_a", user_id=1, occurred_at=acquired)
            payment = await order(session, "cohort-refund", currency="XTR", amount=49)
            decision = await session.get(AdPurchaseAttribution, payment.payment_id)
            decision.campaign_id = 1
            decision.touchpoint_id = (
                await session.execute(select(AdTouchpoint.id).where(AdTouchpoint.user_id == 1))
            ).scalar_one()
            decision.checkout_at = acquired + timedelta(days=1)
            decision.succeeded_at = acquired + timedelta(days=1)
            decision.refunded_at = acquired + timedelta(days=10)
            decision.first_product_purchase = True
            payment.status = "refunded"
            await session.flush()
            report = await campaign_report(
                session,
                await session.get(AdCampaign, 1),
                period_mode="cohort",
                channel="web",
                currency="XTR",
            )
            stars = report["currencies"][0]
            assert stars["d7_minor"] == 49 and stars["d30_minor"] == 0
            assert stars["net_minor"] == 0 and stars["spend_minor"] is None
            assert stars["roas"] is None and stars["cac_minor"] is None
            assert report["platform"]["impressions"] is None

    scenario(run)


def test_legacy_migration_is_repeatable_and_hundred_campaigns_use_three_stat_queries() -> None:
    async def run(factory: Any) -> None:
        from sqlalchemy import event

        from db.dal.ad_statistics import campaign_statistics
        from db.migrator.chain_0097_advertising_evidence import _migration_0097_advertising_evidence

        async with factory() as session:
            await capture_contact(session, code="channel_a", user_id=1)
            await session.commit()
            original = (
                await session.execute(
                    select(AdCampaign.start_param, AdCampaign.cost).order_by(
                        AdCampaign.ad_campaign_id
                    )
                )
            ).all()
            connection = await session.connection()
            for column in [
                "name",
                "description",
                "archived_at",
                "report_currency",
                "attribution_window_days",
                "spend_source",
            ]:
                await connection.execute(text(f"ALTER TABLE ad_campaigns DROP COLUMN {column}"))
            await connection.run_sync(_migration_0097_advertising_evidence)
            await connection.run_sync(_migration_0097_advertising_evidence)
            assert (
                await session.execute(
                    select(AdCampaign.start_param, AdCampaign.cost).order_by(
                        AdCampaign.ad_campaign_id
                    )
                )
            ).all() == original
            assert (await session.get(AdAttribution, 1)).ad_campaign_id == 1
            session.add_all(
                [AdCampaign(source=f"load-{i}", start_param=f"load_{i}", cost=0) for i in range(98)]
            )
            await session.flush()
            ids = list((await session.execute(select(AdCampaign.ad_campaign_id))).scalars())
            calls: list[str] = []
            engine = session.get_bind()

            def count_query(
                conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: Any
            ) -> None:
                calls.append(statement)

            event.listen(engine, "before_cursor_execute", count_query)
            try:
                stats = await campaign_statistics(session, ids)
            finally:
                event.remove(engine, "before_cursor_execute", count_query)
            assert len(stats) == 100 and len(calls) == 3

    scenario(run)
