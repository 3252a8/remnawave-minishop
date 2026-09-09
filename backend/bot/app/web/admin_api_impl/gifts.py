from __future__ import annotations

from aiohttp import web
from pydantic import ConfigDict, Field, model_validator

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.app.web.webapp.gifts import GiftView
from bot.services.gift_revoke import GiftRevokeError, revoke_paid_gift
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
    balance_enabled: bool

    @classmethod
    def from_orm_admin_gift(
        cls,
        gift: SubscriptionGift,
        payment: Payment,
        buyer: User | None,
        recipient: User | None,
        *,
        language: str,
        balance_enabled: bool,
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
            balance_enabled=balance_enabled,
        )


class AdminGiftsList(HttpResponseModel):
    gifts: list[AdminGiftView]
    total: int


class AdminGiftRevokeBody(HttpBodyModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(max_length=500)
    without_reason: bool = False
    restore_promo_usage: bool = True
    refund_to_balance: bool = True

    @model_validator(mode="after")
    def normalize_reason(self) -> AdminGiftRevokeBody:
        self.reason = self.reason.strip()
        if not self.without_reason and len(self.reason) < 3:
            raise ValueError("reason must contain at least 3 non-whitespace characters")
        return self


register_contract(
    "admin_gifts_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminGiftsList),
        models=(AdminGiftsList, AdminGiftView),
    ),
)
register_contract(
    "admin_gift_revoke_route",
    RouteContract(
        request_model=AdminGiftRevokeBody,
        response_schema=ok_envelope_for(AdminGiftView, key="gift"),
        models=(AdminGiftRevokeBody, AdminGiftView),
    ),
)


async def admin_gifts_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    try:
        page = max(0, int(request.query.get("page", "0")))
    except ValueError:
        return _error(400, "invalid_page")
    status = request.query.get("status", "")
    source = request.query.get("source", "")
    if source not in {"", "admin", "purchase"}:
        return _error(400, "invalid_source")
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
            source=source,
        )
        result = AdminGiftsList(
            gifts=[
                AdminGiftView.from_orm_admin_gift(
                    gift,
                    payment,
                    buyer,
                    recipient,
                    language=get_settings(request).DEFAULT_LANGUAGE,
                    balance_enabled=get_settings(request).balance_settings.enabled,
                )
                for gift, payment, buyer, recipient in rows
            ],
            total=total,
        )
    return _ok(result.model_dump(mode="json"))


async def admin_gift_revoke_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    try:
        gift_id = int(request.match_info["gift_id"])
    except (KeyError, ValueError):
        return _error(400, "invalid_gift")
    body = await parse_body_or_400(request, AdminGiftRevokeBody)
    settings = get_settings(request)
    async with get_session_factory(request)() as session:
        try:
            gift = await revoke_paid_gift(
                session,
                gift_id=gift_id,
                actor_admin_id=actor_id,
                reason=body.reason,
                without_reason=body.without_reason,
                restore_promo_usage=body.restore_promo_usage,
                refund_to_balance=body.refund_to_balance,
            )
            await session.commit()
        except GiftRevokeError as exc:
            await session.rollback()
            return _error(exc.status, exc.code)
        payment = await session.get(Payment, gift.payment_id)
        if payment is None:
            return _error(404, "gift_not_found")
        buyer = (
            await session.get(User, gift.purchaser_id) if gift.purchaser_id is not None else None
        )
        recipient = (
            await session.get(User, gift.recipient_id) if gift.recipient_id is not None else None
        )
        result = AdminGiftView.from_orm_admin_gift(
            gift,
            payment,
            buyer,
            recipient,
            language=settings.DEFAULT_LANGUAGE,
            balance_enabled=settings.balance_settings.enabled,
        )
    return _ok({"gift": result.model_dump(mode="json")})
