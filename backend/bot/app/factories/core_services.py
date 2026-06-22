from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, TypeAlias

from bot.services.email_auth_service import EmailAuthService
from bot.services.notification_service import NotificationService
from bot.services.panel_api_service import PanelApiService
from bot.services.panel_dry_run_api_service import PanelDryRunApiService
from bot.services.panel_webhook_service import PanelWebhookService
from bot.services.promo_code_service import PromoCodeService
from bot.services.referral_service import ReferralService
from bot.services.subscription_service import SubscriptionService
from bot.services.support_service import SupportService

PanelService: TypeAlias = PanelApiService | PanelDryRunApiService


@dataclass(frozen=True)
class CoreServices:
    panel_service: PanelService
    subscription_service: SubscriptionService
    referral_service: ReferralService
    promo_code_service: PromoCodeService
    notification_service: NotificationService
    email_auth_service: EmailAuthService
    support_service: SupportService
    panel_webhook_service: PanelWebhookService
    payment_services: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "panel_service": self.panel_service,
            "subscription_service": self.subscription_service,
            "referral_service": self.referral_service,
            "promo_code_service": self.promo_code_service,
            "notification_service": self.notification_service,
            "email_auth_service": self.email_auth_service,
            "support_service": self.support_service,
            "panel_webhook_service": self.panel_webhook_service,
            **self.payment_services,
        }
