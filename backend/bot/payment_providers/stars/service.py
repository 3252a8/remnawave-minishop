import logging
from typing import TYPE_CHECKING, Any

from aiogram import Bot, F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from aiohttp import web
from pydantic_settings import SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import payment_methods_back_callback
from bot.middlewares.i18n import JsonI18n

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    ReferralService = object
    SubscriptionService = object
from bot.utils.callback_answer import callback_message_or_none
from config.settings import Settings
from db.dal import payment_dal

from ..base import (
    PaymentProviderSpec,
    ProviderEnvConfig,
    ProviderManifestField,
    ServiceFactoryContext,
    WebAppPaymentContext,
    provider_env_file,
)
from ..shared import (
    PAYMENT_STATUS_PENDING_FINALIZATION,
    PaymentSuccessRequest,
    create_webapp_payment_record,
    describe_payment,
    finalize_successful_payment,
    format_number_for_payload,
    make_translator,
    notify_callback_parse_error,
    notify_service_unavailable,
    parse_payment_callback,
    payment_failed,
    payment_record_amounts,
    payment_unavailable,
    quote_hwid_callback_parts,
    safe_callback_answer,
    sale_mode_base,
    sale_mode_tariff_key,
)
from ..shared.app_context import app_required


class StarsPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_STARS_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: str | None = None
    WEBAPP_LABEL_EN: str | None = None
    WEBAPP_ICON: str | None = None
    TELEGRAM_LABEL_RU: str | None = None
    TELEGRAM_LABEL_EN: str | None = None
    TELEGRAM_EMOJI: str | None = None


class StarsService:
    def __init__(
        self,
        bot: Bot,
        settings: Settings,
        i18n: JsonI18n,
        subscription_service: SubscriptionService,
        referral_service: ReferralService,
    ):
        self.bot = bot
        self.settings = settings
        self.i18n = i18n
        self.subscription_service = subscription_service
        self.referral_service = referral_service

    async def create_invoice(
        self,
        session: AsyncSession,
        user_id: int,
        months: int,
        stars_price: int,
        description: str,
        sale_mode: str = "subscription",
        hwid_quote: dict[str, Any] | None = None,
    ) -> int | None:
        amounts = payment_record_amounts(
            months=months,
            sale_mode=sale_mode,
            hwid_device_count=hwid_quote.get("device_count") if hwid_quote else None,
        )
        sale_base = sale_mode_base(sale_mode)
        payment_record_data = {
            "user_id": user_id,
            "amount": float(stars_price),
            "currency": "XTR",
            "status": "pending_stars",
            "description": description,
            "subscription_duration_months": int(months) if sale_base == "subscription" else None,
            "provider": "telegram_stars",
            "sale_mode": sale_mode,
            "tariff_key": sale_mode_tariff_key(sale_mode),
            "purchased_gb": amounts.purchased_gb,
            "purchased_hwid_devices": amounts.purchased_hwid_devices,
            "hwid_valid_from": hwid_quote.get("valid_from") if hwid_quote else None,
            "hwid_valid_until": hwid_quote.get("valid_until") if hwid_quote else None,
            "hwid_pricing_period_months": hwid_quote.get("pricing_period_months")
            if hwid_quote
            else None,
            "hwid_proration_ratio": hwid_quote.get("proration_ratio") if hwid_quote else None,
            "hwid_full_price": hwid_quote.get("full_price") if hwid_quote else None,
        }
        try:
            db_payment_record = await payment_dal.create_payment_record(
                session, payment_record_data
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logging.exception("Failed to create stars payment record")
            return None

        payload = f"{db_payment_record.payment_id}:{months}:{sale_mode}"
        prices = [LabeledPrice(label=description, amount=stars_price)]
        try:
            await self.bot.send_invoice(
                chat_id=user_id,
                title=description,
                description=description,
                payload=payload,
                # Required to be empty for Telegram Stars (XTR) per Telegram Bot API.
                provider_token="",
                currency="XTR",
                prices=prices,
            )
            return int(db_payment_record.payment_id)
        except Exception:
            logging.exception("Failed to send Telegram Stars invoice")
            return None

    async def process_successful_payment(
        self,
        session: AsyncSession,
        message: types.Message,
        payment_db_id: int,
        months: int,
        stars_amount: int,
        i18n_data: dict[str, Any],
        sale_mode: str = "subscription",
    ) -> None:
        payment = await payment_dal.get_payment_by_db_id(session, payment_db_id)
        if not payment:
            logging.error("Stars: payment %s not found.", payment_db_id)
            return
        if payment.status == "succeeded":
            logging.info("Stars: payment %s already succeeded.", payment_db_id)
            return
        successful_payment = message.successful_payment
        if successful_payment is None:
            logging.error(
                "Stars: successful payment payload is missing for payment %s.",
                payment_db_id,
            )
            return

        try:
            payment_record = await payment_dal.update_provider_payment_and_status(
                session,
                payment_db_id,
                successful_payment.provider_payment_charge_id,
                PAYMENT_STATUS_PENDING_FINALIZATION,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logging.exception("Failed to update stars payment record %s", payment_db_id)
            return

        target_user_id = (
            int(payment_record.user_id)
            if payment_record and payment_record.user_id is not None
            else int(message.from_user.id if message.from_user else payment.user_id)
        )
        payment = await payment_dal.get_payment_by_db_id(session, payment_db_id)

        await finalize_successful_payment(
            PaymentSuccessRequest(
                bot=self.bot,
                settings=self.settings,
                i18n=i18n_data.get("i18n_instance") or self.i18n,
                session=session,
                subscription_service=self.subscription_service,
                referral_service=self.referral_service,
                payment=payment,
                user_id=target_user_id,
                amount=float(stars_amount),
                currency="XTR",
                sale_mode=sale_mode,
                months=months,
                traffic_amount=float(months),
                provider_subscription="telegram_stars",
                provider_notification="stars",
                log_prefix="Stars",
            )
        )


router = Router(name="user_subscription_payments_stars_router")


@router.callback_query(F.data.startswith("pay_stars:"))
async def pay_stars_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    session: AsyncSession,
    stars_service: StarsService,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    translator = make_translator(i18n, current_lang)

    if not i18n or not callback.message:
        await notify_callback_parse_error(callback, translator)
        return

    if not SPEC.is_available_to_user(
        settings,
        user_id=callback.from_user.id,
        require_configured=False,
    ):
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        await notify_callback_parse_error(callback, translator)
        return
    parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=parts,
        subscription_service=stars_service.subscription_service,
        currency="stars",
    )
    if not parts:
        await notify_callback_parse_error(callback, translator)
        return

    # ``parts.price`` for the Stars callback is the integer Stars price.
    stars_price = int(parts.price)
    payment_description = describe_payment(translator, parts)

    payment_db_id = await stars_service.create_invoice(
        session=session,
        user_id=callback.from_user.id,
        months=int(parts.months),
        stars_price=stars_price,
        description=payment_description,
        sale_mode=parts.sale_mode,
        hwid_quote=hwid_quote,
    )

    if payment_db_id:
        sale_base = parts.sale_base
        text_key = (
            "payment_invoice_sent_message_traffic"
            if sale_base in {"traffic", "traffic_package", "topup", "premium_topup"}
            else "payment_invoice_sent_message"
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=translator("back_to_payment_methods_button"),
                        callback_data=payment_methods_back_callback(
                            parts.human_value, parts.sale_mode, parts.price
                        ),
                    )
                ]
            ]
        )
        try:
            message = callback_message_or_none(callback)
            if message is None:
                await safe_callback_answer(callback)
                return
            await message.edit_text(
                translator(
                    text_key,
                    months=int(parts.months),
                    traffic_gb=parts.human_value,
                ),
                reply_markup=markup,
            )
        except Exception:
            logging.warning("Stars payment: failed to show invoice info message")
        await safe_callback_answer(callback)
        return

    await safe_callback_answer(callback, translator("error_payment_gateway"), show_alert=True)


@router.pre_checkout_query()
async def handle_pre_checkout_query(query: types.PreCheckoutQuery) -> None:
    try:
        await query.answer(ok=True)
    except Exception:
        # Nothing else to do here; Telegram will show an error if not answered
        pass


@router.message(F.successful_payment)
async def handle_successful_stars_payment(
    message: types.Message,
    settings: Settings,
    i18n_data: dict[str, Any],
    session: AsyncSession,
    stars_service: StarsService,
) -> None:
    payload = (
        message.successful_payment.invoice_payload if message and message.successful_payment else ""
    )
    try:
        parts = (payload or "").split(":")
        payment_db_id = int(parts[0])
        months = int(float(parts[1])) if len(parts) > 1 else 0
        sale_mode = parts[2] if len(parts) > 2 else "subscription"
    except Exception:
        return

    stars_amount = int(message.successful_payment.total_amount) if message.successful_payment else 0
    await stars_service.process_successful_payment(
        session=session,
        message=message,
        payment_db_id=payment_db_id,
        months=months,
        stars_amount=stars_amount,
        i18n_data=i18n_data,
        sale_mode=sale_mode,
    )


def create_service(ctx: ServiceFactoryContext) -> StarsService:
    return StarsService(
        ctx.bot,
        ctx.settings,
        ctx.i18n,
        ctx.subscription_service,
        ctx.referral_service,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    if ctx.stars_price is None:
        return payment_unavailable()
    bot = app_required(ctx.request, "bot", Bot)
    try:
        amounts = payment_record_amounts(
            months=ctx.months,
            sale_mode=ctx.sale_mode,
            traffic_gb=ctx.traffic_gb,
            hwid_device_count=ctx.hwid_device_count,
        )
        payment = await create_webapp_payment_record(
            ctx,
            amount=float(ctx.stars_price),
            currency="XTR",
            status="pending_stars",
            provider="telegram_stars",
        )
        payload_units = amounts.purchased_gb if amounts.traffic_sale else ctx.months
        payload = f"{payment.payment_id}:{format_number_for_payload(payload_units)}:{ctx.sale_mode}"
        prices = [LabeledPrice(label=ctx.description, amount=ctx.stars_price)]
        create_invoice_link = getattr(bot, "create_invoice_link", None)
        if callable(create_invoice_link):
            invoice_url = await create_invoice_link(
                title=ctx.description,
                description=ctx.description,
                payload=payload,
                # Required to be empty for Telegram Stars (XTR) per Telegram Bot API.
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
            chat_id=ctx.user_id,
            title=ctx.description,
            description=ctx.description,
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
    except Exception:
        await ctx.session.rollback()
        logging.exception("Stars WebApp payment failed")
        return payment_failed("Failed to create invoice")


_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="Telegram Stars",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_STARS_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_STARS_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_STARS_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "Sparkles",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_STARS_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_STARS_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_STARS_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "🌟",
            "TELEGRAM_EMOJI",
        ),
    )
)


SPEC = PaymentProviderSpec(
    id="stars",
    provider_key="telegram_stars",
    label="Telegram Stars",
    webapp_label="Telegram Stars",
    webapp_labels={"ru": "Звёзды Telegram", "en": "Telegram Stars"},
    webapp_icon="Sparkles",
    telegram_labels={"ru": "Звёзды Telegram", "en": "Telegram Stars"},
    pending_status="pending_stars",
    # Stars toggles stay on global Settings because stars_subscription_options
    # reads them together with STARS_PRICE_* fields.
    enabled=lambda settings: bool(settings.STARS_ENABLED),
    service_key="stars_service",
    callback_prefix="pay_stars",
    router=router,
    create_service=create_service,
    create_webapp_payment=create_webapp_payment,
    requires_configured_service=False,
    price_source="stars",
    emoji="⭐",
    telegram_emoji="⭐",
    presentation_class=StarsPresentation,
    manifest_fields=_PRESENTATION_MANIFEST,
    supported_currencies=("XTR",),
    currency_support_note="Telegram Stars use Telegram's XTR currency and separate Stars prices.",
)
