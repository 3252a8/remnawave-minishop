"""Queue Minishop events and deliver blacklist alerts from the worker."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import cast

from aiogram.exceptions import TelegramAPIError
from pydantic import JsonValue
from sqlalchemy import Select, exists, literal, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from bot.infra import events
from bot.plugins.capabilities import CORE_PLUGIN_CAPABILITIES
from bot.plugins.extensions import (
    DurableSubscription,
    ExtensionContributions,
    ExtensionError,
    JobHandler,
    OperationContext,
)
from bot.plugins.extensions.jobs import enqueue
from bot.plugins.packages import generation_is_current
from bot.plugins.spec import PluginContext
from db.models import Payment, Subscription, User
from db.subscription_notification_models import SubscriptionLifecycleNotification

from .alert_text import render_alert
from .settings import EventName
from .storage import get_matches
from .storage_models import Configuration, Entry, Source

PLUGIN_ID = "minishop-blacklist"
_ALERT_JOB = "send-alert"
_PAYMENT_JOB = "send-payment-alert"
_REQUEST_TIMEOUT = 25
_BUS_EVENTS: dict[str, EventName] = {
    events.USER_REGISTERED: "register",
    events.TRIAL_ACTIVATED: "trial",
    events.SUBSCRIPTION_EXPIRED: "expired",
}
logger = logging.getLogger(__name__)


def _positive_id(value: object) -> int | None:
    return value if type(value) is int and 0 < value < 2**63 else None


def _account_id(value: object) -> int | None:
    return value if type(value) is int and -(2**63) <= value < 2**63 and value != 0 else None


def _event_date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def event_job(
    event: EventName, payload: dict[str, object]
) -> tuple[str, dict[str, JsonValue]] | None:
    user_id = _account_id(payload.get("user_id"))
    if user_id is None:
        return None
    data: dict[str, JsonValue] = {"event": event, "user_id": user_id}
    if event == "register":
        telegram_id = _positive_id(payload.get("telegram_id"))
        if telegram_id is None or payload.get("registered_via") == "panel_sync":
            return None
        data["telegram_id"] = telegram_id
        return f"register:{user_id}:{telegram_id}", data

    end_date = _event_date(payload.get("end_date"))
    if end_date is None:
        return None
    data["end_date"] = end_date.isoformat()
    if event == "trial":
        return f"trial:{user_id}:{end_date.isoformat()}", data
    if event == "expired":
        subscription_id = _positive_id(payload.get("subscription_id"))
        if subscription_id is not None:
            data["subscription_id"] = subscription_id
            return f"expired:{subscription_id}:{end_date.isoformat()}", data
    return None


def _destination(event: EventName) -> Select[tuple[int | None, int | None]]:
    return select(Configuration.chat_id, Configuration.topic_id).where(
        Configuration.id == 1,
        Configuration.chat_id.is_not(None),
        Configuration.events.contains([event]),
        exists().select_from(Source),
    )


def _may_need_alert(
    event: EventName, user_id: int | InstrumentedAttribute[int], telegram_id: int | None = None
) -> ColumnElement[bool]:
    account = (
        select(User.telegram_id)
        .where(User.user_id == user_id)
        .correlate_except(User)
        .scalar_subquery()
    )
    tid = literal(telegram_id) if telegram_id is not None else account
    # Queue an inconclusive event so the worker can retry after registration
    # commits or a source recovers. A covered miss needs no durable operation.
    candidate = _destination(event).where(
        or_(
            tid.is_(None),
            exists().where(Entry.telegram_id == tid),
            exists().where(or_(Source.last_success_at.is_(None), Source.last_error.is_not(None))),
        )
    )
    return candidate.exists()


def subscribe_to_events(ctx: PluginContext) -> None:
    session_factory = ctx.require_session_factory()

    async def receive(event_name: str, payload: dict[str, object]) -> None:
        event = _BUS_EVENTS[event_name]
        if not generation_is_current():
            return
        candidate = event_job(event, payload)
        if candidate is None:
            return
        key, data = candidate
        try:
            async with session_factory.begin() as session:
                eligible = _may_need_alert(
                    event, cast(int, data["user_id"]), _positive_id(data.get("telegram_id"))
                )
                if not await session.scalar(select(eligible)):
                    return
                # Registration can precede commit. Store the ID in the payload to
                # avoid a foreign-key check against the publishing transaction.
                await enqueue(
                    session, job=f"{PLUGIN_ID}:{_ALERT_JOB}", idempotency_key=key, payload=data
                )
        except (SQLAlchemyError, ExtensionError):
            logger.warning("Could not queue blacklist alert for event %s", event_name)

    for event_name in _BUS_EVENTS:
        events.subscribe(event_name, receive)

    async def balance_payment(_name: str, payload: dict[str, object]) -> None:
        # In 3.8.5, adding funds to the balance skips the transactional payment
        # subscription. The public event is emitted after the credit commits.
        sale_mode = payload.get("sale_mode")
        payment_id = _positive_id(payload.get("payment_db_id"))
        if (
            payment_id is None
            or not isinstance(sale_mode, str)
            or sale_mode.split("@", 1)[0].split("|", 1)[0] != "balance_topup"
            or not generation_is_current()
        ):
            return
        try:
            async with session_factory.begin() as session:
                payment = await session.scalar(
                    select(Payment).where(
                        Payment.payment_id == payment_id,
                        Payment.status == "succeeded",
                        Payment.amount > 0,
                        _may_need_alert("payment", Payment.user_id),
                    )
                )
                if payment is None:
                    return
                await enqueue(
                    session,
                    job=f"{PLUGIN_ID}:{_PAYMENT_JOB}",
                    idempotency_key=f"balance-topup:{payment_id}",
                    payload={"payload": {"payment_db_id": payment_id, "amount": payment.amount}},
                    user_id=int(payment.user_id),
                )
        except (SQLAlchemyError, ExtensionError):
            logger.warning("Could not queue blacklist alert for a balance top-up")

    events.subscribe(events.PAYMENT_SUCCEEDED, balance_payment)


async def _action_committed(
    session: AsyncSession, event: EventName, user_id: int, payload: dict[str, JsonValue]
) -> bool:
    if event in ("register", "payment"):
        # At this point the registered account, or the payment's transactional job,
        # has already been found by the worker.
        return True
    end_date = _event_date(payload.get("end_date"))
    if end_date is None:
        return False
    if event == "trial":
        query = select(
            exists().where(
                Subscription.user_id == user_id,
                Subscription.end_date == end_date,
                or_(Subscription.status_from_panel == "TRIAL", Subscription.provider == "trial"),
            )
        )
    else:
        query = select(
            exists().where(
                SubscriptionLifecycleNotification.subscription_id == Subscription.subscription_id,
                Subscription.subscription_id == payload.get("subscription_id"),
                Subscription.user_id == user_id,
                SubscriptionLifecycleNotification.notification_key == "expired:event",
                SubscriptionLifecycleNotification.period_end_date == end_date,
            )
        )
    return bool(await session.scalar(query))


async def _deliver(
    operation: OperationContext, event: EventName, payload: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    user_id = _account_id(operation.user_id) or _account_id(payload.get("user_id"))
    if user_id is None:
        return {"sent": False}
    ctx = operation.runtime
    async with ctx.require_session_factory()() as session:
        destination = (await session.execute(_destination(event))).one_or_none()
        if destination is None:
            return {"sent": False}
        chat_id, topic_id = destination
        user = await session.get(User, user_id)
        if user is None or not await _action_committed(session, event, user_id, payload):
            raise ExtensionError("blacklist_event_not_committed", 502)
        telegram_id = _positive_id(user.telegram_id)
        if telegram_id is None or (
            event == "register" and telegram_id != payload.get("telegram_id")
        ):
            return {"sent": False}

        match = (await get_matches(session, [telegram_id]))[telegram_id]
        if match.state == "unknown":
            raise ExtensionError("blacklist_sources_pending", 502)
        if match.state != "match":
            return {"sent": False}
        text, keyboard = render_alert(ctx, event, user, telegram_id, match)

    bot = ctx.bot
    if bot is None:
        raise ExtensionError("blacklist_telegram_unavailable", 502)
    operation.assert_current()
    try:
        async with asyncio.timeout(_REQUEST_TIMEOUT):
            result = await bot.send_message(
                chat_id=chat_id,
                message_thread_id=topic_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=keyboard,
            )
    except (TelegramAPIError, TimeoutError) as exc:
        raise ExtensionError("blacklist_telegram_send_failed", 502) from exc
    return {"sent": True, "message_id": result.message_id}


async def _send_event(
    operation: OperationContext, payload: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    event = payload.get("event")
    if event == "register":
        return await _deliver(operation, "register", payload)
    if event == "trial":
        return await _deliver(operation, "trial", payload)
    if event == "expired":
        return await _deliver(operation, "expired", payload)
    return {"sent": False}


async def _send_payment(
    operation: OperationContext, payload: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    payment = payload.get("payload")
    if not isinstance(payment, dict) or _positive_id(payment.get("payment_db_id")) is None:
        return {"sent": False}
    amount = payment.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not amount > 0:
        return {"sent": False}
    return await _deliver(operation, "payment", payment)


def alert_contributions() -> ExtensionContributions:
    if CORE_PLUGIN_CAPABILITIES.get("durable_jobs", 0) >= 2:
        payment = DurableSubscription(
            events.PAYMENT_SUCCEEDED, _PAYMENT_JOB, enabled_when=_destination("payment").exists()
        )
    else:
        payment = DurableSubscription(events.PAYMENT_SUCCEEDED, _PAYMENT_JOB)
    return ExtensionContributions(
        jobs=(
            JobHandler(_ALERT_JOB, _send_event),
            JobHandler(_PAYMENT_JOB, _send_payment),
        ),
        events=(payment,),
    )
