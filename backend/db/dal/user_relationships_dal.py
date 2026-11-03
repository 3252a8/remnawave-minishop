"""Read the complete referral/partner graph without traversing ORM relationships."""

from datetime import UTC, datetime

from sqlalchemy import CompoundSelect, case, func, literal, or_, select, union, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from db.models import Payment, Subscription, User, UserTelegramAvatar
from db.partner_models import PartnerClient, PartnerProfile


def relationship_edges_query() -> CompoundSelect:
    """Directed edges between existing, distinct users, including historical partners."""
    inviter = aliased(User)
    invitee = aliased(User)
    referrals = (
        select(
            inviter.user_id.label("source"),
            invitee.user_id.label("target"),
            literal("referral").label("kind"),
        )
        .select_from(invitee)
        .join(inviter, inviter.user_id == invitee.referred_by_id)
        .where(inviter.user_id != invitee.user_id)
    )
    partners = (
        select(
            inviter.user_id.label("source"),
            invitee.user_id.label("target"),
            literal("partner").label("kind"),
        )
        .select_from(PartnerClient)
        .join(PartnerProfile, PartnerProfile.partner_id == PartnerClient.partner_id)
        .join(inviter, inviter.user_id == PartnerProfile.user_id)
        .join(invitee, invitee.user_id == PartnerClient.client_user_id)
        .where(inviter.user_id != invitee.user_id)
    )
    return union_all(referrals, partners)


async def has_user_relationships(session: AsyncSession, user_id: int) -> bool:
    edges = relationship_edges_query().subquery()
    linked = select(edges.c.source).where(or_(edges.c.source == user_id, edges.c.target == user_id))
    return bool(await session.scalar(select(linked.exists())))


async def load_relationship_subscription_and_revenue(
    session: AsyncSession,
) -> tuple[dict[int, tuple[bool, str | None]], dict[int, dict[str, float]]]:
    edges = relationship_edges_query().cte("relationship_metrics_edges")
    connected_ids = union(select(edges.c.source), select(edges.c.target))
    active = case(
        (Subscription.is_active.is_(True) & (Subscription.end_date > datetime.now(UTC)), True),
        else_=False,
    )
    subscriptions = (
        select(
            Subscription.user_id,
            Subscription.tariff_key,
            active.label("active"),
            func.row_number()
            .over(
                partition_by=Subscription.user_id,
                order_by=(
                    active.desc(),
                    Subscription.end_date.desc(),
                    Subscription.subscription_id.desc(),
                ),
            )
            .label("position"),
        )
        .where(Subscription.user_id.in_(connected_ids))
        .subquery()
    )
    subscription_rows = await session.execute(
        select(subscriptions.c.user_id, subscriptions.c.active, subscriptions.c.tariff_key).where(
            subscriptions.c.position == 1
        )
    )
    currency = func.upper(Payment.currency)
    payment_rows = await session.execute(
        select(Payment.user_id, currency, func.sum(Payment.amount))
        .where(
            Payment.user_id.in_(connected_ids),
            Payment.status == "succeeded",
            Payment.funding_source == "external",
        )
        .group_by(Payment.user_id, currency)
        .order_by(currency)
    )
    revenue: dict[int, dict[str, float]] = {}
    for user_id, code, amount in payment_rows:
        revenue.setdefault(int(user_id), {})[str(code)] = float(amount)
    return {
        int(user_id): (bool(is_active), tariff_key)
        for user_id, is_active, tariff_key in subscription_rows
    }, revenue


async def load_user_relationships(
    session: AsyncSession,
) -> tuple[list[tuple[User, datetime | None]], list[tuple[int, int, str]]]:
    """Two bounded-count queries; no depth/page limit or per-user avatar fetch."""
    edges_query = relationship_edges_query().cte("relationship_edges")
    edge_rows = (await session.execute(select(edges_query))).all()
    if not edge_rows:
        return [], []
    connected_ids = union(select(edges_query.c.source), select(edges_query.c.target))
    node_rows = (
        await session.execute(
            select(User, UserTelegramAvatar.updated_at)
            .outerjoin(UserTelegramAvatar, UserTelegramAvatar.user_id == User.user_id)
            .where(User.user_id.in_(connected_ids))
            .order_by(User.user_id)
        )
    ).all()
    nodes = [(user, updated_at) for user, updated_at in node_rows]
    existing_ids = {int(user.user_id) for user, _updated_at in nodes}
    # Keep the response coherent if a user/relationship disappears between reads.
    edges = sorted(
        (int(source), int(target), str(kind))
        for source, target, kind in edge_rows
        if int(source) in existing_ids and int(target) in existing_ids
    )
    linked_ids = {user_id for source, target, _kind in edges for user_id in (source, target)}
    return [(user, stamp) for user, stamp in nodes if int(user.user_id) in linked_ids], edges
