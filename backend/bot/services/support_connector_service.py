"""Owner-scoped reads and atomic conditional replies for external processors."""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from bot.services.message_composition import MessageButtonInput, resolve_message_buttons
from bot.services.support_connector_contracts import (
    SupportConnectorConflict,
    SupportConnectorReply,
    SupportContextMessage,
    SupportTicketContext,
)
from bot.services.support_connector_diagnostics import connection_diagnostics
from bot.services.support_message_buttons import encode_support_buttons
from bot.utils.mini_app_url import subscription_public_install_url
from db.dal import support_dal, user_dal
from db.models import Payment, Subscription, SupportTicket, SupportTicketMessage

if TYPE_CHECKING:
    from bot.services.support_service import SupportService

_FACT_KEYS = (
    "language",
    "subscription_active",
    "panel_status",
    "end_date",
    "tariff",
    "traffic_regular",
    "traffic_premium",
    "is_throttled",
    "topup_balance_bytes",
    "premium_topup_balance_bytes",
    "device_limit",
)


async def get_ticket_context(
    service: SupportService,
    ticket_id: int,
    *,
    expected_user_id: int,
    after_message_id: int | None = None,
) -> SupportTicketContext:
    from bot.services.support_service import TicketNotFound

    async with service.session_factory() as session:
        # Writers use this same lock. The projection and revision describe one
        # coherent conversation; the session closes before external processing.
        result = await session.execute(
            select(SupportTicket)
            .where(SupportTicket.ticket_id == ticket_id, SupportTicket.user_id == expected_user_id)
            .with_for_update()
        )
        ticket = result.scalar_one_or_none()
        if ticket is None:
            raise TicketNotFound("not_found")
        user = await user_dal.get_user_by_id(session, expected_user_id)
        if user is None:
            raise TicketNotFound("not_found")
        snapshot = await service.build_user_snapshot(user, session=session)
        facts: dict[str, object] = {key: snapshot[key] for key in _FACT_KEYS if key in snapshot}
        payment_result = await session.execute(
            select(Payment)
            .where(Payment.user_id == expected_user_id)
            .order_by(Payment.created_at.desc(), Payment.payment_id.desc())
            .limit(10)
        )
        payments = list(payment_result.scalars().all())
        payment = payments[0] if payments else None
        facts["latest_payment"] = (
            None
            if payment is None
            else {
                "status": str(payment.status),
                "amount": float(payment.amount),
                "currency": str(payment.currency),
                "created_at": payment.created_at.isoformat() if payment.created_at else None,
                "updated_at": payment.updated_at.isoformat() if payment.updated_at else None,
            }
        )
        payment_facts = [
            {
                "status": str(item.status),
                "amount": float(item.amount),
                "currency": str(item.currency),
                "provider": str(item.provider),
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            }
            for item in payments
        ]
        for item, projected in zip(payments, payment_facts, strict=True):
            projected.update(
                {
                    "sale_mode": item.sale_mode,
                    "tariff": item.tariff_key,
                    "subscription_days": item.subscription_duration_days,
                    "subscription_months": item.subscription_duration_months,
                    "traffic_gb": item.purchased_gb,
                    "devices": item.purchased_hwid_devices,
                    "auto_renew": bool(item.is_auto_renew),
                }
            )
        facts["payments"] = payment_facts
        payment_counts = await session.execute(
            select(Payment.status, func.count())
            .where(Payment.user_id == expected_user_id)
            .group_by(Payment.status)
        )
        facts["payment_status_counts"] = {
            str(status): int(count) for status, count in payment_counts
        }
        panel_uuid = str(user.panel_user_uuid or "") or None
        subscription = (
            (
                await session.execute(
                    select(Subscription)
                    .where(
                        Subscription.user_id == expected_user_id,
                        Subscription.panel_user_uuid == panel_uuid,
                    )
                    .order_by(Subscription.is_active.desc(), Subscription.subscription_id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if panel_uuid
            else None
        )
        short_uuid = (
            (str(subscription.install_share_panel_short_uuid or "") or None)
            if subscription
            else None
        )
        facts["last_connected_at"] = (
            subscription.last_connected_at.isoformat()
            if subscription and subscription.last_connected_at
            else None
        )
        facts["subscription_active"] = bool(
            subscription
            and subscription.is_active
            and subscription.end_date
            and (
                subscription.end_date
                if subscription.end_date.tzinfo
                else subscription.end_date.replace(tzinfo=UTC)
            )
            > datetime.now(UTC)
        )
        facts["installation_url"] = (
            subscription_public_install_url(service.settings, subscription.install_share_token)
            if subscription and subscription.install_share_token
            else None
        )
        facts["account_binding"] = hashlib.sha256((panel_uuid or "").encode()).hexdigest()
        facts["database_source"] = "current"
        facts["source_updated_at"] = datetime.now(UTC).isoformat()
        # Bound history independently of the DAL's unrestricted operator read.
        query = select(SupportTicketMessage).where(
            SupportTicketMessage.ticket_id == ticket_id,
            SupportTicketMessage.is_internal_note.is_(False),
        )
        if after_message_id is not None:
            query = query.where(SupportTicketMessage.message_id > after_message_id)
        rows = list(
            (
                await session.execute(
                    query.order_by(SupportTicketMessage.message_id.desc()).limit(100)
                )
            )
            .scalars()
            .all()
        )
        rows.reverse()
        context = SupportTicketContext(
            ticket_id=int(ticket.ticket_id),
            user_id=int(ticket.user_id),
            revision=int(ticket.revision),
            change_cursor=int(ticket.change_cursor),
            status=str(ticket.status),
            category=str(ticket.category),
            last_message_role=ticket.last_message_role,
            assigned_admin_id=ticket.assigned_admin_id,
            last_message_id=int(rows[-1].message_id) if rows else int(after_message_id or 0),
            messages=tuple(
                SupportContextMessage(
                    message_id=int(message.message_id),
                    author_role=str(message.author_role),
                    body=str(message.body),
                    body_format=str(message.body_format),
                    has_image=bool(message.image_id),
                    created_at=message.created_at,
                )
                for message in rows
            ),
            facts=facts,
            observed_at=datetime.now(UTC),
        )

    diagnostics = await connection_diagnostics(service.settings, panel_uuid, short_uuid)
    if diagnostics.get("last_connected_at") is None:
        diagnostics.pop("last_connected_at", None)
        diagnostics["connection_source"] = (
            "database" if facts.get("last_connected_at") else "unavailable"
        )
    else:
        diagnostics["connection_source"] = "live"
    async with service.session_factory() as session:
        owner = await user_dal.get_user_by_id(session, expected_user_id)
        current = (
            await session.execute(
                select(SupportTicket).where(
                    SupportTicket.ticket_id == ticket_id, SupportTicket.user_id == expected_user_id
                )
            )
        ).scalar_one_or_none()
        if (
            owner is None
            or owner.is_banned
            or current is None
            or str(owner.panel_user_uuid or "") != str(panel_uuid or "")
        ):
            raise SupportConnectorConflict("owner_unavailable")
        if int(current.revision) != context.revision:
            raise SupportConnectorConflict("stale_revision")
    return replace(context, facts={**facts, **diagnostics})


def encode_reply_buttons(service: SupportService, buttons: list[MessageButtonInput]) -> str | None:
    return encode_support_buttons(
        resolve_message_buttons(
            buttons,
            mini_app_url=getattr(service.settings, "SUBSCRIPTION_MINI_APP_URL", None),
            bot_username=None,
        )
    )


async def reply_from_connector(
    service: SupportService,
    ticket_id: int,
    body: str,
    *,
    expected_user_id: int,
    expected_revision: int,
    idempotency_key: str,
    source: str,
    author_label: str,
    buttons: list[MessageButtonInput] | None = None,
    expected_account_binding: str | None = None,
    replay_only: bool = False,
) -> SupportConnectorReply:
    from bot.services.support_service import TicketNotFound

    if (
        type(replay_only) is not bool
        or (
            expected_account_binding is not None
            and not re.fullmatch(r"[0-9a-f]{64}", expected_account_binding)
        )
        or not re.fullmatch(r"[a-z][a-z0-9_.:-]{0,63}", source)
        or not 1 <= len(idempotency_key) <= 160
        or not 1 <= len(author_label.strip()) <= 160
        or any(ord(character) < 32 for character in author_label + idempotency_key)
    ):
        raise ValueError("invalid_support_connector_identity")
    stored_body, stored_format = service._prepare_body(body, "text")
    encoded_buttons = encode_reply_buttons(service, buttons or [])
    async with service.session_factory() as session:
        # Match ordinary customer writes: owner first, then ticket. Revocation
        # therefore cannot commit between the owner check and reply commit.
        user = await user_dal.lock_user_by_id(session, expected_user_id)
        result = await session.execute(
            select(SupportTicket).where(SupportTicket.ticket_id == ticket_id).with_for_update()
        )
        ticket = result.scalar_one_or_none()
        if ticket is None:
            raise TicketNotFound("not_found")
        if ticket.user_id != expected_user_id:
            raise SupportConnectorConflict("owner_mismatch")
        existing = (
            await session.execute(
                select(SupportTicketMessage).where(
                    SupportTicketMessage.ticket_id == ticket_id,
                    SupportTicketMessage.connector_source == source,
                    SupportTicketMessage.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if (
                existing.body != stored_body
                or existing.author_label != author_label.strip()
                or existing.buttons != encoded_buttons
            ):
                raise SupportConnectorConflict("idempotency_mismatch")
            return SupportConnectorReply(
                ticket_id, int(existing.message_id), int(ticket.revision), True
            )
        if replay_only:
            raise SupportConnectorConflict("reply_not_committed")
        if expected_account_binding is not None and user is not None:
            current_binding = hashlib.sha256(str(user.panel_user_uuid or "").encode()).hexdigest()
            if current_binding != expected_account_binding:
                raise SupportConnectorConflict("account_binding_changed")
        if int(ticket.revision) != expected_revision:
            raise SupportConnectorConflict("stale_revision")
        if ticket.status not in {"open", "awaiting_admin"}:
            raise SupportConnectorConflict("closed_or_answered")
        if ticket.assigned_admin_id is not None:
            raise SupportConnectorConflict("assigned")
        if not service.settings.support_settings.tickets_enabled:
            raise SupportConnectorConflict("disabled")
        if user is None or user.is_banned:
            raise SupportConnectorConflict("owner_unavailable")
        message = await support_dal.add_message(
            session,
            ticket_id,
            "connector",
            None,
            stored_body,
            body_format=stored_format,
            connector_source=source,
            author_label=author_label.strip(),
            idempotency_key=idempotency_key,
            buttons=encoded_buttons,
        )
        if message is None:
            raise TicketNotFound("not_found")
        await session.refresh(ticket)
        await session.commit()
    await service._emit_message_created(ticket, message)
    service._schedule_notification(
        service.notification_service.notify_support_admin_reply(ticket, message, user),
        "Failed to notify user about support connector reply %s",
        ticket_id,
    )
    return SupportConnectorReply(ticket_id, int(message.message_id), int(ticket.revision), False)
