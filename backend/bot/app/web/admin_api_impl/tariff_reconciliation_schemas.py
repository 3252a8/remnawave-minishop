"""Typed admin API contracts for subscription tariff reconciliation."""

from __future__ import annotations

from datetime import datetime

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from db.tariff_reconciliation import (
    TariffReconciliationItem,
    TariffReconciliationReport,
)


class AdminTariffReconciliationApplyBody(HttpBodyModel):
    apply: bool = True


class AdminTariffReconciliationItemOut(HttpResponseModel):
    subscription_id: int
    user_id: int
    user_minishop_id: str | None = None
    current_tariff_key: str | None = None
    proposed_tariff_key: str | None = None
    source: str | None = None
    status: str
    reason: str
    applied: bool

    @classmethod
    def from_item(
        cls,
        item: TariffReconciliationItem,
    ) -> AdminTariffReconciliationItemOut:
        return cls(**item.to_payload())


class AdminTariffReconciliationOut(HttpResponseModel):
    dry_run: bool
    scanned: int
    healthy: int
    candidates: int
    applied: int
    unresolved: int
    generated_at: datetime
    items_truncated: bool
    items: list[AdminTariffReconciliationItemOut]

    @classmethod
    def from_report(
        cls,
        report: TariffReconciliationReport,
    ) -> AdminTariffReconciliationOut:
        return cls(
            dry_run=report.dry_run,
            scanned=report.scanned,
            healthy=report.healthy,
            candidates=report.candidates,
            applied=report.applied,
            unresolved=report.unresolved,
            generated_at=report.generated_at,
            items_truncated=report.items_truncated,
            items=[AdminTariffReconciliationItemOut.from_item(item) for item in report.items],
        )


__all__ = [
    "AdminTariffReconciliationApplyBody",
    "AdminTariffReconciliationItemOut",
    "AdminTariffReconciliationOut",
]
