"""Owner-scoped reads and atomic conditional replies for external processors."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from bot.services.support_connector_contracts import (
    SupportConnectorConflict,
    SupportConnectorReply,
    SupportContextMessage,
    SupportTicketContext,
)
from db.dal import support_dal, user_dal
from db.models import Payment, SupportTicket, SupportTicketMessage

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
            .limit(1)
        )
        payment = payment_result.scalar_one_or_none()
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
        return SupportTicketContext(
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
) -> SupportConnectorReply:
    from bot.services.support_service import TicketNotFound

    if (
        not re.fullmatch(r"[a-z][a-z0-9_.:-]{0,63}", source)
        or not 1 <= len(idempotency_key) <= 160
        or not 1 <= len(author_label.strip()) <= 160
        or any(ord(character) < 32 for character in author_label + idempotency_key)
    ):
        raise ValueError("invalid_support_connector_identity")
    stored_body, stored_format = service._prepare_body(body, "text")
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
            if existing.body != stored_body or existing.author_label != author_label.strip():
                raise SupportConnectorConflict("idempotency_mismatch")
            return SupportConnectorReply(
                ticket_id, int(existing.message_id), int(ticket.revision), True
            )
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
