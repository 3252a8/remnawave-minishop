import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web

from bot.app.web.admin_api_impl import gift_creation
from bot.services.checkout_addons import checkout_addon_grants
from config.tariffs_config import TariffsConfig
from db.gift_models import SubscriptionGift
from db.models import User
from tests.support.settings_stub import settings_stub


class AdminGiftCreationTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.catalog = TariffsConfig.model_validate(
            {
                "schema_version": 2,
                "period_unit": "day",
                "default_tariff": "base",
                "tariffs": [
                    {
                        "key": "base",
                        "billing_model": "period",
                        "period_unit": "day",
                        "monthly_gb": 100,
                        "enabled_periods": [7],
                        "prices_rub": {"7": 100},
                    }
                ],
            }
        )
        self.settings = settings_stub(
            tariffs_config=self.catalog,
            USER_HWID_DEVICE_LIMIT=3,
            USER_TRAFFIC_STRATEGY="NO_RESET",
            MY_DEVICES_SECTION_ENABLED=True,
            TRIAL_DAYS_STRATEGY="add_remaining",
            smtp_delivery_configured=True,
            SUBSCRIPTION_MINI_APP_URL="https://shop.example.test/app",
        )
        self.plan = {
            "id": "base:period:7",
            "tariff_key": "base",
            "period_key": 7,
            "months": None,
            "duration_days": 7,
            "currency": "RUB",
            "price": 100,
            "sale_mode": "subscription",
        }
        self.body = {
            "request_id": "845b7540-2fb8-4fbb-8089-c438c911c734",
            "plan_id": self.plan["id"],
        }
        self.request = SimpleNamespace(json=AsyncMock(side_effect=lambda: self.body))
        self.actor = User(user_id=10, username="admin", is_banned=False)
        self.session = AsyncMock()
        self.session.__aenter__.return_value = self.session
        self.session.scalar.return_value = None
        self.payment = None
        self.gift = SubscriptionGift(
            gift_id=8,
            payment_id=77,
            purchaser_id=10,
            token="R" * 43,
            status="ready",
            delivery_status="not_requested",
            created_at=datetime.now(UTC),
        )

        def add(payment):
            payment.payment_id = 77
            self.payment = payment

        self.session.add = MagicMock(side_effect=add)
        self.emit = AsyncMock()
        self.audit = AsyncMock()
        for name, replacement in (
            ("_require_admin_user_id", lambda _: 10),
            ("get_settings", lambda _: self.settings),
            ("get_session_factory", lambda _: lambda: self.session),
            ("_public_webapp_base_url", lambda *_: "https://shop.example.test/app"),
            ("_serialize_plans", lambda *_: [self.plan]),
            ("user_dal.lock_user_by_id", AsyncMock(return_value=self.actor)),
            ("gift_dal.issue", AsyncMock(return_value=self.gift)),
            ("events.emit_model", self.emit),
        ):
            p = patch(f"bot.app.web.admin_api_impl.gift_creation.{name}", replacement)
            p.start()
            self.addCleanup(p.stop)
        p = patch(
            "bot.services.gift_purchase.message_log_dal.create_message_log_no_commit", self.audit
        )
        p.start()
        self.addCleanup(p.stop)

    async def test_free_creation_freezes_terms_queues_email_and_emits_once(self):
        self.body["recipient_email"] = "friend@example.com"
        response = await gift_creation.admin_gift_create_route(self.request)
        self.assertEqual(response.status, 200)
        result = json.loads(response.text)["gift"]
        self.assertEqual(result["total_amount"], 0)
        self.assertEqual(result["link"], "https://shop.example.test/?gift=" + "R" * 43)
        self.assertEqual(result["delivery_status"], "pending")
        self.assertEqual(result["devices"], 3)
        self.assertEqual(self.payment.funding_source, "admin_grant")
        self.assertEqual(self.payment.fulfilled_by_admin_id, 10)
        frozen = json.loads(self.payment.subscription_terms_snapshot)
        self.assertEqual(frozen["duration_days"], 7)
        self.assertEqual(frozen["tariff"]["monthly_gb"], 100)
        self.assertEqual(frozen["inviter_days"], 0)
        self.assertEqual(frozen["referee_days"], 0)
        self.session.commit.assert_awaited_once()
        self.emit.assert_awaited_once()
        self.assertEqual(self.emit.await_args.args[0].provider, "admin_gift")
        self.assertEqual(self.audit.await_args.args[1]["event_type"], "gift_created_by_admin")
        # A retry must return the already-created gift even if the catalog disappeared.
        self.session.scalar.return_value = self.payment
        with (
            patch.object(gift_creation, "_serialize_plans", return_value=[]),
            patch.object(gift_creation.gift_dal, "by_payment", AsyncMock(return_value=self.gift)),
        ):
            retry = await gift_creation.admin_gift_create_route(self.request)
        self.assertEqual(json.loads(retry.text)["gift"]["gift_id"], result["gift_id"])
        self.session.add.assert_called_once()
        self.emit.assert_awaited_once()

    async def test_stale_plan_and_unavailable_addons_do_not_create_gift(self):
        self.body["plan_id"] = "removed-plan"
        self.assertEqual((await gift_creation.admin_gift_create_route(self.request)).status, 400)
        self.body["plan_id"] = self.plan["id"]
        self.body["checkout_addons"] = {"device_count": 999}
        self.assertEqual((await gift_creation.admin_gift_create_route(self.request)).status, 400)
        self.session.add.assert_not_called()
        self.session.commit.assert_not_awaited()

    async def test_legacy_subscription_options_have_stable_ids_and_limits(self):
        self.plan.pop("id")
        self.plan.pop("tariff_key")
        self.plan.update(months=1, period_key=1, duration_days=30)
        self.settings.tariffs_config = None
        self.settings.USER_TRAFFIC_LIMIT_GB = 150
        options = json.loads((await gift_creation.admin_gift_options_route(self.request)).text)
        self.assertEqual(options["plans"][0]["id"], "legacy:period:30")
        self.assertEqual(options["plans"][0]["effective_hwid_device_limit"], 3)
        self.body["plan_id"] = options["plans"][0]["id"]
        response = await gift_creation.admin_gift_create_route(self.request)
        self.assertEqual(response.status, 200)
        result = json.loads(response.text)["gift"]
        self.assertEqual(result["devices"], 3)
        self.assertEqual(result["regular_limit_gb"], 150)

    async def test_invalid_email_or_client_price_is_rejected(self):
        for invalid in ({"recipient_email": "invalid"}, {"amount": 50}):
            with self.subTest(invalid=invalid):
                self.request.json.return_value = {**self.body, **invalid}
                self.request.json.side_effect = None
                with self.assertRaises(web.HTTPBadRequest):
                    await gift_creation.admin_gift_create_route(self.request)
        self.session.add.assert_not_called()

    async def test_banned_admin_cannot_issue_gift(self):
        self.actor.is_banned = True
        self.assertEqual((await gift_creation.admin_gift_create_route(self.request)).status, 403)
        self.session.add.assert_not_called()

    async def test_flexible_limits_are_issued_without_charging_their_prices(self):
        data = self.catalog.model_dump(mode="json")
        data["tariffs"][0].update(
            {
                "hwid_device_limit": 3,
                "flexible_traffic_limit": {
                    "step_gb": 50,
                    "max_total_gb": 200,
                    "price_per_step": 40,
                },
                "checkout_addons": {
                    "devices": {"enabled": True, "max_extra_devices": 2, "price_per_device": 15},
                    "traffic": {"enabled": True},
                },
            }
        )
        self.settings.tariffs_config = TariffsConfig.model_validate(data)
        self.body["checkout_addons"] = {"device_count": 2, "regular_limit_gb": 200}
        response = await gift_creation.admin_gift_create_route(self.request)
        self.assertEqual(response.status, 200)
        gift = json.loads(response.text)["gift"]
        self.assertEqual(gift["devices"], 5)
        self.assertEqual(gift["regular_limit_gb"], 200)
        self.assertEqual(gift["amount"], 0)
        self.assertEqual(gift["total_amount"], 0)
        grants = checkout_addon_grants(self.payment.checkout_bundle_snapshot)
        self.assertEqual(grants.regular_monthly_amount, 0)
        self.assertEqual(grants.addons_amount, 0)
        self.assertEqual(grants.base_subscription_amount, 0)

    async def test_only_ready_admin_gifts_expose_the_link_in_details(self):
        self.request.match_info = {"gift_id": "8"}
        self.request.json.side_effect = lambda: self.body
        await gift_creation.admin_gift_create_route(self.request)
        with patch.object(
            gift_creation.user_dal, "get_user_by_id", AsyncMock(return_value=self.actor)
        ):
            for provider, status, has_link in (
                ("admin_gift", "ready", True),
                ("admin_gift", "activated", False),
                ("admin_gift", "revoked", False),
                ("yookassa", "ready", False),
            ):
                with self.subTest(provider=provider, status=status):
                    self.payment.provider = provider
                    self.gift.status = status
                    self.session.get.side_effect = [self.gift, self.payment]
                    response = await gift_creation.admin_gift_detail_route(self.request)
                    self.assertEqual(bool(json.loads(response.text)["gift"]["link"]), has_link)


class AdminGiftAuthorizationTests(IsolatedAsyncioTestCase):
    async def test_non_admin_cannot_access_options_or_creation_or_detail(self):
        request = MagicMock(spec=web.Request)
        request.get.return_value = 11
        with (
            patch(
                "bot.app.web.admin_api_impl.auth.get_settings",
                return_value=SimpleNamespace(ADMIN_IDS=[99]),
            ),
            patch("bot.app.web.session.extract_authenticated_user_id", return_value=10),
        ):
            for handler in (
                gift_creation.admin_gift_options_route,
                gift_creation.admin_gift_create_route,
                gift_creation.admin_gift_detail_route,
            ):
                with self.subTest(handler=handler.__name__), self.assertRaises(web.HTTPForbidden):
                    await handler(request)
