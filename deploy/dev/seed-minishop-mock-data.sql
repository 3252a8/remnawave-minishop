BEGIN;

-- Reserved dev-only identities. They intentionally have no Telegram destination
-- and use example.com addresses, so browsing mock screens cannot contact anyone.
INSERT INTO users (
    user_id,
    username,
    email,
    email_verified_at,
    password_hash,
    password_set_at,
    telegram_id,
    first_name,
    last_name,
    language_code,
    registration_date,
    is_banned,
    referral_code,
    telegram_notifications_status,
    channel_subscription_verified
) VALUES
    (
        910000004,
        'mock_new',
        'mock.new@example.com',
        now(),
        'pbkdf2_sha256$260000$ZGV2LW1vY2stc2FsdC12MQ$yidwfE8twrgh7F9p4vZ0grT2zjvEOGIPkSD5XEUt1Nk',
        now(),
        null,
        'Mock',
        'New',
        'ru',
        now() - interval '2 days',
        false,
        'MOCKNEW',
        'unknown',
        false
    ),
    (
        910000005,
        'mock_banned',
        'mock.banned@example.com',
        now(),
        'pbkdf2_sha256$260000$ZGV2LW1vY2stc2FsdC12MQ$yidwfE8twrgh7F9p4vZ0grT2zjvEOGIPkSD5XEUt1Nk',
        now(),
        null,
        'Mock',
        'Banned',
        'en',
        now() - interval '90 days',
        true,
        'MOCKBANNED',
        'blocked',
        false
    ),
    (
        910000006,
        'mock_email_only',
        'mock.email@example.com',
        now(),
        'pbkdf2_sha256$260000$ZGV2LW1vY2stc2FsdC12MQ$yidwfE8twrgh7F9p4vZ0grT2zjvEOGIPkSD5XEUt1Nk',
        now(),
        null,
        'Mock',
        'Email',
        'ru',
        now() - interval '14 days',
        false,
        'MOCKEMAIL',
        'unknown',
        false
    )
ON CONFLICT (user_id) DO UPDATE SET
    username = EXCLUDED.username,
    email = EXCLUDED.email,
    email_verified_at = EXCLUDED.email_verified_at,
    password_hash = EXCLUDED.password_hash,
    password_set_at = EXCLUDED.password_set_at,
    telegram_id = EXCLUDED.telegram_id,
    first_name = EXCLUDED.first_name,
    last_name = EXCLUDED.last_name,
    language_code = EXCLUDED.language_code,
    is_banned = EXCLUDED.is_banned,
    referral_code = EXCLUDED.referral_code,
    telegram_notifications_status = EXCLUDED.telegram_notifications_status,
    channel_subscription_verified = EXCLUDED.channel_subscription_verified;

-- Mock mode also makes the three base seed personas available through the
-- password form. The fixed value is documented and only loaded by this profile.
UPDATE users
SET
    password_hash = 'pbkdf2_sha256$260000$ZGV2LW1vY2stc2FsdC12MQ$yidwfE8twrgh7F9p4vZ0grT2zjvEOGIPkSD5XEUt1Nk',
    password_set_at = now(),
    email_verified_at = COALESCE(email_verified_at, now())
WHERE user_id BETWEEN 910000001 AND 910000006;

DELETE FROM support_ticket_messages
WHERE ticket_id BETWEEN 910010001 AND 910010099
   OR message_id BETWEEN 910020001 AND 910020999;

INSERT INTO support_tickets (
    ticket_id,
    user_id,
    subject,
    category,
    priority,
    status,
    assigned_admin_id,
    last_message_at,
    last_message_role,
    unread_user_count,
    unread_admin_count,
    created_at,
    updated_at,
    closed_at,
    closed_by_admin_id
) VALUES
    (
        910010001,
        910000002,
        'Connection unavailable after renewal',
        'technical',
        'urgent',
        'awaiting_admin',
        910000001,
        now() - interval '2 hours',
        'admin',
        0,
        2,
        now() - interval '6 hours',
        now() - interval '2 hours',
        null,
        null
    ),
    (
        910010002,
        910000004,
        'Which plan should I choose?',
        'other',
        'normal',
        'awaiting_user',
        910000001,
        now() - interval '1 day',
        'admin',
        1,
        0,
        now() - interval '2 days',
        now() - interval '1 day',
        null,
        null
    ),
    (
        910010003,
        910000003,
        'Expired subscription question',
        'billing',
        'high',
        'open',
        null,
        now() - interval '3 days',
        'user',
        0,
        0,
        now() - interval '3 days',
        now() - interval '3 days',
        null,
        null
    ),
    (
        910010004,
        910000004,
        'Email address updated',
        'account',
        'low',
        'resolved',
        910000001,
        now() - interval '7 days',
        'admin',
        0,
        0,
        now() - interval '8 days',
        now() - interval '7 days',
        now() - interval '7 days',
        910000001
    ),
    (
        910010005,
        910000005,
        'Closed abuse report',
        'other',
        'normal',
        'closed',
        910000001,
        now() - interval '30 days',
        'system',
        0,
        0,
        now() - interval '31 days',
        now() - interval '30 days',
        now() - interval '30 days',
        910000001
    )
ON CONFLICT (ticket_id) DO UPDATE SET
    user_id = EXCLUDED.user_id,
    subject = EXCLUDED.subject,
    category = EXCLUDED.category,
    priority = EXCLUDED.priority,
    status = EXCLUDED.status,
    assigned_admin_id = EXCLUDED.assigned_admin_id,
    last_message_at = EXCLUDED.last_message_at,
    last_message_role = EXCLUDED.last_message_role,
    unread_user_count = EXCLUDED.unread_user_count,
    unread_admin_count = EXCLUDED.unread_admin_count,
    updated_at = EXCLUDED.updated_at,
    closed_at = EXCLUDED.closed_at,
    closed_by_admin_id = EXCLUDED.closed_by_admin_id;

INSERT INTO support_ticket_messages (
    message_id,
    ticket_id,
    author_role,
    author_user_id,
    body,
    body_format,
    buttons,
    is_internal_note,
    created_at,
    read_by_user_at,
    read_by_admin_at
) VALUES
    (910020001, 910010001, 'user', 910000002, 'The connection stopped after renewal.', 'text', null, false, now() - interval '6 hours', now() - interval '6 hours', null),
    (910020002, 910010001, 'user', 910000002, 'I tested two devices and both fail.', 'text', null, false, now() - interval '3 hours', now() - interval '3 hours', null),
    (910020003, 910010001, 'admin', 910000001, 'Check panel sync before replying.', 'text', null, true, now() - interval '2 hours', now() - interval '2 hours', now() - interval '2 hours'),
    (910020004, 910010002, 'user', 910000004, 'I need access on a phone and a laptop.', 'text', null, false, now() - interval '2 days', now() - interval '2 days', now() - interval '2 days'),
    (910020005, 910010002, 'admin', 910000001, 'Please tell us how much monthly traffic you expect.', 'text', '[{"label":"Plan guide","url":"https://example.com/guide"}]', false, now() - interval '1 day', null, now() - interval '1 day'),
    (910020006, 910010003, 'user', 910000003, 'Can an expired subscription be restored?', 'text', null, false, now() - interval '3 days', now() - interval '3 days', now() - interval '3 days'),
    (910020007, 910010004, 'user', 910000004, 'Please update the email on my account.', 'text', null, false, now() - interval '8 days', now() - interval '8 days', now() - interval '8 days'),
    (910020008, 910010004, 'admin', 910000001, 'The email was updated and verified.', 'text', null, false, now() - interval '7 days', now() - interval '7 days', now() - interval '7 days'),
    (910020009, 910010005, 'system', null, 'The ticket was closed by an administrator.', 'text', null, false, now() - interval '30 days', now() - interval '30 days', now() - interval '30 days');

INSERT INTO payments (
    user_id,
    provider_payment_id,
    provider_payment_url,
    provider,
    funding_source,
    idempotence_key,
    amount,
    currency,
    status,
    description,
    subscription_duration_months,
    is_auto_renew,
    sale_mode,
    tariff_key,
    failure_kind,
    promo_conflict_override,
    promo_usage_restored,
    created_at,
    updated_at
) VALUES
    (910000004, 'mock-payment-succeeded', 'https://payments.example.test/mock-payment-succeeded', 'dev_mock', 'external', 'mock-idempotence-succeeded', 299.00, 'RUB', 'succeeded', 'Mock successful payment', 1, false, 'subscription@standard', 'standard', null, false, false, now() - interval '10 days', now() - interval '10 days'),
    (910000006, 'mock-payment-pending', 'https://payments.example.test/mock-payment-pending', 'dev_mock', 'external', 'mock-idempotence-pending', 499.00, 'RUB', 'pending', 'Mock pending payment', 1, false, 'subscription@premium', 'premium', null, false, false, now() - interval '2 hours', now() - interval '2 hours'),
    (910000003, 'mock-payment-canceled', 'https://payments.example.test/mock-payment-canceled', 'dev_mock', 'external', 'mock-idempotence-canceled', 299.00, 'RUB', 'canceled', 'Mock canceled payment', 1, false, 'subscription@standard', 'standard', 'user_cancelled', false, false, now() - interval '5 days', now() - interval '5 days'),
    (910000005, 'mock-payment-failed', 'https://payments.example.test/mock-payment-failed', 'dev_mock', 'external', 'mock-idempotence-failed', 149.00, 'RUB', 'failed', 'Mock failed payment', null, false, 'topup@premium', 'premium', 'provider_error', false, false, now() - interval '1 day', now() - interval '1 day')
ON CONFLICT (provider, provider_payment_id) DO UPDATE SET
    user_id = EXCLUDED.user_id,
    provider_payment_url = EXCLUDED.provider_payment_url,
    funding_source = EXCLUDED.funding_source,
    idempotence_key = EXCLUDED.idempotence_key,
    amount = EXCLUDED.amount,
    currency = EXCLUDED.currency,
    status = EXCLUDED.status,
    description = EXCLUDED.description,
    subscription_duration_months = EXCLUDED.subscription_duration_months,
    is_auto_renew = EXCLUDED.is_auto_renew,
    sale_mode = EXCLUDED.sale_mode,
    tariff_key = EXCLUDED.tariff_key,
    failure_kind = EXCLUDED.failure_kind,
    promo_conflict_override = EXCLUDED.promo_conflict_override,
    promo_usage_restored = EXCLUDED.promo_usage_restored,
    updated_at = EXCLUDED.updated_at;

INSERT INTO promo_codes (
    code,
    bonus_days,
    regular_traffic_gb,
    premium_traffic_gb,
    discount_percent,
    duration_multiplier,
    traffic_multiplier,
    bonus_requires_payment,
    applies_to,
    origin,
    max_activations,
    current_activations,
    is_active,
    created_by_admin_id,
    created_at,
    valid_until
) VALUES
    ('DEVWELCOME', 7, 5, null, null, null, null, false, 'all', 'admin', 100, 3, true, 910000001, now() - interval '20 days', now() + interval '365 days'),
    ('DEVHALF', 0, null, null, 50, null, null, true, 'subscription', 'admin', 25, 5, true, 910000001, now() - interval '10 days', now() + interval '30 days'),
    ('DEVEXPIRED', 3, null, null, null, null, null, false, 'all', 'admin', 10, 10, false, 910000001, now() - interval '60 days', now() - interval '30 days')
ON CONFLICT (code) DO UPDATE SET
    bonus_days = EXCLUDED.bonus_days,
    regular_traffic_gb = EXCLUDED.regular_traffic_gb,
    premium_traffic_gb = EXCLUDED.premium_traffic_gb,
    discount_percent = EXCLUDED.discount_percent,
    duration_multiplier = EXCLUDED.duration_multiplier,
    traffic_multiplier = EXCLUDED.traffic_multiplier,
    bonus_requires_payment = EXCLUDED.bonus_requires_payment,
    applies_to = EXCLUDED.applies_to,
    origin = EXCLUDED.origin,
    max_activations = EXCLUDED.max_activations,
    current_activations = EXCLUDED.current_activations,
    is_active = EXCLUDED.is_active,
    created_by_admin_id = EXCLUDED.created_by_admin_id,
    valid_until = EXCLUDED.valid_until;

DELETE FROM admin_broadcast_deliveries
WHERE broadcast_id BETWEEN 910030001 AND 910030099
   OR delivery_id BETWEEN 910040001 AND 910040999;

INSERT INTO admin_broadcasts (
    broadcast_id,
    created_by_admin_id,
    status,
    is_visible,
    target,
    channels,
    texts,
    email_subjects,
    buttons,
    scheduled_at,
    created_at,
    started_at,
    finished_at,
    updated_at,
    recipient_count,
    total_deliveries,
    successful_deliveries,
    failed_deliveries,
    telegram_sent,
    telegram_failed,
    email_sent,
    email_failed,
    last_error
) VALUES
    (910030001, 910000001, 'completed_with_errors', true, 'all', '["telegram","email"]'::json, '{"ru":"Mock completed broadcast","en":"Mock completed broadcast"}'::json, '{"ru":"Mock result","en":"Mock result"}'::json, '[]'::json, now() - interval '2 days', now() - interval '2 days', now() - interval '2 days', now() - interval '2 days' + interval '1 minute', now() - interval '2 days' + interval '1 minute', 2, 4, 3, 1, 1, 1, 2, 0, 'One mock Telegram delivery failed'),
    (910030002, 910000001, 'scheduled', true, 'all', '["email"]'::json, '{"ru":"Future mock broadcast","en":"Future mock broadcast"}'::json, '{"ru":"Future mock","en":"Future mock"}'::json, '[]'::json, '2099-01-01 12:00:00+00', now(), null, null, now(), 0, 0, 0, 0, 0, 0, 0, 0, null),
    (910030003, 910000001, 'failed', true, 'admins', '["email"]'::json, '{"ru":"Failed mock broadcast","en":"Failed mock broadcast"}'::json, '{"ru":"Mock failure","en":"Mock failure"}'::json, '[]'::json, now() - interval '5 days', now() - interval '5 days', now() - interval '5 days', now() - interval '5 days' + interval '1 minute', now() - interval '5 days' + interval '1 minute', 1, 1, 0, 1, 0, 0, 0, 1, 'Mock provider failure')
ON CONFLICT (broadcast_id) DO UPDATE SET
    created_by_admin_id = EXCLUDED.created_by_admin_id,
    status = EXCLUDED.status,
    is_visible = EXCLUDED.is_visible,
    target = EXCLUDED.target,
    channels = EXCLUDED.channels,
    texts = EXCLUDED.texts,
    email_subjects = EXCLUDED.email_subjects,
    buttons = EXCLUDED.buttons,
    scheduled_at = EXCLUDED.scheduled_at,
    started_at = EXCLUDED.started_at,
    finished_at = EXCLUDED.finished_at,
    updated_at = EXCLUDED.updated_at,
    recipient_count = EXCLUDED.recipient_count,
    total_deliveries = EXCLUDED.total_deliveries,
    successful_deliveries = EXCLUDED.successful_deliveries,
    failed_deliveries = EXCLUDED.failed_deliveries,
    telegram_sent = EXCLUDED.telegram_sent,
    telegram_failed = EXCLUDED.telegram_failed,
    email_sent = EXCLUDED.email_sent,
    email_failed = EXCLUDED.email_failed,
    last_error = EXCLUDED.last_error;

INSERT INTO admin_broadcast_deliveries (
    delivery_id,
    broadcast_id,
    user_id,
    channel,
    destination,
    language_code,
    status,
    attempts,
    error,
    created_at,
    queued_at,
    finished_at
) VALUES
    (910040001, 910030001, 910000002, 'telegram', 'dev-null-telegram-910000002', 'ru', 'sent', 1, null, now() - interval '2 days', now() - interval '2 days', now() - interval '2 days' + interval '30 seconds'),
    (910040002, 910030001, 910000002, 'email', 'runes.active@example.com', 'ru', 'sent', 1, null, now() - interval '2 days', now() - interval '2 days', now() - interval '2 days' + interval '35 seconds'),
    (910040003, 910030001, 910000004, 'telegram', 'dev-null-telegram-910000004', 'ru', 'failed', 3, 'Mock bot blocked', now() - interval '2 days', now() - interval '2 days', now() - interval '2 days' + interval '40 seconds'),
    (910040004, 910030001, 910000004, 'email', 'mock.new@example.com', 'ru', 'sent', 1, null, now() - interval '2 days', now() - interval '2 days', now() - interval '2 days' + interval '45 seconds'),
    (910040005, 910030003, 910000001, 'email', 'runes.admin@example.com', 'ru', 'failed', 3, 'Mock SMTP error', now() - interval '5 days', now() - interval '5 days', now() - interval '5 days' + interval '1 minute');

COMMIT;
