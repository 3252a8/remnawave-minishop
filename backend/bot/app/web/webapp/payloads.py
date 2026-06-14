# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405

from typing import Literal


class WebAppEmailPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalize_and_limit_email(cls, value: EmailStr) -> str:
        normalized = normalize_email(str(value))
        if len(normalized) > 254:
            raise ValueError("email_too_long")
        return normalized


class WebAppEmailCodePayload(WebAppEmailPayload):
    code: str = ""


class WebAppEmailPasswordPayload(WebAppEmailPayload):
    password: constr(min_length=1, max_length=128)


class WebAppSetPasswordPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    password: constr(min_length=8, max_length=128)
    password_confirm: constr(min_length=8, max_length=128)
    code: constr(min_length=1, max_length=32)


class WebAppEmailMagicPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token: constr(min_length=8, max_length=512)


class WebAppPaymentCreatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    method: str = ""
    months: Any = None
    traffic_gb: Any = None
    device_count: Any = None
    tariff_key: Optional[constr(max_length=128)] = None
    sale_mode: Optional[constr(max_length=64)] = None
    renew_hwid_devices: Optional[bool] = None
    description: Optional[constr(max_length=4096)] = None
    comment: Optional[constr(max_length=4096)] = None
    note: Optional[constr(max_length=4096)] = None


class WebAppAutoRenewPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool


class WebAppTariffChangePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tariff_key: constr(min_length=1, max_length=128)
    mode: constr(min_length=1, max_length=64)


class WebAppLanguagePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    language: constr(min_length=2, max_length=16)


class WebAppDeviceDisconnectPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token: constr(min_length=8, max_length=128)


SupportCategory = Literal["billing", "technical", "account", "other"]
SupportPriority = Literal["low", "normal", "high", "urgent"]
SupportStatus = Literal["open", "awaiting_user", "awaiting_admin", "resolved", "closed"]


class CreateTicketPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subject: constr(min_length=1, max_length=160)
    category: SupportCategory = "other"
    priority: Literal["normal", "high"] = "normal"
    body: constr(min_length=1, max_length=4000)

    @field_validator("subject", "body")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("empty_text")
        return stripped


class TicketReplyPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    body: constr(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def _strip_body(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("empty_text")
        return stripped


class AdminTicketReplyPayload(TicketReplyPayload):
    is_internal_note: bool = False


class AdminTicketPatchPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Optional[SupportStatus] = None
    priority: Optional[SupportPriority] = None
    category: Optional[SupportCategory] = None
    assigned_admin_id: Optional[int] = None
