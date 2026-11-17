import { withDemoIdentities } from '../../../frontend/src/lib/webapp/demoIdentities';
import { DEMO_AUTO_RENEW_SUBSCRIPTION } from '../../../frontend/src/lib/webapp/previewMock/devMock';

type RecordData = Record<string, unknown>;
type Language = 'ru' | 'en';

function record(input: unknown): RecordData {
  return typeof input === 'object' && input !== null && !Array.isArray(input) ? input as RecordData : {};
}

function rows(input: unknown): RecordData[] {
  return Array.isArray(input) ? input.map(record) : [];
}

function text(input: unknown, fallback = '') {
  return typeof input === 'string' && input ? input : fallback;
}

function numeric(input: unknown, fallback = 0) {
  if (input === null || input === undefined || input === '') return fallback;
  const value = Number(input);
  return Number.isFinite(value) ? value : fallback;
}

function displayName(user: RecordData) {
  return [text(user.first_name), text(user.last_name)].filter(Boolean).join(' ')
    || text(user.username) || text(user.email) || String(user.user_id ?? '');
}

function pair(input: unknown, fallback: string): Record<Language, string> {
  const localized = record(input);
  return { ru: text(localized.ru, fallback), en: text(localized.en, fallback) };
}

function plan(row: RecordData) {
  const months = numeric(row.months);
  return {
    months,
    days: numeric(row.duration_days, months === 12 ? 365 : months * 30),
    price: numeric(row.price),
    currency: text(row.currency, 'RUB'),
    stars: numeric(row.stars_price) || undefined,
    gb: numeric(row.traffic_gb),
    count: numeric(row.device_count),
    kind: text(row.sale_mode),
    methods: Array.isArray(row.available_payment_method_ids) ? row.available_payment_method_ids.map(String) : [],
  };
}

function tariffList(plans: RecordData[], catalog: RecordData[], deviceLimit: number) {
  const groups = new Map<string, RecordData[]>();
  for (const row of plans) {
    const key = text(row.tariff_key);
    if (key && numeric(row.price) > 0) groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  return [...groups].map(([key, group]) => {
    const settings = catalog.find((item) => text(item.key) === key) ?? {};
    const seed = group[0];
    return {
      key,
      names: pair(settings.names, text(seed.tariff_name, key)),
      descriptions: pair(settings.descriptions, text(seed.tariff_description, text(seed.description))),
      isTraffic: seed.billing_model === 'traffic',
      limit: numeric(seed.monthly_gb, numeric(settings.monthly_gb)),
      premiumLimit: numeric(seed.premium_monthly_gb, numeric(settings.premium_monthly_gb)),
      deviceLimit: numeric(settings.hwid_device_limit, deviceLimit),
      periods: group.map(plan),
    };
  });
}

function methods(input: unknown) {
  return rows(input).map((row) => ({
    id: text(row.id),
    label: text(row.name, text(row.id)),
    min: numeric(row.min_amount),
    minCurrency: text(row.min_currency, 'RUB'),
  }));
}

export function botDemoData(
  source: unknown,
  checkoutPlans: unknown,
  checkoutMethods: unknown,
  checkoutPromoCode: string,
) {
  const sourceData = withDemoIdentities(record(source));
  const current = record(sourceData.currentUser);
  const currentId = numeric(current.user_id);
  const subscription = record(sourceData.currentSubscription);
  const settings = record(sourceData.webappSettings);
  const config = record(sourceData.config);
  const deviceData = record(sourceData.devices);
  const deviceTopup = record(sourceData.device_topup_options);
  const trafficTopup = record(sourceData.topup_options);
  const change = record(sourceData.tariff_change_options);
  const referral = record(sourceData.referral);
  const details = record(sourceData.adminUserDetails);
  const stats = record(sourceData.stats);
  const userStats = record(stats.users);
  const financial = record(stats.financial);
  const panelSystem = record(record(stats.panel).system);
  const panelUsers = record(panelSystem.users);
  const panelStatuses = record(panelUsers.statusCounts);
  const panelMemory = record(panelSystem.memory);
  const sync = record(stats.panel_sync);
  const queue = record(stats.queue);
  const fields = rows(sourceData.settingsSections).flatMap((section) => rows(section.fields));
  const deviceLimit = numeric(deviceData.max_devices);

  const users = rows(sourceData.adminUsers).map((user) => {
    const id = numeric(user.user_id);
    const detail = record(details[String(id)]);
    const subscriptions = rows(detail.subscriptions);
    const sub = record(detail.active_subscription);
    const previousExpiry = subscriptions.map((item) => text(item.end_date)).sort().at(-1);
    const active = sub.is_active === true;
    const expiry = text(sub.end_date, text(user.subscription_expires_at, previousExpiry));
    const timestamp = Date.parse(expiry);
    const remaining = Number.isFinite(timestamp) ? Math.ceil((timestamp - Date.now()) / 86_400_000) : 0;
    const days = active ? Math.max(1, remaining) : expiry ? Math.min(-1, remaining) : 0;
    const provider = text(sub.provider);
    const traffic = numeric(sub.traffic_used_bytes) / 2 ** 30;
    const premiumTraffic = numeric(sub.premium_used_bytes) / 2 ** 30;
    return {
      id, minishop: text(user.minishop_id), name: displayName(user), username: text(user.username) || undefined,
      firstName: text(user.first_name),
      telegram: numeric(user.telegram_id) || undefined, email: text(user.email), days, expiry,
      trial: provider === 'trial', trialUsed: user.has_used_trial === true || subscriptions.length > 0,
      banned: user.is_banned === true, tariff: text(sub.tariff_key) || undefined,
      premium: sub.premium_unlimited_override === true ? 'unlimited' as const
        : numeric(sub.premium_bonus_bytes) / 2 ** 30 || undefined,
      limit: sub.hwid_device_limit == null ? undefined : numeric(sub.hwid_device_limit),
      traffic: Math.round(traffic * 100) / 100, premiumTraffic: Math.round(premiumTraffic * 100) / 100,
      lifetimeTraffic: subscriptions.reduce((total, item) => total + numeric(item.traffic_used_bytes), 0) / 2 ** 30,
      revenue: numeric(record(detail.total_paid).RUB, numeric(detail.total_paid)),
      referredBy: numeric(user.referred_by_id) || undefined,
      language: text(user.language_code), panelUuid: text(user.panel_user_uuid),
      panelStatus: text(sub.status_from_panel, 'UNKNOWN'), trafficLimit: numeric(sub.traffic_limit_bytes) / 2 ** 30,
      trafficStrategy: text(sub.traffic_limit_strategy), extraDevices: numeric(sub.extra_hwid_devices),
      logCount: numeric(detail.log_count), subscriptionUrl: text(detail.subscription_url),
      botReferral: text(record(detail.referral).bot_link), webReferral: text(record(detail.referral).webapp_link),
      registration: text(user.registration_date),
      isAdmin: user.is_admin === true,
    };
  }).filter((user) => user.id);

  return {
    current: {
      id: currentId,
      name: displayName(current),
      expiry: text(record(record(details[String(currentId)]).active_subscription).end_date).slice(0, 10)
        || text(subscription.end_date_text),
      days: numeric(subscription.days_left),
      tariff: text(subscription.tariff_key),
      used: text(subscription.traffic_used),
      limit: text(subscription.traffic_limit),
      premiumUsed: numeric(subscription.premium_used_bytes) / 2 ** 30,
      premiumLimit: numeric(subscription.premium_limit_bytes) / 2 ** 30,
      premiumBalance: numeric(subscription.premium_topup_balance_bytes) / 2 ** 30,
      premiumLimited: subscription.premium_is_limited === true,
      premiumServers: Array.isArray(subscription.premium_node_labels) ? subscription.premium_node_labels.map(String) : [],
      premiumStrategy: text(subscription.premium_traffic_limit_strategy),
      configUrl: text(subscription.config_link),
      connectUrl: text(subscription.connect_url),
      installUrl: text(subscription.install_share_url),
      deviceLimit,
      devices: rows(deviceData.devices).map((row) => {
        const [platform, ...version] = text(row.platform_label).split(' ');
        return {
          model: text(row.display_name), platform, version: version.join(' '), client: text(row.user_agent),
          hwid: text(row.hwid_short), since: text(row.created_at_text), token: text(row.token),
        };
      }),
      trialDays: numeric(settings.trial_duration_days),
      trialGb: numeric(settings.trial_traffic_limit_gb),
      purchaseDescription: text(settings.subscription_purchase_description),
      supportUrl: text(settings.support_url, text(config.supportUrl)),
      supportTickets: settings.support_tickets_enabled !== false,
      giftsEnabled: config.giftsEnabled !== false && settings.gifts_enabled !== false,
      partnerEnabled: config.partnerProgramEnabled === true || settings.partner_program_enabled === true,
      statusUrl: text(fields.find((field) => field.key === 'SERVER_STATUS_URL')?.value),
      privacyUrl: text(config.privacyPolicyUrl),
      agreementUrl: text(config.userAgreementUrl),
      deviceSection: settings.my_devices_enabled === true,
      deviceExtra: numeric(deviceTopup.extra_hwid_devices),
      deviceExtraExpiry: text(deviceTopup.extra_hwid_devices_valid_until_text),
      renewDevices: deviceTopup.renewal_available === true,
      autoRenew: { enabled: subscription.auto_renew_enabled === true, available: subscription.auto_renew_available === true },
    },
    recurring: {
      enabled: DEMO_AUTO_RENEW_SUBSCRIPTION.auto_renew_enabled,
      available: DEMO_AUTO_RENEW_SUBSCRIPTION.auto_renew_available,
    },
    referral: {
      telegram: text(referral.bot_link), webapp: text(referral.webapp_link),
      invited: numeric(referral.invited_count), paid: numeric(referral.purchased_count),
      bonuses: rows(referral.bonus_details).map((row) => ({
        tariff: text(row.tariff_key),
        name: text(row.tariff_name),
        periods: rows(row.details).map((item) => ({
          months: numeric(item.months), inviter: numeric(item.inviter_days), friend: numeric(item.friend_days),
        })),
      })),
    },
    tariffs: tariffList(rows(sourceData.plans), rows(record(sourceData.tariffsCatalog).tariffs), deviceLimit),
    starsTariffs: tariffList(rows(checkoutPlans), [], deviceLimit),
    methods: methods(sourceData.paymentMethods),
    starsMethods: methods(checkoutMethods),
    devicePlans: rows(deviceTopup.plans).map(plan),
    trafficPlans: rows(trafficTopup.plans).map(plan),
    tariffChanges: rows(change.targets).map((target) => ({
      key: text(target.tariff_key, text(target.key)),
      actions: rows(target.actions).map((action) => ({
        mode: text(action.mode), days: numeric(action.days_after),
        price: numeric(action.price), currency: text(action.currency, 'RUB'),
        gb: numeric(action.converted_gb, numeric(action.traffic_gb)),
      })),
    })),
    users,
    payments: rows(sourceData.adminPayments).map((payment) => ({
      id: numeric(payment.payment_id), userId: numeric(payment.user_id), userLabel: text(payment.user_label),
      provider: text(payment.provider), amount: numeric(payment.amount), currency: text(payment.currency),
      status: text(payment.status), description: text(payment.description), date: text(payment.created_at),
      months: numeric(payment.subscription_duration_months), days: numeric(payment.subscription_duration_days),
      gb: numeric(payment.purchased_gb), mode: text(payment.sale_mode), tariff: text(payment.tariff_key),
      checkoutUrl: text(payment.provider_payment_url), checkoutExpires: text(payment.checkout_expires_at),
    })),
    logs: rows(sourceData.adminLogs).map((log) => ({
      date: text(log.timestamp), userId: numeric(log.user_id),
      event: text(log.event_type), text: text(log.content),
      actor: text(log.telegram_username) || text(log.telegram_first_name) || text(log.email) || String(log.user_id ?? ''),
    })),
    promos: rows(sourceData.promos).map((promo) => ({
      id: numeric(promo.id), code: text(promo.code), bonus: numeric(promo.bonus_days),
      limit: numeric(promo.max_activations), count: numeric(promo.current_activations),
      enabled: promo.is_active === true, expires: text(promo.valid_until), created: text(promo.created_at),
      creator: numeric(promo.created_by_admin_id), discount: numeric(promo.discount_percent) || undefined,
      duration: numeric(promo.duration_multiplier, 1) === 1 ? undefined : numeric(promo.duration_multiplier),
      traffic: numeric(promo.traffic_multiplier, 1) === 1 ? undefined : numeric(promo.traffic_multiplier),
      scope: text(promo.applies_to) || undefined, minMonths: numeric(promo.min_subscription_months) || undefined,
      minGb: numeric(promo.min_traffic_gb) || undefined,
    })),
    checkoutPromoCode,
    ads: rows(sourceData.ads).map((advertisement) => {
      const metrics = record(advertisement.stats);
      return {
        id: numeric(advertisement.id), source: text(advertisement.source), param: text(advertisement.start_param),
        cost: numeric(advertisement.cost), starts: numeric(metrics.users), trials: numeric(metrics.trial_activations),
        payers: numeric(metrics.payments), revenue: numeric(metrics.revenue), active: advertisement.is_active === true,
      };
    }),
    stats: {
      today: numeric(financial.today_revenue), week: numeric(financial.week_revenue),
      month: numeric(financial.month_revenue), total: numeric(financial.all_time_revenue),
      paid: numeric(userStats.paid_subscriptions), trial: numeric(userStats.trial_users),
      free: numeric(userStats.free_subscription_users), referred: numeric(userStats.referral_users),
      currency: text(stats.currency_symbol, 'RUB'), online: numeric(record(panelSystem.onlineStats).onlineNow),
      panelActive: numeric(panelStatuses.ACTIVE), panelDisabled: numeric(panelStatuses.DISABLED),
      panelExpired: numeric(panelStatuses.EXPIRED), panelLimited: numeric(panelStatuses.LIMITED),
      panelTotal: numeric(panelUsers.totalUsers), memory: 100 * numeric(panelMemory.used) / (numeric(panelMemory.total) || 1),
      lastSync: text(sync.last_sync_time), syncStatus: text(sync.status),
      syncedUsers: numeric(sync.users_processed), syncedSubscriptions: numeric(sync.subscriptions_synced),
      userQueue: numeric(queue.user_queue_size), groupQueue: numeric(queue.group_queue_size),
    },
  };
}

export type BotDemoData = ReturnType<typeof botDemoData>;
export type DemoTariff = BotDemoData['tariffs'][number];
export type DemoPlan = DemoTariff['periods'][number];
export type DemoAdminUser = BotDemoData['users'][number];
export type DemoCampaign = BotDemoData['ads'][number];
