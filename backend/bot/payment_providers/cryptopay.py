import hashlib
import hmac
import json
import logging
from typing import Optional

from aiocryptopay import AioCryptoPay, Networks
from aiocryptopay.models.update import Update
from aiogram import Bot, F, Router, types
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.referral_service import ReferralService
from bot.services.subscription_service import SubscriptionService
from config.settings import Settings
from db.dal import payment_dal

from .base import PaymentProviderSpec, ServiceFactoryContext, WebAppPaymentContext
from .shared import (
    PaymentSuccessRequest,
    describe_payment,
    finalize_successful_payment,
    make_translator,
    notify_callback_parse_error,
    notify_service_unavailable,
    parse_payment_callback,
    payment_failed,
    payment_link_response,
    payment_unavailable,
    render_payment_link,
    sale_mode_base,
    sale_mode_tariff_key,
)

logger = logging.getLogger(__name__)
_LOG = "cryptopay"


class CryptoPayService:
    def __init__(
        self,
        token: Optional[str],
        network: str,
        bot: Bot,
        settings: Settings,
        i18n: JsonI18n,
        async_session_factory: sessionmaker,
        subscription_service: SubscriptionService,
        referral_service: ReferralService,
    ):
        self.bot = bot
        self.settings = settings
        self.i18n = i18n
        self.async_session_factory = async_session_factory
        self.subscription_service = subscription_service
        self.referral_service = referral_service
        self.token = token
        if token:
            net = Networks.TEST_NET if str(network).lower() == "testnet" else Networks.MAIN_NET
            self.client = AioCryptoPay(token=token, network=net)
            self.client.register_pay_handler(self._invoice_paid_handler)
            self.configured = True
        else:
            logging.warning("CryptoPay token not provided. CryptoPay disabled")
            self.client = None
            self.configured = False

    async def close(self):
        if self.client:
            try:
                await self.client.close()
                logging.info("CryptoPay client session closed.")
            except Exception as e:
                logging.warning("Failed to close CryptoPay client: %s", e)

    async def create_invoice(
        self,
        session: AsyncSession,
        user_id: int,
        months: int,
        amount: float,
        description: str,
        sale_mode: str = "subscription",
        url_kind: str = "bot",
    ) -> Optional[str]:
        if not self.configured or not self.client:
            logging.error("CryptoPayService not configured")
            return None

        sale_base = sale_mode_base(sale_mode)
        is_traffic = sale_base in {"traffic", "traffic_package", "topup", "premium_topup"}
        try:
            payment_record = await payment_dal.create_payment_record(
                session,
                {
                    "user_id": user_id,
                    "amount": float(amount),
                    "currency": self.settings.CRYPTOPAY_ASSET,
                    "status": "pending_cryptopay",
                    "description": description,
                    "subscription_duration_months": (
                        int(months) if sale_base == "subscription" else None
                    ),
                    "provider": "cryptopay",
                    "sale_mode": sale_mode,
                    "tariff_key": sale_mode_tariff_key(sale_mode),
                    "purchased_gb": float(months) if is_traffic else None,
                },
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logging.exception("Failed to create cryptopay payment record for user %s.", user_id)
            return None

        payload = json.dumps(
            {
                "user_id": str(user_id),
                "subscription_months": str(months),
                "payment_db_id": str(payment_record.payment_id),
                "sale_mode": sale_mode,
                "traffic_gb": str(months) if is_traffic else None,
            }
        )
        try:
            invoice = await self.client.create_invoice(
                amount=amount,
                currency_type=self.settings.CRYPTOPAY_CURRENCY_TYPE,
                fiat=self.settings.CRYPTOPAY_ASSET
                if self.settings.CRYPTOPAY_CURRENCY_TYPE == "fiat"
                else None,
                asset=self.settings.CRYPTOPAY_ASSET
                if self.settings.CRYPTOPAY_CURRENCY_TYPE == "crypto"
                else None,
                description=description,
                payload=payload,
            )
            try:
                await payment_dal.update_provider_payment_and_status(
                    session,
                    payment_record.payment_id,
                    str(invoice.invoice_id),
                    str(invoice.status),
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logging.exception(
                    "Failed to update cryptopay payment record %s.",
                    payment_record.payment_id,
                )
                return None
            if url_kind == "web":
                return (
                    getattr(invoice, "web_app_invoice_url", None)
                    or getattr(invoice, "mini_app_invoice_url", None)
                    or invoice.bot_invoice_url
                )
            return invoice.bot_invoice_url
        except Exception:
            logging.exception("CryptoPay invoice creation failed.")
            return None

    async def _invoice_paid_handler(self, update: Update, app: web.Application):
        invoice = update.payload
        if not invoice.payload:
            logging.warning("CryptoPay webhook without payload")
            return
        try:
            meta = json.loads(invoice.payload)
            user_id = int(meta["user_id"])
            months = float(meta.get("subscription_months") or 0)
            payment_db_id = int(meta["payment_db_id"])
            sale_mode = meta.get("sale_mode") or (
                "traffic" if self.settings.traffic_sale_mode else "subscription"
            )
            traffic_gb = float(meta.get("traffic_gb")) if meta.get("traffic_gb") else months
        except Exception:
            logging.exception("Failed to parse CryptoPay payload.")
            return

        async_session_factory: sessionmaker = app["async_session_factory"]
        bot: Bot = app["bot"]
        settings: Settings = app["settings"]
        i18n: JsonI18n = app["i18n"]
        subscription_service: SubscriptionService = app["subscription_service"]
        referral_service: ReferralService = app["referral_service"]

        async with async_session_factory() as session:
            try:
                await payment_dal.update_provider_payment_and_status(
                    session,
                    payment_db_id,
                    str(invoice.invoice_id),
                    "succeeded",
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logging.exception(
                    "Failed to mark CryptoPay invoice %s as succeeded.",
                    payment_db_id,
                )
                return

            payment = await payment_dal.get_payment_by_db_id(session, payment_db_id)
            if not payment:
                logging.error(
                    "CryptoPay webhook: payment %s vanished after status update.",
                    payment_db_id,
                )
                return

            currency = invoice.asset or settings.DEFAULT_CURRENCY_SYMBOL
            await finalize_successful_payment(
                PaymentSuccessRequest(
                    bot=bot,
                    settings=settings,
                    i18n=i18n,
                    session=session,
                    subscription_service=subscription_service,
                    referral_service=referral_service,
                    payment=payment,
                    user_id=user_id,
                    amount=float(invoice.amount),
                    currency=str(currency),
                    sale_mode=sale_mode,
                    months=int(months) if months else int(traffic_gb),
                    traffic_amount=float(traffic_gb),
                    provider_subscription="cryptopay",
                    provider_notification="crypto_pay",
                    log_prefix="CryptoPay webhook",
                )
            )

    def _validate_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        if not self.token:
            return False

        expected_signature = hmac.new(
            hashlib.sha256(self.token.encode("utf-8")).digest(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_signature, signature or ""):
            logger.error("CryptoPay signature mismatch")
            return False
        return True

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured or not self.client:
            return web.Response(status=503, text="cryptopay_disabled")
        raw_body = await request.read()
        signature = request.headers.get("crypto-pay-api-signature", "")
        if not self._validate_webhook_signature(raw_body, signature):
            return web.Response(status=401)
        return await self.client.get_updates(request)


async def cryptopay_webhook_route(request: web.Request) -> web.Response:
    service: CryptoPayService = request.app["cryptopay_service"]
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_crypto_router")


@router.callback_query(F.data.startswith("pay_crypto:"))
async def pay_crypto_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    cryptopay_service: CryptoPayService,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    translator = make_translator(i18n, current_lang)

    if not i18n or not callback.message:
        await notify_callback_parse_error(callback, translator)
        return

    if (
        not settings.CRYPTOPAY_ENABLED
        or not cryptopay_service
        or not getattr(cryptopay_service, "configured", False)
    ):
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        await notify_callback_parse_error(callback, translator)
        return

    payment_description = describe_payment(translator, parts)
    invoice_url = await cryptopay_service.create_invoice(
        session=session,
        user_id=callback.from_user.id,
        months=parts.months,
        amount=parts.price,
        description=payment_description,
        sale_mode=parts.sale_mode,
    )

    if invoice_url:
        await render_payment_link(
            callback,
            translator=translator,
            current_lang=current_lang,
            i18n=i18n,
            parts=parts,
            payment_url=invoice_url,
            log_prefix=_LOG,
        )
        return

    from .shared import safe_callback_answer

    await safe_callback_answer(callback, translator("error_payment_gateway"), show_alert=True)


def create_service(ctx: ServiceFactoryContext) -> CryptoPayService:
    return CryptoPayService(
        ctx.settings.CRYPTOPAY_TOKEN,
        ctx.settings.CRYPTOPAY_NETWORK,
        ctx.bot,
        ctx.settings,
        ctx.i18n,
        ctx.async_session_factory,
        ctx.subscription_service,
        ctx.referral_service,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    service: CryptoPayService = ctx.request.app["cryptopay_service"]
    if not service or not service.configured:
        return payment_unavailable()
    url = await service.create_invoice(
        session=ctx.session,
        user_id=ctx.user_id,
        months=ctx.months,
        amount=ctx.price,
        description=ctx.description,
        sale_mode=ctx.sale_mode,
        url_kind="web",
    )
    if not url:
        return payment_failed()
    return payment_link_response(payment_url=url, payment_id=None)


SPEC = PaymentProviderSpec(
    id="cryptopay",
    provider_key="cryptopay",
    label="CryptoPay",
    webapp_label="CryptoPay",
    webapp_labels={"ru": "CryptoPay", "en": "CryptoPay"},
    webapp_icon="Bitcoin",
    telegram_labels={"ru": "CryptoBot", "en": "CryptoBot"},
    pending_status="pending_cryptopay",
    enabled=lambda settings: settings.CRYPTOPAY_ENABLED,
    service_key="cryptopay_service",
    button_text_key="pay_with_cryptopay_button",
    callback_prefix="pay_crypto",
    router=router,
    create_service=create_service,
    webhook_path=lambda settings: settings.cryptopay_webhook_path,
    webhook_route=cryptopay_webhook_route,
    create_webapp_payment=create_webapp_payment,
    emoji="₿",
    telegram_emoji="₿",
)
