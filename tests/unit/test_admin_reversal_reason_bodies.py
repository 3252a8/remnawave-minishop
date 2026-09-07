import pytest
from pydantic import ValidationError

from bot.app.web.admin_api_impl.gifts import AdminGiftRevokeBody
from bot.app.web.admin_api_impl.payment_schemas import AdminPaymentReverseBody

ReversalBody = AdminPaymentReverseBody | AdminGiftRevokeBody


@pytest.mark.parametrize("body_type", [AdminPaymentReverseBody, AdminGiftRevokeBody])
def test_reversal_reason_is_required_without_explicit_flag(body_type: type[ReversalBody]) -> None:
    with pytest.raises(ValidationError, match="at least 3 non-whitespace"):
        body_type.model_validate({"reason": "  "})


@pytest.mark.parametrize("body_type", [AdminPaymentReverseBody, AdminGiftRevokeBody])
def test_reversal_reason_can_be_empty_with_explicit_flag(body_type: type[ReversalBody]) -> None:
    body = body_type.model_validate({"reason": "  ", "without_reason": True})

    assert body.reason == ""
