import csv
import io

from aiohttp import web
from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_session_factory,
)
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from db.dal import payment_dal
from db.models import Payment, User

from .auth import (
    _require_admin_user_id,
)
from .common import (
    _error,
    _ok,
    _payment_user_display_label,
)
from .schemas import AdminPaymentsListOut, PaymentDetailOut, PaymentOut

register_contract(
    "admin_payments_list_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminPaymentsListOut),
        models=(AdminPaymentsListOut, PaymentOut),
    ),
)
register_contract(
    "admin_payment_detail_route",
    RouteContract(
        response_schema=ok_envelope_for(PaymentDetailOut, key="payment"),
        models=(PaymentDetailOut,),
    ),
)
register_contract(
    "admin_payments_export_route",
    RouteContract(
        response_schema={"type": "string", "contentMediaType": "text/csv"},
        response_content_type="text/csv",
    ),
)


async def admin_payments_list_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = get_session_factory(request)

    page = max(0, int(request.query.get("page", 0) or 0))
    page_size = min(100, max(1, int(request.query.get("page_size", 25) or 25)))
    sort = str(request.query.get("sort") or "date_desc").lower()

    async with async_session_factory() as session:
        from sqlalchemy.orm import selectinload

        full_name = func.nullif(
            func.trim(func.coalesce(User.first_name, "") + " " + func.coalesce(User.last_name, "")),
            "",
        )
        user_label = case(
            (
                User.telegram_id.is_not(None),
                func.coalesce(full_name, User.username, User.email, cast(Payment.user_id, String)),
            ),
            else_=func.coalesce(
                User.email, full_name, User.username, cast(Payment.user_id, String)
            ),
        )
        sale_mode = func.lower(func.coalesce(Payment.sale_mode, ""))
        regular_mode = or_(
            sale_mode.in_(("traffic", "traffic_package", "topup")),
            sale_mode.like("traffic@%"),
            sale_mode.like("traffic|%"),
            sale_mode.like("traffic_package@%"),
            sale_mode.like("traffic_package|%"),
            sale_mode.like("topup@%"),
            sale_mode.like("topup|%"),
        )
        premium_mode = or_(
            sale_mode == "premium_topup",
            sale_mode.like("premium_topup@%"),
            sale_mode.like("premium_topup|%"),
        )
        regular_traffic = case(
            (and_(Payment.purchased_gb.is_not(None), regular_mode), Payment.purchased_gb),
            else_=None,
        )
        premium_traffic = case(
            (and_(Payment.purchased_gb.is_not(None), premium_mode), Payment.purchased_gb),
            else_=None,
        )
        sort_columns = {
            "id": Payment.payment_id,
            "user": user_label,
            "user_id": Payment.user_id,
            "traffic_regular": regular_traffic,
            "traffic_premium": premium_traffic,
            "amount": Payment.amount,
            "provider": Payment.provider,
            "description": Payment.description,
            "status": Payment.status,
            "date": Payment.created_at,
        }
        sort_key, _, direction = sort.rpartition("_")
        sort_column = sort_columns.get(sort_key, Payment.created_at)
        descending = direction != "asc"
        order = sort_column.desc().nullslast() if descending else sort_column.asc().nullslast()
        tie_breaker = Payment.payment_id.desc() if descending else Payment.payment_id.asc()
        stmt = (
            select(Payment)
            .outerjoin(User, User.user_id == Payment.user_id)
            .options(selectinload(Payment.user))
            .order_by(order, tie_breaker)
            .offset(page * page_size)
            .limit(page_size)
        )
        rows = (await session.execute(stmt)).scalars().all()
        total = await payment_dal.get_payments_count(session)

    return _ok(
        {
            "payments": [PaymentOut.from_orm_payment(p).model_dump(mode="json") for p in rows],
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
        }
    )


async def admin_payment_detail_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = get_session_factory(request)

    try:
        payment_id = int(request.match_info["payment_id"])
    except (TypeError, ValueError):
        return _error(400, "invalid_payment", "Invalid payment id")

    async with async_session_factory() as session:
        payment = await payment_dal.get_payment_by_db_id(session, payment_id)
        if not payment:
            return _error(404, "not_found", "Payment not found")

        payload = PaymentDetailOut.from_orm_payment_detail(payment).model_dump(mode="json")

    return _ok({"payment": payload})


async def admin_payments_export_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = get_session_factory(request)

    async with async_session_factory() as session:
        from sqlalchemy.orm import selectinload

        stmt = (
            select(Payment)
            .options(selectinload(Payment.user))
            .order_by(Payment.created_at.desc())
            .limit(10000)
        )
        rows = (await session.execute(stmt)).scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "payment_id",
            "user_id",
            "user_label",
            "provider",
            "provider_payment_id",
            "amount",
            "currency",
            "status",
            "description",
            "duration_months",
            "sale_mode",
            "tariff_key",
            "created_at",
        ]
    )
    for p in rows:
        label = _payment_user_display_label(p.user, int(p.user_id)) if p.user else str(p.user_id)
        writer.writerow(
            [
                p.payment_id,
                p.user_id,
                label,
                p.provider,
                p.provider_payment_id or "",
                p.amount,
                p.currency,
                p.status,
                p.description or "",
                p.subscription_duration_months or "",
                p.sale_mode or "",
                p.tariff_key or "",
                p.created_at.isoformat() if p.created_at else "",
            ]
        )

    response = web.Response(
        body=buffer.getvalue().encode("utf-8-sig"),
        content_type="text/csv",
        charset="utf-8",
    )
    response.headers["Content-Disposition"] = 'attachment; filename="payments.csv"'
    return response
