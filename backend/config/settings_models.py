from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class DBSettings(BaseModel):
    user: str
    password: str
    host: str
    port: int
    database: str


class EmailSettings(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_fallback_ports: str | None
    smtp_timeout_seconds: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from_email: str | None
    smtp_from_name: str | None
    smtp_starttls: bool
    smtp_use_ssl: bool
    email_code_ttl_seconds: int
    email_code_resend_seconds: int
    email_code_max_attempts: int
    brute_force_max_failures: int
    brute_force_window_seconds: int
    brute_force_lock_seconds: int


class WebAppSettings(BaseModel):
    title: str
    primary_color: str
    user_theme_mode_enabled: bool
    logo_url: str | None
    favicon_use_custom: bool
    favicon_url: str | None
    logo_favicon_url: str | None
    session_ttl_seconds: int
    session_secret: str
    webhook_secret_token: str
    auth_max_age_seconds: int
    login_token_ttl_seconds: int
    server_host: str
    server_port: int
    enabled: bool
    trusted_proxies: list[str]


class PaymentSettings(BaseModel):
    default_currency_symbol: str
    payment_request_timeout_seconds: float
    payment_methods_order: list[str]
    subscription_options: dict[int, float]
    stars_subscription_options: dict[int, int]
    traffic_packages: dict[float, float]
    stars_traffic_packages: dict[float, int]
    traffic_sale_mode: bool


class CompatibilitySettings(BaseModel):
    remnashop_referral_code_compat_enabled: bool
    remnashop_promo_code_compat_enabled: bool
    remnashop_imported_at: str | None
    remnashop_notes: str | None


class RegistrationSettings(BaseModel):
    invite_only_enabled: bool


class PanelSettings(BaseModel):
    api_url: str | None
    api_key: str | None
    api_cookie: str | None
    webhook_secret: str | None
    write_mode: str
    dry_run_enabled: bool
    api_total_timeout_seconds: float
    api_connect_timeout_seconds: float
    api_sock_connect_timeout_seconds: float
    api_sock_read_timeout_seconds: float


class SupportSettings(BaseModel):
    link: str | None
    tickets_enabled: bool
    ticket_max_body_length: int
    ticket_max_subject_length: int
    ticket_rate_limit_per_hour: int
    message_rate_limit_per_minute: int
    image_rate_limit_per_day: int
    admin_email_notifications_enabled: bool
    admin_notification_cooldown_seconds: int
    admin_email_cooldown_seconds: int


class ReferralSettings(BaseModel):
    enabled: bool = True
    bonus_days_inviter_1_month: int | None
    bonus_days_inviter_3_months: int | None
    bonus_days_inviter_6_months: int | None
    bonus_days_inviter_12_months: int | None
    bonus_days_referee_1_month: int | None
    bonus_days_referee_3_months: int | None
    bonus_days_referee_6_months: int | None
    bonus_days_referee_12_months: int | None
    one_bonus_per_referee: bool
    welcome_bonus_days: int
    welcome_bonus_without_telegram_enabled: bool
    webapp_link_enabled: bool = True
    telegram_link_enabled: bool = True
    legacy_refs_enabled: bool


class PartnerWithdrawalField(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=120)
    required: bool = True
    placeholder: str = Field(default="", max_length=120)

    @field_validator("id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized.replace("_", "").isalnum():
            raise ValueError("field id must contain only letters, digits and underscores")
        return normalized


class PartnerWithdrawalNetwork(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)

    @field_validator("id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        return value.strip().lower()


class PartnerWithdrawalMethod(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    type: Literal["bank_card", "sbp", "crypto"]
    enabled: bool = True
    label: str = Field(default="", max_length=120)
    debit_currency: str = Field(min_length=2, max_length=16)
    currency_scale: int = Field(default=2, ge=0, le=8)
    min_amount_minor: int = Field(gt=0)
    max_amount_minor: int | None = Field(default=None, gt=0)
    fields: list[PartnerWithdrawalField] = Field(default_factory=list)
    settlement_asset: str | None = Field(default=None, max_length=16)
    networks: list[PartnerWithdrawalNetwork] = Field(default_factory=list)
    sort_order: int = Field(default=0, ge=0)
    help_text: str = Field(default="", max_length=500)

    @field_validator("id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized.replace("-", "").replace("_", "").isalnum():
            raise ValueError("method id contains unsupported characters")
        return normalized

    @field_validator("debit_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_method(self) -> "PartnerWithdrawalMethod":
        if self.max_amount_minor is not None and self.max_amount_minor < self.min_amount_minor:
            raise ValueError("maximum amount must be greater than or equal to minimum amount")
        if self.type == "crypto":
            if not self.settlement_asset:
                raise ValueError("crypto method requires settlement_asset")
            if not self.networks:
                raise ValueError("crypto method requires at least one network")
        field_ids = [field.id for field in self.fields]
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("withdrawal field ids must be unique")
        required_field = {
            "bank_card": "card_number",
            "sbp": "phone",
            "crypto": "address",
        }[self.type]
        if self.enabled and required_field not in field_ids:
            raise ValueError(f"enabled {self.type} method requires {required_field} field")
        network_ids = [network.id for network in self.networks]
        if len(network_ids) != len(set(network_ids)):
            raise ValueError("withdrawal network ids must be unique")
        return self


class PartnerSettings(BaseModel):
    enabled: bool = False
    auto_enrollment_enabled: bool = False
    referral_program_disabled: bool = False
    withdrawals_enabled: bool = True
    balance_payment_enabled: bool = True
    client_welcome_bonus_enabled: bool = False
    client_payment_bonus_enabled: bool = False
    one_bonus_per_client: bool = True
    default_commission_bps: int = Field(default=3000, ge=0, le=10000)
    commission_hold_days: int = Field(default=0, ge=0, le=365)
    eligible_currencies: list[str] = Field(default_factory=lambda: ["RUB"])
    excluded_sale_modes: list[str] = Field(default_factory=list)
    withdrawal_methods: list[PartnerWithdrawalMethod] = Field(default_factory=list)
    telegram_link_enabled: bool = True
    webapp_link_enabled: bool = True
    application_message_max_length: int = Field(default=2000, ge=10, le=10000)
    max_active_withdrawals: int = Field(default=3, ge=1, le=50)
    reapplication_enabled: bool = False
    reapplication_cooldown_days: int = Field(default=0, ge=0, le=3650)
    list_page_limit: int = Field(default=50, ge=10, le=200)
    application_rate_limit_hours: int = Field(default=24, ge=1, le=8760)
    withdrawal_rate_limit_seconds: int = Field(default=10, ge=1, le=3600)
    audit_retention_days: int = Field(default=1095, ge=30, le=3650)
    requisites_retention_days: int = Field(default=90, ge=1, le=3650)

    @field_validator("eligible_currencies")
    @classmethod
    def normalize_currencies(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip().upper() for value in values if value.strip()))
        if not normalized:
            raise ValueError("at least one eligible currency is required")
        return normalized

    @field_validator("excluded_sale_modes")
    @classmethod
    def normalize_sale_modes(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip().lower() for value in values if value.strip()))

    @model_validator(mode="after")
    def validate_links_and_methods(self) -> "PartnerSettings":
        if not self.telegram_link_enabled and not self.webapp_link_enabled:
            raise ValueError("at least one partner link must remain enabled")
        ids = [method.id for method in self.withdrawal_methods]
        if len(ids) != len(set(ids)):
            raise ValueError("withdrawal method ids must be unique")
        scales: dict[str, int] = {}
        for method in self.withdrawal_methods:
            previous = scales.setdefault(method.debit_currency, method.currency_scale)
            if previous != method.currency_scale:
                raise ValueError("withdrawal methods for one currency must use the same scale")
        return self
