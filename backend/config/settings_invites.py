"""Shared invitation link configuration."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

RESERVED_INVITE_PREFIXES = frozenset(
    [
        "ref",
        "partner",
        "r",
        "p",
        "start",
        "startapp",
        "start_param",
        "tgwebappstartparam",
        "promo",
        "plan",
        "gift",
        "ticket",
        "admin",
        "ext",
        "webapp",
        "page",
        "notifications",
        "home",
        "plans",
        "checkout",
        "invite",
        "install",
        "trial",
        "devices",
        "support",
        "settings",
        "security",
        "status",
        "balance",
        "gifts",
        "lang",
        "theme",
        "login_token",
        "login_purpose",
        "telegram_auth",
        "external_auth",
        "id",
        "first_name",
        "last_name",
        "username",
        "photo_url",
        "auth_date",
        "hash",
    ]
)


class InvitationSettings(BaseSettings):
    INVITE_LINK_PREFIX: str = Field(default="discount", pattern=r"^(?:[a-z][a-z0-9]{0,15})?$")

    @field_validator("INVITE_LINK_PREFIX")
    @classmethod
    def validate_invite_link_prefix(cls, value: str) -> str:
        if value in RESERVED_INVITE_PREFIXES:
            raise ValueError("invitation prefix conflicts with a reserved link parameter")
        return value
