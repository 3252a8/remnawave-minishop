import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiohttp import ClientSession, ClientTimeout, web
from aiogram import Bot, Dispatcher
from aiogram.types import LabeledPrice
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.webapp_auth import (
    create_webapp_session_token,
    validate_telegram_login_widget_data,
    validate_telegram_webapp_init_data,
    verify_webapp_session_token,
)
from bot.services.crypto_pay_service import CryptoPayService
from bot.services.email_auth_service import EmailAuthService, normalize_email
from bot.services.freekassa_service import FreeKassaService
from bot.services.platega_service import PlategaService
from bot.services.promo_code_service import PromoCodeService
from bot.services.referral_service import ReferralService
from bot.services.severpay_service import SeverPayService
from bot.services.subscription_service import SubscriptionService
from bot.services.yookassa_service import YooKassaService
from bot.utils.text_sanitizer import sanitize_display_name, sanitize_username
from config.settings import Settings
from db.dal import payment_dal, subscription_dal, user_dal
from db.dal.user_dal import UserMergeConflictError
from db.models import Payment, User

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "subscription_webapp.html"
ASSET_DIR = TEMPLATE_PATH.parent
TELEGRAM_WEB_APP_SDK_URL = "https://telegram.org/js/telegram-web-app.js"
TELEGRAM_WEB_APP_SDK_PATH = ASSET_DIR / "telegram-web-app.js"
TELEGRAM_WIDGET_SDK_URL = "https://telegram.org/js/telegram-widget.js?23"
TELEGRAM_WIDGET_SDK_PATH = ASSET_DIR / "telegram-widget.js"
_UNPATCHED_WIDGET_ORIGIN_SNIPPET = """    if (origin == 'https://telegram.org') {\n      origin = default_origin;\n    } else if (origin == 'https://telegram-js.azureedge.net' || origin == 'https://tg.dev') {\n      origin = dev_origin;\n    }\n"""
_PATCHED_WIDGET_ORIGIN_SNIPPET = """    if (origin == 'https://telegram.org') {\n      origin = default_origin;\n    } else if (origin == 'https://telegram-js.azureedge.net' || origin == 'https://tg.dev') {\n      origin = dev_origin;\n    } else {\n      origin = default_origin;\n    }\n"""
WEBAPP_CONFIG_PLACEHOLDER = "<!-- WEBAPP_CONFIG_SCRIPT -->"
DEV_MOCK_START_MARKER = "<!-- WEBAPP_DEV_MOCK_START -->"
DEV_MOCK_END_MARKER = "<!-- WEBAPP_DEV_MOCK_END -->"


def create_subscription_webapp_application(
    dp: Dispatcher,
    bot: Bot,
    settings: Settings,
    async_session_factory: sessionmaker,
) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app["dp"] = dp
    app["settings"] = settings
    app["async_session_factory"] = async_session_factory
    app["i18n"] = dp.get("i18n_instance")
    app["email_auth_service"] = EmailAuthService(settings)

    for key in (
        "subscription_service",
        "yookassa_service",
        "freekassa_service",
        "cryptopay_service",
        "platega_service",
        "severpay_service",
        "promo_code_service",
        "referral_service",
    ):
        if hasattr(dp, "workflow_data") and key in dp.workflow_data:  # type: ignore[attr-defined]
            app[key] = dp.workflow_data[key]  # type: ignore[index]

    if hasattr(dp, "workflow_data") and "bot_username" in dp.workflow_data:  # type: ignore[attr-defined]
        app["bot_username"] = dp.workflow_data["bot_username"]  # type: ignore[index]

    setup_subscription_webapp_routes(app)
    return app


def setup_subscription_webapp_routes(app: web.Application) -> None:
    app.router.add_get("/", index_route)
    app.router.add_get("/health", health_route)
    app.router.add_get("/telegram-web-app.js", telegram_web_app_asset_route)
    app.router.add_get("/telegram-widget.js", telegram_widget_asset_route)
    app.router.add_get("/subscription_webapp.css", css_asset_route)
    app.router.add_get("/subscription_webapp.js", js_asset_route)
    app.router.add_post("/api/auth/token", auth_token_route)
    app.router.add_post("/api/auth/email/request", email_auth_request_route)
    app.router.add_post("/api/auth/email/verify", email_auth_verify_route)
    app.router.add_get("/api/me", me_route)
    app.router.add_post("/api/account/email/request", account_email_request_route)
    app.router.add_post("/api/account/email/verify", account_email_verify_route)
    app.router.add_post("/api/account/telegram/link", account_telegram_link_route)
    app.router.add_post("/api/promo/apply", apply_promo_route)
    app.router.add_post("/api/payments", create_payment_route)
    app.router.add_get("/api/payments/{payment_id}", payment_status_route)


async def health_route(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def css_asset_route(request: web.Request) -> web.Response:
    return await _serve_template_asset(request, "subscription_webapp.css", "text/css")


async def telegram_web_app_asset_route(request: web.Request) -> web.Response:
    if not TELEGRAM_WEB_APP_SDK_PATH.exists():
        await refresh_telegram_web_app_sdk()

    try:
        response = await _serve_template_asset(
            request,
            "telegram-web-app.js",
            "application/javascript",
        )
    except FileNotFoundError:
        logger.exception(
            "Telegram Web App SDK is unavailable at %s",
            TELEGRAM_WEB_APP_SDK_PATH,
        )
        raise web.HTTPServiceUnavailable(text="telegram_web_app_sdk_unavailable")

    response.headers["Cache-Control"] = "no-cache"
    return response


async def telegram_widget_asset_route(request: web.Request) -> web.Response:
    if not TELEGRAM_WIDGET_SDK_PATH.exists():
        await refresh_telegram_login_widget_sdk()

    try:
        data = TELEGRAM_WIDGET_SDK_PATH.read_bytes()
    except FileNotFoundError:
        logger.exception(
            "Telegram Login Widget SDK is unavailable at %s",
            TELEGRAM_WIDGET_SDK_PATH,
        )
        raise web.HTTPServiceUnavailable(text="telegram_widget_sdk_unavailable")

    data = _normalize_telegram_login_widget_sdk(data)
    response = web.Response(body=data, content_type="application/javascript")
    response.headers["Cache-Control"] = "no-cache"
    return response


async def refresh_telegram_web_app_sdk() -> bool:
    """Best-effort refresh of the vendored Telegram Web App SDK."""
    try:
        timeout = ClientTimeout(total=30)
        async with ClientSession(
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/javascript,text/javascript,*/*;q=0.8",
            },
        ) as session:
            async with session.get(TELEGRAM_WEB_APP_SDK_URL) as response:
                if response.status != 200:
                    logger.warning(
                        "Telegram Web App SDK refresh returned HTTP %s; keeping the bundled copy.",
                        response.status,
                    )
                    return False
                data = await response.read()
    except Exception as exc:
        logger.warning("Failed to refresh Telegram Web App SDK: %s", exc)
        return False

    try:
        TELEGRAM_WEB_APP_SDK_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing_data = (
            TELEGRAM_WEB_APP_SDK_PATH.read_bytes()
            if TELEGRAM_WEB_APP_SDK_PATH.exists()
            else None
        )
        if existing_data == data:
            logger.info("Telegram Web App SDK is already up to date.")
            return True

        temp_path = TELEGRAM_WEB_APP_SDK_PATH.with_name(
            f"{TELEGRAM_WEB_APP_SDK_PATH.name}.tmp"
        )
        temp_path.write_bytes(data)
        temp_path.replace(TELEGRAM_WEB_APP_SDK_PATH)
        logger.info(
            "Telegram Web App SDK updated at %s (%d bytes).",
            TELEGRAM_WEB_APP_SDK_PATH,
            len(data),
        )
        return True
    except Exception as exc:
        logger.warning("Failed to store Telegram Web App SDK locally: %s", exc)
        return False


async def refresh_telegram_login_widget_sdk() -> bool:
    """Best-effort refresh of the vendored Telegram Login Widget SDK."""
    try:
        timeout = ClientTimeout(total=30)
        async with ClientSession(
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/javascript,text/javascript,*/*;q=0.8",
            },
        ) as session:
            async with session.get(TELEGRAM_WIDGET_SDK_URL) as response:
                if response.status != 200:
                    logger.warning(
                        "Telegram Login Widget SDK refresh returned HTTP %s; keeping the bundled copy.",
                        response.status,
                    )
                    return False
        data = await response.read()
    except Exception as exc:
        logger.warning("Failed to refresh Telegram Login Widget SDK: %s", exc)
        return False

    try:
        data = _normalize_telegram_login_widget_sdk(data)
        TELEGRAM_WIDGET_SDK_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing_data = (
            TELEGRAM_WIDGET_SDK_PATH.read_bytes()
            if TELEGRAM_WIDGET_SDK_PATH.exists()
            else None
        )
        if existing_data == data:
            logger.info("Telegram Login Widget SDK is already up to date.")
            return True

        temp_path = TELEGRAM_WIDGET_SDK_PATH.with_name(
            f"{TELEGRAM_WIDGET_SDK_PATH.name}.tmp"
        )
        temp_path.write_bytes(data)
        temp_path.replace(TELEGRAM_WIDGET_SDK_PATH)
        logger.info(
            "Telegram Login Widget SDK updated at %s (%d bytes).",
            TELEGRAM_WIDGET_SDK_PATH,
            len(data),
        )
        return True
    except Exception as exc:
        logger.warning("Failed to store Telegram Login Widget SDK locally: %s", exc)
        return False


def _normalize_telegram_login_widget_sdk(data: bytes) -> bytes:
    # Keep the vendored widget pointing to Telegram's OAuth host instead of the local origin.
    text = data.decode("utf-8")
    normalized = text.replace(
        _UNPATCHED_WIDGET_ORIGIN_SNIPPET,
        _PATCHED_WIDGET_ORIGIN_SNIPPET,
        1,
    )
    return normalized.encode("utf-8")


async def js_asset_route(request: web.Request) -> web.Response:
    return await _serve_template_asset(
        request,
        "subscription_webapp.js",
        "application/javascript",
        strip_dev_mock=True,
    )


async def index_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    if not settings.WEBAPP_ENABLED:
        raise web.HTTPNotFound(text="webapp_disabled")

    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    config = {
        "title": settings.WEBAPP_TITLE,
        "primaryColor": settings.WEBAPP_PRIMARY_COLOR,
        "logoUrl": settings.WEBAPP_LOGO_URL or "",
        "apiBase": "/api",
        "telegramLoginBotUsername": request.app.get("bot_username") or "",
        "supportUrl": settings.SUPPORT_LINK or "",
        "privacyPolicyUrl": settings.PRIVACY_POLICY_URL or "",
        "userAgreementUrl": settings.USER_AGREEMENT_URL or "",
        "currency": settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
        "language": _normalize_language(settings.DEFAULT_LANGUAGE),
        "emailAuthEnabled": settings.email_auth_configured,
    }
    html = _strip_marked_block(html, DEV_MOCK_START_MARKER, DEV_MOCK_END_MARKER)
    html = html.replace(
        WEBAPP_CONFIG_PLACEHOLDER,
        (
            "<script>window.__WEBAPP_CONFIG__="
            + json.dumps(config, ensure_ascii=False, separators=(",", ":"))
            + ";</script>"
        ),
    )
    return web.Response(text=html, content_type="text/html", charset="utf-8")


async def _serve_template_asset(
    request: web.Request,
    filename: str,
    content_type: str,
    *,
    strip_dev_mock: bool = False,
) -> web.Response:
    settings: Settings = request.app["settings"]
    if not settings.WEBAPP_ENABLED:
        raise web.HTTPNotFound(text="webapp_disabled")

    path = ASSET_DIR / filename
    text = path.read_text(encoding="utf-8")
    if strip_dev_mock:
        text = _strip_marked_block(
            text,
            "/* WEBAPP_DEV_MOCK_START */",
            "/* WEBAPP_DEV_MOCK_END */",
        )
    return web.Response(text=text, content_type=content_type, charset="utf-8")


def _strip_marked_block(html: str, start_marker: str, end_marker: str) -> str:
    start = html.find(start_marker)
    if start == -1:
        return html
    end = html.find(end_marker, start)
    if end == -1:
        return html[:start]
    return html[:start] + html[end + len(end_marker):]


async def auth_token_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)
    init_data = str(payload.get("init_data") or "")
    auth_data = payload.get("auth_data")
    referral_param = str(payload.get("referral_code") or payload.get("start_param") or "")
    telegram_user = None
    if init_data:
        telegram_user = validate_telegram_webapp_init_data(
            init_data,
            settings.BOT_TOKEN,
            max_age_seconds=settings.WEBAPP_AUTH_MAX_AGE_SECONDS,
        )
    elif auth_data is not None:
        telegram_user = validate_telegram_login_widget_data(
            auth_data,
            settings.BOT_TOKEN,
            max_age_seconds=settings.WEBAPP_AUTH_MAX_AGE_SECONDS,
        )

    if not telegram_user:
        return _json_error(401, "invalid_auth", "Invalid Telegram auth data")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    authenticated_user_id: Optional[int] = None
    async with async_session_factory() as session:
        try:
            db_user = await _ensure_user_from_telegram(
                session,
                telegram_user,
                settings,
                referral_param=referral_param,
            )
            if db_user.is_banned:
                await session.rollback()
                return _json_error(403, "banned", "Access denied")
            referral_applied = await _apply_referral_to_existing_user(
                request,
                session,
                db_user,
                referral_param or telegram_user.get("start_param"),
            )
            if getattr(db_user, "_webapp_created", False) or referral_applied:
                await _apply_referral_welcome_bonus_if_needed(
                    request,
                    session,
                    db_user,
                    referral_param or telegram_user.get("start_param"),
                )
            authenticated_user_id = int(db_user.user_id)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error("WebApp auth failed: %s", exc, exc_info=True)
            return _json_error(500, "auth_failed", "Auth failed")

    token = create_webapp_session_token(settings, int(authenticated_user_id))
    return web.json_response({"ok": True, "token": token})


async def email_auth_request_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)
    email = normalize_email(str(payload.get("email") or ""))
    lang = _normalize_language(str(payload.get("language") or settings.DEFAULT_LANGUAGE))
    return await _request_email_code(
        request,
        email=email,
        purpose="login",
        language_code=lang,
        target_user_id=None,
    )


async def email_auth_verify_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)
    email = normalize_email(str(payload.get("email") or ""))
    code = str(payload.get("code") or "")
    referral_param = str(payload.get("referral_code") or payload.get("start_param") or "")
    email_service: EmailAuthService = request.app["email_auth_service"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]

    async with async_session_factory() as session:
        try:
            verify_result = await email_service.verify_code(
                session,
                email=email,
                purpose="login",
                code=code,
                target_user_id=None,
            )
            if not verify_result.ok:
                await session.rollback()
                return _json_error(400, verify_result.error or "invalid_code", "Invalid code")

            db_user = await user_dal.get_user_by_email(session, email)
            created_user = False
            if not db_user:
                referred_by_id = await _resolve_referrer_id(
                    session,
                    referral_param,
                    current_user_id=None,
                )
                db_user, _ = await user_dal.create_email_user(
                    session,
                    email=email,
                    language_code=_normalize_language(settings.DEFAULT_LANGUAGE),
                    email_verified_at=datetime.now(timezone.utc),
                    referred_by_id=referred_by_id,
                )
                created_user = True
            elif not db_user.email_verified_at:
                db_user.email_verified_at = datetime.now(timezone.utc)

            referral_applied = await _apply_referral_to_existing_user(
                request,
                session,
                db_user,
                referral_param,
            )
            if created_user or referral_applied:
                await _apply_referral_welcome_bonus_if_needed(
                    request,
                    session,
                    db_user,
                    referral_param,
                )

            if db_user.is_banned:
                await session.rollback()
                return _json_error(403, "banned", "Access denied")

            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error("Email WebApp auth failed: %s", exc, exc_info=True)
            return _json_error(500, "auth_failed", "Auth failed")

    token = create_webapp_session_token(settings, int(db_user.user_id))
    return web.json_response(
        {
            "ok": True,
            "token": token,
            "user_id": int(db_user.user_id),
            "telegram_id": _telegram_id_for_user(db_user),
        }
    )


async def account_email_request_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)
    email = normalize_email(str(payload.get("email") or ""))
    async_session_factory: sessionmaker = request.app["async_session_factory"]

    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        if db_user.email == email and db_user.email_verified_at:
            return web.json_response({"ok": True, "already_linked": True})
        lang = _normalize_language(db_user.language_code or settings.DEFAULT_LANGUAGE)

    return await _request_email_code(
        request,
        email=email,
        purpose="link_email",
        language_code=lang,
        target_user_id=user_id,
    )


async def account_email_verify_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    payload = await _read_json(request)
    email = normalize_email(str(payload.get("email") or ""))
    code = str(payload.get("code") or "")
    email_service: EmailAuthService = request.app["email_auth_service"]
    settings: Settings = request.app["settings"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]

    async with async_session_factory() as session:
        try:
            verify_result = await email_service.verify_code(
                session,
                email=email,
                purpose="link_email",
                code=code,
                target_user_id=user_id,
            )
            if not verify_result.ok:
                await session.rollback()
                return _json_error(400, verify_result.error or "invalid_code", "Invalid code")

            current_user = await user_dal.get_user_by_id(session, user_id)
            if not current_user or current_user.is_banned:
                await session.rollback()
                return _json_error(403, "access_denied", "Access denied")

            existing_email_user = await user_dal.get_user_by_email(session, email)
            if existing_email_user and existing_email_user.user_id != current_user.user_id:
                current_user = await user_dal.merge_users(
                    session,
                    source_user_id=existing_email_user.user_id,
                    target_user_id=current_user.user_id,
                )
            current_user.email = email
            current_user.email_verified_at = datetime.now(timezone.utc)
            await _sync_panel_identity_for_user(request, current_user)
            await session.commit()
        except UserMergeConflictError as exc:
            await session.rollback()
            return _json_error(409, "account_merge_conflict", str(exc))
        except Exception as exc:
            await session.rollback()
            logger.error("Email account link failed: %s", exc, exc_info=True)
            return _json_error(500, "link_failed", "Link failed")

    token = create_webapp_session_token(settings, int(current_user.user_id))
    return web.json_response({"ok": True, "token": token})


async def account_telegram_link_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)
    init_data = str(payload.get("init_data") or "")
    auth_data = payload.get("auth_data")
    telegram_user = None
    if init_data:
        telegram_user = validate_telegram_webapp_init_data(
            init_data,
            settings.BOT_TOKEN,
            max_age_seconds=settings.WEBAPP_AUTH_MAX_AGE_SECONDS,
        )
    elif auth_data is not None:
        telegram_user = validate_telegram_login_widget_data(
            auth_data,
            settings.BOT_TOKEN,
            max_age_seconds=settings.WEBAPP_AUTH_MAX_AGE_SECONDS,
        )
    if not telegram_user:
        return _json_error(401, "invalid_auth", "Invalid Telegram auth data")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        try:
            db_user = await _link_telegram_to_user(
                request,
                session,
                current_user_id=user_id,
                telegram_user=telegram_user,
                settings=settings,
            )
            if db_user.is_banned:
                await session.rollback()
                return _json_error(403, "banned", "Access denied")
            await session.commit()
        except UserMergeConflictError as exc:
            await session.rollback()
            return _json_error(409, "account_merge_conflict", str(exc))
        except Exception as exc:
            await session.rollback()
            logger.error("Telegram account link failed: %s", exc, exc_info=True)
            return _json_error(500, "link_failed", "Link failed")

    token = create_webapp_session_token(settings, int(db_user.user_id))
    return web.json_response(
        {
            "ok": True,
            "token": token,
            "user_id": int(db_user.user_id),
            "telegram_id": _telegram_id_for_user(db_user),
        }
    )


async def me_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    data = await _build_user_payload(request, user_id)
    return web.json_response({"ok": True, **data})


async def apply_promo_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    payload = await _read_json(request)
    code = str(payload.get("code") or "").strip()
    if not code:
        return _json_error(400, "empty_code", "Promo code is empty")

    settings: Settings = request.app["settings"]
    promo_code_service: PromoCodeService = request.app.get("promo_code_service")
    if not promo_code_service:
        return _json_error(503, "service_unavailable", "Promo service unavailable")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        try:
            db_user = await user_dal.get_user_by_id(session, user_id)
            if not db_user or db_user.is_banned:
                await session.rollback()
                return _json_error(403, "access_denied", "Access denied")
            lang = _normalize_language(db_user.language_code or settings.DEFAULT_LANGUAGE)
            success, result = await promo_code_service.apply_promo_code(
                session,
                user_id,
                code,
                lang,
            )
            if not success:
                await session.rollback()
                return _json_error(400, "promo_apply_failed", str(result))
            await session.commit()
            end_date = result if isinstance(result, datetime) else None
            return web.json_response(
                {
                    "ok": True,
                    "end_date": end_date.isoformat() if end_date else None,
                    "end_date_text": end_date.strftime("%d.%m.%Y %H:%M") if end_date else None,
                }
            )
        except Exception as exc:
            await session.rollback()
            logger.error("WebApp promo apply failed: %s", exc, exc_info=True)
            return _json_error(500, "promo_apply_failed", "Promo apply failed")


async def create_payment_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    payload = await _read_json(request)
    method = str(payload.get("method") or "").strip().lower()
    try:
        months = int(float(payload.get("months")))
    except (TypeError, ValueError):
        return _json_error(400, "invalid_plan", "Invalid subscription period")

    settings: Settings = request.app["settings"]
    price = settings.subscription_options.get(months)
    stars_price = settings.stars_subscription_options.get(months)
    if price is None and method != "stars":
        return _json_error(400, "invalid_plan", "Subscription period is not available")
    if method == "stars" and (stars_price is None or int(stars_price) <= 0):
        return _json_error(400, "invalid_plan", "Stars price is not configured")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        lang = db_user.language_code or settings.DEFAULT_LANGUAGE
        return await _create_subscription_payment(
            request=request,
            session=session,
            user_id=user_id,
            method=method,
            months=months,
            price=float(price or 0),
            stars_price=stars_price,
            lang=lang,
        )


async def payment_status_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    try:
        payment_id = int(request.match_info["payment_id"])
    except (TypeError, ValueError):
        return _json_error(400, "invalid_payment", "Invalid payment id")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        payment = await payment_dal.get_payment_by_db_id(session, payment_id)
        if not payment or payment.user_id != user_id:
            return _json_error(404, "not_found", "Payment not found")
        return web.json_response(
            {
                "ok": True,
                "payment_id": payment.payment_id,
                "status": payment.status,
                "paid": payment.status == "succeeded",
            }
        )


async def _read_json(request: web.Request) -> Dict[str, Any]:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _json_error(status: int, code: str, message: str) -> web.Response:
    return web.json_response(
        {"ok": False, "error": code, "message": message},
        status=status,
    )


def _require_user_id(request: web.Request) -> int:
    settings: Settings = request.app["settings"]
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    token = header[len(prefix):].strip() if header.startswith(prefix) else ""
    user_id = verify_webapp_session_token(settings, token)
    if not user_id:
        raise web.HTTPUnauthorized(
            text=json.dumps({"ok": False, "error": "unauthorized"}),
            content_type="application/json",
        )
    return user_id


async def _request_email_code(
    request: web.Request,
    *,
    email: str,
    purpose: str,
    language_code: str,
    target_user_id: Optional[int],
) -> web.Response:
    email_service: EmailAuthService = request.app["email_auth_service"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        try:
            result = await email_service.request_code(
                session,
                email=email,
                purpose=purpose,
                language_code=language_code,
                target_user_id=target_user_id,
            )
            if not result.ok:
                await session.rollback()
                status = 429 if result.error == "rate_limited" else 400
                if result.error == "email_auth_not_configured":
                    status = 503
                return web.json_response(
                    {
                        "ok": False,
                        "error": result.error,
                        "retry_after": result.retry_after,
                    },
                    status=status,
                )
            await session.commit()
            return web.json_response({"ok": True})
        except Exception as exc:
            await session.rollback()
            logger.error("Failed to send email verification code: %s", exc, exc_info=True)
            return _json_error(502, "email_send_failed", "Failed to send email")


def _telegram_id_for_user(user: User) -> Optional[int]:
    if user.telegram_id:
        return int(user.telegram_id)
    if user.user_id and int(user.user_id) > 0:
        return int(user.user_id)
    return None


def _panel_description_for_user(user: User) -> str:
    lines = [
        user.email or "",
        user.username or "",
        user.first_name or "",
        user.last_name or "",
    ]
    return "\n".join(line for line in lines if line).strip()


async def _sync_panel_identity_for_user(request: web.Request, user: User) -> None:
    if not user.panel_user_uuid:
        return
    subscription_service: SubscriptionService = request.app.get("subscription_service")
    if not subscription_service or not subscription_service.panel_service:
        return

    payload: Dict[str, Any] = {
        "description": _panel_description_for_user(user),
    }
    telegram_id = _telegram_id_for_user(user)
    if telegram_id:
        payload["telegramId"] = telegram_id
    if user.email:
        payload["email"] = user.email

    try:
        await subscription_service.panel_service.update_user_details_on_panel(
            user.panel_user_uuid,
            payload,
            log_response=False,
        )
    except Exception as exc:
        logger.warning(
            "Failed to sync linked identities to panel for user %s: %s",
            user.user_id,
            exc,
        )


def _apply_telegram_profile_to_user(
    user: User,
    telegram_user: Dict[str, Any],
    settings: Settings,
) -> None:
    language_code = telegram_user.get("language_code") or user.language_code or settings.DEFAULT_LANGUAGE
    if language_code not in {"ru", "en"}:
        language_code = user.language_code or settings.DEFAULT_LANGUAGE

    user.telegram_id = int(telegram_user["id"])
    user.username = sanitize_username(telegram_user.get("username"))
    user.first_name = sanitize_display_name(telegram_user.get("first_name"))
    user.last_name = sanitize_display_name(telegram_user.get("last_name"))
    user.language_code = language_code


async def _link_telegram_to_user(
    request: web.Request,
    session: AsyncSession,
    *,
    current_user_id: int,
    telegram_user: Dict[str, Any],
    settings: Settings,
) -> User:
    telegram_id = int(telegram_user["id"])
    current_user = await user_dal.get_user_by_id(session, current_user_id)
    if not current_user:
        raise ValueError("Current user not found.")

    existing_telegram_user = await user_dal.get_user_by_telegram_id(session, telegram_id)
    if not existing_telegram_user:
        existing_telegram_user = await user_dal.get_user_by_id(session, telegram_id)

    if existing_telegram_user and existing_telegram_user.user_id != current_user.user_id:
        if (
            current_user.email
            and existing_telegram_user.email
            and current_user.email != existing_telegram_user.email
        ):
            raise UserMergeConflictError(
                "Telegram account is already linked to a different email."
            )
        merged_user = await user_dal.merge_users(
            session,
            source_user_id=current_user.user_id,
            target_user_id=existing_telegram_user.user_id,
        )
        _apply_telegram_profile_to_user(merged_user, telegram_user, settings)
        await session.flush()
        await _sync_panel_identity_for_user(request, merged_user)
        return merged_user

    if not existing_telegram_user and int(current_user.user_id) < 0:
        language_code = telegram_user.get("language_code") or current_user.language_code or settings.DEFAULT_LANGUAGE
        if language_code not in {"ru", "en"}:
            language_code = current_user.language_code or settings.DEFAULT_LANGUAGE
        target_user, _ = await user_dal.create_user(
            session,
            {
                "user_id": telegram_id,
                "telegram_id": telegram_id,
                "username": sanitize_username(telegram_user.get("username")),
                "first_name": sanitize_display_name(telegram_user.get("first_name")),
                "last_name": sanitize_display_name(telegram_user.get("last_name")),
                "language_code": language_code,
                "registration_date": current_user.registration_date or datetime.now(timezone.utc),
            },
        )
        target_user.referral_code = None
        await session.flush()
        merged_user = await user_dal.merge_users(
            session,
            source_user_id=current_user.user_id,
            target_user_id=target_user.user_id,
        )
        _apply_telegram_profile_to_user(merged_user, telegram_user, settings)
        await session.flush()
        await _sync_panel_identity_for_user(request, merged_user)
        return merged_user

    if current_user.telegram_id and int(current_user.telegram_id) != telegram_id:
        raise UserMergeConflictError("Current account is already linked to Telegram.")

    _apply_telegram_profile_to_user(current_user, telegram_user, settings)
    await session.flush()
    await _sync_panel_identity_for_user(request, current_user)
    return current_user


def _normalize_referral_param(raw: Optional[str]) -> Optional[str]:
    value = (raw or "").strip()
    if not value:
        return None

    value_lower = value.lower()
    if value_lower.startswith("ref_u"):
        value = value[5:]
    elif value_lower.startswith("ref_"):
        value = value[4:]
    elif value and value[0].lower() == "u" and len(value) == 10:
        value = value[1:]

    if not re.fullmatch(r"[A-Za-z0-9]{1,32}", value):
        return None
    return value.upper()


async def _resolve_referrer_id(
    session: AsyncSession,
    raw_referral_param: Optional[str],
    *,
    current_user_id: Optional[int],
) -> Optional[int]:
    normalized = _normalize_referral_param(raw_referral_param)
    if not normalized:
        return None

    ref_user = None
    if normalized.isdigit():
        ref_user = await user_dal.get_user_by_id(session, int(normalized))
    if not ref_user:
        ref_user = await user_dal.get_user_by_referral_code(session, normalized)
    if not ref_user:
        return None
    if current_user_id is not None and int(ref_user.user_id) == int(current_user_id):
        return None
    return int(ref_user.user_id)


async def _apply_referral_to_existing_user(
    request: web.Request,
    session: AsyncSession,
    user: User,
    raw_referral_param: Optional[str],
) -> bool:
    if not raw_referral_param or user.referred_by_id is not None:
        return False

    referred_by_id = await _resolve_referrer_id(
        session,
        raw_referral_param,
        current_user_id=int(user.user_id),
    )
    if not referred_by_id:
        return False

    subscription_service: SubscriptionService = request.app["subscription_service"]
    try:
        is_active_now = await subscription_service.has_active_subscription(
            session,
            int(user.user_id),
        )
    except Exception:
        is_active_now = False
    if is_active_now:
        return False

    user.referred_by_id = referred_by_id
    await session.flush()
    return True


async def _apply_referral_welcome_bonus_if_needed(
    request: web.Request,
    session: AsyncSession,
    user: User,
    raw_referral_param: Optional[str],
) -> Optional[datetime]:
    if not raw_referral_param or not user.referred_by_id:
        return None

    settings: Settings = request.app["settings"]
    referral_welcome_days = max(
        0,
        int(getattr(settings, "REFERRAL_WELCOME_BONUS_DAYS", 0) or 0),
    )
    if referral_welcome_days <= 0:
        return None

    subscription_service: SubscriptionService = request.app["subscription_service"]
    try:
        if await subscription_service.has_active_subscription(session, int(user.user_id)):
            return None
    except Exception:
        pass

    return await subscription_service.extend_active_subscription_days(
        session,
        int(user.user_id),
        referral_welcome_days,
        reason="referral_welcome_bonus",
    )


async def _ensure_user_from_telegram(
    session: AsyncSession,
    telegram_user: Dict[str, Any],
    settings: Settings,
    *,
    referral_param: Optional[str] = None,
) -> User:
    user_id = int(telegram_user["id"])
    language_code = telegram_user.get("language_code") or settings.DEFAULT_LANGUAGE
    if language_code not in {"ru", "en"}:
        language_code = settings.DEFAULT_LANGUAGE

    update_data = {
        "telegram_id": user_id,
        "username": sanitize_username(telegram_user.get("username")),
        "first_name": sanitize_display_name(telegram_user.get("first_name")),
        "last_name": sanitize_display_name(telegram_user.get("last_name")),
        "language_code": language_code,
    }

    db_user = await user_dal.get_user_by_telegram_id(session, user_id)
    if not db_user:
        db_user = await user_dal.get_user_by_id(session, user_id)
    if not db_user:
        referred_by_id = await _resolve_referrer_id(
            session,
            referral_param or telegram_user.get("start_param"),
            current_user_id=user_id,
        )
        db_user, created = await user_dal.create_user(
            session,
            {
                "user_id": user_id,
                **update_data,
                "referred_by_id": referred_by_id,
                "registration_date": datetime.now(timezone.utc),
            },
        )
        setattr(db_user, "_webapp_created", bool(created))
        return db_user

    changed = {
        key: value
        for key, value in update_data.items()
        if getattr(db_user, key) != value
    }
    if changed:
        db_user = await user_dal.update_user(session, db_user.user_id, changed) or db_user
    return db_user


async def _build_user_payload(request: web.Request, user_id: int) -> Dict[str, Any]:
    settings: Settings = request.app["settings"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    subscription_service: SubscriptionService = request.app["subscription_service"]

    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            raise web.HTTPForbidden(
                text=json.dumps({"ok": False, "error": "access_denied"}),
                content_type="application/json",
            )

        active = await subscription_service.get_active_subscription_details(
            session, user_id
        )
        referral_code = await user_dal.ensure_referral_code(session, db_user)
        referral_service: Optional[ReferralService] = request.app.get("referral_service")
        bot_username = request.app.get("bot_username") or ""
        referral_link = None
        if referral_service and bot_username:
            referral_link = await referral_service.generate_referral_link(
                session,
                bot_username,
                user_id,
            )
        webapp_referral_link = _build_webapp_referral_link(
            request.app["settings"].SUBSCRIPTION_MINI_APP_URL,
            referral_code,
        )
        referral_stats = (
            await referral_service.get_referral_stats(session, user_id)
            if referral_service
            else {"invited_count": 0, "purchased_count": 0}
        )
        local_sub = await subscription_dal.get_active_subscription_by_user_id(
            session,
            user_id,
            db_user.panel_user_uuid,
        ) if db_user.panel_user_uuid else None
        try:
            await session.commit()
        except Exception:
            await session.rollback()

    lang = _normalize_language(db_user.language_code or settings.DEFAULT_LANGUAGE)
    return {
        "user": {
            "id": user_id,
            "username": db_user.username,
            "email": db_user.email,
            "email_verified": bool(db_user.email_verified_at),
            "telegram_id": db_user.telegram_id,
            "telegram_linked": bool(_telegram_id_for_user(db_user)),
            "first_name": db_user.first_name,
            "language_code": lang,
        },
        "subscription": _serialize_subscription(active, local_sub, lang),
        "referral": {
            "code": referral_code,
            "bot_link": referral_link,
            "webapp_link": webapp_referral_link,
            "invited_count": referral_stats.get("invited_count", 0),
            "purchased_count": referral_stats.get("purchased_count", 0),
            "bonus_details": _serialize_referral_bonus_details(settings, lang),
        },
        "plans": _serialize_plans(settings, lang),
        "payment_methods": _serialize_payment_methods(settings, request.app),
        "settings": {
            "support_url": settings.SUPPORT_LINK,
            "traffic_mode": bool(settings.traffic_sale_mode),
            "email_auth_enabled": settings.email_auth_configured,
        },
    }


def _serialize_referral_bonus_details(settings: Settings, lang: str) -> List[Dict[str, Any]]:
    if getattr(settings, "traffic_sale_mode", False):
        return []

    details: List[Dict[str, Any]] = []
    for months, _price in sorted(settings.subscription_options.items()):
        inviter_days = settings.referral_bonus_inviter.get(months)
        friend_days = settings.referral_bonus_referee.get(months)
        if inviter_days is None and friend_days is None:
            continue
        details.append(
            {
                "months": int(months),
                "title": _format_months_title(int(months), lang),
                "inviter_days": int(inviter_days or 0),
                "friend_days": int(friend_days or 0),
            }
        )
    return details


def _build_webapp_referral_link(
    base_url: Optional[str],
    referral_code: Optional[str],
) -> Optional[str]:
    if not base_url or not referral_code:
        return None
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["ref"] = f"u{referral_code}"
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path or "/",
            urlencode(query),
            parts.fragment,
        )
    )


def _serialize_subscription(
    active: Optional[Dict[str, Any]],
    local_sub: Optional[Any],
    lang: str,
) -> Dict[str, Any]:
    if not active:
        return {
            "active": False,
            "status": "INACTIVE",
            "remaining_text": _format_remaining(0, lang),
            "days_left": 0,
            "config_link": None,
            "connect_url": None,
        }

    end_date = active.get("end_date")
    if end_date and end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    seconds_left = 0
    if end_date:
        seconds_left = max(
            0,
            int((end_date - datetime.now(timezone.utc)).total_seconds()),
        )

    return {
        "active": seconds_left > 0,
        "status": active.get("status_from_panel") or "UNKNOWN",
        "end_date": end_date.isoformat() if end_date else None,
        "end_date_text": end_date.strftime("%d.%m.%Y %H:%M") if end_date else "N/A",
        "days_left": seconds_left // 86400,
        "remaining_text": _format_remaining(seconds_left, lang),
        "config_link": active.get("config_link"),
        "connect_url": active.get("connect_button_url") or active.get("config_link"),
        "traffic_limit": _format_bytes(active.get("traffic_limit_bytes")),
        "traffic_used": _format_bytes(active.get("traffic_used_bytes")),
        "traffic_limit_bytes": _coerce_int_or_none(active.get("traffic_limit_bytes")),
        "traffic_used_bytes": _coerce_int_or_none(active.get("traffic_used_bytes")),
        "auto_renew_enabled": bool(getattr(local_sub, "auto_renew_enabled", False)),
        "provider": getattr(local_sub, "provider", None),
    }


def _serialize_plans(settings: Settings, lang: str) -> List[Dict[str, Any]]:
    plans: List[Dict[str, Any]] = []
    for months, price in sorted(settings.subscription_options.items()):
        plan = {
            "months": int(months),
            "price": float(price),
            "currency": settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
            "title": _format_months_title(int(months), lang),
        }
        stars_price = settings.stars_subscription_options.get(months)
        if stars_price is not None and int(stars_price) > 0:
            plan["stars_price"] = int(stars_price)
        plans.append(plan)
    return plans


def _serialize_payment_methods(
    settings: Settings,
    app: web.Application,
) -> List[Dict[str, Any]]:
    labels = {
        "severpay": "SeverPay",
        "freekassa": "FreeKassa / СБП",
        "platega": "Platega",
        "yookassa": "Банковская карта",
        "stars": "Telegram Stars",
        "cryptopay": "CryptoPay",
    }
    methods: List[Dict[str, Any]] = []
    for method in settings.payment_methods_order:
        method = method.lower()
        if method == "severpay" and _service_configured(app, "severpay_service"):
            methods.append({"id": method, "name": labels[method]})
        elif method == "freekassa" and _service_configured(app, "freekassa_service"):
            methods.append({"id": method, "name": labels[method]})
        elif method == "platega" and _service_configured(app, "platega_service"):
            methods.append({"id": method, "name": labels[method]})
        elif method == "yookassa" and _service_configured(app, "yookassa_service"):
            methods.append({"id": method, "name": labels[method]})
        elif method == "stars" and settings.STARS_ENABLED:
            methods.append({"id": method, "name": labels[method]})
        elif method == "cryptopay" and _service_configured(app, "cryptopay_service"):
            methods.append({"id": method, "name": labels[method]})
    return methods


def _service_configured(app: web.Application, key: str) -> bool:
    service = app.get(key)
    return bool(service and getattr(service, "configured", False))


async def _create_subscription_payment(
    *,
    request: web.Request,
    session: AsyncSession,
    user_id: int,
    method: str,
    months: int,
    price: float,
    stars_price: Optional[int],
    lang: str,
) -> web.Response:
    settings: Settings = request.app["settings"]
    description = _payment_description(months, lang)

    if method == "yookassa":
        return await _create_yookassa_payment(
            request, session, user_id, months, price, description
        )
    if method == "freekassa":
        return await _create_freekassa_payment(
            request, session, user_id, months, price, description
        )
    if method == "platega":
        return await _create_platega_payment(
            request, session, user_id, months, price, description
        )
    if method == "severpay":
        return await _create_severpay_payment(
            request, session, user_id, months, price, description
        )
    if method == "cryptopay":
        service: CryptoPayService = request.app["cryptopay_service"]
        if not service or not service.configured:
            return _json_error(400, "payment_unavailable", "Payment method unavailable")
        url = await service.create_invoice(
            session=session,
            user_id=user_id,
            months=months,
            amount=price,
            description=description,
            sale_mode="subscription",
        )
        if not url:
            return _json_error(502, "payment_failed", "Failed to create payment")
        return web.json_response(
            {"ok": True, "action": "open_link", "payment_url": url, "payment_id": None}
        )
    if method == "stars":
        if not settings.STARS_ENABLED or stars_price is None:
            return _json_error(400, "payment_unavailable", "Payment method unavailable")
        return await _create_stars_payment(
            request, session, user_id, months, int(stars_price), description
        )

    return _json_error(400, "payment_unavailable", "Payment method unavailable")


async def _create_base_payment_record(
    session: AsyncSession,
    *,
    user_id: int,
    amount: float,
    currency: str,
    status: str,
    description: str,
    months: int,
    provider: str,
) -> Payment:
    payment = await payment_dal.create_payment_record(
        session,
        {
            "user_id": user_id,
            "amount": amount,
            "currency": currency,
            "status": status,
            "description": description,
            "subscription_duration_months": months,
            "provider": provider,
        },
    )
    await session.commit()
    return payment


async def _create_yookassa_payment(
    request: web.Request,
    session: AsyncSession,
    user_id: int,
    months: int,
    price: float,
    description: str,
) -> web.Response:
    settings: Settings = request.app["settings"]
    service: YooKassaService = request.app["yookassa_service"]
    if not service or not service.configured:
        return _json_error(400, "payment_unavailable", "Payment method unavailable")

    try:
        payment = await _create_base_payment_record(
            session,
            user_id=user_id,
            amount=price,
            currency="RUB",
            status="pending_yookassa",
            description=description,
            months=months,
            provider="yookassa",
        )
        response = await service.create_payment(
            amount=price,
            currency="RUB",
            description=description,
            metadata={
                "user_id": str(user_id),
                "subscription_months": str(months),
                "payment_db_id": str(payment.payment_id),
                "sale_mode": "subscription",
                "source": "webapp",
            },
            receipt_email=settings.YOOKASSA_DEFAULT_RECEIPT_EMAIL,
            save_payment_method=bool(
                settings.yookassa_autopayments_active
                and settings.YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING
            ),
        )
        payment_url = response.get("confirmation_url") if response else None
        if not payment_url:
            await payment_dal.update_payment_status_by_db_id(
                session, payment.payment_id, "failed_creation"
            )
            await session.commit()
            return _json_error(502, "payment_failed", "Failed to create payment")

        await payment_dal.update_payment_status_by_db_id(
            session,
            payment.payment_id,
            response.get("status", "pending"),
            yk_payment_id=response.get("id"),
        )
        await session.commit()
        return web.json_response(
            {
                "ok": True,
                "action": "open_link",
                "payment_url": payment_url,
                "payment_id": payment.payment_id,
            }
        )
    except Exception as exc:
        await session.rollback()
        logger.error("YooKassa WebApp payment failed: %s", exc, exc_info=True)
        return _json_error(502, "payment_failed", "Failed to create payment")


async def _create_freekassa_payment(
    request: web.Request,
    session: AsyncSession,
    user_id: int,
    months: int,
    price: float,
    description: str,
) -> web.Response:
    settings: Settings = request.app["settings"]
    service: FreeKassaService = request.app["freekassa_service"]
    if not service or not service.configured or not service.payment_method_id:
        return _json_error(400, "payment_unavailable", "Payment method unavailable")

    try:
        payment = await _create_base_payment_record(
            session,
            user_id=user_id,
            amount=price,
            currency=service.default_currency,
            status="pending_freekassa",
            description=description,
            months=months,
            provider="freekassa",
        )
        success, response_data = await service.create_order(
            payment_db_id=payment.payment_id,
            user_id=user_id,
            months=months,
            amount=price,
            currency=service.default_currency,
            payment_method_id=service.payment_method_id,
            ip_address=service.server_ip,
            extra_params={"us_method": service.payment_method_id},
        )
        payment_url = response_data.get("location") if success else None
        provider_id = response_data.get("orderHash") or response_data.get("orderId")
        if provider_id:
            await payment_dal.update_provider_payment_and_status(
                session, payment.payment_id, str(provider_id), payment.status
            )
            await session.commit()
        if not payment_url:
            await payment_dal.update_payment_status_by_db_id(
                session, payment.payment_id, "failed_creation"
            )
            await session.commit()
            return _json_error(502, "payment_failed", "Failed to create payment")
        return web.json_response(
            {
                "ok": True,
                "action": "open_link",
                "payment_url": payment_url,
                "payment_id": payment.payment_id,
            }
        )
    except Exception as exc:
        await session.rollback()
        logger.error("FreeKassa WebApp payment failed: %s", exc, exc_info=True)
        return _json_error(502, "payment_failed", "Failed to create payment")


async def _create_platega_payment(
    request: web.Request,
    session: AsyncSession,
    user_id: int,
    months: int,
    price: float,
    description: str,
) -> web.Response:
    settings: Settings = request.app["settings"]
    service: PlategaService = request.app["platega_service"]
    if not service or not service.configured:
        return _json_error(400, "payment_unavailable", "Payment method unavailable")

    try:
        payment = await _create_base_payment_record(
            session,
            user_id=user_id,
            amount=price,
            currency=settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
            status="pending_platega",
            description=description,
            months=months,
            provider="platega",
        )
        payload = json.dumps(
            {
                "payment_db_id": payment.payment_id,
                "user_id": user_id,
                "months": months,
                "sale_mode": "subscription",
                "source": "webapp",
            }
        )
        success, response_data = await service.create_transaction(
            payment_db_id=payment.payment_id,
            user_id=user_id,
            months=months,
            amount=price,
            currency=settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
            description=description,
            payload=payload,
        )
        payment_url = (
            response_data.get("redirect")
            or response_data.get("url")
            or response_data.get("paymentUrl")
        ) if success else None
        provider_id = response_data.get("transactionId") or response_data.get("id")
        if provider_id:
            await payment_dal.update_provider_payment_and_status(
                session,
                payment.payment_id,
                str(provider_id),
                str(response_data.get("status", payment.status)),
            )
            await session.commit()
        if not payment_url:
            await payment_dal.update_payment_status_by_db_id(
                session, payment.payment_id, "failed_creation"
            )
            await session.commit()
            return _json_error(502, "payment_failed", "Failed to create payment")
        return web.json_response(
            {
                "ok": True,
                "action": "open_link",
                "payment_url": payment_url,
                "payment_id": payment.payment_id,
            }
        )
    except Exception as exc:
        await session.rollback()
        logger.error("Platega WebApp payment failed: %s", exc, exc_info=True)
        return _json_error(502, "payment_failed", "Failed to create payment")


async def _create_severpay_payment(
    request: web.Request,
    session: AsyncSession,
    user_id: int,
    months: int,
    price: float,
    description: str,
) -> web.Response:
    settings: Settings = request.app["settings"]
    service: SeverPayService = request.app["severpay_service"]
    if not service or not service.configured:
        return _json_error(400, "payment_unavailable", "Payment method unavailable")

    try:
        payment = await _create_base_payment_record(
            session,
            user_id=user_id,
            amount=price,
            currency=settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
            status="pending_severpay",
            description=description,
            months=months,
            provider="severpay",
        )
        success, response_data = await service.create_payment(
            payment_db_id=payment.payment_id,
            user_id=user_id,
            months=months,
            amount=price,
            currency=settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
            description=description,
        )
        payment_url = (
            response_data.get("url")
            or response_data.get("payment_url")
            or response_data.get("paymentUrl")
        ) if success else None
        provider_id = response_data.get("id") or response_data.get("uid")
        if provider_id:
            await payment_dal.update_provider_payment_and_status(
                session, payment.payment_id, str(provider_id), payment.status
            )
            await session.commit()
        if not payment_url:
            await payment_dal.update_payment_status_by_db_id(
                session, payment.payment_id, "failed_creation"
            )
            await session.commit()
            return _json_error(502, "payment_failed", "Failed to create payment")
        return web.json_response(
            {
                "ok": True,
                "action": "open_link",
                "payment_url": payment_url,
                "payment_id": payment.payment_id,
            }
        )
    except Exception as exc:
        await session.rollback()
        logger.error("SeverPay WebApp payment failed: %s", exc, exc_info=True)
        return _json_error(502, "payment_failed", "Failed to create payment")


async def _create_stars_payment(
    request: web.Request,
    session: AsyncSession,
    user_id: int,
    months: int,
    stars_price: int,
    description: str,
) -> web.Response:
    bot: Bot = request.app["bot"]
    try:
        payment = await _create_base_payment_record(
            session,
            user_id=user_id,
            amount=float(stars_price),
            currency="XTR",
            status="pending_stars",
            description=description,
            months=months,
            provider="telegram_stars",
        )
        payload = f"{payment.payment_id}:{months}:subscription"
        prices = [LabeledPrice(label=description, amount=stars_price)]
        create_invoice_link = getattr(bot, "create_invoice_link", None)
        if callable(create_invoice_link):
            invoice_url = await create_invoice_link(
                title=description,
                description=description,
                payload=payload,
                provider_token="",
                currency="XTR",
                prices=prices,
            )
            return web.json_response(
                {
                    "ok": True,
                    "action": "open_invoice",
                    "payment_url": invoice_url,
                    "payment_id": payment.payment_id,
                }
            )

        await bot.send_invoice(
            chat_id=user_id,
            title=description,
            description=description,
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=prices,
        )
        return web.json_response(
            {
                "ok": True,
                "action": "invoice_sent",
                "payment_id": payment.payment_id,
            }
        )
    except Exception as exc:
        await session.rollback()
        logger.error("Stars WebApp payment failed: %s", exc, exc_info=True)
        return _json_error(502, "payment_failed", "Failed to create invoice")


def _normalize_language(lang: Optional[str]) -> str:
    value = (lang or "ru").split("-")[0].lower()
    return value if value in {"ru", "en"} else "ru"


def _format_remaining(seconds: int, lang: str) -> str:
    if seconds <= 0:
        if lang == "en":
            return "Subscription inactive"
        return "Подписка не активна"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if lang == "en":
        if days > 0:
            return f"{days} d. {hours} h."
        if hours > 0:
            return f"{hours} h. {minutes} min."
        return f"{max(1, minutes)} min."
    if days > 0:
        return f"{days} д. {hours} ч."
    if hours > 0:
        return f"{hours} ч. {minutes} мин."
    return f"{max(1, minutes)} мин."


def _coerce_int_or_none(value: Optional[Any]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_bytes(value: Optional[Any]) -> str:
    if value is None:
        return "N/A"
    try:
        size = float(value)
    except (TypeError, ValueError):
        return str(value)
    if size <= 0:
        return "∞"
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {units[index]}"


def _format_months_title(months: int, lang: str) -> str:
    if lang == "en":
        if months == 1:
            return "1 month"
        return f"{months} months"
    if months == 1:
        return "1 месяц"
    if 2 <= months <= 4:
        return f"{months} месяца"
    return f"{months} месяцев"


def _payment_description(months: int, lang: str) -> str:
    if lang == "en":
        return f"Subscription for {_format_months_title(months, lang)}"
    return f"Подписка на {_format_months_title(months, lang)}"
