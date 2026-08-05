"""Per-recipient personalization for admin broadcasts.

Admins compose one template that references ``{shortcode}`` tokens; this module
extracts the tokens, bulk-loads only the data those tokens need, and renders a
personalized message per recipient. Substituted values are HTML-escaped so they
are safe inside the Telegram-HTML template (an admin who wants a clickable link
writes ``<a href="{referral_bot_link}">…</a>`` themselves).

Design rules (see ``.claude/plans/broadcast-shortcodes-plan.md``):

- strict-whitelist regex substitution, never ``str.format`` (literal braces and
  format specs stay untouched);
- the loader only touches the DB/panel for the shortcodes actually present, so a
  plain broadcast with no shortcodes has zero extra overhead;
- ``config_link`` is the only panel-cost shortcode; a lookup failure degrades to
  a localized fallback and never aborts the broadcast.

Heavy dependencies (config-link encryption, install-guide tokens, DAL access)
are imported lazily inside the async loader to keep this module cheap to import
from the email converter, which only needs :data:`TELEGRAM_BROADCAST_ALLOWED_TAGS`.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from bot.middlewares.i18n import JsonI18n
    from config.settings import Settings

# ``{shortcode}`` — single-brace ASCII identifiers, consistent with the repo's
# i18n placeholder style. Anything non-matching (non-ASCII, spaces) passes
# through untouched.
_SHORTCODE_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")

Cost = Literal["db", "panel"]


@dataclass(frozen=True)
class ShortcodeSpec:
    name: str
    cost: Cost
    description_key: str


def _spec(name: str, cost: Cost) -> ShortcodeSpec:
    return ShortcodeSpec(name=name, cost=cost, description_key=f"admin_broadcast_shortcode_{name}")


# Registry — the single source of truth for validation, the UI picker and docs.
SHORTCODES: dict[str, ShortcodeSpec] = {
    spec.name: spec
    for spec in (
        _spec("first_name", "db"),
        _spec("last_name", "db"),
        _spec("username", "db"),
        _spec("user_id", "db"),
        _spec("email", "db"),
        _spec("end_date", "db"),
        _spec("days_left", "db"),
        _spec("subscription_status", "db"),
        _spec("tariff_name", "db"),
        _spec("tariff_price", "db"),
        _spec("traffic_used", "db"),
        _spec("traffic_limit", "db"),
        _spec("traffic_left", "db"),
        _spec("install_link", "db"),
        _spec("miniapp_link", "db"),
        _spec("config_link", "panel"),
        _spec("referral_code", "db"),
        _spec("referral_bot_link", "db"),
        _spec("referral_webapp_link", "db"),
    )
}

# Editor ∩ email intersection: the tags both Telegram and the email converter
# render. Reused by the HTML lint, the email whitelist and the shortcodes
# endpoint so the frontend editor schema consumes exactly this list.
TELEGRAM_BROADCAST_ALLOWED_TAGS: tuple[str, ...] = (
    "b",
    "i",
    "u",
    "s",
    "code",
    "a",
    "pre",
    "blockquote",
)

# The lint accepts everything Telegram itself parses (plus tag aliases) so
# hand-typed valid Telegram HTML is not rejected; unknown tags fail loudly.
_TELEGRAM_HTML_LINT_TAGS: frozenset[str] = frozenset(
    {
        "a",
        "b",
        "strong",
        "i",
        "em",
        "u",
        "ins",
        "s",
        "strike",
        "del",
        "span",
        "tg-spoiler",
        "code",
        "pre",
        "blockquote",
        "tg-emoji",
    }
)
_ALLOWED_HREF_SCHEMES = ("http://", "https://", "tg://", "mailto:")

# Shortcode groupings — decide what the loader must fetch.
_ACTIVE_SUB_SHORTCODES = frozenset(
    {
        "end_date",
        "days_left",
        "subscription_status",
        "tariff_name",
        "tariff_price",
        "traffic_used",
        "traffic_limit",
        "traffic_left",
    }
)
_REFERRAL_CODE_SHORTCODES = frozenset(
    {"referral_code", "referral_bot_link", "referral_webapp_link"}
)
_CONFIG_LINK = "config_link"
_INSTALL_LINK = "install_link"

_CHUNK_SIZE = 900
_PANEL_LOOKUP_CONCURRENCY = 10


def extract_shortcodes(text: str) -> set[str]:
    """All ``{identifier}`` tokens present, whether or not they are known."""
    return {match.group(1) for match in _SHORTCODE_RE.finditer(text or "")}


def unknown_shortcodes(text: str) -> set[str]:
    """Identifier tokens that are not part of the registry (admin typos)."""
    return extract_shortcodes(text) - set(SHORTCODES)


def known_shortcodes(text: str) -> set[str]:
    return extract_shortcodes(text) & set(SHORTCODES)


@dataclass
class BroadcastUserContext:
    """Prefetched scalars for one recipient — no ORM objects, no lazy loads."""

    user_id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    email: str | None = None
    language_code: str | None = None
    referral_code: str | None = None
    has_active_subscription: bool = False
    has_any_subscription: bool = False
    end_date: datetime | None = None
    traffic_used_bytes: int | None = None
    traffic_limit_bytes: int | None = None
    tariff_key: str | None = None
    effective_monthly_price_rub: float | None = None
    duration_months: int | None = None
    panel_user_uuid: str | None = None
    install_link: str | None = None
    config_link: str | None = None


@dataclass
class _ActiveSubRow:
    end_date: datetime | None
    traffic_used_bytes: int | None
    traffic_limit_bytes: int | None
    tariff_key: str | None
    effective_monthly_price_rub: float | None
    duration_months: int | None
    panel_user_uuid: str | None


def _chunked(values: list[int], size: int = _CHUNK_SIZE) -> list[list[int]]:
    return [values[start : start + size] for start in range(0, len(values), size)]


async def load_broadcast_contexts(
    session: AsyncSession,
    settings: Settings,
    user_ids: list[int],
    needed: set[str],
    panel_service: Any | None,
) -> dict[int, BroadcastUserContext]:
    """Build a ``user_id -> BroadcastUserContext`` map for the shortcodes in use.

    Only the data required by ``needed`` is fetched. Token/code-minting
    shortcodes (``install_link``, referral links) write missing values into the
    supplied session; commit happens with the surrounding route session.
    """
    known = needed & set(SHORTCODES)
    normalized_ids = [int(uid) for uid in dict.fromkeys(user_ids)]
    if not known or not normalized_ids:
        return {}

    from sqlalchemy import select

    from db.models import User  # local import keeps module import light

    contexts: dict[int, BroadcastUserContext] = {}
    users_by_id: dict[int, Any] = {}

    for chunk in _chunked(normalized_ids):
        result = await session.execute(select(User).where(User.user_id.in_(chunk)))
        for row_user in result.scalars().all():
            # Legacy ``Column`` declarations type ORM attrs as ``Column[T]``; read
            # the instance as ``Any`` (repo convention) to fill plain scalars.
            user: Any = row_user
            uid = int(user.user_id)
            users_by_id[uid] = user
            contexts[uid] = BroadcastUserContext(
                user_id=uid,
                first_name=user.first_name,
                last_name=user.last_name,
                username=user.username,
                email=user.email,
                language_code=user.language_code,
                referral_code=user.referral_code,
            )

    need_active = (
        bool(known & _ACTIVE_SUB_SHORTCODES) or _INSTALL_LINK in known or _CONFIG_LINK in known
    )
    if need_active:
        active_by_user = await _load_latest_active_subscriptions(session, normalized_ids)
        for uid, row in active_by_user.items():
            ctx = contexts.get(uid)
            if ctx is None:
                continue
            ctx.has_active_subscription = True
            ctx.has_any_subscription = True
            ctx.end_date = row.end_date
            ctx.traffic_used_bytes = row.traffic_used_bytes
            ctx.traffic_limit_bytes = row.traffic_limit_bytes
            ctx.tariff_key = row.tariff_key
            ctx.effective_monthly_price_rub = row.effective_monthly_price_rub
            ctx.duration_months = row.duration_months
            ctx.panel_user_uuid = row.panel_user_uuid

    if "subscription_status" in known:
        users_with_sub = await _load_users_with_any_subscription(session, normalized_ids)
        for uid in users_with_sub:
            ctx = contexts.get(uid)
            if ctx is not None:
                ctx.has_any_subscription = True

    if known & _REFERRAL_CODE_SHORTCODES:
        await _ensure_referral_codes(session, contexts, users_by_id)

    if _INSTALL_LINK in known:
        await _load_install_links(session, settings, contexts)

    if _CONFIG_LINK in known and panel_service is not None:
        await _load_config_links(settings, panel_service, contexts)

    return contexts


async def _load_latest_active_subscriptions(
    session: AsyncSession,
    user_ids: list[int],
) -> dict[int, _ActiveSubRow]:
    """Latest active subscription per user (portable reduce-in-Python).

    ``DISTINCT ON`` is Postgres-only; local test runs may use SQLite, so we
    order by ``end_date desc`` and keep the first row seen per user.
    """
    from sqlalchemy import select

    from db.models import Subscription

    now = datetime.now(UTC)
    latest: dict[int, _ActiveSubRow] = {}
    for chunk in _chunked(user_ids):
        stmt = (
            select(
                Subscription.user_id,
                Subscription.end_date,
                Subscription.traffic_used_bytes,
                Subscription.traffic_limit_bytes,
                Subscription.tariff_key,
                Subscription.effective_monthly_price_rub,
                Subscription.duration_months,
                Subscription.panel_user_uuid,
            )
            .where(
                Subscription.user_id.in_(chunk),
                Subscription.is_active == True,
                Subscription.end_date > now,
            )
            .order_by(Subscription.user_id.asc(), Subscription.end_date.desc())
        )
        result = await session.execute(stmt)
        for row in result.all():
            uid = int(row[0])
            if uid in latest:
                continue
            latest[uid] = _ActiveSubRow(
                end_date=row[1],
                traffic_used_bytes=int(row[2]) if row[2] is not None else None,
                traffic_limit_bytes=int(row[3]) if row[3] is not None else None,
                tariff_key=row[4],
                effective_monthly_price_rub=float(row[5]) if row[5] is not None else None,
                duration_months=int(row[6]) if row[6] is not None else None,
                panel_user_uuid=str(row[7]).strip() if row[7] else None,
            )
    return latest


async def _load_users_with_any_subscription(
    session: AsyncSession,
    user_ids: list[int],
) -> set[int]:
    from sqlalchemy import select

    from db.models import Subscription

    found: set[int] = set()
    for chunk in _chunked(user_ids):
        stmt = select(Subscription.user_id).where(Subscription.user_id.in_(chunk)).distinct()
        result = await session.execute(stmt)
        found.update(int(uid) for uid in result.scalars().all())
    return found


async def _ensure_referral_codes(
    session: AsyncSession,
    contexts: dict[int, BroadcastUserContext],
    users_by_id: dict[int, Any],
) -> None:
    from db.dal import user_dal

    for uid, ctx in contexts.items():
        if ctx.referral_code:
            continue
        user = users_by_id.get(uid)
        if user is None:
            continue
        try:
            code = await user_dal.ensure_referral_code(session, user)
        except Exception:
            continue
        ctx.referral_code = code or None


async def _load_install_links(
    session: AsyncSession,
    settings: Settings,
    contexts: dict[int, BroadcastUserContext],
) -> None:
    from bot.utils.install_links import ensure_user_install_guide_share_url

    for ctx in contexts.values():
        if not ctx.has_active_subscription:
            continue
        ctx.install_link = await ensure_user_install_guide_share_url(
            session,
            settings,
            ctx.user_id,
            ctx.panel_user_uuid,
        )


async def _load_config_links(
    settings: Settings,
    panel_service: Any,
    contexts: dict[int, BroadcastUserContext],
) -> None:
    import asyncio

    from bot.utils.config_link import prepare_config_links

    uuids = list(
        dict.fromkeys(
            ctx.panel_user_uuid
            for ctx in contexts.values()
            if ctx.has_active_subscription and ctx.panel_user_uuid
        )
    )
    if not uuids:
        return

    semaphore = asyncio.Semaphore(_PANEL_LOOKUP_CONCURRENCY)

    async def resolve(panel_uuid: str) -> str | None:
        async with semaphore:
            try:
                panel_user = await panel_service.get_user_by_uuid(panel_uuid)
            except Exception:
                return None
            raw_link = ""
            if isinstance(panel_user, dict):
                raw_link = str(panel_user.get("subscriptionUrl") or "").strip()
            if not raw_link:
                return None
            try:
                display_link, _ = await prepare_config_links(settings, raw_link)
            except Exception:
                return None
            return display_link

    resolved = dict(
        zip(uuids, await asyncio.gather(*(resolve(uuid) for uuid in uuids)), strict=True)
    )
    for ctx in contexts.values():
        if ctx.panel_user_uuid:
            ctx.config_link = resolved.get(ctx.panel_user_uuid)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def _fmt_gb(bytes_value: int | None) -> str:
    gb = float(bytes_value or 0) / (1024**3)
    return str(int(gb)) if gb.is_integer() else f"{gb:.2f}"


def _fmt_amount(amount: float) -> str:
    rounded = round(float(amount), 2)
    return f"{int(rounded)}" if rounded.is_integer() else f"{rounded:.2f}"


def _tariff_price_value(
    ctx: BroadcastUserContext,
    settings: Settings,
    dash: str,
) -> str:
    from config.tariffs_config import default_currency_key_for_settings

    price: float | None = ctx.effective_monthly_price_rub
    if price is None and ctx.tariff_key:
        tariffs_config = settings.tariffs_config
        try:
            tariff = tariffs_config.get(ctx.tariff_key) if tariffs_config else None
        except Exception:
            tariff = None
        if tariff is not None and ctx.duration_months:
            currency_key = default_currency_key_for_settings(settings)
            price = tariff.period_price(ctx.duration_months, currency_key)
    if price is None:
        return dash
    symbol = str(settings.DEFAULT_CURRENCY_SYMBOL or "").strip()
    return f"{_fmt_amount(price)} {symbol}".strip()


def _tariff_name_value(ctx: BroadcastUserContext, settings: Settings, lang: str, dash: str) -> str:
    if not ctx.tariff_key:
        return dash
    tariffs_config = settings.tariffs_config
    try:
        tariff = tariffs_config.get(ctx.tariff_key) if tariffs_config else None
    except Exception:
        tariff = None
    if tariff is None:
        return ctx.tariff_key
    return tariff.name(lang)


def _resolve_value(
    name: str,
    ctx: BroadcastUserContext | None,
    *,
    lang: str,
    i18n: JsonI18n | None,
    settings: Settings,
    bot_username: str,
) -> str:
    from bot.utils.referral_links import build_bot_referral_link, build_webapp_referral_link

    def t(key: str) -> str:
        return i18n.gettext(lang, key) if i18n is not None else key

    dash = t("broadcast_value_dash")
    mini_app_url = str(settings.SUBSCRIPTION_MINI_APP_URL or "").strip()

    if name == "miniapp_link":
        return mini_app_url

    if ctx is None:
        # Raw-id "admins" test target: no local user row → localized fallbacks.
        if name == "first_name":
            return t("broadcast_value_friend")
        if name == "subscription_status":
            return t("broadcast_value_status_none")
        if name == "end_date":
            return t("broadcast_value_no_subscription")
        if name == "config_link":
            return t("broadcast_value_config_unavailable")
        _empty_without_user = _REFERRAL_CODE_SHORTCODES | {
            "last_name",
            "username",
            "user_id",
            "email",
        }
        return "" if name in _empty_without_user else dash

    if name == "first_name":
        return ctx.first_name or ctx.username or t("broadcast_value_friend")
    if name == "last_name":
        return ctx.last_name or ""
    if name == "username":
        return f"@{ctx.username}" if ctx.username else ""
    if name == "user_id":
        return str(ctx.user_id)
    if name == "email":
        return ctx.email or ""
    if name == "referral_code":
        return ctx.referral_code or ""
    if name == "referral_bot_link":
        return build_bot_referral_link(bot_username, ctx.referral_code) or ""
    if name == "referral_webapp_link":
        return build_webapp_referral_link(mini_app_url, ctx.referral_code) or ""
    if name == "install_link":
        return ctx.install_link or dash
    if name == "config_link":
        return ctx.config_link or t("broadcast_value_config_unavailable")

    if name == "subscription_status":
        if ctx.has_active_subscription:
            return t("broadcast_value_status_active")
        if ctx.has_any_subscription:
            return t("broadcast_value_status_expired")
        return t("broadcast_value_status_none")

    # Remaining shortcodes describe the active subscription; without one they
    # render a localized fallback.
    if not ctx.has_active_subscription:
        if name == "end_date":
            return t("broadcast_value_no_subscription")
        return dash

    if name == "end_date":
        return _fmt_date(ctx.end_date) or t("broadcast_value_no_subscription")
    if name == "days_left":
        return str(_days_left(ctx.end_date))
    if name == "tariff_name":
        return _tariff_name_value(ctx, settings, lang, dash)
    if name == "tariff_price":
        return _tariff_price_value(ctx, settings, dash)
    if name == "traffic_used":
        return _fmt_gb(ctx.traffic_used_bytes)
    if name == "traffic_limit":
        if not ctx.traffic_limit_bytes or ctx.traffic_limit_bytes <= 0:
            return t("broadcast_value_unlimited")
        return _fmt_gb(ctx.traffic_limit_bytes)
    if name == "traffic_left":
        if not ctx.traffic_limit_bytes or ctx.traffic_limit_bytes <= 0:
            return t("broadcast_value_unlimited")
        left = max(0, int(ctx.traffic_limit_bytes) - int(ctx.traffic_used_bytes or 0))
        return _fmt_gb(left)
    return dash


def _fmt_date(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d")


def _days_left(end_date: datetime | None) -> int:
    if end_date is None:
        return 0
    now = datetime.now(UTC)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=UTC)
    return max(0, (end_date - now).days)


def render_broadcast_text(
    template: str,
    ctx: BroadcastUserContext | None,
    *,
    lang: str,
    i18n: JsonI18n | None,
    settings: Settings,
    bot_username: str = "",
    escape: bool = True,
) -> str:
    """Substitute known shortcodes; unknown tokens and literal braces pass through.

    ``escape=True`` (Telegram/email HTML body) HTML-escapes every value;
    ``escape=False`` (email subject — plain text, not HTML) inserts raw values.
    """

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in SHORTCODES:
            return match.group(0)
        value = _resolve_value(
            name,
            ctx,
            lang=lang,
            i18n=i18n,
            settings=settings,
            bot_username=bot_username,
        )
        return html.escape(value) if escape else value

    return _SHORTCODE_RE.sub(replace, template or "")


# --------------------------------------------------------------------------- #
# Telegram-HTML lint
# --------------------------------------------------------------------------- #


class _TelegramHtmlLinter(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.error: str | None = None

    def _fail(self, message: str) -> None:
        if self.error is None:
            self.error = message

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _TELEGRAM_HTML_LINT_TAGS:
            self._fail(tag)
            return
        if tag == "a":
            href = next((value for key, value in attrs if key == "href"), None)
            if href and "{" not in href:
                lowered = href.strip().lower()
                if not lowered.startswith(_ALLOWED_HREF_SCHEMES):
                    self._fail(f"a[href={href}]")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag not in _TELEGRAM_HTML_LINT_TAGS:
            self._fail(tag)


def telegram_html_error(text: str) -> str | None:
    """Return an offending-tag detail if ``text`` uses tags Telegram rejects.

    Advisory-strict: unknown tags and non-``http(s)``/``tg`` literal ``<a href>``
    schemes fail; nesting mistakes are left to Telegram's own parser.
    """
    linter = _TelegramHtmlLinter()
    try:
        linter.feed(str(text or ""))
        linter.close()
    except Exception:
        return None
    return linter.error


__all__ = [
    "SHORTCODES",
    "TELEGRAM_BROADCAST_ALLOWED_TAGS",
    "BroadcastUserContext",
    "ShortcodeSpec",
    "extract_shortcodes",
    "known_shortcodes",
    "load_broadcast_contexts",
    "render_broadcast_text",
    "telegram_html_error",
    "unknown_shortcodes",
]
