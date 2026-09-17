"""Secondary Bedolaga import sections for operational data and settings."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from db.activity_models import AdAttribution, AdCampaign, SupportTicket, SupportTicketMessage
from db.partner_models import PartnerApplication, PartnerProfile

from .common import _as_utc, _json_dumps, _path_write_text, _to_int, _truthy
from .remnashop_base import _RemnashopImporterBase

SETTINGS_MAP = {
    "TRIAL_DURATION_DAYS": ("TRIAL_DURATION_DAYS", False, 1.0),
    "TRIAL_TRAFFIC_LIMIT_GB": ("TRIAL_TRAFFIC_LIMIT_GB", False, 1.0),
    "TRIAL_DEVICE_LIMIT": ("TRIAL_HWID_DEVICE_LIMIT", False, 1.0),
    "TRIAL_PAYMENT_ENABLED": ("TRIAL_PAYMENT_ENABLED", False, 1.0),
    "TRIAL_ACTIVATION_PRICE": ("TRIAL_PAYMENT_PRICE", False, 0.01),
    "REFERRAL_PROGRAM_ENABLED": ("REFERRAL_PROGRAM_ENABLED", False, 1.0),
    "SUPPORT_USERNAME": ("SUPPORT_LINK", False, 1.0),
    "REMNAWAVE_API_URL": ("PANEL_API_URL", False, 1.0),
    "REMNAWAVE_API_KEY": ("PANEL_API_KEY", True, 1.0),
    "REMNAWAVE_WEBHOOK_SECRET": ("PANEL_WEBHOOK_SECRET", True, 1.0),
}


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _string(value: Any, limit: int | None = None) -> str | None:
    result = str(value or "").strip()
    if not result:
        return None
    return result[:limit] if limit else result


def _normalize_panel_api_url(value: Any) -> str | None:
    base = _string(value)
    if not base:
        return None
    base = base.rstrip("/")
    if base.endswith("/api"):
        return base
    return f"{base}/api"


async def _artifact(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    await _path_write_text(target, _json_dumps(payload) + "\n", encoding="utf-8")


class _BedolagaOperationsSection(_RemnashopImporterBase):
    """Import operational tables that do not participate in financial reconciliation."""

    config_plan: dict[str, Any]
    generated_tariff_catalog: dict[str, Any] | None

    async def _mapped_user_id(self, source_user_id: Any) -> int | None:
        raise NotImplementedError

    async def import_support(self) -> None:
        ticket_targets: dict[int, int] = {}
        async for row in self._iter_rows("tickets", order_by="id"):
            source_id = _to_int(row.get("id"))
            user_id = await self._mapped_user_id(row.get("user_id"))
            if source_id is None or user_id is None:
                continue
            mapping = await self._get_mapping("support_ticket", source_id)
            if mapping:
                target_id = _to_int(mapping.target_id)
                if target_id:
                    ticket_targets[source_id] = target_id
                continue
            status = _enum_text(row.get("status"))
            ticket = SupportTicket(
                user_id=user_id,
                subject=_string(row.get("title"), 160) or "Legacy support ticket",
                category="other",
                priority=_string(row.get("priority"), 16) or "normal",
                status="closed" if status == "closed" else "open",
                last_message_at=_as_utc(row.get("updated_at")),
                created_at=_as_utc(row.get("created_at")),
                updated_at=_as_utc(row.get("updated_at")),
                closed_at=_as_utc(row.get("closed_at")),
            )
            self.target.add(ticket)
            await self.target.flush()
            target_id = ticket.ticket_id or source_id
            ticket_targets[source_id] = target_id
            await self._upsert_mapping(
                entity_type="support_ticket",
                source_id=source_id,
                target_table="support_tickets",
                target_id=target_id,
            )
            self.summary["support"]["tickets"] += 1
        async for row in self._iter_rows("ticket_messages", order_by="id"):
            source_id = _to_int(row.get("id"))
            ticket_id = ticket_targets.get(_to_int(row.get("ticket_id")) or -1)
            if (
                source_id is None
                or ticket_id is None
                or await self._get_mapping("support_message", source_id)
            ):
                continue
            author_user_id = await self._mapped_user_id(row.get("user_id"))
            body = (
                _string(row.get("message_text"))
                or _string(row.get("media_caption"))
                or "[legacy media]"
            )
            message = SupportTicketMessage(
                ticket_id=ticket_id,
                author_role="admin" if _truthy(row.get("is_from_admin")) else "user",
                author_user_id=None if _truthy(row.get("is_from_admin")) else author_user_id,
                body=body,
                body_format="text",
                created_at=_as_utc(row.get("created_at")),
            )
            self.target.add(message)
            await self.target.flush()
            await self._upsert_mapping(
                entity_type="support_message",
                source_id=source_id,
                target_table="support_ticket_messages",
                target_id=message.message_id or source_id,
            )
            self.summary["support"]["messages"] += 1

    async def import_advertising(self) -> None:
        campaign_targets: dict[int, int] = {}
        async for row in self._iter_rows("advertising_campaigns", order_by="id"):
            source_id = _to_int(row.get("id"))
            start = _string(row.get("start_parameter"), 255)
            if source_id is None or not start:
                continue
            mapping = await self._get_mapping("ad_campaign", source_id)
            if mapping:
                target_id = _to_int(mapping.target_id)
                if target_id:
                    campaign_targets[source_id] = target_id
                continue
            existing_campaign_result = await self.target.execute(
                select(AdCampaign).where(AdCampaign.start_param == start)
            )
            campaign = existing_campaign_result.scalar_one_or_none()
            if campaign is None:
                campaign = AdCampaign(
                    source="bedolaga",
                    start_param=start,
                    cost=0.0,
                    is_active=_truthy(row.get("is_active")),
                    created_at=_as_utc(row.get("created_at")),
                )
                self.target.add(campaign)
                await self.target.flush()
            target_id = campaign.ad_campaign_id or source_id
            campaign_targets[source_id] = target_id
            await self._upsert_mapping(
                entity_type="ad_campaign",
                source_id=source_id,
                target_table="ad_campaigns",
                target_id=target_id,
                metadata={"name": _string(row.get("name"), 255)},
            )
            self.summary["advertising"]["campaigns"] += 1
        async for row in self._iter_rows("advertising_campaign_registrations", order_by="id"):
            source_id = _to_int(row.get("id"))
            user_id = await self._mapped_user_id(row.get("user_id"))
            campaign_id = campaign_targets.get(_to_int(row.get("campaign_id")) or -1)
            if (
                source_id is None
                or user_id is None
                or campaign_id is None
                or await self._get_mapping("ad_attribution", source_id)
            ):
                continue
            existing_attribution = await self.target.get(AdAttribution, user_id)
            if existing_attribution is None:
                self.target.add(
                    AdAttribution(
                        user_id=user_id,
                        ad_campaign_id=campaign_id,
                        first_start_at=_as_utc(row.get("created_at")),
                    )
                )
            await self._upsert_mapping(
                entity_type="ad_attribution",
                source_id=source_id,
                target_table="ad_attributions",
                target_id=user_id,
            )
            self.summary["advertising"]["attributions"] += 1

    async def import_partners(self) -> None:
        async for row in self._iter_rows("users", order_by="id"):
            if _enum_text(row.get("partner_status")) != "approved":
                continue
            source_id = _to_int(row.get("id"))
            user_id = await self._mapped_user_id(source_id)
            if (
                source_id is None
                or user_id is None
                or await self._get_mapping("partner_profile", source_id)
            ):
                continue
            code = _string(row.get("referral_code"), 64) or f"bedolaga-{source_id}"
            label = (
                _string(row.get("username"), 255)
                or _string(row.get("email"), 255)
                or f"Bedolaga partner {source_id}"
            )
            profile = PartnerProfile(
                user_id=user_id,
                status="active",
                commission_bps=3000,
                partner_code=code,
                display_label_snapshot=label,
                activated_at=_as_utc(row.get("updated_at")) or datetime.now(UTC),
                created_at=_as_utc(row.get("created_at")),
            )
            self.target.add(profile)
            await self.target.flush()
            await self._upsert_mapping(
                entity_type="partner_profile",
                source_id=source_id,
                target_table="partner_profiles",
                target_id=profile.partner_id or source_id,
            )
            self.summary["partners"]["profiles"] += 1
        async for row in self._iter_rows("partner_applications", order_by="id"):
            source_id = _to_int(row.get("id"))
            user_id = await self._mapped_user_id(row.get("user_id"))
            if (
                source_id is None
                or user_id is None
                or await self._get_mapping("partner_application", source_id)
            ):
                continue
            raw_status = _enum_text(row.get("status"))
            status = (
                raw_status
                if raw_status in {"pending", "approved", "rejected", "canceled"}
                else "canceled"
            )
            label = _string(row.get("company_name"), 255) or f"Bedolaga applicant {source_id}"
            message = (
                "\n".join(
                    value
                    for value in (
                        _string(row.get("description")),
                        _string(row.get("website_url")),
                        _string(row.get("telegram_channel")),
                    )
                    if value
                )
                or "Imported application"
            )
            application = PartnerApplication(
                user_id=user_id,
                display_label_snapshot=label,
                message=message,
                status=status,
                submitted_at=_as_utc(row.get("created_at")) or datetime.now(UTC),
                decided_at=_as_utc(row.get("processed_at")),
                decision_message=_string(row.get("admin_comment")),
                approved_commission_bps=(_to_int(row.get("approved_commission_percent")) or 0) * 100
                or None,
            )
            self.target.add(application)
            await self.target.flush()
            await self._upsert_mapping(
                entity_type="partner_application",
                source_id=source_id,
                target_table="partner_applications",
                target_id=application.application_id or source_id,
            )
            self.summary["partners"]["applications"] += 1

    def _setting_value(self, raw: Any, scale: float) -> Any:
        value = raw
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in {"true", "false"}:
                value = lowered == "true"
            else:
                try:
                    value = float(raw) if "." in raw else int(raw)
                except ValueError:
                    value = raw
        if scale != 1.0 and isinstance(value, (int, float)):
            return float(value) * scale
        return value

    async def import_settings(self) -> None:
        source_values: dict[str, Any] = dict(self.source_env)
        async for row in self._iter_rows("system_settings", order_by="id"):
            key = _string(row.get("key"))
            if key:
                source_values[key] = row.get("value")
        changes: list[dict[str, Any]] = []
        for source_key, (target_key, secret, scale) in SETTINGS_MAP.items():
            raw = source_values.get(source_key)
            if raw in (None, ""):
                continue
            value = self._setting_value(raw, scale)
            if source_key == "REMNAWAVE_API_URL":
                value = _normalize_panel_api_url(value)
                if value is None:
                    continue
            written = await self._upsert_setting_override(target_key, value)
            changes.append(
                {
                    "source_key": source_key,
                    "target_key": target_key,
                    "action": "write" if written else "manual",
                    "secret": secret,
                    "value": "<redacted>" if secret else value,
                }
            )
            self.summary["settings"]["written" if written else "manual"] += 1
        methods = await self._fetch_rows("payment_method_configs", order_by="sort_order, id")
        enabled: list[str] = []
        for row in methods:
            value = _string(row.get("method_id"), 50)
            if value and _truthy(row.get("is_enabled")):
                enabled.append(value)
        if enabled and await self._upsert_setting_override(
            "PAYMENT_METHODS_ORDER", ",".join(enabled)
        ):
            self.summary["payment_provider_settings"]["payment_order_written"] += 1
        self.config_plan = {
            "source": self.source_type,
            "changes": changes,
            "payment_methods_order": enabled,
            "manual": [
                "Verify provider credentials and webhook URLs before enabling traffic.",
                "Review required-channel, legal-page and custom-menu settings manually.",
            ],
            "tariff_catalog": {
                "path": self.tariffs_config_path,
                "generated": bool(self.generated_tariff_catalog),
                "tariffs_count": len((self.generated_tariff_catalog or {}).get("tariffs", [])),
            },
        }
        await _artifact(self.config_plan_output, self.config_plan)
        if self.generated_tariff_catalog and not self.dry_run:
            path = Path(self.tariffs_config_path)
            await _path_write_text(
                path,
                _json_dumps(self.generated_tariff_catalog) + "\n",
                encoding="utf-8",
            )
