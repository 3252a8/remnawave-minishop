from __future__ import annotations

from aiohttp import web

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.http_contracts import HttpResponseModel
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.app.web.webapp.gifts import GiftView
from db.dal import gift_dal
from db.gift_models import SubscriptionGift
from db.models import Payment, User

from .auth import _require_admin_user_id
from .common import _error, _ok


class AdminGiftView(GiftView):
    purchaser_id: int | None
    purchaser_label: str
    recipient_id: int | None
    recipient_label: str
    amount: float
    total_amount: float
    currency: str
    provider: str
    payment_status: str
    user_balance_amount: float
    partner_balance_amount: float
    discount_amount: float
    promo_code_id: int | None
    delivery_attempts: int

    @classmethod
    def from_orm_admin_gift(
        cls,
        gift: SubscriptionGift,
        payment: Payment,
        buyer: User | None,
        recipient: User | None,
        *,
        language: str,
    ) -> AdminGiftView:
        # Administrative lists intentionally never return the bearer token.
        public = GiftView.from_orm_gift(
            gift, payment, viewer_id=int(gift.purchaser_id or 0), base_url="", language=language
        ).model_dump()
        public["link"] = None
        return cls(
            **public,
            purchaser_id=gift.purchaser_id,
            purchaser_label=str(
                (buyer.username or buyer.email or buyer.first_name) if buyer else ""
            ),
            recipient_id=gift.recipient_id,
            recipient_label=str(
                (recipient.username or recipient.email or recipient.first_name) if recipient else ""
            ),
            amount=float(payment.amount),
            total_amount=float(
                payment.checkout_total_amount
                if payment.checkout_total_amount is not None
                else payment.amount
            ),
            currency=payment.currency,
            provider=payment.provider,
            payment_status=payment.status,
            user_balance_amount=int(payment.user_balance_amount_minor or 0)
            / (
                10
                ** int(
                    payment.user_balance_currency_scale
                    if payment.user_balance_currency_scale is not None
                    else 2
                )
            ),
            partner_balance_amount=int(payment.partner_balance_amount_minor or 0)
            / (
                10
                ** int(
                    payment.partner_balance_currency_scale
                    if payment.partner_balance_currency_scale is not None
                    else 2
                )
            ),
            discount_amount=float(payment.checkout_discount_amount or 0),
            promo_code_id=payment.promo_code_id,
            delivery_attempts=int(gift.delivery_attempts or 0),
        )


class AdminGiftsList(HttpResponseModel):
    gifts: list[AdminGiftView]
    total: int


register_contract(
    "admin_gifts_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminGiftsList),
        models=(AdminGiftsList, AdminGiftView),
    ),
)


async def admin_gifts_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    try:
        page = max(0, int(request.query.get("page", "0")))
    except ValueError:
        return _error(400, "invalid_page")
    status = request.query.get("status", "")
    sort = request.query.get("sort", "date_desc")
    if sort not in {
        f"{key}_{direction}"
        for key in ("id", "buyer", "recipient", "tariff", "amount", "status", "date", "provider")
        for direction in ("asc", "desc")
    }:
        return _error(400, "invalid_sort")
    if status not in {"", "ready", "activating", "activated", "revoked"}:
        return _error(400, "invalid_status")
    async with get_session_factory(request)() as session:
        rows, total = await gift_dal.admin_list(
            session,
            status=status,
            query=request.query.get("q", "")[:128],
            page=page,
            page_size=25,
            sort=sort,
        )
        result = AdminGiftsList(
            gifts=[
                AdminGiftView.from_orm_admin_gift(
                    gift, payment, buyer, recipient, language=get_settings(request).DEFAULT_LANGUAGE
                )
                for gift, payment, buyer, recipient in rows
            ],
            total=total,
        )
    return _ok(result.model_dump(mode="json"))
