from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from bot.services.email_auth_service import normalize_email

PasswordAuthString = Annotated[str, StringConstraints(min_length=1, max_length=128)]
PasswordSetupString = Annotated[str, StringConstraints(min_length=8, max_length=128)]
ShortCodeString = Annotated[str, StringConstraints(min_length=1, max_length=32)]
MagicTokenString = Annotated[str, StringConstraints(min_length=8, max_length=512)]
TariffKeyString = Annotated[str, StringConstraints(min_length=1, max_length=128)]
OptionalTariffKeyString = Annotated[str, StringConstraints(max_length=128)]
SaleModeString = Annotated[str, StringConstraints(max_length=64)]
LongTextString = Annotated[str, StringConstraints(max_length=4096)]
ChangeModeString = Annotated[str, StringConstraints(min_length=1, max_length=64)]
LanguageString = Annotated[str, StringConstraints(min_length=2, max_length=16)]
DeviceTokenString = Annotated[str, StringConstraints(min_length=8, max_length=128)]
TicketSubjectString = Annotated[str, StringConstraints(min_length=1, max_length=160)]
# The transport cap, not the message cap: markup costs characters the reader
# never sees, so the real limit is applied to the visible text after
# sanitizing (``support_message_body``). This only stops absurd payloads.
TicketBodyString = Annotated[str, StringConstraints(max_length=32000)]
TicketBodyFormat = Literal["text", "html"]


class WebAppEmailPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalize_and_limit_email(cls, value: EmailStr) -> str:
        normalized = normalize_email(str(value))
        if len(normalized) > 254:
            raise ValueError("email_too_long")
        return cast(str, normalized)


class WebAppEmailCodePayload(WebAppEmailPayload):
    code: str = ""


class WebAppEmailRequestPayload(WebAppEmailPayload):
    language: str | None = None
    referral_code: str | None = None
    start_param: str | None = None


class WebAppEmailCodeAuthPayload(WebAppEmailCodePayload):
    referral_code: str | None = None
    start_param: str | None = None


class WebAppEmailPasswordPayload(WebAppEmailPayload):
    password: PasswordAuthString


class WebAppSetPasswordPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    password: PasswordSetupString
    password_confirm: PasswordSetupString
    code: ShortCodeString


class WebAppEmailMagicPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token: MagicTokenString


class WebAppEmailMagicAuthPayload(WebAppEmailMagicPayload):
    referral_code: str | None = None
    start_param: str | None = None


class WebAppTelegramAuthPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    init_data: str = ""
    id_token: str = ""
    nonce: str = ""
    auth_data: Any = None
    referral_code: str | None = None
    start_param: str | None = None


class WebAppPasskeyCredentialPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    challenge: Annotated[str, StringConstraints(min_length=16, max_length=1024)]
    credential: dict[str, Any]
    name: Annotated[str, StringConstraints(max_length=80)] | None = None


class WebAppPasskeyDeletePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    credential_id: Annotated[str, StringConstraints(min_length=8, max_length=1024)]


class WebAppExternalIdentityPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: Literal["discord", "google", "yandex"]


class WebAppEmailChangeCurrentPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: ShortCodeString


class WebAppEmailChangeNewPayload(WebAppEmailPayload):
    change_token: MagicTokenString


class WebAppEmailChangeConfirmPayload(WebAppEmailChangeNewPayload):
    code: ShortCodeString


class WebAppPromoApplyPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: Any = ""


class WebAppCheckoutAddonsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_count: int | None = Field(default=None, ge=0)
    # Total resettable quota selected for each tariff accounting period.
    # These are not consumable top-up amounts.
    regular_limit_gb: float | None = Field(default=None, ge=0)
    premium_limit_gb: float | None = Field(default=None, ge=0)


class WebAppPaymentCreatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    method: str = ""
    gift: bool = False
    gift_recipient_email: EmailStr | None = None
    months: Any = None
    duration_days: int | None = Field(default=None, strict=True, gt=0, le=2147483647)
    traffic_gb: Any = None
    device_count: Any = None
    tariff_key: OptionalTariffKeyString | None = None
    sale_mode: SaleModeString | None = None
    renew_hwid_devices: bool | None = None
    checkout_addons: WebAppCheckoutAddonsPayload | None = None
    balance_source: Literal["user", "partner"] | None = None
    use_partner_balance: bool = False
    promo_code: ShortCodeString | None = None
    description: LongTextString | None = None
    comment: LongTextString | None = None
    note: LongTextString | None = None


class WebAppBalanceTopupPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    amount: float = Field(gt=0, allow_inf_nan=False)


class WebAppPlansViewedPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plans_count: int = 0
    tariff_key: OptionalTariffKeyString | None = None


class WebAppPromoQuotePayload(WebAppPaymentCreatePayload):
    model_config = ConfigDict(extra="ignore")

    promo_code: ShortCodeString


class WebAppSubscriptionQuotePayload(WebAppPaymentCreatePayload):
    model_config = ConfigDict(extra="ignore")


class WebAppAutoRenewPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool


class WebAppSubscriptionReissuePayload(BaseModel):
    """Empty body for the subscription reissue action (extra keys ignored)."""

    model_config = ConfigDict(extra="ignore")


class WebAppTariffChangePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tariff_key: TariffKeyString
    mode: ChangeModeString


class WebAppLanguagePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    language: LanguageString


class WebAppDeviceDisconnectPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token: DeviceTokenString


SupportCategory = Literal["billing", "technical", "account", "other"]
SupportPriority = Literal["low", "normal", "high", "urgent"]
SupportStatus = Literal["open", "awaiting_user", "awaiting_admin", "resolved", "closed"]


class CreateTicketPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subject: TicketSubjectString
    category: SupportCategory = "other"
    priority: Literal["normal", "high"] = "normal"
    body: TicketBodyString
    body_format: TicketBodyFormat = "text"

    @field_validator("subject")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("empty_text")
        return stripped

    @field_validator("body")
    @classmethod
    def _strip_body(cls, value: str) -> str:
        return value.strip()


class TicketReplyPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    body: TicketBodyString
    body_format: TicketBodyFormat = "text"

    @field_validator("body")
    @classmethod
    def _strip_body(cls, value: str) -> str:
        return value.strip()


class AdminTicketReplyPayload(TicketReplyPayload):
    is_internal_note: bool = False


class AdminTicketPatchPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: SupportStatus | None = None
    priority: SupportPriority | None = None
    category: SupportCategory | None = None
    assigned_admin_id: int | None = None
