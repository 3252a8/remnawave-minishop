"""Branded HTML email template public facade."""

from __future__ import annotations

from .email_templates_auth import render_account_merged, render_login_code
from .email_templates_common import (
    _WEBAPP_UPLOADED_LOGO_DIR,
    EmailContent,
    EmailInlineImage,
    _email_logo,
    _inline_uploaded_logo,
    _uploaded_logo_dir,
)
from .email_templates_notifications import (
    render_subscription_expiring,
    render_subscription_lifecycle_notification,
    render_user_notification,
)
from .email_templates_payments import render_payment_success
from .email_templates_support import (
    render_support_admin_reply_user,
    render_support_new_ticket_admin,
    render_support_ticket_closed_user,
    render_support_user_reply_admin,
)

__all__ = [
    "_WEBAPP_UPLOADED_LOGO_DIR",
    "EmailContent",
    "EmailInlineImage",
    "_email_logo",
    "_inline_uploaded_logo",
    "_uploaded_logo_dir",
    "render_account_merged",
    "render_login_code",
    "render_payment_success",
    "render_subscription_expiring",
    "render_subscription_lifecycle_notification",
    "render_support_admin_reply_user",
    "render_support_new_ticket_admin",
    "render_support_ticket_closed_user",
    "render_support_user_reply_admin",
    "render_user_notification",
]
