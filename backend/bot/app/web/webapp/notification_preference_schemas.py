from __future__ import annotations

from typing import Any

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.services.user_notification_preferences import UserNotificationPreferences


class NotificationPreferencesPatchBody(HttpBodyModel):
    marketing_email: bool
    marketing_telegram: bool
    system_email: bool
    system_telegram: bool

    def to_preferences(self) -> UserNotificationPreferences:
        return UserNotificationPreferences(**self.model_dump())


class EmailNotificationPreferencesPatchBody(HttpBodyModel):
    token: str
    marketing_email: bool
    system_email: bool


class NotificationPreferencesOut(HttpResponseModel):
    marketing_email: bool
    marketing_telegram: bool
    system_email: bool
    system_telegram: bool

    @classmethod
    def from_user(cls, user: Any) -> NotificationPreferencesOut:
        return cls(**UserNotificationPreferences.from_user(user).as_dict())
