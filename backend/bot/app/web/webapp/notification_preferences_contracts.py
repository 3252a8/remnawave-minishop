from __future__ import annotations

from bot.app.web.route_contracts import STRING_SCHEMA, RouteContract, ok_envelope_with, schema_ref

from .contract_schemas import user_contract
from .notification_preference_schemas import (
    EmailNotificationPreferencesPatchBody,
    NotificationPreferencesOut,
    NotificationPreferencesPatchBody,
)

_PREFERENCES_RESPONSE = {
    "notification_preferences": schema_ref(NotificationPreferencesOut),
}

NOTIFICATION_PREFERENCES_ROUTE_CONTRACTS: dict[str, RouteContract] = {
    "account_notification_preferences_route": user_contract(
        request_model=NotificationPreferencesPatchBody,
        response_schema=ok_envelope_with(_PREFERENCES_RESPONSE),
        models=(NotificationPreferencesOut,),
    ),
    "email_notification_preferences_route": RouteContract(
        response_schema=ok_envelope_with(
            {"email": STRING_SCHEMA, "language": STRING_SCHEMA, **_PREFERENCES_RESPONSE}
        ),
        models=(NotificationPreferencesOut,),
    ),
    "email_notification_preferences_update_route": RouteContract(
        request_model=EmailNotificationPreferencesPatchBody,
        response_schema=ok_envelope_with(
            {"email": STRING_SCHEMA, "language": STRING_SCHEMA, **_PREFERENCES_RESPONSE}
        ),
        models=(NotificationPreferencesOut,),
    ),
}
