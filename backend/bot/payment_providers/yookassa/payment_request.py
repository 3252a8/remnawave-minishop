"""Build a YooKassa request without mixing saved instruments and method selection."""

from typing import Any

from yookassa.domain.request.payment_request import PaymentRequest
from yookassa.domain.request.payment_request_builder import PaymentRequestBuilder


def build_payment_request(
    *,
    amount: str,
    currency: str,
    capture: bool,
    return_url: str,
    description: str,
    metadata: dict[str, Any],
    receipt: dict[str, Any],
    save_payment_method: bool,
    payment_method_id: str | None,
    payment_method_type: str | None,
) -> PaymentRequest:
    builder = PaymentRequestBuilder()
    builder.set_amount({"value": amount, "currency": currency})
    builder.set_capture(capture)
    if not payment_method_id:
        builder.set_confirmation({"type": "redirect", "return_url": return_url})
    builder.set_description(description)
    builder.set_metadata(metadata)
    if save_payment_method:
        builder.set_save_payment_method(True)
    elif not payment_method_id:
        builder.set_save_payment_method(False)
    if payment_method_id:
        builder.set_payment_method_id(payment_method_id)
    elif payment_method_type:
        builder.set_payment_method_data({"type": payment_method_type})
    builder.set_receipt(receipt)
    return builder.build()
