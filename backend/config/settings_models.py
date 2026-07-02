from pydantic import BaseModel


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
    admin_email_notifications_enabled: bool
    admin_notification_cooldown_seconds: int
    admin_email_cooldown_seconds: int


class ReferralSettings(BaseModel):
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
    legacy_refs_enabled: bool
