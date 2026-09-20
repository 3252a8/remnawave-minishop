"""Balance, advertising and reconciliation support for Remnashop imports."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

from bot.services.partner_common import currency_scale
from db.activity_models import AdAttribution, AdCampaign
from db.balance_models import UserBalanceLedgerEntry

from .common import SOURCE, _as_utc, _json_dumps, _path_write_text, _to_int, _truthy
from .remnashop_env import _normalize_currency
from .remnashop_sales import _RemnashopSalesSection


async def _artifact(path: str | None, payload: dict[str, Any]) -> None:
    if path:
        await _path_write_text(Path(path), _json_dumps(payload) + "\n", encoding="utf-8")


class _RemnashopOperationsSection(_RemnashopSalesSection):
    async def _source_balance_currency(self) -> str | None:
        candidate: str | None
        if self.balance_currency_override:
            candidate = self.balance_currency_override
        else:
            source_settings = await self._fetch_one("settings")
            candidate = _normalize_currency(
                source_settings.get("default_currency") if source_settings else None
            )
        normalized = str(candidate or "").strip().upper()
        if normalized and re.fullmatch(r"[A-Z0-9]{2,16}", normalized):
            return normalized
        return None

    async def build_inventory(self) -> dict[str, Any]:
        relevant_tables = {
            "ad_links",
            "alembic_version",
            "payment_gateways",
            "plan_durations",
            "plan_prices",
            "plans",
            "promocode_activations",
            "promocodes",
            "referrals",
            "settings",
            "subscriptions",
            "transactions",
            "user_oauth_providers",
            "users",
        }
        counts: dict[str, int] = {}
        columns: dict[str, list[str]] = {}
        for table in sorted(relevant_tables & self.tables):
            columns[table] = sorted(await self._source_columns(table))
            result = await self.source.execute(
                text(f'SELECT count(*) FROM "{self.source_schema}"."{table}"')
            )
            counts[table] = int(result.scalar() or 0)
        missing = sorted({"users"} - self.tables)
        if missing:
            self.summary["blockers"].append("Required Remnashop users table is missing")
        self.balance_currency = await self._source_balance_currency()
        user_columns = set(columns.get("users", []))
        self.inventory = {
            "source": self.source_type,
            "schema": self.source_schema,
            "supported": not missing,
            "table_counts": counts,
            "columns": columns,
            "missing_required_tables": missing,
            "capabilities": {
                "balance_points": "points" in user_columns,
                "email_accounts": "email" in user_columns,
                "oauth_identities": "user_oauth_providers" in self.tables,
                "advertising": "ad_links" in self.tables and "ad_link_id" in user_columns,
            },
            "balance_currency": self.balance_currency,
        }
        await _artifact(self.inventory_output, self.inventory)
        return self.inventory

    async def import_balances(self) -> None:
        columns = await self._source_columns("users")
        if "points" not in columns:
            self.summary["balance_ledger"]["missing_source_column"] += 1
            return
        currency = self.balance_currency or await self._source_balance_currency()
        rows = await self._fetch_rows("users", order_by="id")
        nonzero_rows = [row for row in rows if (_to_int(row.get("points")) or 0) != 0]
        if not currency:
            if nonzero_rows:
                self.summary["blockers"].append(
                    "Remnashop points have no valid currency; pass --balance-currency"
                )
            return
        scale = currency_scale(currency)
        factor = 10**scale
        self.summary["balance_ledger"]["currency"] = currency
        self.summary["balance_ledger"]["currency_scale"] = scale
        self.summary["balance_ledger"]["source_nonzero_users"] = len(nonzero_rows)
        self.summary["balance_ledger"]["source_total_minor"] = sum(
            (_to_int(row.get("points")) or 0) * factor for row in rows
        )
        if self.target_balance_currency and self.target_balance_currency != currency:
            self.summary["warnings"].append(
                "Target user-balance currency differs from Remnashop balance currency: "
                f"{self.target_balance_currency} != {currency}. Configure USER_BALANCE_CURRENCY."
            )
        for row in nonzero_rows:
            source_id = _to_int(row.get("id"))
            target_id = await self._mapped_user_id(source_id)
            if source_id is None or target_id is None:
                self.summary["balance_ledger"]["skipped"] += 1
                continue
            amount_minor = (_to_int(row.get("points")) or 0) * factor
            idempotency_key = f"remnashop:user:{source_id}:opening-balance"
            existing = (
                await self.target.execute(
                    select(UserBalanceLedgerEntry).where(
                        UserBalanceLedgerEntry.idempotency_key == idempotency_key
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                if (
                    int(existing.user_id) != target_id
                    or str(existing.currency).upper() != currency
                    or int(existing.currency_scale) != scale
                    or int(existing.amount_minor) != amount_minor
                ):
                    self.summary["blockers"].append(
                        f"Opening balance entry for Remnashop user {source_id} differs from source"
                    )
                    self.summary["balance_ledger"]["conflict"] += 1
                else:
                    self.summary["balance_ledger"]["existing"] += 1
                continue
            now = datetime.now(UTC)
            self.target.add(
                UserBalanceLedgerEntry(
                    user_id=target_id,
                    currency=currency,
                    currency_scale=scale,
                    amount_minor=amount_minor,
                    kind="admin_adjustment",
                    state="posted",
                    reference_type="legacy_import",
                    reference_id=str(source_id),
                    idempotency_key=idempotency_key,
                    actor_admin_id=self.created_by_admin_id or None,
                    reason="Remnashop opening balance",
                    metadata_json=_json_dumps(
                        {"source_user_id": source_id, "source_points": row.get("points")}
                    ),
                    created_at=now,
                    posted_at=now,
                )
            )
            await self._upsert_mapping(
                entity_type="balance_adjustment",
                source_id=source_id,
                target_table="user_balance_ledger_entries",
                target_id=idempotency_key,
                metadata={
                    "amount_minor": amount_minor,
                    "currency": currency,
                    "currency_scale": scale,
                },
            )
            self.summary["balance_ledger"]["created"] += 1

    async def import_advertising(self) -> None:
        campaign_targets: dict[int, int] = {}
        for row in await self._fetch_rows("ad_links", order_by="id"):
            source_id = _to_int(row.get("id"))
            start_param = str(row.get("code") or "").strip()
            if source_id is None or not start_param:
                self.summary["advertising"]["campaigns_skipped"] += 1
                continue
            mapping = await self._get_mapping("ad_campaign", source_id)
            campaign = None
            if mapping and str(mapping.target_id).isdigit():
                campaign = await self.target.get(AdCampaign, int(mapping.target_id))
            if campaign is None:
                campaign = (
                    await self.target.execute(
                        select(AdCampaign).where(AdCampaign.start_param == start_param)
                    )
                ).scalar_one_or_none()
            if campaign is None:
                campaign = AdCampaign(
                    source=SOURCE,
                    start_param=start_param,
                    cost=0.0,
                    is_active=_truthy(row.get("is_active")),
                    created_at=_as_utc(row.get("created_at")),
                )
                self.target.add(campaign)
                await self.target.flush()
                self.summary["advertising"]["campaigns_created"] += 1
            target_id = campaign.ad_campaign_id or source_id
            campaign_targets[source_id] = int(target_id)
            await self._upsert_mapping(
                entity_type="ad_campaign",
                source_id=source_id,
                target_table="ad_campaigns",
                target_id=target_id,
                metadata={"name": str(row.get("name") or "").strip() or None},
            )
        if "ad_link_id" not in await self._source_columns("users"):
            return
        for row in await self._fetch_rows("users", order_by="id"):
            source_id = _to_int(row.get("id"))
            campaign_id = campaign_targets.get(_to_int(row.get("ad_link_id")) or -1)
            user_id = await self._mapped_user_id(source_id)
            if source_id is None or campaign_id is None or user_id is None:
                continue
            attribution = await self.target.get(AdAttribution, user_id)
            if attribution is None:
                self.target.add(
                    AdAttribution(
                        user_id=user_id,
                        ad_campaign_id=campaign_id,
                        first_start_at=_as_utc(row.get("created_at")),
                    )
                )
                self.summary["advertising"]["attributions_created"] += 1
            elif self._can_overwrite():
                attribution.ad_campaign_id = campaign_id
                self.summary["advertising"]["attributions_updated"] += 1
            else:
                self.summary["advertising"]["attributions_preserved"] += 1
            await self._upsert_mapping(
                entity_type="ad_attribution",
                source_id=source_id,
                target_table="ad_attributions",
                target_id=user_id,
            )

    async def build_reconciliation(self) -> dict[str, Any]:
        mapping_counts: dict[str, int] = {}
        if not self.dry_run:
            result = await self.target.execute(
                text(
                    """
                    SELECT entity_type, count(*)
                    FROM legacy_import_mappings
                    WHERE source = 'remnashop'
                    GROUP BY entity_type
                    ORDER BY entity_type
                    """
                )
            )
            mapping_counts = {str(row[0]): int(row[1]) for row in result.all()}
        self.reconciliation = {
            "source": self.source_type,
            "dry_run": self.dry_run,
            "source_counts": self.inventory.get("table_counts", {}),
            "target_mapping_counts": mapping_counts,
            "import_summary": self._plain_summary(),
            "invariants": {
                "source_and_target_are_distinct": True,
                "source_schema_supported": bool(self.inventory.get("supported")),
                "identity_conflicts": len(self.summary["identity_conflicts"]),
                "balance_currency": self.balance_currency,
                "balance_entries_conflicting": self.summary["balance_ledger"].get("conflict", 0),
            },
            "blockers": list(self.summary["blockers"]),
            "warnings": list(self.summary["warnings"]),
        }
        await _artifact(self.reconciliation_output, self.reconciliation)
        return self.reconciliation

    async def build_config_plan(self) -> dict[str, Any]:
        nonzero_balances = int(self.summary["balance_ledger"].get("source_nonzero_users", 0))
        self.config_plan = {
            "source": self.source_type,
            "balance": {
                "currency": self.balance_currency,
                "currency_scale": self.summary["balance_ledger"].get("currency_scale"),
                "nonzero_users": nonzero_balances,
                "recommended_env": {
                    "USER_BALANCE_CURRENCY": self.balance_currency,
                    "USER_BALANCE_ENABLED": bool(nonzero_balances),
                },
            },
            "features": {
                "verified_email_accounts": self.summary["identities"].get("verified_emails", 0),
                "oauth_identities": self.summary["identities"].get("oauth", 0),
                "advertising_campaigns": self.summary["advertising"].get("campaigns_created", 0),
                "squad_overrides": sum(self.summary["squad_overrides"].values()),
            },
            "manual": [
                "Review source broadcasts; delivery history is not imported.",
                "Review unsupported device and persistent-discount activation codes.",
                "Referral relationships remain ordinary referrals; "
                "partner profiles are not created.",
            ],
        }
        await _artifact(self.config_plan_output, self.config_plan)
        return self.config_plan
