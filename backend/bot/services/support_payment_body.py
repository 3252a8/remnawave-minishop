"""Freeze a small, server-authored payment summary in the opening message."""

from html import escape

from bot.middlewares.i18n import JsonI18n
from bot.services.support_message_body import BODY_FORMAT_HTML, support_body_telegram_html
from db.models import Payment
from db.payment_history import payment_history_state


class SupportPaymentUnavailable(ValueError):
    pass


def attach_payment_summary(
    body: str, body_format: str, payment: Payment, *, lang: str, i18n: JsonI18n | None
) -> tuple[str, str]:
    state = payment_history_state(payment)
    status = i18n.gettext(lang, f"wa_payment_history_state_{state}") if i18n else state
    values = {
        "payment_id": int(payment.payment_id),
        "amount": escape(f"{payment.amount:.2f}"),
        "currency": escape(str(payment.currency or "—")),
        "provider": escape(str(payment.provider or "—")[:80]),
        "created_at": escape(payment.created_at.isoformat() if payment.created_at else "—"),
        "status": escape(status),
    }
    summary = (
        i18n.gettext(lang, "support_attached_payment", **values)
        if i18n
        else (
            "<b>Attached payment #{payment_id}</b>\n"
            "Amount: {amount} {currency}\nProvider: {provider}\n"
            "Created: {created_at}\nState at submission: {status}"
        ).format(**values)
    )
    message = support_body_telegram_html(body, body_format)
    return f"{message}\n\n{summary}".strip(), BODY_FORMAT_HTML
