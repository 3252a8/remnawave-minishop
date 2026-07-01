from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Optional

from bot.app.web.webapp.cache_helpers import invalidate_webapp_user_caches
from bot.infra import events
from bot.infra.payment_events import PaymentPurchase, resolve_payment_success_snapshot
from bot.payment_providers.shared.common import (
    make_translator,
)
from bot.plugins import PluginContext
from bot.services.email_templates import render_account_merged
from bot.services.notification_service import NotificationService
from bot.services.user_email_notifications import send_user_notification_email
from db.dal import payment_dal, promo_code_dal, subscription_dal, user_dal
from db.models import Payment, Subscription, User

logger = logging.getLogger(__name__)

_registered_handlers: list[tuple[str, events.EventHandler]] = []
_ACCOUNT_MERGE_NOTIFY_REASONS = {"email_link", "telegram_link", "login"}


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _format_webapp_datetime(value: Optional[datetime]) -> str:
    if not value:
        return ""
    normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.strftime("%d.%m.%Y %H:%M")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _payment_status_timestamp(payment: Any) -> Optional[datetime]:
    """Best-effort time when a payment reached its current status."""

    updated_at = _parse_datetime(getattr(payment, "updated_at", None))
    created_at = _parse_datetime(getattr(payment, "created_at", None))
    if updated_at and created_at:
        return max(updated_at, created_at)
    return updated_at or created_at


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _has_superseding_success(
    canceled_payment: Any,
    successful_payments: Iterable[Any],
) -> bool:
    canceled_created_at = _parse_datetime(getattr(canceled_payment, "created_at", None))
    if canceled_created_at is None:
        return False
    canceled_payment_id = _int_or_none(getattr(canceled_payment, "payment_id", None))
    for payment in successful_payments:
        if (
            canceled_payment_id is not None
            and _int_or_none(getattr(payment, "payment_id", None)) == canceled_payment_id
        ):
            continue
        success_at = _payment_status_timestamp(payment)
        if success_at is not None and success_at >= canceled_created_at:
            return True
    return False


def _format_plain_amount(value: float) -> str:
    amount = float(value)
    if amount.is_integer():
        return str(int(amount))
    return f"{amount:g}"


def _tariff_display_name(settings: Any, tariff_key: Optional[str], language: str) -> str:
    if not tariff_key:
        return ""
    cfg = settings.tariffs_config
    if not cfg:
        return str(tariff_key)
    try:
        tariff = cfg.require(str(tariff_key))
        return str(tariff.name(language))
    except Exception:
        return str(tariff_key)


def _format_failed_payment_purchase(
    translate: Callable[..., str], purchase: PaymentPurchase
) -> str:
    if purchase.kind == "traffic":
        traffic_kind = translate(
            "payment_failed_traffic_kind_premium"
            if purchase.scope == "premium"
            else "payment_failed_traffic_kind_regular"
        )
        return translate(
            "payment_failed_detail_purchase_traffic",
            gb=_format_plain_amount(float(purchase.amount)),
            kind=traffic_kind,
        )
    if purchase.kind == "hwid_devices":
        return translate(
            "payment_failed_detail_purchase_hwid_devices",
            count=int(float(purchase.amount)),
        )
    label_kwargs = {
        "amount": _format_plain_amount(float(purchase.amount)),
        "unit": purchase.unit,
        "kind": purchase.kind,
        "scope": purchase.scope or "",
        **dict(purchase.label_kwargs),
    }
    if purchase.label_key:
        return translate(purchase.label_key, **label_kwargs)
    return translate("payment_failed_detail_purchase_generic", **label_kwargs)


def _failed_payment_provider_detail(
    settings: Any,
    payment: Any,
    payload: Dict[str, Any],
    language: str,
) -> str:
    provider = str(
        payload.get("provider")
        or getattr(payment, "provider", None)
        or payload.get("notification_provider")
        or ""
    ).strip()
    if not provider:
        return ""
    try:
        from bot.payment_providers import (
            iter_provider_specs,
            provider_label_map,
            resolve_provider_presentation,
        )

        specs = tuple(iter_provider_specs())
        exact_spec = next((spec for spec in specs if provider == spec.id), None)
        provider_specs = [spec for spec in specs if provider == spec.provider_key]
        provider_label = provider_label_map(settings, language=language).get(provider, provider)
        if exact_spec is not None:
            button_label = resolve_provider_presentation(
                exact_spec,
                settings,
                language=language,
            ).webapp_label
            return f"{button_label} ({provider_label}; {provider})"
        if len(provider_specs) == 1:
            button_label = resolve_provider_presentation(
                provider_specs[0],
                settings,
                language=language,
            ).webapp_label
            return f"{button_label} ({provider_label}; {provider})"
        return f"{provider_label} ({provider})"
    except Exception:
        logger.exception("Failed to resolve payment provider label for %s.", provider)
        return provider


def _format_failed_payment_details(
    *,
    translate: Callable[..., str],
    settings: Any,
    language: str,
    payment: Any,
    payload: Dict[str, Any],
) -> str:
    snapshot = resolve_payment_success_snapshot(
        payload,
        payment,
        default_currency=getattr(settings, "DEFAULT_CURRENCY", "RUB"),
    )
    lines: list[str] = []

    tariff_name = _tariff_display_name(settings, snapshot.tariff_key, language)
    if snapshot.months > 0:
        key = (
            "payment_failed_detail_subscription_with_tariff"
            if tariff_name
            else "payment_failed_detail_subscription"
        )
        lines.append(translate(key, months=snapshot.months, tariff=tariff_name))

    for purchase in snapshot.purchases:
        detail = _format_failed_payment_purchase(translate, purchase)
        if detail:
            lines.append(detail)

    if not lines:
        description = str(getattr(payment, "description", "") or "").strip()
        if description:
            lines.append(description)

    details = [translate("payment_failed_detail_item", item=line) for line in lines if line]
    details.append(
        translate(
            "payment_failed_detail_amount",
            amount=_format_plain_amount(snapshot.amount),
            currency=snapshot.currency,
        )
    )
    provider_detail = _failed_payment_provider_detail(settings, payment, payload, language)
    if provider_detail:
        details.append(translate("payment_failed_detail_provider", provider=provider_detail))
    payment_id = getattr(payment, "payment_id", None)
    if payment_id is not None:
        details.append(translate("payment_failed_detail_payment_id", payment_id=payment_id))
    return "\n".join(details)


class CoreEventReactions:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def _notification_service(self) -> Optional[NotificationService]:
        service = self.ctx.notification_service
        if service is not None:
            return service
        if self.ctx.bot is None:
            return None
        return NotificationService(
            self.ctx.bot,
            self.ctx.settings,
            self.ctx.i18n,
            session_factory=self.ctx.session_factory,
            email_auth_service=self.ctx.email_auth_service,
        )

    async def _load_user(self, user_id: Any) -> Optional[User]:
        if self.ctx.session_factory is None or user_id is None:
            return None
        try:
            async with self.ctx.session_factory() as session:
                return await user_dal.get_user_by_id(session, int(user_id))
        except Exception:
            logger.exception("Failed to load user %s for event reaction.", user_id)
            return None

    async def _load_payment(self, payment_db_id: Any) -> Optional[Payment]:
        if self.ctx.session_factory is None or payment_db_id is None:
            return None
        try:
            async with self.ctx.session_factory() as session:
                return await payment_dal.get_payment_by_db_id(session, int(payment_db_id))
        except Exception:
            logger.exception("Failed to load payment %s for event reaction.", payment_db_id)
            return None

    async def _load_active_subscription(
        self, user_id: Any, panel_user_uuid: Optional[str] = None
    ) -> Optional[Subscription]:
        if self.ctx.session_factory is None or user_id is None:
            return None
        try:
            async with self.ctx.session_factory() as session:
                return await subscription_dal.get_active_subscription_by_user_id(
                    session,
                    int(user_id),
                    panel_user_uuid,
                )
        except Exception:
            logger.exception(
                "Failed to load active subscription for user %s during event reaction.",
                user_id,
            )
            return None

    async def _payment_failure_is_superseded(self, payment: Any, user_id: Any) -> bool:
        payment_user_id = _int_or_none(getattr(payment, "user_id", None))
        event_user_id = _int_or_none(user_id)
        if payment_user_id is None or event_user_id is None or payment_user_id != event_user_id:
            return False
        if str(getattr(payment, "status", "") or "").lower() == "succeeded":
            return True
        created_at = _parse_datetime(getattr(payment, "created_at", None))
        if created_at is None or self.ctx.session_factory is None:
            return False

        try:
            async with self.ctx.session_factory() as session:
                successful_payments = await payment_dal.get_user_succeeded_payments_after(
                    session,
                    payment_user_id,
                    created_at,
                    exclude_payment_id=_int_or_none(getattr(payment, "payment_id", None)),
                )
        except Exception:
            logger.exception(
                "Failed to check superseding successful payments for payment %s.",
                getattr(payment, "payment_id", None),
            )
            return False
        return _has_superseding_success(payment, successful_payments)

    async def _release_payment_promo_activation(self, payment: Any, user_id: Any) -> None:
        promo_code_id = _int_or_none(getattr(payment, "promo_code_id", None))
        payment_id = _int_or_none(getattr(payment, "payment_id", None))
        event_user_id = _int_or_none(user_id)
        if promo_code_id is None or payment_id is None or event_user_id is None:
            return
        if self.ctx.session_factory is None:
            return
        try:
            async with self.ctx.session_factory() as session:
                released = await promo_code_dal.release_promo_activation(
                    session,
                    promo_code_id,
                    event_user_id,
                    payment_id=payment_id,
                )
                if released:
                    await session.commit()
        except Exception:
            logger.exception(
                "Failed to release code activation for payment %s.",
                payment_id,
            )

    async def on_trial_activated(self, event_name: str, payload: Dict[str, Any]) -> None:
        del event_name
        user_id = payload.get("user_id")
        if user_id is None:
            return
        user = await self._load_user(user_id)
        service = self._notification_service()
        end_date = _parse_datetime(payload.get("end_date")) or datetime.now(timezone.utc)
        if service is not None:
            try:
                await service.notify_trial_activation(
                    int(user_id),
                    end_date,
                    username=getattr(user, "username", None),
                    email=getattr(user, "email", None),
                )
            except Exception:
                logger.exception("Failed to react to trial activation for user %s.", user_id)

        try:
            await invalidate_webapp_user_caches(
                self.ctx.settings,
                int(user_id),
                include_devices=True,
            )
        except Exception:
            logger.exception("Failed to invalidate trial caches for user %s.", user_id)

    async def on_user_registered(self, event_name: str, payload: Dict[str, Any]) -> None:
        del event_name
        if payload.get("registered_via") == "panel_sync":
            return
        user_id = payload.get("user_id")
        if user_id is None:
            return
        user = await self._load_user(user_id)
        service = self._notification_service()
        if service is None:
            return

        referred_by_id = payload.get("referred_by_id")
        email = payload.get("email") or getattr(user, "email", None)
        try:
            if payload.get("registered_via") == "email":
                if not email:
                    return
                await service.notify_new_email_user_registration(
                    user_id=int(user_id),
                    email=str(email),
                    referred_by_id=referred_by_id,
                )
            else:
                await service.notify_new_user_registration(
                    user_id=int(user_id),
                    username=payload.get("username") or getattr(user, "username", None),
                    first_name=payload.get("first_name") or getattr(user, "first_name", None),
                    email=email,
                    referred_by_id=referred_by_id,
                )
        except Exception:
            logger.exception("Failed to react to user registration for user %s.", user_id)

    async def on_promo_code_applied(self, event_name: str, payload: Dict[str, Any]) -> None:
        del event_name
        user_id = payload.get("user_id")
        if user_id is None:
            return
        service = self._notification_service()
        if service is None:
            return
        user = await self._load_user(user_id)
        try:
            await service.notify_promo_activation(
                user_id=int(user_id),
                promo_code=str(payload.get("code") or ""),
                bonus_days=int(payload.get("bonus_days") or 0),
                username=getattr(user, "username", None),
                email=getattr(user, "email", None),
            )
        except Exception:
            logger.exception("Failed to react to promo activation for user %s.", user_id)

    async def on_account_email_linked(self, event_name: str, payload: Dict[str, Any]) -> None:
        del event_name
        if not _truthy(payload.get("first_link")):
            return
        user_id = payload.get("user_id")
        email = payload.get("email")
        if user_id is None or not email:
            return
        service = self._notification_service()
        if service is None:
            return
        user = await self._load_user(user_id)
        try:
            await service.notify_account_email_linked(
                user_id=int(user_id),
                email=str(email),
                telegram_id=payload.get("telegram_id") or getattr(user, "telegram_id", None),
                username=payload.get("username") or getattr(user, "username", None),
                first_name=payload.get("first_name") or getattr(user, "first_name", None),
            )
        except Exception:
            logger.exception("Failed to react to email link for user %s.", user_id)

    async def on_account_telegram_linked(self, event_name: str, payload: Dict[str, Any]) -> None:
        del event_name
        if not _truthy(payload.get("first_link")):
            return
        user_id = payload.get("user_id")
        telegram_id = payload.get("telegram_id")
        if user_id is None or not telegram_id:
            return
        service = self._notification_service()
        if service is None:
            return
        user = await self._load_user(user_id)
        try:
            await service.notify_account_telegram_linked(
                user_id=int(user_id),
                email=payload.get("email") or getattr(user, "email", None),
                telegram_id=int(telegram_id),
                username=payload.get("username") or getattr(user, "username", None),
                first_name=payload.get("first_name") or getattr(user, "first_name", None),
            )
        except Exception:
            logger.exception("Failed to react to Telegram link for user %s.", user_id)

    async def on_payment_succeeded(self, event_name: str, payload: Dict[str, Any]) -> None:
        del event_name
        user_id = payload.get("user_id")
        if user_id is None:
            return
        user = await self._load_user(user_id)
        payment = await self._load_payment(payload.get("payment_db_id"))
        service = self._notification_service()
        if service is not None:
            try:
                snapshot = resolve_payment_success_snapshot(
                    payload,
                    payment,
                    default_currency=getattr(self.ctx.settings, "DEFAULT_CURRENCY", "RUB"),
                )
                await service.notify_payment_received(
                    user_id=int(user_id),
                    amount=snapshot.amount,
                    currency=snapshot.currency,
                    months=snapshot.months,
                    traffic_gb=snapshot.traffic_gb,
                    payment_provider=snapshot.notification_provider,
                    username=getattr(user, "username", None),
                    email=getattr(user, "email", None),
                    traffic_is_premium=snapshot.traffic_is_premium,
                    tariff_key=snapshot.tariff_key,
                    purchased_hwid_devices=snapshot.purchased_hwid_devices,
                    purchases=snapshot.purchases,
                )
            except Exception:
                logger.exception("Failed to react to successful payment for user %s.", user_id)

        try:
            # In worker processes this clears the shared Redis layer; backend
            # in-process caches keep their normal short TTL until pub/sub
            # invalidation exists.
            await invalidate_webapp_user_caches(
                self.ctx.settings,
                int(user_id),
                include_devices=True,
            )
        except Exception:
            logger.exception("Failed to invalidate payment caches for user %s.", user_id)

    async def on_payment_canceled(self, event_name: str, payload: Dict[str, Any]) -> None:
        del event_name
        user_id = payload.get("user_id")
        if user_id is None:
            return
        payment = await self._load_payment(payload.get("payment_db_id"))
        if payment is not None:
            await self._release_payment_promo_activation(payment, user_id)
        if self.ctx.bot is None:
            return
        if payment is not None and await self._payment_failure_is_superseded(payment, user_id):
            logger.info(
                "Suppressing canceled payment notification for user %s payment %s: "
                "a newer successful payment already superseded it.",
                user_id,
                getattr(payment, "payment_id", None),
            )
            return
        user = await self._load_user(user_id)
        language = (
            getattr(user, "language_code", None)
            or getattr(self.ctx.settings, "DEFAULT_LANGUAGE", "ru")
            or "ru"
        )
        translator = make_translator(self.ctx.i18n, language)
        message_text = translator(payload.get("message_key") or "payment_failed")
        if payment is not None:
            try:
                payment_details = _format_failed_payment_details(
                    translate=translator,
                    settings=self.ctx.settings,
                    language=language,
                    payment=payment,
                    payload=payload,
                )
                if payment_details:
                    message_text = translator(
                        "payment_failed_with_details",
                        message=message_text,
                        details=payment_details,
                    )
            except Exception:
                logger.exception(
                    "Failed to format canceled payment details for payment %s.",
                    getattr(payment, "payment_id", None),
                )
        try:
            await self.ctx.bot.send_message(int(user_id), message_text)
        except Exception:
            logger.exception("Failed to notify user %s about canceled payment.", user_id)
        if user is not None:
            await send_user_notification_email(
                settings=self.ctx.settings,
                i18n=self.ctx.i18n,
                user=user,
                subject_key="email_payment_failed_subject",
                message_text=message_text,
                dashboard_url=(getattr(self.ctx.settings, "SUBSCRIPTION_MINI_APP_URL", "") or None),
            )

    async def on_referral_bonus_granted(self, event_name: str, payload: Dict[str, Any]) -> None:
        del event_name
        if not _truthy(payload.get("inviter_bonus_applied")):
            return
        inviter_user_id = payload.get("inviter_user_id")
        inviter_bonus_days = int(payload.get("inviter_bonus_days") or 0)
        if inviter_user_id is None or inviter_bonus_days <= 0 or self.ctx.bot is None:
            return
        inviter = await self._load_user(inviter_user_id)
        if inviter is None:
            return
        language = (
            getattr(inviter, "language_code", None)
            or getattr(self.ctx.settings, "DEFAULT_LANGUAGE", "ru")
            or "ru"
        )
        translator = make_translator(self.ctx.i18n, language)
        end_date = _parse_datetime(payload.get("inviter_bonus_end_date"))
        message_key = (
            "referral_bonus_inviter_notification_new_sub"
            if payload.get("inviter_bonus_kind") == "new_sub"
            else "referral_bonus_inviter_notification_extended"
        )
        message_text = translator(
            message_key,
            days=inviter_bonus_days,
            referee_name=payload.get("referee_name") or f"User {payload.get('referee_user_id')}",
            new_end_date=end_date.strftime("%Y-%m-%d") if end_date else "",
        )
        try:
            await self.ctx.bot.send_message(int(inviter_user_id), message_text)
        except Exception:
            logger.exception(
                "Failed to send referral bonus notification to inviter %s.",
                inviter_user_id,
            )
        await send_user_notification_email(
            settings=self.ctx.settings,
            i18n=self.ctx.i18n,
            user=inviter,
            subject_key="email_referral_bonus_subject",
            message_text=message_text,
            dashboard_url=(getattr(self.ctx.settings, "SUBSCRIPTION_MINI_APP_URL", "") or None),
        )

    async def on_account_merged(self, event_name: str, payload: Dict[str, Any]) -> None:
        del event_name
        reason = str(payload.get("reason") or "")
        if reason not in _ACCOUNT_MERGE_NOTIFY_REASONS:
            return

        target_user_id = payload.get("target_user_id")
        source_user_id = payload.get("source_user_id")
        if target_user_id is None or source_user_id is None:
            return

        service = self._notification_service()
        final_end_date = _parse_datetime(payload.get("final_end_date"))
        if final_end_date is None:
            subscription = await self._load_active_subscription(
                target_user_id,
                payload.get("target_panel_user_uuid"),
            )
            final_end_date = getattr(subscription, "end_date", None)

        if service is not None:
            try:
                await service.notify_account_merged(
                    primary_user_id=int(target_user_id),
                    removed_user_id=int(source_user_id),
                    email=payload.get("email"),
                    telegram_id=payload.get("telegram_id"),
                    username=payload.get("username"),
                    first_name=payload.get("first_name"),
                    final_end_date_text=_format_webapp_datetime(final_end_date),
                    primary_panel_user_uuid=payload.get("target_panel_user_uuid"),
                    removed_panel_user_uuid=payload.get("source_panel_user_uuid"),
                )
            except Exception:
                logger.exception(
                    "Failed to react to account merge %s -> %s.",
                    source_user_id,
                    target_user_id,
                )

        email_service = self.ctx.email_auth_service
        email = str(payload.get("email") or "").strip()
        if email_service is not None and email and _truthy(payload.get("send_user_email")):
            try:
                content = render_account_merged(
                    self.ctx.settings,
                    language_code=payload.get("language")
                    or getattr(self.ctx.settings, "DEFAULT_LANGUAGE", "ru"),
                    primary_user_id=int(target_user_id),
                    removed_user_id=int(source_user_id),
                    final_end_date_text=_format_webapp_datetime(final_end_date),
                    i18n=self.ctx.i18n,
                )
                await email_service.send_rendered_email(email=email, content=content)
            except Exception:
                logger.exception("Failed to send account merge email to %s.", email)


def register_core_reactions(ctx: PluginContext) -> None:
    """Subscribe built-in side-effect reactions to domain events."""
    for event_name, handler in _registered_handlers:
        events.unsubscribe(event_name, handler)
    _registered_handlers.clear()

    reactions = CoreEventReactions(ctx)
    subscriptions: list[tuple[str, events.EventHandler]] = [
        (events.TRIAL_ACTIVATED, reactions.on_trial_activated),
        (events.USER_REGISTERED, reactions.on_user_registered),
        (events.PROMO_CODE_APPLIED, reactions.on_promo_code_applied),
        (events.ACCOUNT_EMAIL_LINKED, reactions.on_account_email_linked),
        (events.ACCOUNT_TELEGRAM_LINKED, reactions.on_account_telegram_linked),
        (events.PAYMENT_SUCCEEDED, reactions.on_payment_succeeded),
        (events.PAYMENT_CANCELED, reactions.on_payment_canceled),
        (events.REFERRAL_BONUS_GRANTED, reactions.on_referral_bonus_granted),
        (events.ACCOUNT_MERGED, reactions.on_account_merged),
    ]
    for event_name, handler in subscriptions:
        events.subscribe(event_name, handler)
    _registered_handlers.extend(subscriptions)
