from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.infra.event_payloads import (
    PartnerApplicationDecidedPayload,
    PartnerApplicationSubmittedPayload,
    PartnerClientAttributedPayload,
    PartnerStatusChangedPayload,
)
from bot.services.partner_common import PartnerError, as_utc, compact_json, safe_user_label
from bot.services.registration_invite_gate import referral_program_enabled
from bot.utils.invite_links import invitation_link_prefix
from bot.utils.partner_links import build_partner_bot_link, build_partner_webapp_link
from config.settings import Settings
from db.dal import partner_dal, partner_reporting_dal, user_dal
from db.models import User
from db.partner_models import PartnerApplication, PartnerClient, PartnerProfile


def _profile_code() -> str:
    return secrets.token_urlsafe(18).rstrip("=")


def _public_client_id() -> str:
    return secrets.token_hex(8)


AUTO_ENROLLMENT_BATCH_SIZE = 500


class PartnerProgramService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def config(self):
        return self.settings.partner_settings

    @property
    def automatic_enrollment_active(self) -> bool:
        config = getattr(self.settings, "partner_settings", None)
        return bool(config and config.enabled and config.auto_enrollment_enabled)

    async def auto_enroll_user(
        self,
        session: AsyncSession,
        *,
        user: User,
        actor_admin_id: int | None = None,
    ) -> PartnerProfile | None:
        """Materialize the automatic entitlement without overriding moderation state."""

        if not self.automatic_enrollment_active or bool(user.is_banned):
            return None
        existing = await partner_dal.get_profile_by_user_id(session, int(user.user_id))
        if existing is not None:
            if existing.status == "active":
                await partner_dal.approve_pending_applications_for_users(
                    session,
                    user_ids=[int(user.user_id)],
                    actor_user_id=actor_admin_id,
                )
            return existing
        profile = await self.create_profile_for_user(
            session,
            user=user,
            actor_admin_id=actor_admin_id,
            emit_status_event=False,
            audit_reason="automatic_enrollment",
        )
        if profile.status == "active":
            await partner_dal.approve_pending_applications_for_users(
                session,
                user_ids=[int(user.user_id)],
                actor_user_id=actor_admin_id,
            )
        return profile

    async def auto_enroll_all_users(
        self,
        session: AsyncSession,
        *,
        actor_admin_id: int | None = None,
    ) -> int:
        """Activate every eligible account in bounded, idempotent batches."""

        if not self.automatic_enrollment_active:
            return 0
        enrolled = 0
        stalled_batches = 0
        while True:
            users = await partner_dal.list_users_without_partner_profile(
                session,
                limit=AUTO_ENROLLMENT_BATCH_SIZE,
            )
            if not users:
                return enrolled
            now = datetime.now(UTC)
            created = await partner_dal.create_profiles_bulk(
                session,
                profiles=[
                    {
                        "user_id": int(user.user_id),
                        "status": "active",
                        "commission_bps": int(self.config.default_commission_bps),
                        "partner_code": _profile_code(),
                        "display_label_snapshot": safe_user_label(user),
                        "activated_at": now,
                        "created_at": now,
                        "updated_at": now,
                    }
                    for user in users
                ],
                actor_user_id=actor_admin_id,
            )
            await partner_dal.approve_pending_applications_for_users(
                session,
                user_ids=[int(user.user_id) for user in users],
                actor_user_id=actor_admin_id,
            )
            enrolled += len(created)
            stalled_batches = stalled_batches + 1 if not created else 0
            if stalled_batches >= 5:  # pragma: no cover - collision/concurrency defence
                raise PartnerError("partner_auto_enrollment_failed", 500)

    async def referral_program_enabled_for_user(
        self,
        session: AsyncSession,
        *,
        user_id: int,
    ) -> bool:
        if not referral_program_enabled(self.settings):
            return False
        if not bool(getattr(self.config, "enabled", False)) or not bool(
            getattr(self.config, "referral_program_disabled", False)
        ):
            return True
        profile = await partner_dal.get_profile_by_user_id(session, user_id)
        return profile is None

    async def submit_application(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        message: str,
    ) -> PartnerApplication:
        if not self.config.enabled:
            raise PartnerError("partner_program_disabled", 403)
        if self.config.auto_enrollment_enabled:
            raise PartnerError("partner_application_not_required", 409)
        normalized = message.strip()
        if len(normalized) < 10:
            raise PartnerError("application_message_too_short", 400)
        if len(normalized) > self.config.application_message_max_length:
            raise PartnerError("application_message_too_long", 400)
        if await partner_dal.get_profile_by_user_id(session, user_id):
            raise PartnerError("already_partner", 409)
        latest = await partner_dal.latest_application_for_user(session, user_id, for_update=True)
        if latest:
            if latest.status == "pending":
                if str(latest.message).strip() == normalized:
                    return latest
                raise PartnerError("application_already_pending", 409)
            if latest.status == "approved":
                raise PartnerError("already_partner", 409)
            if latest.status == "rejected":
                explicit_reopen = (
                    latest.reapply_allowed_at is not None
                    and latest.reapply_allowed_at <= datetime.now(UTC)
                )
                allowed_at = getattr(latest, "decided_at", None)
                if self.config.reapplication_cooldown_days and allowed_at:
                    allowed_at += timedelta(days=self.config.reapplication_cooldown_days)
                if not explicit_reopen and (
                    not self.config.reapplication_enabled
                    or (allowed_at is not None and allowed_at > datetime.now(UTC))
                ):
                    raise PartnerError("reapplication_not_allowed", 409)
            submitted_at = getattr(latest, "submitted_at", None)
            if submitted_at is not None and as_utc(submitted_at) + timedelta(
                hours=self.config.application_rate_limit_hours
            ) > datetime.now(UTC):
                raise PartnerError("application_rate_limited", 429)
        user = await user_dal.get_user_by_id(session, user_id)
        if user is None:
            raise PartnerError("user_not_found", 404)
        try:
            application = await partner_dal.create_application(
                session,
                user_id=user_id,
                display_label=safe_user_label(user),
                message=normalized,
            )
        except IntegrityError as exc:
            raise PartnerError("application_already_pending", 409) from exc
        await partner_dal.create_audit_event(
            session,
            event_type="application_submitted",
            actor_type="user",
            application_id=int(application.application_id),
            actor_user_id=user_id,
            new_values_json=compact_json({"status": "pending"}),
        )
        await events.emit_model(
            PartnerApplicationSubmittedPayload(
                application_id=int(application.application_id),
                user_id=user_id,
                status="pending",
                submitted_at=application.submitted_at or datetime.now(UTC),
            )
        )
        return application

    async def create_profile_for_user(
        self,
        session: AsyncSession,
        *,
        user: User,
        commission_bps: int | None = None,
        welcome_message: str | None = None,
        actor_admin_id: int | None = None,
        application_id: int | None = None,
        emit_status_event: bool = True,
        audit_reason: str | None = None,
    ) -> PartnerProfile:
        existing = await partner_dal.get_profile_by_user_id(
            session,
            int(user.user_id),
            for_update=True,
        )
        if existing:
            if existing.status == "closed":
                raise PartnerError("partner_closed", 409)
            return existing
        bps = self.config.default_commission_bps if commission_bps is None else commission_bps
        if bps < 0 or bps > 10000:
            raise PartnerError("invalid_commission_rate", 400)
        for _ in range(5):
            try:
                async with session.begin_nested():
                    profile = await partner_dal.create_profile(
                        session,
                        user_id=int(user.user_id),
                        partner_code=_profile_code(),
                        display_label=safe_user_label(user),
                        commission_bps=bps,
                        welcome_message=(welcome_message or "").strip() or None,
                    )
                break
            except IntegrityError:
                existing = await partner_dal.get_profile_by_user_id(
                    session,
                    int(user.user_id),
                    for_update=True,
                )
                if existing:
                    return existing
        else:  # pragma: no cover - cryptographic collision defence
            raise PartnerError("partner_code_generation_failed", 500)
        audit_values: dict[str, Any] = {
            "status": "active",
            "commission_bps": int(profile.commission_bps),
        }
        if audit_reason:
            audit_values["source"] = audit_reason
        await partner_dal.create_audit_event(
            session,
            event_type="partner_created",
            actor_type="admin" if actor_admin_id else "system",
            partner_id=int(profile.partner_id),
            application_id=application_id,
            actor_user_id=actor_admin_id,
            new_values_json=compact_json(audit_values),
            reason=audit_reason,
        )
        if application_id is None and emit_status_event:
            await events.emit_model(
                PartnerStatusChangedPayload(
                    partner_id=int(profile.partner_id),
                    user_id=int(user.user_id),
                    old_status="none",
                    status="active",
                    changed_at=profile.activated_at or datetime.now(UTC),
                )
            )
        return profile

    async def decide_application(
        self,
        session: AsyncSession,
        *,
        application_id: int,
        approve: bool,
        actor_admin_id: int,
        decision_message: str | None,
        commission_bps: int | None = None,
        welcome_message: str | None = None,
    ) -> tuple[PartnerApplication, PartnerProfile | None]:
        application = await partner_dal.get_application_by_id(
            session,
            application_id,
            for_update=True,
        )
        if not application:
            raise PartnerError("application_not_found", 404)
        if application.status != "pending":
            raise PartnerError("stale_application", 409)
        now = datetime.now(UTC)
        application.decided_at = now
        application.decided_by_admin_id = actor_admin_id
        application.decision_message = (decision_message or "").strip() or None
        profile: PartnerProfile | None = None
        if approve:
            if application.user_id is None:
                raise PartnerError("application_user_deleted", 409)
            user = await user_dal.get_user_by_id(session, int(application.user_id))
            if not user:
                raise PartnerError("application_user_deleted", 409)
            rate = self.config.default_commission_bps if commission_bps is None else commission_bps
            profile = await self.create_profile_for_user(
                session,
                user=user,
                commission_bps=rate,
                welcome_message=welcome_message,
                actor_admin_id=actor_admin_id,
                application_id=application_id,
            )
            application.status = "approved"
            application.approved_commission_bps = rate
            application.welcome_message = (welcome_message or "").strip() or None
        else:
            application.status = "rejected"
            if self.config.reapplication_enabled:
                application.reapply_allowed_at = now + timedelta(
                    days=self.config.reapplication_cooldown_days
                )
        await session.flush()
        await partner_dal.create_audit_event(
            session,
            event_type="application_decided",
            actor_type="admin",
            partner_id=int(profile.partner_id) if profile else None,
            application_id=application_id,
            actor_user_id=actor_admin_id,
            old_values_json=compact_json({"status": "pending"}),
            new_values_json=compact_json({"status": str(application.status)}),
            reason=application.decision_message,
        )
        await events.emit_model(
            PartnerApplicationDecidedPayload(
                application_id=application_id,
                partner_id=int(profile.partner_id) if profile else None,
                user_id=int(application.user_id) if application.user_id is not None else None,
                status=str(application.status),
                decided_at=now,
            )
        )
        return application, profile

    async def resolve_invite_code(
        self,
        session: AsyncSession,
        code: str,
    ) -> PartnerProfile | None:
        if not self.config.enabled:
            return None
        normalized = str(code or "").strip()
        if normalized.startswith("p_"):
            normalized = normalized[2:]
        if not normalized:
            return None
        profile = await partner_dal.get_profile_by_code(session, normalized)
        if not profile or profile.status != "active" or profile.user_id is None:
            return None
        return profile

    async def client_welcome_bonus_eligible(
        self,
        session: AsyncSession,
        *,
        user_id: int,
    ) -> bool:
        config = getattr(self.settings, "partner_settings", None)
        if (
            config is None
            or not bool(getattr(config, "enabled", False))
            or not bool(getattr(config, "client_welcome_bonus_enabled", False))
        ):
            return False
        attribution = await partner_dal.get_client_with_profile_for_user(session, user_id)
        if not attribution:
            return False
        client, profile = attribution
        return bool(
            profile.status == "active"
            and client.source in {"partner_telegram_link", "partner_web_link"}
            and client.welcome_bonus_eligible_at is not None
        )

    async def client_payment_bonus_eligible(
        self,
        session: AsyncSession,
        *,
        user_id: int,
    ) -> bool:
        config = getattr(self.settings, "partner_settings", None)
        if (
            config is None
            or not bool(getattr(config, "enabled", False))
            or not bool(getattr(config, "client_payment_bonus_enabled", False))
        ):
            return False
        attribution = await partner_dal.get_client_with_profile_for_user(session, user_id)
        if not attribution:
            return False
        _client, profile = attribution
        return bool(profile.status == "active")

    async def attribute_user(
        self,
        session: AsyncSession,
        *,
        user: User,
        partner_code: str,
        source: str,
        actor_admin_id: int | None = None,
        registered_via_partner_link: bool = False,
    ) -> PartnerClient:
        if not self.config.enabled and source != "admin_manual":
            raise PartnerError("partner_program_disabled", 403)
        existing = await partner_dal.get_client_by_user_id(
            session,
            int(user.user_id),
            for_update=True,
        )
        if existing:
            return existing
        profile = await partner_dal.get_profile_by_code(session, partner_code, for_update=True)
        if not profile or profile.status != "active" or profile.user_id is None:
            raise PartnerError("invalid_partner_code", 400)
        if int(profile.user_id) == int(user.user_id):
            raise PartnerError("partner_self_attribution", 409)
        try:
            async with session.begin_nested():
                attribution = await partner_dal.create_client_attribution(
                    session,
                    partner_id=int(profile.partner_id),
                    client_user_id=int(user.user_id),
                    public_client_id=_public_client_id(),
                    public_label=safe_user_label(user, "Client"),
                    source=source,
                    attributed_by_admin_id=actor_admin_id,
                    welcome_bonus_eligible_at=(
                        datetime.now(UTC)
                        if registered_via_partner_link
                        and self.config.client_welcome_bonus_enabled
                        and source in {"partner_telegram_link", "partner_web_link"}
                        else None
                    ),
                )
        except IntegrityError as exc:
            existing = await partner_dal.get_client_by_user_id(session, int(user.user_id))
            if existing:
                return existing
            raise PartnerError("partner_attribution_conflict", 409) from exc
        await partner_dal.create_audit_event(
            session,
            event_type="client_attributed",
            actor_type="admin" if actor_admin_id else "user",
            partner_id=int(profile.partner_id),
            actor_user_id=actor_admin_id or int(user.user_id),
            new_values_json=compact_json(
                {"partner_client_id": int(attribution.partner_client_id), "source": source}
            ),
        )
        await events.emit_model(
            PartnerClientAttributedPayload(
                partner_id=int(profile.partner_id),
                partner_client_id=int(attribution.partner_client_id),
                client_user_id=int(user.user_id),
                source=source,
                attributed_at=attribution.attributed_at or datetime.now(UTC),
            )
        )
        return attribution

    def links(self, profile: PartnerProfile, *, bot_username: str = "") -> dict[str, Any]:
        code = str(profile.partner_code)
        telegram = (
            build_partner_bot_link(bot_username, code, invitation_link_prefix(self.settings))
            if self.config.telegram_link_enabled
            else None
        )
        web_link = (
            build_partner_webapp_link(
                self.settings.SUBSCRIPTION_MINI_APP_URL, code, invitation_link_prefix(self.settings)
            )
            if self.config.webapp_link_enabled
            else None
        )
        return {
            "telegram": telegram,
            "web": web_link,
            "telegram_enabled": self.config.telegram_link_enabled,
            "web_enabled": self.config.webapp_link_enabled,
        }

    async def rotate_link(
        self,
        session: AsyncSession,
        *,
        partner_id: int,
        actor_admin_id: int,
    ) -> PartnerProfile:
        profile = await partner_dal.get_profile_by_id(session, partner_id, for_update=True)
        if not profile:
            raise PartnerError("partner_not_found", 404)
        old_code = str(profile.partner_code)
        profile.partner_code = _profile_code()
        profile.updated_at = datetime.now(UTC)
        await session.flush()
        await partner_dal.create_audit_event(
            session,
            event_type="link_rotated",
            actor_type="admin",
            partner_id=partner_id,
            actor_user_id=actor_admin_id,
            old_values_json=compact_json({"code_suffix": old_code[-4:]}),
            new_values_json=compact_json({"code_suffix": str(profile.partner_code)[-4:]}),
        )
        return profile

    async def change_status(
        self,
        session: AsyncSession,
        *,
        partner_id: int,
        status: str,
        actor_admin_id: int,
        reason: str | None,
    ) -> PartnerProfile:
        normalized = status.strip().lower()
        if normalized not in {"active", "paused", "closed"}:
            raise PartnerError("invalid_partner_status", 400)
        profile = await partner_dal.get_profile_by_id(session, partner_id, for_update=True)
        if not profile:
            raise PartnerError("partner_not_found", 404)
        old = str(profile.status)
        if old == "closed" and normalized != "closed":
            raise PartnerError("partner_closed", 409)
        if normalized == "paused" and not str(reason or "").strip():
            raise PartnerError("pause_reason_required", 400)
        if old == normalized:
            return profile
        now = datetime.now(UTC)
        profile.status = normalized
        profile.updated_at = now
        profile.pause_reason = str(reason or "").strip() or None
        if normalized == "paused":
            profile.paused_at = now
        elif normalized == "active":
            profile.paused_at = None
        else:
            profile.closed_at = now
        await session.flush()
        await partner_dal.create_audit_event(
            session,
            event_type="partner_status_changed",
            actor_type="admin",
            partner_id=partner_id,
            actor_user_id=actor_admin_id,
            old_values_json=compact_json({"status": old}),
            new_values_json=compact_json({"status": normalized}),
            reason=profile.pause_reason,
        )
        await events.emit_model(
            PartnerStatusChangedPayload(
                partner_id=partner_id,
                user_id=int(profile.user_id) if profile.user_id is not None else None,
                old_status=old,
                status=normalized,
                changed_at=now,
            )
        )
        return profile

    async def referral_import_preview(
        self,
        session: AsyncSession,
        *,
        partner_id: int,
    ) -> dict[str, int]:
        profile = await partner_dal.get_profile_by_id(session, partner_id)
        if not profile or profile.user_id is None:
            raise PartnerError("partner_not_found", 404)
        candidates = await partner_dal.referral_import_candidates(
            session,
            partner_user_id=int(profile.user_id),
        )
        counts = {
            "found": len(candidates),
            "importable": 0,
            "already_this_partner": 0,
            "other_partner": 0,
            "self_conflict": 0,
            "historical_payments": 0,
        }
        for user, attribution, payments in candidates:
            counts["historical_payments"] += payments
            if int(user.user_id) == int(profile.user_id):
                counts["self_conflict"] += 1
            elif attribution is None:
                counts["importable"] += 1
            elif int(attribution.partner_id) == partner_id:
                counts["already_this_partner"] += 1
            else:
                counts["other_partner"] += 1
        return counts

    async def execute_referral_import(
        self,
        session: AsyncSession,
        *,
        partner_id: int,
        actor_admin_id: int,
    ) -> dict[str, int]:
        profile = await partner_dal.get_profile_by_id(session, partner_id, for_update=True)
        if not profile or profile.user_id is None:
            raise PartnerError("partner_not_found", 404)
        candidates = await partner_dal.referral_import_candidates(
            session,
            partner_user_id=int(profile.user_id),
        )
        imported = conflicts = existing = 0
        now = datetime.now(UTC)
        for user, attribution, _payments in candidates:
            if attribution is not None:
                if int(attribution.partner_id) == partner_id:
                    existing += 1
                else:
                    conflicts += 1
                continue
            if int(user.user_id) == int(profile.user_id):
                conflicts += 1
                continue
            try:
                async with session.begin_nested():
                    await partner_dal.create_client_attribution(
                        session,
                        partner_id=partner_id,
                        client_user_id=int(user.user_id),
                        public_client_id=_public_client_id(),
                        public_label=safe_user_label(user, "Client"),
                        source="referral_import",
                        attributed_by_admin_id=actor_admin_id,
                        eligible_from=now,
                    )
                imported += 1
            except IntegrityError:
                conflicts += 1
        result = {"imported": imported, "existing": existing, "conflicts": conflicts}
        await partner_dal.create_audit_event(
            session,
            event_type="referrals_imported",
            actor_type="admin",
            partner_id=partner_id,
            actor_user_id=actor_admin_id,
            new_values_json=compact_json(result),
        )
        return result

    async def bulk_referral_import_preview(self, session: AsyncSession) -> dict[str, int]:
        if referral_program_enabled(self.settings):
            raise PartnerError("referral_program_enabled", 409)
        candidates = await partner_reporting_dal.all_referral_import_candidates(session)
        counts = {
            "partners": len({int(profile.partner_id) for profile, *_rest in candidates}),
            "found": len(candidates),
            "importable": 0,
            "already_this_partner": 0,
            "other_partner": 0,
            "self_conflict": 0,
            "historical_payments": 0,
        }
        for profile, user, attribution, payments in candidates:
            partner_id = int(profile.partner_id)
            counts["historical_payments"] += payments
            if int(user.user_id) == int(profile.user_id):
                counts["self_conflict"] += 1
            elif attribution is None:
                counts["importable"] += 1
            elif int(attribution.partner_id) == partner_id:
                counts["already_this_partner"] += 1
            else:
                counts["other_partner"] += 1
        return counts

    async def execute_bulk_referral_import(
        self,
        session: AsyncSession,
        *,
        actor_admin_id: int,
    ) -> dict[str, int]:
        if referral_program_enabled(self.settings):
            raise PartnerError("referral_program_enabled", 409)
        candidates = await partner_reporting_dal.all_referral_import_candidates(session)
        conflicts = existing = 0
        now = datetime.now(UTC)
        partner_results: dict[int, dict[str, int]] = {}
        pending_clients: list[dict[str, Any]] = []
        pending_partner_by_user: dict[int, int] = {}
        for profile, user, attribution, _payments in candidates:
            partner_id = int(profile.partner_id)
            result = partner_results.setdefault(
                partner_id,
                {"imported": 0, "existing": 0, "conflicts": 0},
            )
            if attribution is not None:
                if int(attribution.partner_id) == partner_id:
                    existing += 1
                    result["existing"] += 1
                else:
                    conflicts += 1
                    result["conflicts"] += 1
                continue
            if int(user.user_id) == int(profile.user_id):
                conflicts += 1
                result["conflicts"] += 1
                continue
            client_user_id = int(user.user_id)
            pending_clients.append(
                {
                    "partner_id": partner_id,
                    "client_user_id": client_user_id,
                    "public_client_id": _public_client_id(),
                    "public_label_snapshot": safe_user_label(user, "Client"),
                    "source": "referral_import",
                    "attributed_at": now,
                    "eligible_from": now,
                    "attributed_by_admin_id": actor_admin_id,
                }
            )
            pending_partner_by_user[client_user_id] = partner_id
        created = await partner_dal.create_client_attributions_bulk(
            session,
            clients=pending_clients,
        )
        for client_user_id, partner_id in pending_partner_by_user.items():
            result = partner_results[partner_id]
            if created.get(client_user_id) == partner_id:
                result["imported"] += 1
            else:
                conflicts += 1
                result["conflicts"] += 1
        imported = len(created)
        for partner_id, result in partner_results.items():
            if not result["imported"]:
                continue
            await partner_dal.create_audit_event(
                session,
                event_type="referrals_imported",
                actor_type="admin",
                partner_id=partner_id,
                actor_user_id=actor_admin_id,
                new_values_json=compact_json({**result, "bulk": True}),
            )
        return {
            "partners_updated": sum(1 for result in partner_results.values() if result["imported"]),
            "imported": imported,
            "existing": existing,
            "conflicts": conflicts,
        }
