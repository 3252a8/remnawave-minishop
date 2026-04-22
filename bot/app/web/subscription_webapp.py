import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import LabeledPrice
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.webapp_auth import (
    consume_authorized_webapp_auth_token,
    create_pending_webapp_auth_token,
    create_webapp_session_token,
    validate_telegram_webapp_init_data,
    verify_webapp_session_token,
)
from bot.services.crypto_pay_service import CryptoPayService
from bot.services.freekassa_service import FreeKassaService
from bot.services.platega_service import PlategaService
from bot.services.severpay_service import SeverPayService
from bot.services.subscription_service import SubscriptionService
from bot.services.yookassa_service import YooKassaService
from bot.utils.text_sanitizer import sanitize_display_name, sanitize_username
from config.settings import Settings
from db.dal import payment_dal, subscription_dal, user_dal
from db.models import Payment, User

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "subscription_webapp.html"


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

    for key in (
        "subscription_service",
        "yookassa_service",
        "freekassa_service",
        "cryptopay_service",
        "platega_service",
        "severpay_service",
    ):
        if hasattr(dp, "workflow_data") and key in dp.workflow_data:  # type: ignore[attr-defined]
            app[key] = dp.workflow_data[key]  # type: ignore[index]

    setup_subscription_webapp_routes(app)
    return app


def setup_subscription_webapp_routes(app: web.Application) -> None:
    app.router.add_get("/", index_route)
    app.router.add_get("/health", health_route)
    app.router.add_post("/api/auth/token", auth_token_route)
    app.router.add_get("/api/auth/request-token", auth_request_token_route)
    app.router.add_get("/api/auth/check-token/{token}", auth_check_token_route)
    app.router.add_get("/api/me", me_route)
    app.router.add_post("/api/payments", create_payment_route)
    app.router.add_get("/api/payments/{payment_id}", payment_status_route)


async def health_route(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


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
        "supportUrl": settings.SUPPORT_LINK or "",
        "currency": settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
    }
    html = html.replace(
        "__WEBAPP_CONFIG__",
        json.dumps(config, ensure_ascii=False, separators=(",", ":")),
    )
    return web.Response(text=html, content_type="text/html", charset="utf-8")


async def auth_token_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)
    init_data = str(payload.get("init_data") or "")
    telegram_user = validate_telegram_webapp_init_data(
        init_data,
        settings.BOT_TOKEN,
        max_age_seconds=settings.WEBAPP_AUTH_MAX_AGE_SECONDS,
    )
    if not telegram_user:
        return _json_error(401, "invalid_auth", "Invalid Telegram auth data")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        try:
            db_user = await _ensure_user_from_telegram(session, telegram_user, settings)
            if db_user.is_banned:
                await session.rollback()
                return _json_error(403, "banned", "Access denied")
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error("WebApp auth failed: %s", exc, exc_info=True)
            return _json_error(500, "auth_failed", "Auth failed")

    token = create_webapp_session_token(settings, int(telegram_user["id"]))
    return web.json_response({"ok": True, "token": token})


async def auth_request_token_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    token = create_pending_webapp_auth_token(settings)
    bot: Bot = request.app["bot"]
    bot_info = await bot.get_me()
    auth_url = f"https://t.me/{bot_info.username}?start=webapp_auth_{token}"
    return web.json_response({"ok": True, "token": token, "auth_url": auth_url})


async def auth_check_token_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    token = request.match_info.get("token", "")
    user_id = consume_authorized_webapp_auth_token(settings, token)
    if not user_id:
        return web.json_response({"ok": True, "authorized": False})

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return web.json_response(
                {"ok": True, "authorized": False, "error": "Access denied"}
            )

    session_token = create_webapp_session_token(settings, user_id)
    return web.json_response(
        {
            "ok": True,
            "authorized": True,
            "token": session_token,
        }
    )


async def me_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    data = await _build_user_payload(request, user_id)
    return web.json_response({"ok": True, **data})


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


async def _ensure_user_from_telegram(
    session: AsyncSession,
    telegram_user: Dict[str, Any],
    settings: Settings,
) -> User:
    user_id = int(telegram_user["id"])
    language_code = telegram_user.get("language_code") or settings.DEFAULT_LANGUAGE
    if language_code not in {"ru", "en"}:
        language_code = settings.DEFAULT_LANGUAGE

    update_data = {
        "username": sanitize_username(telegram_user.get("username")),
        "first_name": sanitize_display_name(telegram_user.get("first_name")),
        "last_name": sanitize_display_name(telegram_user.get("last_name")),
        "language_code": language_code,
    }

    db_user = await user_dal.get_user_by_id(session, user_id)
    if not db_user:
        db_user, _ = await user_dal.create_user(
            session,
            {
                "user_id": user_id,
                **update_data,
                "registration_date": datetime.now(timezone.utc),
            },
        )
        return db_user

    changed = {
        key: value
        for key, value in update_data.items()
        if getattr(db_user, key) != value
    }
    if changed:
        db_user = await user_dal.update_user(session, user_id, changed) or db_user
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
        local_sub = await subscription_dal.get_active_subscription_by_user_id(
            session,
            user_id,
            db_user.panel_user_uuid,
        ) if db_user.panel_user_uuid else None
        try:
            await session.commit()
        except Exception:
            await session.rollback()

    return {
        "user": {
            "id": user_id,
            "username": db_user.username,
            "first_name": db_user.first_name,
            "language_code": db_user.language_code or settings.DEFAULT_LANGUAGE,
        },
        "subscription": _serialize_subscription(active, local_sub),
        "plans": _serialize_plans(settings),
        "payment_methods": _serialize_payment_methods(settings, request.app),
        "settings": {
            "support_url": settings.SUPPORT_LINK,
            "traffic_mode": bool(settings.traffic_sale_mode),
        },
    }


def _serialize_subscription(
    active: Optional[Dict[str, Any]],
    local_sub: Optional[Any],
) -> Dict[str, Any]:
    if not active:
        return {
            "active": False,
            "status": "INACTIVE",
            "remaining_text": "Нет активной подписки",
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
        "remaining_text": _format_remaining(seconds_left),
        "config_link": active.get("config_link"),
        "connect_url": active.get("connect_button_url") or active.get("config_link"),
        "traffic_limit": _format_bytes(active.get("traffic_limit_bytes")),
        "traffic_used": _format_bytes(active.get("traffic_used_bytes")),
        "auto_renew_enabled": bool(getattr(local_sub, "auto_renew_enabled", False)),
        "provider": getattr(local_sub, "provider", None),
    }


def _serialize_plans(settings: Settings) -> List[Dict[str, Any]]:
    plans: List[Dict[str, Any]] = []
    for months, price in sorted(settings.subscription_options.items()):
        plan = {
            "months": int(months),
            "price": float(price),
            "currency": settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
            "title": _format_months_title(int(months)),
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


def _format_remaining(seconds: int) -> str:
    if seconds <= 0:
        return "Подписка не активна"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days > 0:
        return f"{days} д. {hours} ч."
    if hours > 0:
        return f"{hours} ч. {minutes} мин."
    return f"{max(1, minutes)} мин."


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


def _format_months_title(months: int) -> str:
    if months == 1:
        return "1 месяц"
    if 2 <= months <= 4:
        return f"{months} месяца"
    return f"{months} месяцев"


def _payment_description(months: int, lang: str) -> str:
    if lang == "en":
        return f"Subscription for {months} month(s)"
    return f"Подписка на {_format_months_title(months)}"
