import unittest
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from bot.app.web.admin_api_impl import broadcast as broadcast_route_module
from bot.app.web.admin_api_impl import broadcast_shortcodes as broadcast_shortcodes_module
from bot.middlewares.i18n import JsonI18n
from bot.services.broadcast_personalization import (
    SHORTCODES,
    TELEGRAM_BROADCAST_ALLOWED_TAGS,
    BroadcastUserContext,
    extract_shortcodes,
    known_shortcodes,
    load_broadcast_contexts,
    render_broadcast_text,
    telegram_html_error,
    unknown_shortcodes,
)
from bot.services.email_templates_common import _telegram_html_to_email_html
from config.tariffs_config import TariffsConfig
from tests.support.settings_stub import settings_stub

REPO_ROOT = Path(__file__).resolve().parents[2]


def _i18n() -> JsonI18n:
    return JsonI18n(str(REPO_ROOT / "locales"), default="ru")


def _tariffs_config() -> TariffsConfig:
    return TariffsConfig.model_validate(
        {
            "default_tariff": "basic",
            "default_currency": "rub",
            "tariffs": [
                {
                    "key": "basic",
                    "billing_model": "period",
                    "monthly_gb": 100,
                    "names": {"ru": "Базовый", "en": "Basic"},
                    "enabled_periods": [1, 3],
                    "prices": {"rub": {"1": 100, "3": 270}},
                }
            ],
        }
    )


def _settings(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "SUBSCRIPTION_MINI_APP_URL": "https://app.example.test/",
        "DEFAULT_CURRENCY_SYMBOL": "₽",
        "tariffs_config": _tariffs_config(),
    }
    base.update(overrides)
    return settings_stub(**base)


def _full_ctx(**overrides: Any) -> BroadcastUserContext:
    values: dict[str, Any] = {
        "user_id": 42,
        "first_name": "Alice",
        "last_name": "Ng",
        "username": "alice",
        "email": "alice@example.com",
        "language_code": "en",
        "referral_code": "abc123",
        "has_active_subscription": True,
        "has_any_subscription": True,
        "end_date": datetime(2030, 5, 1, tzinfo=UTC),
        "traffic_used_bytes": 30 * 1024**3,
        "traffic_limit_bytes": 100 * 1024**3,
        "tariff_key": "basic",
        "effective_monthly_price_rub": 150.0,
        "duration_months": 1,
        "panel_user_uuid": "uuid-1",
        "install_link": "https://app.example.test/s/tok",
        "config_link": "happ://crypt4/xyz",
    }
    values.update(overrides)
    return BroadcastUserContext(**values)


class ExtractTest(unittest.TestCase):
    def test_extract_matches_ascii_identifiers_only(self):
        text = "Hi {first_name} {frist_name} {это} {User} {a1_b}"
        self.assertEqual(extract_shortcodes(text), {"first_name", "frist_name", "a1_b"})

    def test_unknown_and_known_split(self):
        text = "{first_name} and {frist_name}"
        self.assertEqual(unknown_shortcodes(text), {"frist_name"})
        self.assertEqual(known_shortcodes(text), {"first_name"})

    def test_registry_covers_every_spec(self):
        self.assertIn("config_link", SHORTCODES)
        self.assertEqual(SHORTCODES["config_link"].cost, "panel")
        self.assertEqual(SHORTCODES["first_name"].cost, "db")


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.i18n = _i18n()
        self.settings = _settings()

    def render(self, template: str, ctx: BroadcastUserContext | None, *, lang="en", escape=True):
        return render_broadcast_text(
            template,
            ctx,
            lang=lang,
            i18n=self.i18n,
            settings=self.settings,
            bot_username="demo_bot",
            escape=escape,
        )

    def test_literal_braces_and_unknown_pass_through(self):
        text = "{это текст} {frist_name}"
        self.assertEqual(self.render(text, _full_ctx()), text)

    def test_user_values_are_html_escaped(self):
        ctx = _full_ctx(first_name="<b>&x</b>")
        self.assertEqual(self.render("{first_name}", ctx), "&lt;b&gt;&amp;x&lt;/b&gt;")

    def test_subject_mode_is_not_escaped(self):
        ctx = _full_ctx(first_name="A&B")
        self.assertEqual(self.render("{first_name}", ctx, escape=False), "A&B")

    def test_core_user_fields(self):
        ctx = _full_ctx()
        self.assertEqual(self.render("{first_name}", ctx), "Alice")
        self.assertEqual(self.render("{last_name}", ctx), "Ng")
        self.assertEqual(self.render("{username}", ctx), "@alice")
        self.assertEqual(self.render("{user_id}", ctx), "42")
        self.assertEqual(self.render("{email}", ctx), "alice@example.com")

    def test_first_name_falls_back_to_username_then_localized(self):
        self.assertEqual(self.render("{first_name}", _full_ctx(first_name=None)), "alice")
        friend = self.i18n.gettext("en", "broadcast_value_friend")
        self.assertEqual(
            self.render("{first_name}", _full_ctx(first_name=None, username=None)),
            friend,
        )

    def test_subscription_fields_with_active_sub(self):
        ctx = _full_ctx()
        self.assertEqual(self.render("{end_date}", ctx), "2030-05-01")
        self.assertEqual(self.render("{tariff_name}", ctx, lang="ru"), "Базовый")
        self.assertEqual(self.render("{tariff_name}", ctx, lang="en"), "Basic")
        self.assertEqual(self.render("{tariff_price}", ctx), "150 ₽")
        self.assertEqual(self.render("{traffic_used}", ctx), "30")
        self.assertEqual(self.render("{traffic_limit}", ctx), "100")
        self.assertEqual(self.render("{traffic_left}", ctx), "70")

    def test_tariff_price_from_period_when_effective_missing(self):
        ctx = _full_ctx(effective_monthly_price_rub=None, duration_months=3)
        self.assertEqual(self.render("{tariff_price}", ctx), "270 ₽")

    def test_days_left_never_negative(self):
        ctx = _full_ctx(end_date=datetime.now(UTC) - timedelta(days=5))
        # end_date in the past but flagged active → clamps to 0
        self.assertEqual(self.render("{days_left}", ctx), "0")

    def test_unlimited_traffic(self):
        ctx = _full_ctx(traffic_limit_bytes=0)
        unlimited = self.i18n.gettext("en", "broadcast_value_unlimited")
        self.assertEqual(self.render("{traffic_limit}", ctx), unlimited)
        self.assertEqual(self.render("{traffic_left}", ctx), unlimited)

    def test_subscription_status_variants(self):
        active = self.i18n.gettext("en", "broadcast_value_status_active")
        expired = self.i18n.gettext("en", "broadcast_value_status_expired")
        none = self.i18n.gettext("en", "broadcast_value_status_none")
        self.assertEqual(self.render("{subscription_status}", _full_ctx()), active)
        self.assertEqual(
            self.render(
                "{subscription_status}",
                _full_ctx(has_active_subscription=False, has_any_subscription=True),
            ),
            expired,
        )
        self.assertEqual(
            self.render(
                "{subscription_status}",
                _full_ctx(has_active_subscription=False, has_any_subscription=False),
            ),
            none,
        )

    def test_no_active_subscription_fallbacks(self):
        ctx = _full_ctx(has_active_subscription=False)
        self.assertEqual(
            self.render("{end_date}", ctx),
            self.i18n.gettext("en", "broadcast_value_no_subscription"),
        )
        dash = self.i18n.gettext("en", "broadcast_value_dash")
        self.assertEqual(self.render("{days_left}", ctx), dash)
        self.assertEqual(self.render("{traffic_left}", ctx), dash)
        self.assertEqual(self.render("{tariff_name}", ctx), dash)

    def test_links(self):
        ctx = _full_ctx()
        self.assertEqual(self.render("{miniapp_link}", ctx), "https://app.example.test/")
        self.assertEqual(self.render("{install_link}", ctx), "https://app.example.test/s/tok")
        self.assertEqual(self.render("{config_link}", ctx), "happ://crypt4/xyz")
        self.assertEqual(self.render("{referral_code}", ctx), "abc123")
        self.assertEqual(
            self.render("{referral_bot_link}", ctx),
            "https://t.me/demo_bot?start=ref_uabc123",
        )
        self.assertEqual(
            self.render("{referral_webapp_link}", ctx),
            "https://app.example.test/?ref=uabc123",
        )

    def test_config_link_fallback_when_missing(self):
        ctx = _full_ctx(config_link=None)
        self.assertEqual(
            self.render("{config_link}", ctx),
            self.i18n.gettext("en", "broadcast_value_config_unavailable"),
        )

    def test_none_context_uses_localized_fallbacks(self):
        friend = self.i18n.gettext("ru", "broadcast_value_friend")
        self.assertEqual(self.render("{first_name}", None, lang="ru"), friend)
        self.assertEqual(self.render("{last_name}", None), "")
        self.assertEqual(self.render("{referral_bot_link}", None), "")
        self.assertEqual(self.render("{miniapp_link}", None), "https://app.example.test/")


class LintTest(unittest.TestCase):
    def test_accepts_valid_subset(self):
        for text in (
            "<b>bold</b> <i>i</i> <u>u</u> <s>s</s> <code>c</code>",
            "<pre>block</pre> <blockquote>q</blockquote>",
            '<a href="https://ok.example">link</a>',
            '<span class="tg-spoiler">x</span> <tg-spoiler>y</tg-spoiler>',
            "plain text with {shortcode} and literal { brace",
            '<a href="{config_link}">key</a>',  # shortcode href allowed pre-render
        ):
            self.assertIsNone(telegram_html_error(text), text)

    def test_rejects_unknown_tag(self):
        self.assertEqual(telegram_html_error("<p>para</p>"), "p")
        self.assertEqual(telegram_html_error("hi <br> there"), "br")

    def test_rejects_bad_href_scheme(self):
        self.assertIsNotNone(telegram_html_error('<a href="javascript:alert(1)">x</a>'))


class EmailConverterTest(unittest.TestCase):
    def test_inline_marks_map(self):
        out = _telegram_html_to_email_html("Hello <b>world</b> <i>x</i>")
        self.assertIn("<strong>world</strong>", out)
        self.assertIn("<em>x</em>", out)

    def test_anchor_http_kept_other_dropped(self):
        out = _telegram_html_to_email_html('<a href="https://e.com">L</a>')
        self.assertIn('<a href="https://e.com">L</a>', out)
        dropped = _telegram_html_to_email_html('<a href="javascript:x">bad</a>')
        self.assertNotIn("<a", dropped)
        self.assertIn("bad", dropped)

    def test_pre_and_blockquote_styled(self):
        out = _telegram_html_to_email_html("<pre>code</pre><blockquote>q</blockquote>")
        self.assertIn("<pre style=", out)
        self.assertIn("<blockquote style=", out)

    def test_unknown_tag_escaped_as_text(self):
        out = _telegram_html_to_email_html("<p>lit</p>")
        self.assertIn("&lt;p&gt;lit&lt;/p&gt;", out)

    def test_newlines_become_breaks(self):
        self.assertEqual(_telegram_html_to_email_html("a\nb"), "a<br>b")

    def test_allowed_tags_are_the_shared_set(self):
        self.assertEqual(
            set(TELEGRAM_BROADCAST_ALLOWED_TAGS),
            {"b", "i", "u", "s", "code", "a", "pre", "blockquote"},
        )


class _FakeScalars:
    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def all(self) -> list[Any]:
        return self._values


class _FakeResult:
    def __init__(self, scalars: list[Any] | None = None, rows: list[Any] | None = None) -> None:
        self._scalars = scalars or []
        self._rows = rows or []

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._scalars)

    def all(self) -> list[Any]:
        return self._rows


class _FakeSession:
    def __init__(self, results: list[_FakeResult]) -> None:
        self._results = deque(results)

    async def execute(self, *_args: Any, **_kwargs: Any) -> _FakeResult:
        return self._results.popleft()


class LoaderTest(unittest.IsolatedAsyncioTestCase):
    async def test_loads_only_requested_data(self):
        end = datetime(2030, 1, 1, tzinfo=UTC)
        user1 = SimpleNamespace(
            user_id=1,
            first_name="A",
            last_name=None,
            username="a",
            email=None,
            language_code="en",
            referral_code="r1",
        )
        user2 = SimpleNamespace(
            user_id=2,
            first_name="B",
            last_name=None,
            username="b",
            email=None,
            language_code="ru",
            referral_code="r2",
        )
        session = _FakeSession(
            [
                _FakeResult(scalars=[user1, user2]),  # users
                _FakeResult(rows=[(1, end, 10, 100, "basic", None, 1, "uuid1")]),  # active subs
                _FakeResult(scalars=[1, 2]),  # any-subscription flag
            ]
        )
        contexts = await load_broadcast_contexts(
            cast(Any, session),
            _settings(),
            [1, 2],
            {"first_name", "end_date", "subscription_status", "traffic_left"},
            None,
        )
        self.assertEqual(set(contexts), {1, 2})
        self.assertTrue(contexts[1].has_active_subscription)
        self.assertEqual(contexts[1].end_date, end)
        self.assertEqual(contexts[1].traffic_limit_bytes, 100)
        self.assertFalse(contexts[2].has_active_subscription)
        self.assertTrue(contexts[2].has_any_subscription)

    async def test_empty_when_no_known_shortcodes(self):
        session = _FakeSession([])
        contexts = await load_broadcast_contexts(
            cast(Any, session), _settings(), [1], {"frist_name"}, None
        )
        self.assertEqual(contexts, {})


class _FakeCommitSession:
    async def __aenter__(self) -> "_FakeCommitSession":
        return self

    async def __aexit__(self, *_exc: Any) -> bool:
        return False

    async def commit(self) -> None:
        return None


class _FakeCommitSessionFactory:
    def __call__(self) -> _FakeCommitSession:
        return _FakeCommitSession()


class _FakeQueue:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)


class _FakeRequest:
    def __init__(self, payload: dict[str, Any], app: dict[str, Any]) -> None:
        self._payload = payload
        self.app = app

    async def json(self) -> dict[str, Any]:
        return self._payload

    def get(self, key: str, default: Any = None) -> Any:
        return self.app.get(key, default)


def _request(payload: dict[str, Any], **app_extra: Any) -> _FakeRequest:
    app: dict[str, Any] = {
        "settings": _settings(),
        "async_session_factory": _FakeCommitSessionFactory(),
        "i18n": None,
        "bot_username": "demo_bot",
    }
    app.update(app_extra)
    return _FakeRequest(payload, app)


class AdminBroadcastPersonalizationRouteTest(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_shortcode_rejected(self):
        request = _request({"target": "all", "text": "Hi {frist_name}", "channels": ["telegram"]})
        with (
            patch.object(broadcast_route_module, "_require_admin_user_id", return_value=1),
            patch.object(broadcast_route_module, "get_queue_manager", return_value=_FakeQueue()),
        ):
            response = await broadcast_route_module.admin_broadcast_route(cast(Any, request))
        self.assertEqual(response.status, 400)

    async def test_invalid_html_rejected(self):
        request = _request({"target": "all", "text": "<p>bad</p>", "channels": ["telegram"]})
        with (
            patch.object(broadcast_route_module, "_require_admin_user_id", return_value=1),
            patch.object(broadcast_route_module, "get_queue_manager", return_value=_FakeQueue()),
        ):
            response = await broadcast_route_module.admin_broadcast_route(cast(Any, request))
        self.assertEqual(response.status, 400)

    async def test_personalized_enqueue_differs_per_recipient(self):
        request = _request(
            {"target": "all", "text": "Hi {first_name}", "channels": ["telegram", "email"]},
            settings=_settings(email_auth_configured=True),
        )
        queue = _FakeQueue()
        contexts = {
            1: _full_ctx(user_id=1, first_name="A", language_code="en"),
            2: _full_ctx(user_id=2, first_name="B", language_code="ru"),
        }
        scheduled: list[dict[str, Any]] = []

        def schedule(**kwargs: Any) -> int:
            scheduled.append(kwargs)
            return len(kwargs["recipients"])

        with (
            patch.object(broadcast_route_module, "_require_admin_user_id", return_value=999),
            patch.object(
                broadcast_route_module,
                "_resolve_audience_service",
                return_value=SimpleNamespace(resolve_user_ids=AsyncMock(return_value=[1, 2])),
            ),
            patch.object(broadcast_route_module, "get_queue_manager", return_value=queue),
            patch.object(
                broadcast_route_module,
                "load_broadcast_contexts",
                AsyncMock(return_value=contexts),
            ),
            patch.object(
                broadcast_route_module.user_dal,
                "get_telegram_recipients_for_broadcast",
                AsyncMock(return_value=[(1, 111), (2, 222)]),
            ),
            patch.object(
                broadcast_route_module.user_dal,
                "get_email_recipients_for_broadcast",
                AsyncMock(return_value=[(1, "a@x.test", "en"), (2, "b@x.test", "ru")]),
            ),
            patch.object(broadcast_route_module.message_log_dal, "create_message_log", AsyncMock()),
            patch.object(broadcast_route_module, "schedule_broadcast_emails", side_effect=schedule),
        ):
            response = await broadcast_route_module.admin_broadcast_route(cast(Any, request))

        self.assertEqual(response.status, 200)
        self.assertEqual([m["text"] for m in queue.messages], ["Hi A", "Hi B"])
        recipients = scheduled[0]["recipients"]
        self.assertEqual(recipients[0].message_text, "Hi A")
        self.assertEqual(recipients[1].message_text, "Hi B")


class BroadcastEndpointsTest(unittest.IsolatedAsyncioTestCase):
    async def test_shortcodes_endpoint_returns_registry(self):
        request = _request({}, i18n=_i18n())
        with (
            patch.object(broadcast_shortcodes_module, "_require_admin_user_id", return_value=999),
            patch.object(
                broadcast_shortcodes_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=SimpleNamespace(language_code="ru")),
            ),
        ):
            response = await broadcast_shortcodes_module.admin_broadcast_shortcodes_route(
                cast(Any, request)
            )
        import json

        payload = json.loads(response.body)
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["shortcodes"]), len(SHORTCODES))
        self.assertEqual(payload["allowed_tags"], list(TELEGRAM_BROADCAST_ALLOWED_TAGS))

    async def test_preview_render_mode(self):
        request = _request({"text": "Hi {first_name}!", "mode": "render"}, i18n=_i18n())
        ctx = {999: _full_ctx(user_id=999, first_name="A", language_code="en")}
        with (
            patch.object(broadcast_shortcodes_module, "_require_admin_user_id", return_value=999),
            patch.object(
                broadcast_shortcodes_module,
                "load_broadcast_contexts",
                AsyncMock(return_value=ctx),
            ),
        ):
            response = await broadcast_shortcodes_module.admin_broadcast_preview_route(
                cast(Any, request)
            )
        import json

        payload = json.loads(response.body)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["rendered_text"], "Hi A!")
        self.assertEqual(payload["unknown_shortcodes"], [])
        self.assertFalse(payload["sent"])


if __name__ == "__main__":
    unittest.main()
