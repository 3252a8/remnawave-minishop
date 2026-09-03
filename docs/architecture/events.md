# Каталог доменных событий

Файл сгенерирован из `bot.infra.event_payloads`; не редактируйте его вручную.
Для обновления выполните `PYTHONPATH=backend python -m bot.infra.event_catalog`.

Подписчики по-прежнему получают данные в формате `(event_name, dict)`. Модели ниже описывают плоский, совместимый с JSON словарь, который публикует код Core.

## `account.email_linked`

Модель данных события: `AccountEmailLinkedPayload`

Источники события: `backend/bot/app/web/webapp/account.py`

Реакции Core: `CoreEventReactions.on_account_email_linked`

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `email` | `str` | обязательно |
| `first_link` | `bool` | обязательно |
| `telegram_id` | `int | None` | `None` |
| `username` | `str | None` | `None` |
| `first_name` | `str | None` | `None` |

## `account.external_identity_linked`

Модель данных события: `AccountExternalIdentityLinkedPayload`

Источники события: `backend/bot/app/web/webapp/external_oauth.py`

Реакции Core: `CoreEventReactions.on_account_external_identity_linked`

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `provider` | `'google' | 'yandex'` | обязательно |
| `link_source` | `'settings' | 'email_confirmation'` | обязательно |
| `email` | `str | None` | `None` |
| `telegram_id` | `int | None` | `None` |
| `username` | `str | None` | `None` |
| `first_name` | `str | None` | `None` |

## `account.merged`

Модель данных события: `AccountMergedPayload`

Источники события: `backend/db/dal/user_merge_dal.py`

Реакции Core: `CoreEventReactions.on_account_merged`

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `source_user_id` | `int` | обязательно |
| `target_user_id` | `int` | обязательно |
| `reason` | `str` | обязательно |
| `send_user_email` | `bool` | обязательно |
| `source_panel_user_uuid` | `str | None` | `None` |
| `target_panel_user_uuid` | `str | None` | `None` |
| `email` | `str | None` | `None` |
| `telegram_id` | `int | None` | `None` |
| `username` | `str | None` | `None` |
| `first_name` | `str | None` | `None` |
| `language` | `str | None` | `None` |
| `final_end_date` | `datetime | None` | `None` |

## `account.telegram_linked`

Модель данных события: `AccountTelegramLinkedPayload`

Источники события: `backend/bot/app/web/webapp/account.py`

Реакции Core: `CoreEventReactions.on_account_telegram_linked`

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `telegram_id` | `int | None` | `None` |
| `first_link` | `bool` | обязательно |
| `email` | `str | None` | `None` |
| `username` | `str | None` | `None` |
| `first_name` | `str | None` | `None` |

## `bot.started`

Модель данных события: `BotStartedPayload`

Источники события: `backend/bot/services/behavior_events.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `returning` | `bool` | обязательно |
| `source` | `'direct' | 'referral' | 'promo' | 'ad' | 'ticket' | 'notifications'` | обязательно |
| `start_param` | `str | None` | `None` |

## `device.connected`

Модель данных события: `DeviceConnectedPayload`

Источники события: `backend/bot/services/hwid_device_notifications.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `subscription_id` | `int` | обязательно |
| `panel_user_uuid` | `str | None` | `None` |
| `device_label` | `str` | обязательно |
| `platform` | `str | None` | `None` |
| `os_version` | `str | None` | `None` |
| `current_devices` | `int | None` | `None` |
| `device_limit` | `int | None` | `None` |
| `occurred_at` | `datetime` | обязательно |

## `device.limit_reached`

Модель данных события: `DeviceLimitReachedPayload`

Источники события: `backend/bot/services/hwid_device_notifications.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `subscription_id` | `int` | обязательно |
| `tariff_key` | `str | None` | `None` |
| `current_devices` | `int` | обязательно |
| `device_limit` | `int` | обязательно |
| `device_topup_available` | `bool` | обязательно |
| `occurred_at` | `datetime` | обязательно |

## `panel.webhook_received`

Модель данных события: `PanelWebhookReceivedPayload`

Источники события: `backend/bot/services/panel_webhook_service.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `event` | `str` | обязательно |
| `panel_user_uuid` | `str | None` | `None` |
| `telegram_id` | `int | str | None` | `None` |

## `partner.application_decided`

Модель данных события: `PartnerApplicationDecidedPayload`

Источники события: `backend/bot/services/partner_program_service.py`

Реакции Core: `CoreEventReactions.on_partner_application_decided`

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `application_id` | `int` | обязательно |
| `partner_id` | `int | None` | `None` |
| `user_id` | `int | None` | `None` |
| `status` | `str` | обязательно |
| `decided_at` | `datetime` | обязательно |

## `partner.application_submitted`

Модель данных события: `PartnerApplicationSubmittedPayload`

Источники события: `backend/bot/services/partner_program_service.py`

Реакции Core: `CoreEventReactions.on_partner_application_submitted`

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `application_id` | `int` | обязательно |
| `user_id` | `int` | обязательно |
| `status` | `str` | обязательно |
| `submitted_at` | `datetime` | обязательно |

## `partner.balance_adjusted`

Модель данных события: `PartnerBalanceAdjustedPayload`

Источники события: `backend/bot/services/partner_commission_service.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `partner_id` | `int` | обязательно |
| `currency` | `str` | обязательно |
| `amount_minor` | `int` | обязательно |
| `balance_minor` | `int` | обязательно |
| `adjusted_at` | `datetime` | обязательно |

## `partner.balance_spent`

Модель данных события: `PartnerBalanceSpentPayload`

Источники события: `backend/bot/services/partner_checkout_balance.py`, `backend/bot/services/partner_commission_service.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `partner_id` | `int` | обязательно |
| `payment_db_id` | `int` | обязательно |
| `currency` | `str` | обязательно |
| `amount_minor` | `int` | обязательно |
| `spent_at` | `datetime` | обязательно |

## `partner.client_attributed`

Модель данных события: `PartnerClientAttributedPayload`

Источники события: `backend/bot/services/partner_program_service.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `partner_id` | `int` | обязательно |
| `partner_client_id` | `int` | обязательно |
| `client_user_id` | `int` | обязательно |
| `source` | `str` | обязательно |
| `attributed_at` | `datetime` | обязательно |

## `partner.commission_available`

Модель данных события: `PartnerCommissionAvailablePayload`

Источники события: `backend/bot/services/partner_commission_service.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `partner_id` | `int` | обязательно |
| `commission_id` | `int` | обязательно |
| `currency` | `str` | обязательно |
| `commission_amount_minor` | `int` | обязательно |
| `available_at` | `datetime` | обязательно |

## `partner.commission_recorded`

Модель данных события: `PartnerCommissionRecordedPayload`

Источники события: `backend/bot/services/partner_commission_service.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `partner_id` | `int` | обязательно |
| `commission_id` | `int` | обязательно |
| `payment_db_id` | `int` | обязательно |
| `status` | `str` | обязательно |
| `currency` | `str` | обязательно |
| `gross_amount_minor` | `int` | обязательно |
| `commission_amount_minor` | `int` | обязательно |
| `available_at` | `datetime` | обязательно |

## `partner.commission_reversed`

Модель данных события: `PartnerCommissionReversedPayload`

Источники события: `backend/bot/services/partner_commission_service.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `partner_id` | `int` | обязательно |
| `commission_id` | `int` | обязательно |
| `payment_db_id` | `int | None` | `None` |
| `currency` | `str` | обязательно |
| `commission_amount_minor` | `int` | обязательно |
| `reversed_at` | `datetime` | обязательно |

## `partner.status_changed`

Модель данных события: `PartnerStatusChangedPayload`

Источники события: `backend/bot/services/partner_program_service.py`

Реакции Core: `CoreEventReactions.on_partner_status_changed`

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `partner_id` | `int` | обязательно |
| `user_id` | `int | None` | `None` |
| `old_status` | `str` | обязательно |
| `status` | `str` | обязательно |
| `changed_at` | `datetime` | обязательно |

## `partner.withdrawal_requested`

Модель данных события: `PartnerWithdrawalRequestedPayload`

Источники события: `backend/bot/services/partner_withdrawal_service.py`

Реакции Core: `CoreEventReactions.on_partner_withdrawal_requested`

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `partner_id` | `int` | обязательно |
| `user_id` | `int` | обязательно |
| `withdrawal_id` | `int` | обязательно |
| `status` | `str` | обязательно |
| `currency` | `str` | обязательно |
| `currency_scale` | `int` | обязательно |
| `amount_minor` | `int` | обязательно |
| `requested_at` | `datetime` | обязательно |

## `partner.withdrawal_status_changed`

Модель данных события: `PartnerWithdrawalStatusChangedPayload`

Источники события: `backend/bot/services/partner_withdrawal_service.py`

Реакции Core: `CoreEventReactions.on_partner_withdrawal_status_changed`

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `partner_id` | `int` | обязательно |
| `user_id` | `int | None` | `None` |
| `withdrawal_id` | `int` | обязательно |
| `old_status` | `str` | обязательно |
| `status` | `str` | обязательно |
| `status_version` | `int` | обязательно |
| `currency` | `str` | обязательно |
| `currency_scale` | `int` | обязательно |
| `amount_minor` | `int` | обязательно |
| `settlement_amount` | `str | None` | `None` |
| `external_reference` | `str | None` | `None` |
| `changed_at` | `datetime` | обязательно |

## `payment.canceled`

Модель данных события: `PaymentCanceledPayload`

Источники события: `backend/bot/app/web/webapp/billing.py`, `backend/bot/payment_providers/shared/webhooks.py`, `backend/bot/payment_providers/yookassa.py`, `backend/bot/services/yookassa_reconciliation_worker.py`, `backend/main_worker.py`

Реакции Core: `CoreEventReactions.on_payment_canceled`

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `payment_db_id` | `int | None` | `None` |
| `provider` | `str | None` | `None` |
| `provider_payment_id` | `str | None` | `None` |
| `status` | `str | None` | `None` |
| `message_key` | `str | None` | `None` |
| `cancellation_party` | `str | None` | `None` |
| `cancellation_reason` | `str | None` | `None` |
| `auto_renew_cycle_id` | `int | None` | `None` |
| `auto_renew_retry_scheduled` | `bool` | `False` |
| `retry_at` | `datetime | None` | `None` |

## `payment.succeeded`

Модель данных события: `PaymentSucceededPayload`

Источники события: `backend/bot/infra/payment_events.py`, `backend/bot/payment_providers/shared/success.py`, `backend/bot/payment_providers/yookassa.py`

Реакции Core: `CoreEventReactions.on_payment_succeeded`

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `payment_db_id` | `int` | обязательно |
| `provider` | `str` | обязательно |
| `notification_provider` | `str` | обязательно |
| `amount` | `float` | обязательно |
| `currency` | `str` | обязательно |
| `sale_mode` | `str` | обязательно |
| `tariff_key` | `str | None` | `None` |
| `months` | `int | None` | `None` |
| `duration_days` | `int | None` | `None` |
| `traffic_gb` | `float | None` | `None` |
| `purchased_hwid_devices` | `int | None` | `None` |
| `promo_code_id` | `int | None` | `None` |
| `base_amount` | `float | None` | `None` |
| `discount_amount` | `float | None` | `None` |
| `end_date` | `datetime | None` | `None` |
| `is_auto_renew` | `bool` | обязательно |
| `renewal_subscription_id` | `int | None` | `None` |

## `plans.viewed`

Модель данных события: `PlansViewedPayload`

Источники события: `backend/bot/app/web/webapp/billing_contracts.py`, `backend/bot/app/web/webapp/billing_options.py`, `backend/bot/app/web/webapp/payloads.py`, `backend/bot/services/behavior_events.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `source` | `'webapp' | 'bot'` | обязательно |
| `plans_count` | `int` | обязательно |
| `tariff_key` | `str | None` | `None` |

## `promo_code.applied`

Модель данных события: `PromoCodeAppliedPayload`

Источники события: `backend/bot/services/promo_code_service.py`

Реакции Core: `CoreEventReactions.on_promo_code_applied`

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `code` | `str` | обязательно |
| `bonus_days` | `int` | обязательно |
| `regular_traffic_gb` | `float` | `0` |
| `premium_traffic_gb` | `float` | `0` |
| `new_end_date` | `datetime | None` | `None` |

## `referral.bonus_granted`

Модель данных события: `ReferralBonusGrantedPayload`

Источники события: `backend/bot/app/web/webapp/auth.py`, `backend/bot/handlers/user/start.py`, `backend/bot/payment_providers/shared/success.py`, `backend/bot/payment_providers/yookassa.py`, `backend/bot/services/referral_service.py`

Реакции Core: `CoreEventReactions.on_referral_bonus_granted`

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `referee_user_id` | `int` | обязательно |
| `referee_bonus_days` | `int | None` | `None` |
| `referee_new_end_date` | `datetime | None` | `None` |
| `inviter_bonus_applied` | `bool` | обязательно |
| `inviter_user_id` | `int | None` | `None` |
| `inviter_bonus_days` | `int | None` | `None` |
| `inviter_bonus_end_date` | `datetime | None` | `None` |
| `inviter_bonus_kind` | `'extended' | 'new_sub' | None` | `None` |
| `referee_name` | `str | None` | `None` |
| `payment_db_id` | `int | None` | `None` |
| `purchased_subscription_months` | `int | None` | `None` |
| `purchased_subscription_days` | `int | None` | `None` |
| `tariff_key` | `str | None` | `None` |
| `one_bonus_per_referee` | `bool | None` | `None` |
| `reason` | `'payment' | 'welcome'` | обязательно |

## `subscription.auto_renew_failed`

Модель данных события: `SubscriptionAutoRenewFailedPayload`

Источники события: `backend/bot/payment_providers/shared/webhooks.py`, `backend/bot/services/subscription_service_impl/renewal.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `subscription_id` | `int` | обязательно |
| `provider` | `str` | обязательно |
| `reason_code` | `'provider_unavailable' | 'saved_payment_method_missing' | 'renewal_quote_unavailable' | 'provider_request_failed' | 'provider_rejected' | 'provider_webhook_failed'` | обязательно |
| `payment_db_id` | `int | None` | `None` |
| `provider_payment_id` | `str | None` | `None` |
| `renewal_cycle_end` | `datetime | None` | `None` |
| `retryable` | `bool` | обязательно |
| `occurred_at` | `datetime` | обязательно |

## `subscription.created`

Модель данных события: `SubscriptionCreatedPayload`

Источники события: `backend/bot/payment_providers/shared/success.py`, `backend/bot/payment_providers/yookassa.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `subscription_id` | `int | None` | `None` |
| `tariff_key` | `str | None` | `None` |
| `end_date` | `datetime | None` | `None` |
| `provider` | `str | None` | `None` |
| `months` | `int | None` | `None` |
| `duration_days` | `int | None` | `None` |
| `payment_db_id` | `int | None` | `None` |

## `subscription.expired`

Модель данных события: `SubscriptionExpiredPayload`

Источники события: `backend/bot/services/subscription_notification_worker.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `subscription_id` | `int | None` | `None` |
| `tariff_key` | `str | None` | `None` |
| `end_date` | `datetime | None` | `None` |

## `subscription.extended`

Модель данных события: `SubscriptionExtendedPayload`

Источники события: `backend/bot/payment_providers/shared/success.py`, `backend/bot/payment_providers/yookassa.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `subscription_id` | `int | None` | `None` |
| `tariff_key` | `str | None` | `None` |
| `end_date` | `datetime | None` | `None` |
| `provider` | `str | None` | `None` |
| `months` | `int | None` | `None` |
| `duration_days` | `int | None` | `None` |
| `payment_db_id` | `int | None` | `None` |

## `subscription.lapsed`

Модель данных события: `SubscriptionLapsedPayload`

Источники события: `backend/bot/services/subscription_notification_worker.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `subscription_id` | `int | None` | `None` |
| `tariff_key` | `str | None` | `None` |
| `end_date` | `datetime | None` | `None` |

## `support.ticket_created`

Модель данных события: `SupportTicketCreatedPayload`

Источники события: `backend/bot/services/support_service.py`

Реакции Core: нет

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `ticket_id` | `int` | обязательно |
| `category` | `str` | обязательно |
| `priority` | `str` | обязательно |

## `trial.activated`

Модель данных события: `TrialActivatedPayload`

Источники события: `backend/bot/services/subscription_service_impl/trial.py`

Реакции Core: `CoreEventReactions.on_trial_activated`

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `end_date` | `datetime | None` | `None` |
| `days` | `int` | обязательно |
| `traffic_gb` | `float | None` | `None` |

## `user.registered`

Модель данных события: `UserRegisteredPayload`

Источники события: `backend/bot/app/web/webapp/external_oauth.py`, `backend/db/dal/user_dal.py`

Реакции Core: `CoreEventReactions.on_user_registered`

| Поле | Тип | Значение по умолчанию |
| --- | --- | --- |
| `user_id` | `int` | обязательно |
| `telegram_id` | `int | None` | `None` |
| `username` | `str | None` | `None` |
| `first_name` | `str | None` | `None` |
| `email` | `str | None` | `None` |
| `language` | `str | None` | `None` |
| `referred_by_id` | `int | None` | `None` |
| `registered_via` | `'telegram' | 'email' | 'google_oauth' | 'yandex_oauth' | 'panel_sync' | 'unknown'` | обязательно |
