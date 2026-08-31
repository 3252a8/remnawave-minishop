# SQLAlchemy legacy Column declarations expose instance attributes as Column[T]
# to mypy; this DAL intentionally mutates loaded ORM instances.
# mypy: disable-error-code="assignment,arg-type"

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Payment, User
from db.partner_models import (
    PartnerApplication,
    PartnerAuditEvent,
    PartnerClient,
    PartnerCommission,
    PartnerLedgerEntry,
    PartnerProfile,
    PartnerWithdrawal,
)

from .partner_reporting_dal import (
    attention_counts as attention_counts,
)
from .partner_reporting_dal import (
    list_profiles as list_profiles,
)
from .partner_reporting_dal import (
    overview_metrics as overview_metrics,
)
from .partner_reporting_dal import (
    overview_series as overview_series,
)
from .partner_reporting_dal import (
    referral_import_candidates as referral_import_candidates,
)
from .partner_withdrawal_dal import (
    active_withdrawal_count as active_withdrawal_count,
)
from .partner_withdrawal_dal import (
    active_withdrawal_methods_in_use as active_withdrawal_methods_in_use,
)
from .partner_withdrawal_dal import (
    create_audit_event as create_audit_event,
)
from .partner_withdrawal_dal import (
    create_withdrawal as create_withdrawal,
)
from .partner_withdrawal_dal import (
    get_withdrawal_by_id as get_withdrawal_by_id,
)
from .partner_withdrawal_dal import (
    get_withdrawal_by_idempotency_key as get_withdrawal_by_idempotency_key,
)
from .partner_withdrawal_dal import (
    latest_withdrawal_for_partner as latest_withdrawal_for_partner,
)
from .partner_withdrawal_dal import (
    list_withdrawals as list_withdrawals,
)
from .partner_withdrawal_dal import (
    purge_expired_partner_data as purge_expired_partner_data,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


async def get_profile_by_id(
    session: AsyncSession,
    partner_id: int,
    *,
    for_update: bool = False,
) -> PartnerProfile | None:
    statement = select(PartnerProfile).where(PartnerProfile.partner_id == partner_id)
    if for_update:
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


async def get_profiles_by_ids(
    session: AsyncSession,
    partner_ids: list[int],
) -> dict[int, PartnerProfile]:
    unique = {int(value) for value in partner_ids}
    if not unique:
        return {}
    statement = select(PartnerProfile).where(PartnerProfile.partner_id.in_(unique))
    profiles = (await session.execute(statement)).scalars().all()
    return {int(profile.partner_id): profile for profile in profiles}


async def get_profile_by_user_id(
    session: AsyncSession,
    user_id: int,
    *,
    for_update: bool = False,
) -> PartnerProfile | None:
    statement = select(PartnerProfile).where(PartnerProfile.user_id == user_id)
    if for_update:
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


async def get_profile_by_code(
    session: AsyncSession,
    partner_code: str,
    *,
    for_update: bool = False,
) -> PartnerProfile | None:
    statement = select(PartnerProfile).where(PartnerProfile.partner_code == partner_code)
    if for_update:
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


async def create_profile(
    session: AsyncSession,
    *,
    user_id: int,
    partner_code: str,
    display_label: str,
    commission_bps: int,
    welcome_message: str | None = None,
) -> PartnerProfile:
    profile = PartnerProfile(
        user_id=user_id,
        partner_code=partner_code,
        display_label_snapshot=display_label,
        commission_bps=commission_bps,
        welcome_message=welcome_message,
        status="active",
        activated_at=utcnow(),
    )
    session.add(profile)
    await session.flush()
    return profile


async def list_users_without_partner_profile(
    session: AsyncSession,
    *,
    limit: int,
) -> list[User]:
    statement = (
        select(User)
        .outerjoin(PartnerProfile, PartnerProfile.user_id == User.user_id)
        .where(
            PartnerProfile.partner_id.is_(None),
            User.is_banned.is_not(True),
        )
        .order_by(User.user_id)
        .limit(limit)
    )
    rows = await session.execute(statement)
    return list(rows.scalars().all())


async def create_profiles_bulk(
    session: AsyncSession,
    *,
    profiles: list[dict[str, Any]],
    actor_user_id: int | None,
) -> dict[int, int]:
    """Insert profile rows without replacing concurrent or moderated profiles."""

    if not profiles:
        return {}
    bind = session.get_bind()
    insert_factory = sqlite_insert if bind.dialect.name == "sqlite" else postgresql_insert
    statement = (
        insert_factory(PartnerProfile)
        .values(profiles)
        .on_conflict_do_nothing()
        .returning(
            PartnerProfile.partner_id,
            PartnerProfile.user_id,
            PartnerProfile.commission_bps,
        )
    )
    result = await session.execute(statement)
    created: list[tuple[int, int, int]] = [
        (int(partner_id), int(user_id), int(commission_bps))
        for partner_id, user_id, commission_bps in result.all()
        if user_id is not None
    ]
    actor_type = "admin" if actor_user_id is not None else "system"
    session.add_all(
        [
            PartnerAuditEvent(
                partner_id=partner_id,
                event_type="partner_created",
                actor_type=actor_type,
                actor_user_id=actor_user_id,
                new_values_json=json.dumps(
                    {
                        "commission_bps": commission_bps,
                        "source": "automatic_enrollment",
                        "status": "active",
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                reason="automatic_enrollment",
            )
            for partner_id, _user_id, commission_bps in created
        ]
    )
    await session.flush()
    return {user_id: partner_id for partner_id, user_id, _commission_bps in created}


async def approve_pending_applications_for_users(
    session: AsyncSession,
    *,
    user_ids: list[int],
    actor_user_id: int | None,
) -> int:
    """Close stale pending applications when automatic enrollment created a profile."""

    if not user_ids:
        return 0
    result = await session.execute(
        select(
            PartnerApplication,
            PartnerProfile.partner_id,
            PartnerProfile.commission_bps,
        )
        .join(PartnerProfile, PartnerProfile.user_id == PartnerApplication.user_id)
        .where(
            PartnerApplication.user_id.in_(user_ids),
            PartnerApplication.status == "pending",
            PartnerProfile.status == "active",
        )
    )
    rows = list(result.all())
    if not rows:
        return 0
    now = utcnow()
    actor_type = "admin" if actor_user_id is not None else "system"
    for application, partner_id, commission_bps in rows:
        application.status = "approved"
        application.decided_at = now
        application.decided_by_admin_id = actor_user_id
        application.approved_commission_bps = int(commission_bps)
        application.reapply_allowed_at = None
        session.add(
            PartnerAuditEvent(
                partner_id=int(partner_id),
                application_id=int(application.application_id),
                event_type="application_decided",
                actor_type=actor_type,
                actor_user_id=actor_user_id,
                old_values_json='{"status":"pending"}',
                new_values_json='{"source":"automatic_enrollment","status":"approved"}',
                reason="automatic_enrollment",
            )
        )
    await session.flush()
    return len(rows)


async def latest_application_for_user(
    session: AsyncSession,
    user_id: int,
    *,
    for_update: bool = False,
) -> PartnerApplication | None:
    statement = (
        select(PartnerApplication)
        .where(PartnerApplication.user_id == user_id)
        .order_by(desc(PartnerApplication.submitted_at), desc(PartnerApplication.application_id))
        .limit(1)
    )
    if for_update:
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


async def get_application_by_id(
    session: AsyncSession,
    application_id: int,
    *,
    for_update: bool = False,
) -> PartnerApplication | None:
    statement = select(PartnerApplication).where(
        PartnerApplication.application_id == application_id
    )
    if for_update:
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


async def create_application(
    session: AsyncSession,
    *,
    user_id: int,
    display_label: str,
    message: str,
) -> PartnerApplication:
    application = PartnerApplication(
        user_id=user_id,
        display_label_snapshot=display_label,
        message=message,
        status="pending",
    )
    session.add(application)
    await session.flush()
    return application


async def list_applications(
    session: AsyncSession,
    *,
    status: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> tuple[list[PartnerApplication], int]:
    conditions: list[Any] = []
    normalized_status = str(status or "").strip().lower()
    if normalized_status and normalized_status != "all":
        conditions.append(PartnerApplication.status == normalized_status)
    normalized_search = str(search or "").strip()
    if normalized_search:
        pattern = f"%{normalized_search}%"
        search_conditions: list[Any] = [
            PartnerApplication.display_label_snapshot.ilike(pattern),
        ]
        if normalized_search.isdigit():
            search_conditions.extend(
                (
                    PartnerApplication.application_id == int(normalized_search),
                    PartnerApplication.user_id == int(normalized_search),
                )
            )
        conditions.append(or_(*search_conditions))
    where = and_(*conditions) if conditions else True
    total = int(
        (
            await session.execute(select(func.count()).select_from(PartnerApplication).where(where))
        ).scalar_one()
        or 0
    )
    rows = (
        await session.execute(
            select(PartnerApplication)
            .where(where)
            .order_by(
                desc(PartnerApplication.submitted_at), desc(PartnerApplication.application_id)
            )
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return list(rows.all()), total


async def create_client_attribution(
    session: AsyncSession,
    *,
    partner_id: int,
    client_user_id: int,
    public_client_id: str,
    public_label: str,
    source: str,
    attributed_by_admin_id: int | None = None,
    eligible_from: datetime | None = None,
    welcome_bonus_eligible_at: datetime | None = None,
) -> PartnerClient:
    now = utcnow()
    attribution = PartnerClient(
        partner_id=partner_id,
        client_user_id=client_user_id,
        public_client_id=public_client_id,
        public_label_snapshot=public_label,
        source=source,
        attributed_at=now,
        eligible_from=eligible_from or now,
        welcome_bonus_eligible_at=welcome_bonus_eligible_at,
        attributed_by_admin_id=attributed_by_admin_id,
    )
    session.add(attribution)
    await session.flush()
    return attribution


async def create_client_attributions_bulk(
    session: AsyncSession,
    *,
    clients: list[dict[str, Any]],
) -> dict[int, int]:
    """Insert client attribution rows without blocking on per-row savepoints."""

    if not clients:
        return {}
    bind = session.get_bind()
    insert_factory = sqlite_insert if bind.dialect.name == "sqlite" else postgresql_insert
    statement = (
        insert_factory(PartnerClient)
        .values(clients)
        .on_conflict_do_nothing()
        .returning(PartnerClient.client_user_id, PartnerClient.partner_id)
    )
    result = await session.execute(statement)
    return {
        int(client_user_id): int(partner_id)
        for client_user_id, partner_id in result.all()
        if client_user_id is not None
    }


async def get_client_by_user_id(
    session: AsyncSession,
    user_id: int,
    *,
    for_update: bool = False,
) -> PartnerClient | None:
    statement = select(PartnerClient).where(PartnerClient.client_user_id == user_id)
    if for_update:
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


async def get_client_with_profile_for_user(
    session: AsyncSession,
    user_id: int,
    *,
    for_update: bool = False,
) -> tuple[PartnerClient, PartnerProfile] | None:
    statement = (
        select(PartnerClient, PartnerProfile)
        .join(PartnerProfile, PartnerProfile.partner_id == PartnerClient.partner_id)
        .where(PartnerClient.client_user_id == user_id)
    )
    if for_update:
        statement = statement.with_for_update(of=PartnerProfile)
    row = (await session.execute(statement)).one_or_none()
    return (row[0], row[1]) if row else None


async def list_clients(
    session: AsyncSession,
    partner_id: int,
    *,
    currency: str | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[PartnerClient, int, int, int]], int]:
    commission_conditions = [
        PartnerCommission.partner_client_id == PartnerClient.partner_client_id,
        PartnerCommission.payment_id.is_not(None),
        PartnerCommission.status != "excluded",
    ]
    if currency:
        commission_conditions.append(func.upper(PartnerCommission.currency) == currency.upper())
    payments_count = (
        select(func.count(PartnerCommission.payment_id))
        .where(*commission_conditions)
        .correlate(PartnerClient)
        .scalar_subquery()
    )
    gross_minor = (
        select(func.coalesce(func.sum(PartnerCommission.gross_amount_minor), 0))
        .where(*commission_conditions)
        .correlate(PartnerClient)
        .scalar_subquery()
    )
    currency_scale = (
        select(func.coalesce(func.max(PartnerCommission.currency_scale), 2))
        .where(*commission_conditions)
        .correlate(PartnerClient)
        .scalar_subquery()
    )
    total = int(
        (
            await session.execute(
                select(func.count())
                .select_from(PartnerClient)
                .where(PartnerClient.partner_id == partner_id)
            )
        ).scalar_one()
        or 0
    )
    rows = (
        await session.execute(
            select(PartnerClient, payments_count, gross_minor, currency_scale)
            .where(PartnerClient.partner_id == partner_id)
            .order_by(desc(PartnerClient.attributed_at), desc(PartnerClient.partner_client_id))
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [(row[0], int(row[1] or 0), int(row[2] or 0), int(row[3] or 2)) for row in rows], total


async def get_commission_by_payment_id(
    session: AsyncSession,
    payment_id: int,
    *,
    for_update: bool = False,
) -> PartnerCommission | None:
    statement = select(PartnerCommission).where(PartnerCommission.payment_id == payment_id)
    if for_update:
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


async def create_commission(
    session: AsyncSession,
    **values: Any,
) -> PartnerCommission:
    commission = PartnerCommission(**values)
    session.add(commission)
    await session.flush()
    return commission


async def list_commissions(
    session: AsyncSession,
    partner_id: int,
    *,
    currency: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[PartnerCommission, PartnerClient]], int]:
    conditions: list[Any] = [PartnerCommission.partner_id == partner_id]
    if currency:
        conditions.append(func.upper(PartnerCommission.currency) == currency.upper())
    if status and status != "all":
        conditions.append(PartnerCommission.status == status)
    total = int(
        (
            await session.execute(
                select(func.count()).select_from(PartnerCommission).where(*conditions)
            )
        ).scalar_one()
        or 0
    )
    rows = (
        await session.execute(
            select(PartnerCommission, PartnerClient)
            .join(
                PartnerClient,
                PartnerClient.partner_client_id == PartnerCommission.partner_client_id,
            )
            .where(*conditions)
            .order_by(desc(PartnerCommission.created_at), desc(PartnerCommission.commission_id))
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [(row[0], row[1]) for row in rows], total


async def list_pending_commissions(
    session: AsyncSession,
    *,
    now: datetime,
    limit: int,
) -> list[PartnerCommission]:
    result = await session.execute(
        select(PartnerCommission)
        .where(
            PartnerCommission.status == "pending",
            PartnerCommission.available_at <= now,
        )
        .order_by(PartnerCommission.available_at, PartnerCommission.commission_id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars().all())


async def list_successful_payments_without_decision(
    session: AsyncSession,
    *,
    limit: int,
) -> list[Payment]:
    result = await session.execute(
        select(Payment)
        .join(PartnerClient, PartnerClient.client_user_id == Payment.user_id)
        .outerjoin(PartnerCommission, PartnerCommission.payment_id == Payment.payment_id)
        .where(Payment.status == "succeeded", PartnerCommission.commission_id.is_(None))
        .order_by(Payment.payment_id)
        .limit(limit)
        .with_for_update(skip_locked=True, of=Payment)
    )
    return list(result.scalars().all())


async def list_refunded_payments_with_active_commission(
    session: AsyncSession,
    *,
    limit: int,
) -> list[Payment]:
    result = await session.execute(
        select(Payment)
        .join(PartnerCommission, PartnerCommission.payment_id == Payment.payment_id)
        .where(
            Payment.status == "refunded",
            PartnerCommission.status.in_(("pending", "available")),
        )
        .order_by(Payment.payment_id)
        .limit(limit)
        .with_for_update(skip_locked=True, of=Payment)
    )
    return list(result.scalars().all())


async def create_ledger_entry(
    session: AsyncSession,
    **values: Any,
) -> PartnerLedgerEntry:
    values.setdefault("withdrawable_amount_minor", values.get("amount_minor", 0))
    entry = PartnerLedgerEntry(**values)
    session.add(entry)
    await session.flush()
    return entry


async def get_ledger_entry_by_key(
    session: AsyncSession,
    idempotency_key: str,
) -> PartnerLedgerEntry | None:
    return (
        await session.execute(
            select(PartnerLedgerEntry).where(PartnerLedgerEntry.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()


async def balance_minor(
    session: AsyncSession,
    partner_id: int,
    currency: str,
) -> int:
    result = await session.execute(
        select(func.coalesce(func.sum(PartnerLedgerEntry.amount_minor), 0)).where(
            PartnerLedgerEntry.partner_id == partner_id,
            func.upper(PartnerLedgerEntry.currency) == currency.upper(),
            PartnerLedgerEntry.state == "posted",
        )
    )
    return int(result.scalar_one() or 0)


async def balance_minor_by_user_ids(
    session: AsyncSession,
    user_ids: list[int],
    currency: str,
) -> dict[int, int]:
    unique_ids = sorted({int(user_id) for user_id in user_ids})
    if not unique_ids:
        return {}
    rows = (
        await session.execute(
            select(
                PartnerProfile.user_id,
                func.coalesce(func.sum(PartnerLedgerEntry.amount_minor), 0).label("amount"),
            )
            .join(
                PartnerLedgerEntry,
                PartnerLedgerEntry.partner_id == PartnerProfile.partner_id,
            )
            .where(
                PartnerProfile.user_id.in_(unique_ids),
                func.upper(PartnerLedgerEntry.currency) == currency.upper(),
                PartnerLedgerEntry.state == "posted",
            )
            .group_by(PartnerProfile.user_id)
        )
    ).all()
    return {int(row.user_id): int(row.amount or 0) for row in rows if row.user_id is not None}


async def withdrawable_balance_minor(
    session: AsyncSession,
    partner_id: int,
    currency: str,
) -> int:
    """Return the non-converted part of partner funds that may be withdrawn."""

    withdrawable = int(
        (
            await session.execute(
                select(
                    func.coalesce(func.sum(PartnerLedgerEntry.withdrawable_amount_minor), 0)
                ).where(
                    PartnerLedgerEntry.partner_id == partner_id,
                    func.upper(PartnerLedgerEntry.currency) == currency.upper(),
                    PartnerLedgerEntry.state == "posted",
                )
            )
        ).scalar_one()
        or 0
    )
    available = await balance_minor(session, partner_id, currency)
    return max(0, min(withdrawable, available))


async def balance_summaries(
    session: AsyncSession,
    partner_id: int,
) -> list[dict[str, Any]]:
    ledger_rows = (
        await session.execute(
            select(
                PartnerLedgerEntry.currency,
                PartnerLedgerEntry.currency_scale,
                func.coalesce(
                    func.sum(
                        case(
                            (PartnerLedgerEntry.state == "posted", PartnerLedgerEntry.amount_minor),
                            else_=0,
                        )
                    ),
                    0,
                ).label("available"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    PartnerLedgerEntry.state == "pending",
                                    PartnerLedgerEntry.kind == "commission_credit",
                                ),
                                PartnerLedgerEntry.amount_minor,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("pending"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    PartnerLedgerEntry.kind.in_(
                                        ("commission_credit", "commission_reversal")
                                    ),
                                    PartnerLedgerEntry.state != "void",
                                ),
                                PartnerLedgerEntry.amount_minor,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("lifetime_earned"),
            )
            .where(PartnerLedgerEntry.partner_id == partner_id)
            .group_by(PartnerLedgerEntry.currency, PartnerLedgerEntry.currency_scale)
        )
    ).all()
    active_reserves = {
        str(row[0]).upper(): int(row[1] or 0)
        for row in (
            await session.execute(
                select(
                    PartnerWithdrawal.debit_currency,
                    func.coalesce(func.sum(PartnerWithdrawal.debit_amount_minor), 0),
                )
                .where(
                    PartnerWithdrawal.partner_id == partner_id,
                    PartnerWithdrawal.status.in_(("requested", "processing")),
                )
                .group_by(PartnerWithdrawal.debit_currency)
            )
        ).all()
    }
    return [
        {
            "currency": str(row.currency).upper(),
            "currency_scale": int(row.currency_scale),
            "available_minor": int(row.available or 0),
            "pending_minor": int(row.pending or 0),
            "reserved_minor": active_reserves.get(str(row.currency).upper(), 0),
            "lifetime_earned_minor": int(row.lifetime_earned or 0),
        }
        for row in ledger_rows
    ]


async def profile_currency_metrics(
    session: AsyncSession,
    partner_id: int,
    currency: str,
) -> dict[str, int]:
    row = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (PartnerCommission.status != "excluded", 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("payments_count"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                PartnerCommission.status != "excluded",
                                PartnerCommission.gross_amount_minor,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("gross"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                PartnerCommission.status == "reversed",
                                -PartnerCommission.commission_amount_minor,
                            ),
                            (
                                PartnerCommission.status != "excluded",
                                PartnerCommission.commission_amount_minor,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("earned"),
            ).where(
                PartnerCommission.partner_id == partner_id,
                func.upper(PartnerCommission.currency) == currency.upper(),
            )
        )
    ).one()
    return {
        "payments_count": int(row.payments_count or 0),
        "gross_minor": int(row.gross or 0),
        "earned_minor": int(row.earned or 0),
    }


async def list_ledger_entries(
    session: AsyncSession,
    partner_id: int,
    *,
    currency: str | None = None,
    limit: int = 200,
) -> list[PartnerLedgerEntry]:
    conditions = [PartnerLedgerEntry.partner_id == partner_id]
    if currency:
        conditions.append(func.upper(PartnerLedgerEntry.currency) == currency.upper())
    return list(
        (
            await session.execute(
                select(PartnerLedgerEntry)
                .where(*conditions)
                .order_by(
                    desc(PartnerLedgerEntry.created_at),
                    desc(PartnerLedgerEntry.entry_id),
                )
                .limit(limit)
            )
        ).scalars()
    )


async def list_audit_events(
    session: AsyncSession,
    partner_id: int,
    *,
    limit: int = 200,
) -> list[PartnerAuditEvent]:
    return list(
        (
            await session.execute(
                select(PartnerAuditEvent)
                .where(PartnerAuditEvent.partner_id == partner_id)
                .order_by(
                    desc(PartnerAuditEvent.created_at),
                    desc(PartnerAuditEvent.audit_event_id),
                )
                .limit(limit)
            )
        ).scalars()
    )
