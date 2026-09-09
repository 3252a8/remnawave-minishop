"""Gift issuance uses the same locked, provider-confirmed payment boundary."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bot.infra import events
from bot.infra.event_payloads import PaymentSucceededPayload
from bot.infra.payment_events import build_payment_succeeded_payload
from bot.services.gift_purchase import issue_paid_gift
from bot.services.partner_commission_service import PartnerCommissionService
from bot.services.subscription_gifts import gift_url, is_gift_sale
from db.dal import gift_dal, payment_dal

if TYPE_CHECKING:
    from .success import PaymentSuccessOutcome, PaymentSuccessRequest

logger = logging.getLogger(__name__)


async def resolve_gift_payment(
    req: PaymentSuccessRequest,
) -> tuple[bool, PaymentSuccessOutcome | None]:
    from .common import sale_mode_base
    from .success import _mark_activation_failed

    if is_gift_sale(req.sale_mode):
        return True, await finalize_gift_payment(req)
    if (
        sale_mode_base(req.sale_mode) != "balance_topup"
        and await gift_dal.activating_for_user(req.session, req.user_id) is not None
    ):
        await _mark_activation_failed(req, int(req.payment.payment_id))
        return True, None
    return False, None


async def finalize_gift_payment(req: PaymentSuccessRequest) -> PaymentSuccessOutcome | None:
    from .common import make_translator
    from .success import (
        PaymentSuccessOutcome,
        _mark_activation_failed,
        resolve_user_language,
        send_success_message_to_user,
    )

    payment_id = int(req.payment.payment_id)
    partner_decision = None
    try:
        gift = await issue_paid_gift(req.session, req.payment)
        token = str(gift.token)
        try:
            async with req.session.begin_nested():
                partner_decision = await PartnerCommissionService(
                    req.settings
                ).record_payment_decision(req.session, req.payment)
        except Exception:
            logger.exception("Gift partner commission failed for payment %s", payment_id)
        await payment_dal.update_payment_status_by_db_id(req.session, payment_id, "succeeded")
        await req.session.commit()
    except Exception:
        logger.exception("Gift issuance failed for payment %s", payment_id)
        await _mark_activation_failed(req, payment_id)
        return None
    await PartnerCommissionService.emit_recorded(partner_decision)
    await events.emit_model(
        PaymentSucceededPayload.model_validate(
            build_payment_succeeded_payload(
                user_id=req.user_id,
                payment_db_id=payment_id,
                provider=req.provider_subscription,
                notification_provider=req.provider_notification,
                amount=req.amount,
                currency=req.currency,
                sale_mode=req.sale_mode,
                tariff_key=req.payment.tariff_key,
                months=req.months,
                traffic_gb=None,
                payment=req.payment,
                activation=None,
                end_date=None,
                is_auto_renew=False,
                renewal_subscription_id=None,
            )
        )
    )
    user, language = await resolve_user_language(
        req.session, user_id=req.user_id, db_user=req.db_user, settings=req.settings
    )
    translator = make_translator(req.i18n, language)
    base = str(req.settings.SUBSCRIPTION_MINI_APP_URL or "").strip()
    if base and not req.skip_user_notification:
        await send_success_message_to_user(
            bot=req.bot,
            user_id=req.user_id,
            text=translator("gift_payment_success", link=gift_url(base, token)),
            language=language,
            i18n=req.i18n,
            settings=req.settings,
            config_link_display=None,
            connect_button_url=None,
            include_keyboard=False,
            log_prefix=req.log_prefix,
            user=user,
            sale_mode=req.sale_mode,
        )
    return PaymentSuccessOutcome(None, None, None, 0, 0, user, language)
