from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_api_impl import ads as admin_ads
from bot.handlers.user import advertiser as advertiser_handler
from db.activity_models import AdCampaign
from db.dal import ad_dal
from db.models import Payment, User


class FakeSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.added = []
        self._get_map = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def refresh(self, obj):
        pass

    async def get(self, model, ident):
        return self._get_map.get((model, ident))


class AdDalAdvertiserTests(IsolatedAsyncioTestCase):
    async def test_list_campaigns_filters_by_advertiser_id(self):
        session = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute.return_value = result_mock

        campaigns = await ad_dal.list_campaigns(session, advertiser_id=123456789)

        assert campaigns == []
        session.execute.assert_awaited_once()
        statement = session.execute.await_args[0][0]
        compiled = str(
            statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        )
        assert "WHERE ad_campaigns.advertiser_id = 123456789" in compiled

    async def test_reset_campaign_stats_executes_update(self):
        session = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.rowcount = 1
        session.execute.return_value = result_mock

        ok = await ad_dal.reset_campaign_stats(session, campaign_id=42)

        assert ok is True
        session.execute.assert_awaited_once()
        statement = session.execute.await_args[0][0]
        compiled = str(
            statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        )
        assert "UPDATE ad_campaigns SET stats_reset_at=now()" in compiled
        assert "WHERE ad_campaigns.ad_campaign_id = 42" in compiled

    async def test_list_campaign_purchases_queries_payment_and_attribution(self):
        session = AsyncMock(spec=AsyncSession)
        campaign = AdCampaign(
            ad_campaign_id=10,
            source="Telegram",
            start_param="ad_tg",
            cost=100.0,
            is_active=True,
            stats_reset_at=None,
        )
        session.get.return_value = campaign
        result_mock = MagicMock()
        payment = Payment(
            payment_id=101,
            user_id=50,
            amount=500.0,
            currency="RUB",
            status="succeeded",
            funding_source="external",
            created_at=datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
        )
        result_mock.all.return_value = [(payment, "buyer55", 50)]
        session.execute.return_value = result_mock

        items = await ad_dal.list_campaign_purchases(
            session,
            campaign_id=10,
            page=0,
            page_size=20,
        )

        assert len(items) == 1
        assert items[0]["payment_id"] == 101
        assert items[0]["user_id"] == 50
        assert items[0]["username"] == "buyer55"
        assert items[0]["amount"] == 500.0

        session.execute.assert_awaited_once()
        items_stmt = session.execute.await_args[0][0]
        compiled = str(
            items_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        )
        assert "JOIN users" in compiled
        assert "LIMIT 20" in compiled


class AdminAdsAdvertiserRouteTests(IsolatedAsyncioTestCase):
    def _create_request(
        self,
        session: FakeSession,
        match_info: dict[str, str],
        json_data: dict | None = None,
        query: dict[str, str] | None = None,
    ):
        req = SimpleNamespace(
            app={
                "async_session_factory": lambda: session,
                "settings": SimpleNamespace(),
            },
            match_info=match_info,
            query=query or {},
            json=AsyncMock(return_value=json_data or {}),
        )
        return req

    async def test_assign_advertiser_success(self):
        session = FakeSession()
        campaign = AdCampaign(
            ad_campaign_id=1,
            source="Test Campaign",
            start_param="test_slug",
            cost=50.0,
            is_active=True,
            advertiser_id=None,
        )
        session._get_map[(AdCampaign, 1)] = campaign

        advertiser_user = User(
            user_id=999,
            telegram_id=999,
            first_name="Advertiser",
        )

        request = self._create_request(
            session,
            match_info={"campaign_id": "1"},
            json_data={"advertiser_id": 999},
        )

        with (
            patch.object(admin_ads, "_require_admin_user_id", return_value=1),
            patch(
                "bot.app.web.admin_api_impl.ads.user_dal.get_user_by_telegram_id",
                AsyncMock(return_value=advertiser_user),
            ),
        ):
            resp = await admin_ads.admin_ad_assign_route(request)
            assert resp.status == 200
            assert campaign.advertiser_id == 999
            assert session.committed is True

    async def test_assign_advertiser_campaign_not_found(self):
        session = FakeSession()
        request = self._create_request(
            session,
            match_info={"campaign_id": "9999"},
            json_data={"advertiser_id": 123},
        )

        with patch.object(admin_ads, "_require_admin_user_id", return_value=1):
            resp = await admin_ads.admin_ad_assign_route(request)
            assert resp.status == 404

    async def test_reset_campaign_stats_route_success(self):
        session = FakeSession()
        request = self._create_request(session, match_info={"campaign_id": "1"})

        with (
            patch.object(admin_ads, "_require_admin_user_id", return_value=1),
            patch.object(
                ad_dal, "reset_campaign_stats", AsyncMock(return_value=True)
            ) as reset_mock,
        ):
            resp = await admin_ads.admin_ad_reset_stats_route(request)
            assert resp.status == 200
            reset_mock.assert_awaited_once_with(session, 1)
            assert session.committed is True

    async def test_get_campaign_purchases_route_success(self):
        session = FakeSession()
        request = self._create_request(
            session,
            match_info={"campaign_id": "1"},
            query={"page": "0", "page_size": "10"},
        )

        sample_purchases = [
            {
                "payment_id": 101,
                "user_id": 50,
                "username": "buyer55",
                "amount": 500.0,
                "currency": "RUB",
                "description": "Premium 1m",
                "created_at": datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
            }
        ]

        with (
            patch.object(admin_ads, "_require_admin_user_id", return_value=1),
            patch.object(
                ad_dal, "list_campaign_purchases", AsyncMock(return_value=sample_purchases)
            ),
        ):
            resp = await admin_ads.admin_ad_purchases_route(request)
            assert resp.status == 200
            data = json.loads(resp.text)
            assert data["ok"] is True
            assert len(data["purchases"]) == 1
            purchase = data["purchases"][0]
            assert purchase["payment_id"] == 101
            assert purchase["user_id"] == 50
            assert purchase["username"] == "buyer55"
            assert purchase["amount"] == 500.0


class AdvertiserBotHandlerTests(IsolatedAsyncioTestCase):
    async def test_my_ads_empty(self):
        user = SimpleNamespace(id=12345, username="adv_user")
        message = SimpleNamespace(
            from_user=user,
            answer=AsyncMock(),
        )
        session = FakeSession()
        i18n = SimpleNamespace(gettext=lambda _lang, key, **kw: key)
        settings = SimpleNamespace(DEFAULT_LANGUAGE="ru")

        with (
            patch(
                "bot.handlers.user.advertiser.user_dal.get_user_by_telegram_id",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.handlers.user.advertiser.user_dal.get_user_by_id", AsyncMock(return_value=None)
            ),
            patch.object(ad_dal, "list_campaigns", AsyncMock(return_value=[])),
        ):
            await advertiser_handler.my_ads_command(
                message=message,
                session=session,
                i18n_data={"current_language": "ru", "i18n_instance": i18n},
                settings=settings,
            )

        message.answer.assert_awaited_once_with("advertiser_no_campaigns")

    async def test_my_ads_with_campaigns(self):
        user = SimpleNamespace(id=12345, username="adv_user")
        message = SimpleNamespace(
            from_user=user,
            answer=AsyncMock(),
        )
        session = FakeSession()
        i18n = SimpleNamespace(
            gettext=lambda _lang, key, **kw: {
                "advertiser_campaigns_header": "📊 <b>Кабинет рекламодателя</b>\n\n",
                "advertiser_campaign_item": (
                    f"📢 <b>{kw.get('source')}</b> (<code>{kw.get('start_param')}</code>)\n"
                    f"• Статус: {kw.get('status')}\n"
                    f"• Переходы: <b>{kw.get('starts')}</b>\n"
                    f"• Триалы: <b>{kw.get('trials')}</b>\n"
                    f"• Первые оплаты: <b>{kw.get('payers')}</b>\n"
                    f"• Выручка: <b>{kw.get('revenue')}</b>\n\n"
                ),
                "advertiser_status_active": "🟢 Активна",
            }.get(key, key)
        )
        settings = SimpleNamespace(DEFAULT_LANGUAGE="ru")

        campaign = AdCampaign(
            ad_campaign_id=1,
            source="Special Promo",
            start_param="special_promo",
            cost=100.0,
            is_active=True,
            advertiser_id=12345,
        )

        stats = {
            "starts": 100,
            "trials": 20,
            "payers": 10,
            "revenue": 1500.0,
        }

        db_user = User(user_id=12345, telegram_id=12345, first_name="Advertiser")

        with (
            patch(
                "bot.handlers.user.advertiser.user_dal.get_user_by_telegram_id",
                AsyncMock(return_value=db_user),
            ),
            patch.object(ad_dal, "list_campaigns", AsyncMock(return_value=[campaign])),
            patch.object(ad_dal, "get_campaign_stats", AsyncMock(return_value=stats)),
        ):
            await advertiser_handler.my_ads_command(
                message=message,
                session=session,
                i18n_data={"current_language": "ru", "i18n_instance": i18n},
                settings=settings,
            )

        message.answer.assert_awaited_once()
        text = message.answer.await_args[0][0]
        assert "📊 <b>Кабинет рекламодателя</b>" in text
        assert "Special Promo" in text
        assert "special_promo" in text
        assert "1500.00" in text


class WebAppAuthAdAttributionTests(IsolatedAsyncioTestCase):
    async def test_apply_ad_attribution_creates_attribution_when_campaign_active(self):
        from bot.app.web.webapp.auth import _apply_ad_attribution_if_needed

        session = FakeSession()
        campaign = AdCampaign(
            ad_campaign_id=7,
            source="Influencer",
            start_param="promo_ad",
            cost=200.0,
            is_active=True,
        )

        with (
            patch.object(ad_dal, "get_campaign_by_start_param", AsyncMock(return_value=campaign)),
            patch.object(ad_dal, "ensure_attribution", AsyncMock()) as ensure_mock,
        ):
            await _apply_ad_attribution_if_needed(session, user_id=100, raw_start_param="promo_ad")
            ensure_mock.assert_awaited_once_with(session, user_id=100, campaign_id=7)

    async def test_apply_ad_attribution_ignores_inactive_or_missing_campaign(self):
        from bot.app.web.webapp.auth import _apply_ad_attribution_if_needed

        session = FakeSession()
        inactive_campaign = AdCampaign(
            ad_campaign_id=8,
            source="Old Promo",
            start_param="old_ad",
            cost=50.0,
            is_active=False,
        )

        with (
            patch.object(
                ad_dal, "get_campaign_by_start_param", AsyncMock(return_value=inactive_campaign)
            ),
            patch.object(ad_dal, "ensure_attribution", AsyncMock()) as ensure_mock,
        ):
            await _apply_ad_attribution_if_needed(session, user_id=100, raw_start_param="old_ad")
            ensure_mock.assert_not_called()
