"""Safe unlink flow for external OAuth identities."""

from __future__ import annotations

import logging

from aiohttp import web
from sqlalchemy import func
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import get_session_factory, get_settings
from config.settings import Settings
from db.dal import user_dal, user_email_dal
from db.models import UserExternalIdentity, UserPasskeyCredential

from .auth import _sync_panel_identity_for_user
from .common import (
    _extract_authenticated_user_id,
    _invalidate_webapp_user_caches,
    _parse_model_payload,
)
from .external_identity_state import (
    external_identity_can_unlink,
    external_identity_email_survives,
    external_identity_replacement_email,
    normalized_identity_email,
)
from .payloads import WebAppExternalIdentityPayload
from .response_helpers import json_response

logger = logging.getLogger(__name__)


async def external_identity_unlink_route(request: web.Request) -> web.Response:
    user_id = _extract_authenticated_user_id(request)
    if not user_id:
        return json_response({"ok": False, "error": "unauthorized"}, status=401)
    settings: Settings = get_settings(request)
    payload = await _parse_model_payload(request, WebAppExternalIdentityPayload)
    provider = str(payload.provider)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        user = await user_dal.lock_user_by_id(session, user_id)
        if not user or user.is_banned:
            return json_response({"ok": False, "error": "access_denied"}, status=403)
        external_identities = list(
            (
                await session.execute(
                    select(UserExternalIdentity)
                    .where(UserExternalIdentity.user_id == user_id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        identity = next(
            (item for item in external_identities if str(item.provider) == provider),
            None,
        )
        if not identity:
            return json_response({"ok": False, "error": "identity_not_found"}, status=404)
        await user_email_dal.ensure_primary_user_email_address(
            session,
            user,
            source=provider,
        )
        email_addresses = await user_email_dal.list_user_email_addresses(
            session,
            user_id,
            for_update=True,
        )
        other_external_enabled = any(
            str(item.provider) != provider and str(item.provider) in settings.webapp_auth_providers
            for item in external_identities
        )
        passkey_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(UserPasskeyCredential)
                    .where(UserPasskeyCredential.user_id == user_id)
                )
            ).scalar_one()
        )
        email_survives = external_identity_email_survives(
            identity,
            email_addresses,
            external_identities,
        )
        replacement = external_identity_replacement_email(identity, email_addresses)
        provider_email = normalized_identity_email(identity)
        if provider_email and not email_survives and replacement is None:
            return json_response(
                {"ok": False, "error": "replacement_email_required"},
                status=409,
            )
        if not external_identity_can_unlink(
            identity,
            email_addresses,
            external_identities,
            user=user,
            has_other_external_identity=other_external_enabled,
            has_passkey_login=bool(settings.PASSKEY_LOGIN_ENABLED and passkey_count),
            has_telegram_login=bool(settings.TELEGRAM_LOGIN_ENABLED and user.telegram_id),
            email_login_enabled=bool(settings.email_auth_configured),
        ):
            return json_response({"ok": False, "error": "last_login_method"}, status=409)

        email_replaced = False
        provider_address_removed = False
        if provider_email and not email_survives and replacement is not None:
            replacement_email = str(replacement.email).strip().lower()
            replace_primary = str(user.email or "").strip().lower() == provider_email
            replace_notification = (
                str(user.notification_email or "").strip().lower() == provider_email
            )
            if replace_primary:
                user.email = replacement_email
                user.email_verified_at = replacement.verified_at
                email_replaced = True
            if replace_notification:
                user.notification_email = replacement_email
            if replace_primary or replace_notification:
                await user_email_dal.upsert_user_email_address(
                    session,
                    user_id=user_id,
                    email=replacement_email,
                    source=str(replacement.source or "email"),
                    verified_at=replacement.verified_at,
                    is_primary=replace_primary,
                    is_notification=replace_notification,
                )
            provider_address = next(
                (
                    address
                    for address in email_addresses
                    if str(address.email or "").strip().lower() == provider_email
                    and str(address.source or "") == provider
                ),
                None,
            )
            if provider_address is not None:
                await session.delete(provider_address)
                provider_address_removed = True
            if email_replaced:
                await _sync_panel_identity_for_user(request, user)
        await session.delete(identity)
        await session.commit()
    logger.info(
        "External OAuth identity unlinked provider=%s user_id=%s "
        "email_replaced=%s provider_address_removed=%s",
        provider,
        user_id,
        email_replaced,
        provider_address_removed,
    )
    await _invalidate_webapp_user_caches(settings, user_id)
    return json_response({"ok": True})
