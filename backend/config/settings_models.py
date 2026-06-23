from typing import List, Optional

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
    smtp_fallback_ports: Optional[str]
    smtp_timeout_seconds: int
    smtp_username: Optional[str]
    smtp_password: Optional[str]
    smtp_from_email: Optional[str]
    smtp_from_name: Optional[str]
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
    logo_url: Optional[str]
    favicon_use_custom: bool
    favicon_url: Optional[str]
    logo_favicon_url: Optional[str]
    session_ttl_seconds: int
    session_secret: str
    webhook_secret_token: str
    auth_max_age_seconds: int
    login_token_ttl_seconds: int
    server_host: str
    server_port: int
    enabled: bool
    trusted_proxies: List[str]
