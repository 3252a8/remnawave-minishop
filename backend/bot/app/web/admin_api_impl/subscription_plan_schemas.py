"""Additive admin plan contracts shared by users and dashboard statistics."""

from typing import Literal

from bot.app.web.http_contracts import HttpResponseModel


class AdminTariffOptionOut(HttpResponseModel):
    tariff_key: str
    tariff_names: dict[str, str]
    is_configured: bool
    is_enabled: bool | None


class AdminPlanOut(HttpResponseModel):
    kind: Literal["tariff", "trial", "unassigned"]
    tariff_key: str | None
    tariff_names: dict[str, str]
    is_configured: bool
    is_enabled: bool | None


class AdminSubscriptionPlanOut(AdminPlanOut):
    is_active: bool


class AdminActiveTariffOut(AdminPlanOut):
    active_users: int
