import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");
const datasetPath = path.join(repoRoot, "frontend", "src", "lib", "webapp", "demoDataset.js");
const minishopSeedPath = path.join(repoRoot, "deploy", "dev", "seed-minishop-mock-data.sql");
const remnawaveSeedPath = path.join(repoRoot, "deploy", "dev", "seed-remnawave-mock-data.sql");
const checkOnly = process.argv.includes("--check");
const passwordHash =
  "pbkdf2_sha256$260000$ZGV2LW1vY2stc2FsdC12MQ$yidwfE8twrgh7F9p4vZ0grT2zjvEOGIPkSD5XEUt1Nk";

const datasetSource = await readFile(datasetPath, "utf8");
const { DEMO_DATASET } = await import(
  `data:text/javascript;base64,${Buffer.from(datasetSource).toString("base64")}`
);
const datasetSha256 = createHash("sha256").update(datasetSource).digest("hex");
const anchor = DEMO_DATASET.generatedFrom?.dumpCreatedAt;

if (!anchor || !DEMO_DATASET.generatedFrom?.anonymized) {
  throw new Error("Refusing to generate dev seeds from a dataset without an anonymized timestamp");
}

function uniqueBy(items, key) {
  return [...new Map(items.map((item) => [item[key], item])).values()];
}

function safeEmail(user) {
  if (!user.email) return null;
  return `demo.${user.user_id}@client.example`;
}

const subscriptions = uniqueBy(
  Object.values(DEMO_DATASET.adminUserDetails || {}).flatMap((detail) => detail.subscriptions || []),
  "subscription_id"
);
const subscriptionsByUser = new Map();
for (const subscription of subscriptions) {
  const current = subscriptionsByUser.get(subscription.user_id);
  if (
    !current ||
    (subscription.is_active && !current.is_active) ||
    Date.parse(subscription.end_date) > Date.parse(current.end_date)
  ) {
    subscriptionsByUser.set(subscription.user_id, subscription);
  }
}

const users = (DEMO_DATASET.adminUsers || []).map((user) => ({
  ...user,
  email: safeEmail(user),
  original_telegram_linked: Boolean(user.telegram_linked),
  telegram_id: null,
  panel_user_uuid: subscriptionsByUser.get(user.user_id)?.panel_user_uuid || null,
  password_hash: user.password_auth_enabled ? passwordHash : null,
}));

const supportMessages = Object.values(DEMO_DATASET.supportMessages || {}).flat();
const sourcePayments = DEMO_DATASET.adminPayments || [];
const latestSucceededPaymentByUser = new Map();
for (const payment of sourcePayments) {
  if (String(payment.status || "").toLowerCase() !== "succeeded") continue;
  const current = latestSucceededPaymentByUser.get(payment.user_id);
  const paymentTime = Date.parse(payment.updated_at || payment.created_at || 0);
  const currentTime = Date.parse(current?.updated_at || current?.created_at || 0);
  if (!current || paymentTime > currentTime) {
    latestSucceededPaymentByUser.set(payment.user_id, payment);
  }
}
const reversiblePaymentIds = new Set(
  [...latestSucceededPaymentByUser.values()]
    .filter((payment) => subscriptionsByUser.has(payment.user_id))
    .map((payment) => payment.payment_id)
);
const payments = sourcePayments.map((payment) => ({
  ...payment,
  dev_reversible: reversiblePaymentIds.has(payment.payment_id),
  dev_reversal_subscription_id: reversiblePaymentIds.has(payment.payment_id)
    ? subscriptionsByUser.get(payment.user_id)?.subscription_id || null
    : null,
}));
const payers = uniqueBy(
  payments.filter((payment) => String(payment.status).toLowerCase() === "succeeded"),
  "user_id"
);
const remainingUserIds = users.map((user) => user.user_id);
const usedAttributionIds = new Set();
const adAttributions = [];

for (const campaign of DEMO_DATASET.ads || []) {
  const wantedPayers = Number(campaign.stats?.payments || 0);
  const wantedUsers = Number(campaign.stats?.users || 0);
  const selected = [];
  for (const payment of payers) {
    if (selected.length >= wantedPayers) break;
    if (!usedAttributionIds.has(payment.user_id)) selected.push(payment.user_id);
  }
  for (const userId of remainingUserIds) {
    if (selected.length >= wantedUsers) break;
    if (!usedAttributionIds.has(userId) && !selected.includes(userId)) selected.push(userId);
  }
  selected.forEach((userId, index) => {
    usedAttributionIds.add(userId);
    adAttributions.push({
      user_id: userId,
      ad_campaign_id: campaign.id,
      first_start_at: campaign.created_at,
      trial_activated_at:
        index < Number(campaign.stats?.trial_activations || 0) ? campaign.created_at : null,
    });
  });
}

const payload = {
  meta: {
    source: DEMO_DATASET.generatedFrom.source,
    dump_created_at: anchor,
    dataset_sha256: datasetSha256,
  },
  users,
  subscriptions,
  payments,
  logs: DEMO_DATASET.adminLogs || [],
  tickets: DEMO_DATASET.supportTickets || [],
  messages: supportMessages,
  promos: DEMO_DATASET.promos || [],
  ads: DEMO_DATASET.ads || [],
  ad_attributions: adAttributions,
};

const panelUsers = users
  .map((user) => {
    const subscription = subscriptionsByUser.get(user.user_id);
    if (!subscription) return null;
    const used = Number(subscription.traffic_used_bytes || 0);
    const limit = Number(subscription.traffic_limit_bytes || 0);
    return {
      user_id: user.user_id,
      uuid: subscription.panel_user_uuid,
      short_uuid: `demo${user.user_id}`,
      username: `demo_${user.user_id}`,
      status: String(subscription.status_from_panel || "ACTIVE").toUpperCase(),
      traffic_limit_bytes: limit,
      traffic_limit_strategy: subscription.traffic_limit_strategy || "MONTH",
      expire_at: subscription.end_date,
      trojan_password: `demo-trojan-${user.user_id}`,
      vless_uuid: subscription.panel_subscription_uuid,
      ss_password: `demo-ss-${user.user_id}`,
      description: `Anonymized docs demo user ${user.user_id}`,
      email: user.email || `demo.${user.user_id}@client.example`,
      telegram_id: 900000000000000 + Number(user.user_id),
      hwid_device_limit: Number(subscription.hwid_device_limit || 0),
      tag: "mini-shop-docs-demo",
      last_triggered_threshold: limit > 0 ? Math.min(100, Math.floor((used / limit) * 100)) : 0,
      tariff_key: subscription.tariff_key || "",
    };
  })
  .filter(Boolean);

function sqlJson(value, tag) {
  const text = JSON.stringify(value);
  if (text.includes(`$${tag}$`)) throw new Error(`Dataset contains reserved SQL delimiter ${tag}`);
  return `$${tag}$${text}$${tag}$::jsonb`;
}

const header = (target, counts) => `-- Generated by scripts/generate_dev_mock_seed.mjs. Do not edit manually.
-- Source: ${DEMO_DATASET.generatedFrom.source} (${anchor}, anonymized)
-- Dataset SHA-256: ${datasetSha256}
-- Target: ${target}
-- Records: ${counts}
`;

const minishopSql = `${header(
  "Minishop PostgreSQL",
  `users=${users.length}, subscriptions=${subscriptions.length}, payments=${payments.length}, reversible_payments=${reversiblePaymentIds.size}, logs=${payload.logs.length}, tickets=${payload.tickets.length}, messages=${supportMessages.length}, promos=${payload.promos.length}, ads=${payload.ads.length}`
)}BEGIN;

CREATE TEMP TABLE dev_demo_payload (payload jsonb NOT NULL) ON COMMIT DROP;
INSERT INTO dev_demo_payload VALUES (${sqlJson(payload, "minishop_demo")});

CREATE OR REPLACE FUNCTION pg_temp.dev_demo_time(value text)
RETURNS timestamptz
LANGUAGE sql
STABLE
AS $$
    SELECT CASE
        WHEN value IS NULL OR value = '' THEN NULL
        ELSE now() + (value::timestamptz - '${anchor}'::timestamptz)
    END
$$;

-- Remove the small handcrafted fixture used by the previous mock profile.
-- These ranges and keys were reserved exclusively for that profile.
DELETE FROM admin_broadcast_deliveries
WHERE broadcast_id BETWEEN 910030001 AND 910030003;
DELETE FROM support_ticket_messages
WHERE ticket_id BETWEEN 910010001 AND 910010005
   OR message_id BETWEEN 910020001 AND 910020009;
DELETE FROM support_tickets
WHERE ticket_id BETWEEN 910010001 AND 910010005;
DELETE FROM payments
WHERE provider = 'dev_mock'
  AND provider_payment_id LIKE 'mock-payment-%';
DELETE FROM promo_code_activations
WHERE promo_code_id IN (
    SELECT promo_code_id FROM promo_codes
    WHERE code IN ('DEVWELCOME', 'DEVHALF', 'DEVEXPIRED')
);
DELETE FROM promo_codes
WHERE code IN ('DEVWELCOME', 'DEVHALF', 'DEVEXPIRED');
DELETE FROM users
WHERE user_id BETWEEN 910000004 AND 910000006;

-- Keep the three base QA personas login-capable when the optional profile is enabled.
UPDATE users
SET
    password_hash = '${passwordHash}',
    password_set_at = now(),
    email_verified_at = COALESCE(email_verified_at, now())
WHERE user_id BETWEEN 910000001 AND 910000003;

WITH source AS (
    SELECT item
    FROM dev_demo_payload,
         jsonb_array_elements(payload -> 'users') AS item
)
INSERT INTO users (
    user_id, username, email, email_verified_at, password_hash, password_set_at,
    telegram_id, telegram_photo_url, telegram_notifications_status,
    telegram_notifications_checked_at, telegram_notifications_blocked_at,
    first_name, last_name, language_code, registration_date, is_banned,
    panel_user_uuid, referral_code, referred_by_id, channel_subscription_verified
)
SELECT
    (item ->> 'user_id')::bigint,
    NULLIF(item ->> 'username', ''),
    NULLIF(item ->> 'email', ''),
    CASE WHEN COALESCE((item ->> 'email_verified')::boolean, false)
        THEN pg_temp.dev_demo_time(item ->> 'registration_date') END,
    NULLIF(item ->> 'password_hash', ''),
    CASE WHEN NULLIF(item ->> 'password_hash', '') IS NOT NULL THEN now() END,
    NULL,
    NULLIF(item ->> 'telegram_photo_url', ''),
    'blocked',
    now(),
    now(),
    NULLIF(item ->> 'first_name', ''),
    NULLIF(item ->> 'last_name', ''),
    COALESCE(NULLIF(item ->> 'language_code', ''), 'ru'),
    pg_temp.dev_demo_time(item ->> 'registration_date'),
    COALESCE((item ->> 'is_banned')::boolean, false),
    NULLIF(item ->> 'panel_user_uuid', ''),
    NULLIF(item ->> 'referral_code', ''),
    NULL,
    false
FROM source
ON CONFLICT (user_id) DO UPDATE SET
    username = EXCLUDED.username,
    email = EXCLUDED.email,
    email_verified_at = EXCLUDED.email_verified_at,
    password_hash = EXCLUDED.password_hash,
    password_set_at = EXCLUDED.password_set_at,
    telegram_id = NULL,
    telegram_photo_url = EXCLUDED.telegram_photo_url,
    telegram_notifications_status = 'blocked',
    telegram_notifications_checked_at = now(),
    telegram_notifications_blocked_at = now(),
    first_name = EXCLUDED.first_name,
    last_name = EXCLUDED.last_name,
    language_code = EXCLUDED.language_code,
    registration_date = EXCLUDED.registration_date,
    is_banned = EXCLUDED.is_banned,
    panel_user_uuid = EXCLUDED.panel_user_uuid,
    referral_code = EXCLUDED.referral_code,
    referred_by_id = NULL,
    channel_subscription_verified = false;

WITH source AS (
    SELECT item
    FROM dev_demo_payload,
         jsonb_array_elements(payload -> 'users') AS item
)
UPDATE users AS target
SET referred_by_id = (source.item ->> 'referred_by_id')::bigint
FROM source
WHERE target.user_id = (source.item ->> 'user_id')::bigint
  AND NULLIF(source.item ->> 'referred_by_id', '') IS NOT NULL;

WITH source AS (
    SELECT item
    FROM dev_demo_payload,
         jsonb_array_elements(payload -> 'subscriptions') AS item
)
INSERT INTO subscriptions (
    subscription_id, user_id, panel_user_uuid, panel_subscription_uuid,
    install_share_token, start_date, end_date, duration_months, is_active,
    status_from_panel, traffic_limit_bytes, traffic_used_bytes, provider,
    skip_notifications, suppress_early_expiry_notifications, auto_renew_enabled,
    auto_renew_consent_version, tariff_key, tariff_binding_source, tariff_bound_at, tier_baseline_bytes,
    topup_balance_bytes, premium_baseline_bytes, premium_topup_balance_bytes,
    premium_topup_used_bytes, premium_used_bytes, premium_is_limited,
    premium_period_start_at, premium_unlimited_override, premium_bonus_bytes,
    regular_bonus_bytes, regular_unlimited_override, period_start_at,
    is_throttled, hwid_device_limit, extra_hwid_devices
)
SELECT
    (item ->> 'subscription_id')::integer,
    (item ->> 'user_id')::bigint,
    item ->> 'panel_user_uuid',
    NULLIF(item ->> 'panel_subscription_uuid', ''),
    NULLIF(item ->> 'install_share_token', ''),
    pg_temp.dev_demo_time(item ->> 'start_date'),
    pg_temp.dev_demo_time(item ->> 'end_date'),
    NULLIF(item ->> 'duration_months', '')::integer,
    COALESCE((item ->> 'is_active')::boolean, false),
    NULLIF(item ->> 'status_from_panel', ''),
    NULLIF(item ->> 'traffic_limit_bytes', '')::bigint,
    NULLIF(item ->> 'traffic_used_bytes', '')::bigint,
    NULLIF(item ->> 'provider', ''),
    true,
    true,
    COALESCE((item ->> 'auto_renew_enabled')::boolean, false),
    0,
    NULLIF(item ->> 'tariff_key', ''),
    'docs_demo',
    now(),
    COALESCE(NULLIF(item ->> 'tier_baseline_bytes', '')::bigint, 0),
    COALESCE(NULLIF(item ->> 'topup_balance_bytes', '')::bigint, 0),
    COALESCE(NULLIF(item ->> 'premium_baseline_bytes', '')::bigint, 0),
    COALESCE(NULLIF(item ->> 'premium_topup_balance_bytes', '')::bigint, 0),
    COALESCE(NULLIF(item ->> 'premium_topup_used_bytes', '')::bigint, 0),
    COALESCE(NULLIF(item ->> 'premium_used_bytes', '')::bigint, 0),
    COALESCE((item ->> 'premium_is_limited')::boolean, false),
    pg_temp.dev_demo_time(item ->> 'start_date'),
    COALESCE((item ->> 'premium_unlimited_override')::boolean, false),
    COALESCE(NULLIF(item ->> 'premium_bonus_bytes', '')::bigint, 0),
    COALESCE(NULLIF(item ->> 'regular_bonus_bytes', '')::bigint, 0),
    COALESCE((item ->> 'regular_unlimited_override')::boolean, false),
    pg_temp.dev_demo_time(item ->> 'start_date'),
    COALESCE((item ->> 'is_throttled')::boolean, false),
    NULLIF(item ->> 'hwid_device_limit', '')::integer,
    COALESCE(NULLIF(item ->> 'extra_hwid_devices', '')::integer, 0)
FROM source
ON CONFLICT (subscription_id) DO UPDATE SET
    user_id = EXCLUDED.user_id,
    panel_user_uuid = EXCLUDED.panel_user_uuid,
    panel_subscription_uuid = EXCLUDED.panel_subscription_uuid,
    install_share_token = EXCLUDED.install_share_token,
    start_date = EXCLUDED.start_date,
    end_date = EXCLUDED.end_date,
    duration_months = EXCLUDED.duration_months,
    is_active = EXCLUDED.is_active,
    status_from_panel = EXCLUDED.status_from_panel,
    traffic_limit_bytes = EXCLUDED.traffic_limit_bytes,
    traffic_used_bytes = EXCLUDED.traffic_used_bytes,
    provider = EXCLUDED.provider,
    skip_notifications = true,
    suppress_early_expiry_notifications = true,
    auto_renew_enabled = EXCLUDED.auto_renew_enabled,
    auto_renew_consent_version = 0,
    tariff_key = EXCLUDED.tariff_key,
    tariff_binding_source = 'docs_demo',
    tariff_bound_at = now(),
    tier_baseline_bytes = EXCLUDED.tier_baseline_bytes,
    topup_balance_bytes = EXCLUDED.topup_balance_bytes,
    premium_baseline_bytes = EXCLUDED.premium_baseline_bytes,
    premium_topup_balance_bytes = EXCLUDED.premium_topup_balance_bytes,
    premium_topup_used_bytes = EXCLUDED.premium_topup_used_bytes,
    premium_used_bytes = EXCLUDED.premium_used_bytes,
    premium_is_limited = EXCLUDED.premium_is_limited,
    premium_period_start_at = EXCLUDED.premium_period_start_at,
    premium_unlimited_override = EXCLUDED.premium_unlimited_override,
    premium_bonus_bytes = EXCLUDED.premium_bonus_bytes,
    regular_bonus_bytes = EXCLUDED.regular_bonus_bytes,
    regular_unlimited_override = EXCLUDED.regular_unlimited_override,
    period_start_at = EXCLUDED.period_start_at,
    is_throttled = EXCLUDED.is_throttled,
    hwid_device_limit = EXCLUDED.hwid_device_limit,
    extra_hwid_devices = EXCLUDED.extra_hwid_devices;

WITH source AS (
    SELECT item
    FROM dev_demo_payload,
         jsonb_array_elements(payload -> 'promos') AS item
)
INSERT INTO promo_codes (
    promo_code_id, code, bonus_days, max_activations, current_activations,
    is_active, valid_until, created_at, created_by_admin_id, applies_to, origin,
    bonus_requires_payment
)
SELECT
    (item ->> 'id')::integer,
    item ->> 'code',
    (item ->> 'bonus_days')::integer,
    (item ->> 'max_activations')::integer,
    COALESCE((item ->> 'current_activations')::integer, 0),
    COALESCE((item ->> 'is_active')::boolean, true),
    pg_temp.dev_demo_time(item ->> 'valid_until'),
    pg_temp.dev_demo_time(item ->> 'created_at'),
    NULLIF(item ->> 'created_by_admin_id', '')::bigint,
    'all',
    'admin',
    false
FROM source
ON CONFLICT (promo_code_id) DO UPDATE SET
    code = EXCLUDED.code,
    bonus_days = EXCLUDED.bonus_days,
    max_activations = EXCLUDED.max_activations,
    current_activations = EXCLUDED.current_activations,
    is_active = EXCLUDED.is_active,
    valid_until = EXCLUDED.valid_until,
    created_by_admin_id = EXCLUDED.created_by_admin_id;

WITH source AS (
    SELECT item
    FROM dev_demo_payload,
         jsonb_array_elements(payload -> 'payments') AS item
)
INSERT INTO payments (
    payment_id, user_id, yookassa_payment_id, provider_payment_id,
    provider_payment_url, provider, funding_source, idempotence_key, amount,
    currency, status, description, subscription_duration_months, is_auto_renew,
    sale_mode, tariff_key, purchased_gb, purchased_hwid_devices, promo_code_id,
    fulfillment_source, fulfilled_at, fulfilled_by_admin_id, fulfillment_note,
    fulfillment_before_snapshot, fulfillment_after_snapshot, promo_conflict_override,
    promo_usage_restored, reversed_at, reversed_by_admin_id, reversal_note,
    created_at, updated_at
)
SELECT
    (item ->> 'payment_id')::integer,
    (item ->> 'user_id')::bigint,
    NULLIF(item ->> 'yookassa_payment_id', ''),
    NULLIF(item ->> 'provider_payment_id', ''),
    NULL,
    COALESCE(NULLIF(item ->> 'provider', ''), 'dev_mock'),
    'external',
    NULLIF(item ->> 'idempotence_key', ''),
    (item ->> 'amount')::double precision,
    COALESCE(NULLIF(item ->> 'currency', ''), 'RUB'),
    item ->> 'status',
    NULLIF(item ->> 'description', ''),
    NULLIF(item ->> 'subscription_duration_months', '')::integer,
    false,
    NULLIF(item ->> 'sale_mode', ''),
    NULLIF(item ->> 'tariff_key', ''),
    NULLIF(item ->> 'purchased_gb', '')::double precision,
    NULLIF(item ->> 'purchased_hwid_devices', '')::integer,
    promo.promo_code_id,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    false,
    false,
    NULL,
    NULL,
    NULL,
    pg_temp.dev_demo_time(item ->> 'created_at'),
    pg_temp.dev_demo_time(item ->> 'updated_at')
FROM source
LEFT JOIN promo_codes AS promo ON promo.code = NULLIF(source.item ->> 'promo_code', '')
ON CONFLICT (payment_id) DO UPDATE SET
    user_id = EXCLUDED.user_id,
    yookassa_payment_id = EXCLUDED.yookassa_payment_id,
    provider_payment_id = EXCLUDED.provider_payment_id,
    provider_payment_url = NULL,
    provider = EXCLUDED.provider,
    funding_source = 'external',
    idempotence_key = EXCLUDED.idempotence_key,
    amount = EXCLUDED.amount,
    currency = EXCLUDED.currency,
    status = EXCLUDED.status,
    description = EXCLUDED.description,
    subscription_duration_months = EXCLUDED.subscription_duration_months,
    is_auto_renew = false,
    sale_mode = EXCLUDED.sale_mode,
    tariff_key = EXCLUDED.tariff_key,
    purchased_gb = EXCLUDED.purchased_gb,
    purchased_hwid_devices = EXCLUDED.purchased_hwid_devices,
    promo_code_id = EXCLUDED.promo_code_id,
    fulfillment_source = NULL,
    fulfilled_at = NULL,
    fulfilled_by_admin_id = NULL,
    fulfillment_note = NULL,
    fulfillment_before_snapshot = NULL,
    fulfillment_after_snapshot = NULL,
    promo_conflict_override = false,
    promo_usage_restored = false,
    reversed_at = NULL,
    reversed_by_admin_id = NULL,
    reversal_note = NULL,
    created_at = EXCLUDED.created_at,
    updated_at = EXCLUDED.updated_at;

-- Only the latest successful payment for each user is reversible. Older
-- successful payments intentionally remain blocked because a later payment
-- changed the same entitlement. The snapshots below target the entitlement
-- field represented by each docs-demo payment and are rebuilt from the
-- freshly shifted subscription rows on every seed application.
WITH source AS (
    SELECT item
    FROM dev_demo_payload,
         jsonb_array_elements(payload -> 'payments') AS item
    WHERE COALESCE((item ->> 'dev_reversible')::boolean, false)
), snapshots AS (
    SELECT
        payment.payment_id,
        payment.user_id,
        COALESCE(payment.updated_at, payment.created_at, now()) AS fulfilled_at,
        jsonb_build_object(
            'subscription_id', subscription.subscription_id,
            'user_id', subscription.user_id
        ) || CASE COALESCE(NULLIF(payment.sale_mode, ''), 'unknown')
            WHEN 'subscription' THEN jsonb_build_object(
                'end_date', to_jsonb(subscription.end_date - make_interval(
                    months => GREATEST(COALESCE(payment.subscription_duration_months, 1), 1)
                ))
            )
            WHEN 'topup' THEN jsonb_build_object(
                'topup_balance_bytes', GREATEST(
                    0,
                    COALESCE(subscription.topup_balance_bytes, 0)
                    - ROUND(COALESCE(payment.purchased_gb, 0) * 1073741824)::bigint
                )
            )
            WHEN 'premium_topup' THEN jsonb_build_object(
                'premium_topup_balance_bytes', GREATEST(
                    0,
                    COALESCE(subscription.premium_topup_balance_bytes, 0)
                    - ROUND(COALESCE(payment.purchased_gb, 0) * 1073741824)::bigint
                )
            )
            ELSE '{}'::jsonb
        END AS before_subscription,
        jsonb_build_object(
            'subscription_id', subscription.subscription_id,
            'user_id', subscription.user_id
        ) || CASE COALESCE(NULLIF(payment.sale_mode, ''), 'unknown')
            WHEN 'subscription' THEN jsonb_build_object('end_date', to_jsonb(subscription.end_date))
            WHEN 'topup' THEN jsonb_build_object(
                'topup_balance_bytes', COALESCE(subscription.topup_balance_bytes, 0)
            )
            WHEN 'premium_topup' THEN jsonb_build_object(
                'premium_topup_balance_bytes',
                COALESCE(subscription.premium_topup_balance_bytes, 0)
            )
            ELSE '{}'::jsonb
        END AS after_subscription,
        app_user.panel_user_uuid
    FROM source
    JOIN payments AS payment ON payment.payment_id = (source.item ->> 'payment_id')::integer
    JOIN users AS app_user ON app_user.user_id = payment.user_id
    JOIN subscriptions AS subscription
      ON subscription.subscription_id = (source.item ->> 'dev_reversal_subscription_id')::integer
), payloads AS (
    SELECT
        payment_id,
        fulfilled_at,
        jsonb_build_object(
            'version', 1,
            'users', jsonb_build_array(jsonb_build_object(
                'user_id', snapshots.user_id,
                'panel_user_uuid', snapshots.panel_user_uuid,
                'subscriptions', jsonb_build_array(before_subscription)
            ))
        ) AS before_snapshot,
        jsonb_build_object(
            'version', 1,
            'users', jsonb_build_array(jsonb_build_object(
                'user_id', snapshots.user_id,
                'panel_user_uuid', snapshots.panel_user_uuid,
                'subscriptions', jsonb_build_array(after_subscription)
            ))
        ) AS after_snapshot
    FROM snapshots
)
UPDATE payments AS payment
SET fulfillment_source = 'dev_mock',
    fulfilled_at = payloads.fulfilled_at,
    fulfillment_note = 'Reversible docs-demo fixture',
    fulfillment_before_snapshot = payloads.before_snapshot::text,
    fulfillment_after_snapshot = payloads.after_snapshot::text
FROM payloads
WHERE payment.payment_id = payloads.payment_id;

WITH source AS (
    SELECT item
    FROM dev_demo_payload,
         jsonb_array_elements(payload -> 'logs') AS item
)
INSERT INTO message_logs (
    log_id, user_id, telegram_username, telegram_first_name, event_type, content,
    raw_update_preview, timestamp, is_admin_event, target_user_id
)
SELECT
    (item ->> 'log_id')::integer,
    NULLIF(item ->> 'user_id', '')::bigint,
    NULLIF(item ->> 'telegram_username', ''),
    NULLIF(item ->> 'telegram_first_name', ''),
    item ->> 'event_type',
    NULLIF(item ->> 'content', ''),
    NULL,
    pg_temp.dev_demo_time(item ->> 'timestamp'),
    COALESCE((item ->> 'is_admin_event')::boolean, false),
    NULLIF(item ->> 'target_user_id', '')::bigint
FROM source
ON CONFLICT (log_id) DO UPDATE SET
    user_id = EXCLUDED.user_id,
    telegram_username = EXCLUDED.telegram_username,
    telegram_first_name = EXCLUDED.telegram_first_name,
    event_type = EXCLUDED.event_type,
    content = EXCLUDED.content,
    timestamp = EXCLUDED.timestamp,
    is_admin_event = EXCLUDED.is_admin_event,
    target_user_id = EXCLUDED.target_user_id;

DELETE FROM support_ticket_messages
WHERE ticket_id IN (
    SELECT (item ->> 'ticket_id')::integer
    FROM dev_demo_payload,
         jsonb_array_elements(payload -> 'tickets') AS item
);

WITH source AS (
    SELECT item
    FROM dev_demo_payload,
         jsonb_array_elements(payload -> 'tickets') AS item
)
INSERT INTO support_tickets (
    ticket_id, user_id, subject, category, priority, status, assigned_admin_id,
    last_message_at, last_message_role, unread_user_count, unread_admin_count,
    created_at, updated_at, closed_at, closed_by_admin_id
)
SELECT
    (item ->> 'ticket_id')::integer,
    (item ->> 'user_id')::bigint,
    item ->> 'subject',
    COALESCE(NULLIF(item ->> 'category', ''), 'other'),
    COALESCE(NULLIF(item ->> 'priority', ''), 'normal'),
    COALESCE(NULLIF(item ->> 'status', ''), 'open'),
    NULLIF(item ->> 'assigned_admin_id', '')::bigint,
    pg_temp.dev_demo_time(item ->> 'last_message_at'),
    NULLIF(item ->> 'last_message_role', ''),
    COALESCE((item ->> 'unread_user_count')::integer, 0),
    COALESCE((item ->> 'unread_admin_count')::integer, 0),
    pg_temp.dev_demo_time(item ->> 'created_at'),
    pg_temp.dev_demo_time(item ->> 'updated_at'),
    pg_temp.dev_demo_time(item ->> 'closed_at'),
    NULL
FROM source
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
    closed_at = EXCLUDED.closed_at;

WITH source AS (
    SELECT item
    FROM dev_demo_payload,
         jsonb_array_elements(payload -> 'messages') AS item
)
INSERT INTO support_ticket_messages (
    message_id, ticket_id, author_role, author_user_id, body, body_format,
    buttons, is_internal_note, created_at, read_by_user_at, read_by_admin_at
)
SELECT
    (item ->> 'message_id')::integer,
    (item ->> 'ticket_id')::integer,
    item ->> 'author_role',
    NULLIF(item ->> 'author_user_id', '')::bigint,
    item ->> 'body',
    'text',
    NULL,
    COALESCE((item ->> 'is_internal_note')::boolean, false),
    pg_temp.dev_demo_time(item ->> 'created_at'),
    pg_temp.dev_demo_time(item ->> 'read_by_user_at'),
    pg_temp.dev_demo_time(item ->> 'read_by_admin_at')
FROM source;

WITH source AS (
    SELECT item
    FROM dev_demo_payload,
         jsonb_array_elements(payload -> 'ads') AS item
)
INSERT INTO ad_campaigns (
    ad_campaign_id, source, start_param, cost, is_active, created_at
)
SELECT
    (item ->> 'id')::integer,
    item ->> 'source',
    item ->> 'start_param',
    COALESCE((item ->> 'cost')::double precision, 0),
    COALESCE((item ->> 'is_active')::boolean, true),
    pg_temp.dev_demo_time(item ->> 'created_at')
FROM source
ON CONFLICT (ad_campaign_id) DO UPDATE SET
    source = EXCLUDED.source,
    start_param = EXCLUDED.start_param,
    cost = EXCLUDED.cost,
    is_active = EXCLUDED.is_active,
    created_at = EXCLUDED.created_at;

DELETE FROM ad_attributions
WHERE ad_campaign_id IN (
    SELECT (item ->> 'id')::integer
    FROM dev_demo_payload,
         jsonb_array_elements(payload -> 'ads') AS item
);

WITH source AS (
    SELECT item
    FROM dev_demo_payload,
         jsonb_array_elements(payload -> 'ad_attributions') AS item
)
INSERT INTO ad_attributions (
    user_id, ad_campaign_id, first_start_at, trial_activated_at
)
SELECT
    (item ->> 'user_id')::bigint,
    (item ->> 'ad_campaign_id')::integer,
    pg_temp.dev_demo_time(item ->> 'first_start_at'),
    pg_temp.dev_demo_time(item ->> 'trial_activated_at')
FROM source;

-- Broadcasts are the dynamic docs-demo fixtures. The scheduled item is kept
-- far in the future so a local worker cannot accidentally deliver it.
DELETE FROM admin_broadcast_deliveries
WHERE broadcast_id BETWEEN 910030001 AND 910030003;

INSERT INTO admin_broadcasts (
    broadcast_id, created_by_admin_id, status, is_visible, target, channels,
    texts, email_subjects, buttons, scheduled_at, created_at, started_at,
    finished_at, updated_at, recipient_count, total_deliveries,
    successful_deliveries, failed_deliveries, telegram_sent, telegram_failed,
    email_sent, email_failed, last_error
)
VALUES
    (910030001, 910000001, 'completed_with_errors', true, 'expired', '["telegram"]'::json,
     '{"ru":"Ваша подписка закончилась. Продлите её в мини-приложении, чтобы снова подключиться."}'::json,
     '{}'::json, '[{"kind":"webapp_section","section":"plans"}]'::json,
     now() - interval '1 day', now() - interval '25 hours', now() - interval '1 day',
     now() - interval '23 hours 59 minutes', now() - interval '23 hours 59 minutes',
     311, 311, 306, 5, 306, 5, 0, 0, null),
    (910030002, 910000001, 'running', true, 'all', '["telegram","email"]'::json,
     '{"ru":"Летнее обновление уже доступно. Откройте приложение и посмотрите, что изменилось!"}'::json,
     '{"ru":"Летнее обновление"}'::json, '[]'::json,
     now() - interval '2 minutes', now() - interval '5 minutes', now() - interval '2 minutes',
     null, now() - interval '10 seconds', 1280, 1766, 618, 3, 472, 2, 146, 1, null),
    (910030003, 910000001, 'scheduled', true, 'active', '["telegram","email"]'::json,
     '{"ru":"Напоминаем о технических работах сегодня ночью.","en":"Scheduled maintenance is planned for tonight."}'::json,
     '{"ru":"Технические работы","en":"Scheduled maintenance"}'::json,
     '[{"kind":"url","label":"Статус сервиса","url":"https://status.example.com"}]'::json,
     '2099-01-01 12:00:00+00', now(), null, null, now(), 0, 0, 0, 0, 0, 0, 0, 0, null)
ON CONFLICT (broadcast_id) DO UPDATE SET
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

SELECT setval(pg_get_serial_sequence('subscriptions', 'subscription_id'), GREATEST((SELECT COALESCE(MAX(subscription_id), 1) FROM subscriptions), 1), true);
SELECT setval(pg_get_serial_sequence('payments', 'payment_id'), GREATEST((SELECT COALESCE(MAX(payment_id), 1) FROM payments), 1), true);
SELECT setval(pg_get_serial_sequence('message_logs', 'log_id'), GREATEST((SELECT COALESCE(MAX(log_id), 1) FROM message_logs), 1), true);
SELECT setval(pg_get_serial_sequence('support_tickets', 'ticket_id'), GREATEST((SELECT COALESCE(MAX(ticket_id), 1) FROM support_tickets), 1), true);
SELECT setval(pg_get_serial_sequence('support_ticket_messages', 'message_id'), GREATEST((SELECT COALESCE(MAX(message_id), 1) FROM support_ticket_messages), 1), true);
SELECT setval(pg_get_serial_sequence('promo_codes', 'promo_code_id'), GREATEST((SELECT COALESCE(MAX(promo_code_id), 1) FROM promo_codes), 1), true);
SELECT setval(pg_get_serial_sequence('ad_campaigns', 'ad_campaign_id'), GREATEST((SELECT COALESCE(MAX(ad_campaign_id), 1) FROM ad_campaigns), 1), true);
SELECT setval(pg_get_serial_sequence('admin_broadcasts', 'broadcast_id'), GREATEST((SELECT COALESCE(MAX(broadcast_id), 1) FROM admin_broadcasts), 1), true);

COMMIT;
`;

const remnawavePayload = {
  meta: payload.meta,
  users: panelUsers,
};

const remnawaveSql = `${header("Remnawave PostgreSQL", `panel_users=${panelUsers.length}`)}BEGIN;

CREATE TEMP TABLE remnawave_docs_demo_payload (payload jsonb NOT NULL) ON COMMIT DROP;
INSERT INTO remnawave_docs_demo_payload VALUES (${sqlJson(remnawavePayload, "remnawave_demo")});

CREATE TEMP TABLE remnawave_docs_demo_users (
    uuid uuid NOT NULL,
    short_uuid text NOT NULL,
    username text NOT NULL,
    status text NOT NULL,
    traffic_limit_bytes bigint NOT NULL,
    traffic_limit_strategy text NOT NULL,
    expire_at timestamptz NOT NULL,
    trojan_password text NOT NULL,
    vless_uuid uuid NOT NULL,
    ss_password text NOT NULL,
    description text NOT NULL,
    email text NOT NULL,
    telegram_id bigint NOT NULL,
    hwid_device_limit integer NOT NULL,
    tag text NOT NULL,
    last_triggered_threshold integer NOT NULL,
    tariff_key text NOT NULL,
    updated_at timestamptz NOT NULL
) ON COMMIT DROP;

INSERT INTO remnawave_docs_demo_users
SELECT
    (item ->> 'uuid')::uuid,
    item ->> 'short_uuid',
    item ->> 'username',
    item ->> 'status',
    (item ->> 'traffic_limit_bytes')::bigint,
    item ->> 'traffic_limit_strategy',
    now() + ((item ->> 'expire_at')::timestamptz - '${anchor}'::timestamptz),
    item ->> 'trojan_password',
    (item ->> 'vless_uuid')::uuid,
    item ->> 'ss_password',
    item ->> 'description',
    item ->> 'email',
    (item ->> 'telegram_id')::bigint,
    (item ->> 'hwid_device_limit')::integer,
    item ->> 'tag',
    (item ->> 'last_triggered_threshold')::integer,
    item ->> 'tariff_key',
    now()
FROM remnawave_docs_demo_payload,
     jsonb_array_elements(payload -> 'users') AS item;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'uuid'
    ) THEN
        EXECUTE $sql$
            WITH upserted_users AS (
                INSERT INTO users (
                    uuid, short_uuid, username, status, traffic_limit_bytes,
                    traffic_limit_strategy, expire_at, trojan_password, vless_uuid,
                    ss_password, description, email, telegram_id, hwid_device_limit,
                    tag, last_triggered_threshold, updated_at
                )
                SELECT
                    uuid, short_uuid, username, status, traffic_limit_bytes,
                    traffic_limit_strategy, expire_at, trojan_password, vless_uuid,
                    ss_password, description, email, telegram_id, hwid_device_limit,
                    tag, last_triggered_threshold, updated_at
                FROM remnawave_docs_demo_users
                ON CONFLICT (uuid) DO UPDATE SET
                    short_uuid = EXCLUDED.short_uuid,
                    username = EXCLUDED.username,
                    status = EXCLUDED.status,
                    traffic_limit_bytes = EXCLUDED.traffic_limit_bytes,
                    traffic_limit_strategy = EXCLUDED.traffic_limit_strategy,
                    expire_at = EXCLUDED.expire_at,
                    trojan_password = EXCLUDED.trojan_password,
                    vless_uuid = EXCLUDED.vless_uuid,
                    ss_password = EXCLUDED.ss_password,
                    description = EXCLUDED.description,
                    email = EXCLUDED.email,
                    telegram_id = EXCLUDED.telegram_id,
                    hwid_device_limit = EXCLUDED.hwid_device_limit,
                    tag = EXCLUDED.tag,
                    last_triggered_threshold = EXCLUDED.last_triggered_threshold,
                    updated_at = now()
                RETURNING t_id, username
            )
            INSERT INTO internal_squad_members (internal_squad_uuid, user_id)
            SELECT squad.uuid, upserted.t_id
            FROM upserted_users AS upserted
            JOIN remnawave_docs_demo_users AS source USING (username)
            JOIN internal_squads AS squad
              ON squad.name = 'Default-Squad'
              OR squad.name = CASE source.tariff_key
                  WHEN 'standard' THEN 'MiniShop Standard'
                  WHEN 'premium' THEN 'MiniShop Premium'
                  ELSE NULL
              END
            ON CONFLICT DO NOTHING
        $sql$;
    ELSE
        EXECUTE $sql$
            WITH upserted_users AS (
                INSERT INTO users (
                    short_uuid, username, status, traffic_limit_bytes,
                    traffic_limit_strategy, expire_at, trojan_password, vless_uuid,
                    ss_password, description, email, telegram_id, hwid_device_limit,
                    tag, last_triggered_threshold, updated_at
                )
                SELECT
                    short_uuid, username, status, traffic_limit_bytes,
                    traffic_limit_strategy, expire_at, trojan_password, vless_uuid,
                    ss_password, description, email, telegram_id, hwid_device_limit,
                    tag, last_triggered_threshold, updated_at
                FROM remnawave_docs_demo_users
                ON CONFLICT (username) DO UPDATE SET
                    short_uuid = EXCLUDED.short_uuid,
                    status = EXCLUDED.status,
                    traffic_limit_bytes = EXCLUDED.traffic_limit_bytes,
                    traffic_limit_strategy = EXCLUDED.traffic_limit_strategy,
                    expire_at = EXCLUDED.expire_at,
                    trojan_password = EXCLUDED.trojan_password,
                    vless_uuid = EXCLUDED.vless_uuid,
                    ss_password = EXCLUDED.ss_password,
                    description = EXCLUDED.description,
                    email = EXCLUDED.email,
                    telegram_id = EXCLUDED.telegram_id,
                    hwid_device_limit = EXCLUDED.hwid_device_limit,
                    tag = EXCLUDED.tag,
                    last_triggered_threshold = EXCLUDED.last_triggered_threshold,
                    updated_at = now()
                RETURNING id, username
            )
            INSERT INTO internal_squad_members (internal_squad_uuid, user_id)
            SELECT squad.uuid, upserted.id
            FROM upserted_users AS upserted
            JOIN remnawave_docs_demo_users AS source USING (username)
            JOIN internal_squads AS squad
              ON squad.name = 'Default-Squad'
              OR squad.name = CASE source.tariff_key
                  WHEN 'standard' THEN 'MiniShop Standard'
                  WHEN 'premium' THEN 'MiniShop Premium'
                  ELSE NULL
              END
            ON CONFLICT DO NOTHING
        $sql$;
    END IF;
END $$;

COMMIT;
`;

async function updateGeneratedFile(filePath, contents) {
  if (checkOnly) {
    const current = await readFile(filePath, "utf8").catch(() => "");
    if (current !== contents) {
      throw new Error(`${path.relative(repoRoot, filePath)} is stale; run npm run dev:stand:generate:mocks`);
    }
    return;
  }
  await writeFile(filePath, contents, "utf8");
}

await Promise.all([
  updateGeneratedFile(minishopSeedPath, minishopSql),
  updateGeneratedFile(remnawaveSeedPath, remnawaveSql),
]);

console.log(
  `${checkOnly ? "Verified" : "Generated"} docs-demo dev seeds (${users.length} users, ${subscriptions.length} subscriptions, ${payments.length} payments, ${payload.logs.length} logs)`
);
