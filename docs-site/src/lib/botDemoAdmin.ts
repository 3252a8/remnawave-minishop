import { escape, type Button, type ButtonRow, type ChatMessage } from './botDemoConversation';
import { adminMessageKeys } from './botDemoAdminCopy';
import { AdminPromoDemo } from './botDemoAdminPromos';
import { AdminUi, formatDemoDate, type AdminHost, type AdminMessages } from './botDemoAdminUi';
import { AdminUserDemo } from './botDemoAdminUsers';
import type { BotDemoData, DemoAdminUser, DemoCampaign } from './botDemoData';

export type { AdminMessages } from './botDemoAdminUi';

export function adminMessages(locale: Record<string, string>): AdminMessages {
  return Object.fromEntries(adminMessageKeys.map((key) => {
    if (!locale[key]) throw new Error(`Missing Telegram admin demo locale key: ${key}`);
    return [key, locale[key]];
  }));
}

type Payment = BotDemoData['payments'][number];
type Audience = 'all' | 'active' | 'inactive' | 'expired';
const audiences = ['all', 'active', 'inactive', 'expired'] as const;

export class AdminDemo {
  private readonly ui: AdminUi;
  private readonly users: AdminUserDemo;
  private readonly promos: AdminPromoDemo;
  private paymentRows: Payment[] = [];
  private paymentId = 0;
  private logRows: BotDemoData['logs'] = [];
  private campaigns: DemoCampaign[] = [];
  private campaignId = 0;
  private additionalRevenue = 0;
  private empty = false;
  private lastSync?: Date;
  private sentRecently = 0;

  constructor(host: AdminHost) {
    this.ui = new AdminUi(host);
    this.users = new AdminUserDemo(this.ui, (message) => this.panel(message), (message, user, back) => {
      this.recentActions(message, user, back);
    });
    this.promos = new AdminPromoDemo(this.ui, (message) => this.panel(message));
  }

  get acceptsAttachment() {
    return this.ui.acceptsAttachment;
  }

  clearInput() {
    this.ui.clearInput();
  }

  reset(empty: boolean) {
    const { data } = this.ui.host;
    this.clearInput();
    this.empty = empty;
    this.users.reset(empty);
    this.promos.reset(empty);
    this.paymentRows = empty ? [] : [...data.payments];
    this.paymentId = Math.max(this.paymentId, ...data.payments.map(({ id }) => id));
    this.logRows = empty ? [] : data.logs;
    this.campaigns = empty ? [] : data.ads.map((campaign) => ({ ...campaign }));
    this.campaignId = Math.max(0, ...this.campaigns.map(({ id }) => id));
    this.additionalRevenue = 0;
    this.lastSync = undefined;
    this.sentRecently = 0;
  }

  recordPayment(payment: Omit<Payment, 'id'>) {
    const id = ++this.paymentId;
    this.paymentRows.unshift({ ...payment, id });
    if (payment.currency === 'RUB') this.additionalRevenue += payment.amount;
    return id;
  }

  recordPromoActivation(id: number) {
    this.promos.recordActivation(id, this.ui.host.data.current.id);
  }

  findPromo(code: string) {
    return this.promos.find(code) ?? (this.empty ? this.ui.host.data.promos.find((promo) => promo.code === code) : undefined);
  }

  handleCommand(input: string) {
    const [command, ...arguments_] = input.split(/\s+/);
    if (command === '/admin') {
      this.panel(this.ui.host.append(''));
      return true;
    }
    if (command === '/syncstatus') {
      this.ui.host.append(this.syncStatus());
      return true;
    }
    const target = arguments_.join(' ').match(/^admin_user_(ms_[a-f0-9]{32}|\d+)$/)?.[1];
    if (command === '/start' && target) {
      this.users.openDeepLink(target);
      return true;
    }
    return false;
  }

  private back(message: ChatMessage) {
    return this.ui.button('back_to_admin_panel_button', () => this.panel(message));
  }

  panel(message: ChatMessage) {
    const { ui } = this;
    const webTitle = ui.t('admin_open_web_panel_button');
    ui.view(message, ui.t('admin_panel_title'), [
      ui.button('admin_stats_and_monitoring_section', () => this.monitoring(message)),
      ui.button('admin_user_management_section', () => this.users.menu(message)),
      ui.button('admin_promo_marketing_section', () => this.promos.menu(message)),
      ui.button('admin_ads_section', () => this.ads(message)),
      ui.button('admin_system_functions_section', () => this.system(message)),
      ...(ui.host.hasMiniApp() ? [{
        label: webTitle, external: true, activate: () => ({ kind: 'app' as const, title: webTitle, route: '/admin/stats' }),
      }] : []),
      ui.button('back_to_main_menu_button', () => ui.host.mainMenu(message)),
    ]);
  }

  private monitoring(message: ChatMessage) {
    const { ui } = this;
    ui.view(message, ui.t('admin_stats_and_monitoring_section'), [
      [
        ui.button('admin_stats_button', () => this.statistics(message)),
        ui.button('admin_view_payments_button', () => this.payments(message, 0)),
      ],
      ui.button('admin_view_logs_menu_button', () => this.logsMenu(message)),
      this.back(message),
    ]);
  }

  private statistics(message: ChatMessage) {
    const { ui } = this;
    const stats = ui.host.data.stats;
    const { records } = this.users;
    const active = records.filter((user) => user.days > 0 && !user.banned);
    const banned = records.filter((user) => user.banned);
    const line = (key: string, value: string | number) => `${ui.t(key)}: <b>${value}</b>`;
    const revenue = (amount: number) => `${((this.empty ? 0 : amount) + this.additionalRevenue).toFixed(2)} ${stats.currency}`;
    ui.view(message, [
      `<b>${ui.t('admin_stats_header')}</b>`, '',
      `<b>👥 ${ui.t('admin_enhanced_users_stats_header')}</b>`,
      `📊 ${line('admin_total', records.length)}`,
      `📡 ${line('admin_user_stats_active_subscription_label', active.length)}`,
      `💳 ${line('admin_user_stats_paid_subs_label', this.empty ? 0 : stats.paid)}`,
      `🧪 ${line('admin_user_stats_trial_label', this.empty ? 0 : stats.trial)}`,
      `🎁 ${line('admin_user_stats_free_subscription_label', this.empty ? 0 : stats.free)}`,
      `😴 ${line('admin_user_stats_inactive_label', records.length - active.length - banned.length)}`,
      `🚫 ${line('admin_user_stats_banned_label', banned.length)}`,
      `🎁 ${line('admin_user_stats_referral_label', this.empty ? 0 : stats.referred)}`, '',
      `<b>🖥 ${ui.t('admin_panel_stats_header')}</b>`,
      `🟢 ${line('admin_panel_online_label', this.empty ? 0 : stats.online)}`,
      `📊 ${line('admin_panel_active_label', this.empty ? 0 : stats.panelActive)}`,
      `🔴 ${line('admin_panel_disabled_label', this.empty ? 0 : stats.panelDisabled)}`,
      `⏰ ${line('admin_panel_expired_label', this.empty ? 0 : stats.panelExpired)}`,
      `⚠️ ${line('admin_panel_limited_label', this.empty ? 0 : stats.panelLimited)}`,
      `👥 ${line('admin_panel_total_users_label', this.empty ? 0 : stats.panelTotal)}`,
      `💾 ${line('admin_panel_memory_usage_label', `${(this.empty ? 0 : stats.memory).toFixed(1)}%`)}`, '',
      `<b>💰 ${ui.t('admin_financial_stats_header')}</b>`,
      line('admin_financial_today_label', revenue(stats.today)),
      line('admin_financial_week_label', revenue(stats.week)),
      line('admin_financial_month_label', revenue(stats.month)),
      line('admin_financial_all_time_label', revenue(stats.total)), '',
      this.syncStatus(),
    ].join('\n'), [ui.button('back_to_stats_monitoring_button', () => this.monitoring(message))]);
  }

  private payments(message: ChatMessage, page: number) {
    const { ui } = this;
    if (this.paymentRows.length === 0) {
      ui.view(message, ui.t('admin_no_payments_found'), [ui.button('back_to_stats_monitoring_button', () => this.monitoring(message))]);
      return;
    }
    const pageSize = 5;
    const rows = this.paymentRows.slice(page * pageSize, (page + 1) * pageSize);
    const totalPages = Math.ceil(this.paymentRows.length / pageSize);
    const methods = [...ui.host.data.methods, ...ui.host.data.starsMethods];
    const text = [
      ui.t('admin_payments_header'),
      ui.t('admin_payments_pagination_info', {
        shown: rows.length, total: this.paymentRows.length, current_page: page + 1, total_pages: totalPages,
      }),
      '',
      ...rows.map((payment, index) => {
        const { userId, userLabel, amount, currency, provider, status, date, months, days, gb, tariff, mode, description } = payment;
        const label = methods.find((method) => method.id === provider || (provider === 'telegram_stars' && method.id === 'stars'))?.label ?? provider;
        const traffic = ['traffic', 'traffic_package', 'topup', 'premium_topup'].includes(mode.split(/[@|]/, 1)[0]);
        const period = traffic ? ui.t('admin_payment_traffic_label', { traffic_gb: gb || months })
          : days ? ui.t('admin_payment_days_label', { days }) : ui.t('admin_payment_months_label', { months });
        return [
          `<b>${page * pageSize + index + 1}.</b> ${status === 'succeeded' ? '✅' : ['pending', 'waiting_for_capture'].includes(status) ? '⏳' : '❌'} <b>${amount} ${escape(currency)}</b>`,
          `👤 User ${userId}${userLabel ? ` (${escape(userLabel)})` : ''}`,
          `💳 ${escape(label)}`, `📅 ${formatDemoDate(date)}`, period,
          ...(tariff ? [`Tariff: ${escape(tariff)}`] : []), ...(mode ? [`Sale mode: ${escape(mode)}`] : []),
          `📋 ${escape(status)}`, `📝 ${escape(description || 'N/A')}`, '',
        ].join('\n');
      }),
    ].join('\n');
    ui.view(message, text, [
      ...ui.pager(page, totalPages, (next) => this.payments(message, next), true, true),
      [
        ui.button('admin_export_payments_csv', () => ui.document('payments-demo.csv',
          [['payment_id', 'user_id', 'amount', 'currency', 'provider', 'status', 'description', 'created_at'],
            ...this.paymentRows.map((row) => [row.id, row.userId, row.amount, row.currency, row.provider, row.status, row.description, row.date])])),
        ui.button('admin_refresh_payments', () => this.payments(message, page)),
      ],
      ui.button('back_to_stats_monitoring_button', () => this.monitoring(message)),
    ]);
  }

  private logsMenu(message: ChatMessage) {
    const { ui } = this;
    ui.view(message, ui.t('admin_logs_menu_title'), [
      [
        ui.button('admin_view_all_logs_button', () => this.logs(message, 0)),
        ui.button('admin_view_user_logs_prompt_button', () => this.lookupLogs(message)),
      ],
      ui.button('admin_export_logs_csv_button', () => {
        ui.alert('admin_logs_csv_export_started');
        ui.document('logs-demo.csv', [
          ['timestamp', 'user_id', 'event_type', 'content'],
          ...this.logEntries().map(({ date, userId, event, text }) => [date, userId, event, text]),
        ]);
        ui.answer('admin_logs_csv_export_success');
      }),
      ui.button('back_to_stats_monitoring_button', () => this.monitoring(message)),
    ]);
  }

  private lookupLogs(message: ChatMessage) {
    const { ui } = this;
    ui.prompt(message, ui.t('admin_prompt_for_user_id_or_username_logs'), (input) => {
      const user = this.users.find(input);
      if (!user) {
        ui.answer('admin_log_user_not_found', { input: escape(input) });
        return;
      }
      const results = ui.host.append('');
      this.logs(results, 0, user, () => this.lookupLogs(results));
    }, [ui.button('cancel_button', () => this.logsMenu(message))]);
  }

  private logEntries(user?: DemoAdminUser) {
    return user ? this.logRows.filter((log) => log.userId === user.id) : this.logRows;
  }

  private recentActions(message: ChatMessage, user: DemoAdminUser, fromCard: () => void) {
    const { ui } = this;
    const text = this.logEntries(user).slice(0, 5).map(({ date, event, text }) =>
      `🕐 <code>${formatDemoDate(date)}</code> - <code>${escape(event)}</code>\n   ${escape(text)}`).join('\n\n');
    ui.view(message, `${ui.t('admin_user_recent_actions_title', { user_id: user.minishop })}\n\n${text || ui.t('admin_no_logs_found')}`, [
      ui.button('admin_user_view_all_logs_button', () => this.logs(message, 0, user, () => this.recentActions(message, user, fromCard))),
      ui.button('admin_user_back_to_card_button', fromCard),
    ]);
  }

  private logs(message: ChatMessage, page: number, user?: DemoAdminUser, back?: () => void) {
    const { ui } = this;
    const entries = this.logEntries(user);
    const perPage = 10;
    const totalPages = Math.max(1, Math.ceil(entries.length / perPage));
    const title = ui.t(user ? 'admin_user_logs_title' : 'admin_all_logs_title', {
      user_display: user ? escape(user.name) : '', current_page: page + 1, total_pages: totalPages,
    });
    const text = entries.slice(page * perPage, (page + 1) * perPage).map((entry) =>
      ui.t('admin_log_entry_format', {
        timestamp_str: formatDemoDate(entry.date), user_display: escape(this.users.find(String(entry.userId))?.name ?? entry.actor),
        user_id: entry.userId, event_type: escape(entry.event), content_preview: escape(entry.text),
      })).join('\n\n');
    ui.view(message, `${title}\n\n${text || ui.t('admin_no_logs_found')}`, [
      ...ui.pager(page, totalPages, (next) => this.logs(message, next, user, back)),
      back ? ui.button('back_to_main_menu_button', back) : ui.button('admin_logs_menu_title', () => this.logsMenu(message)),
    ]);
  }

  private system(message: ChatMessage) {
    const { ui } = this;
    ui.view(message, ui.t('admin_system_functions_section'), [
      [
        ui.button('admin_broadcast_button', () => this.broadcast(message)),
        ui.button('admin_sync_panel_button', () => {
          this.lastSync = new Date();
          ui.alert('admin_sync_initiated_from_panel');
          ui.answer('sync_success_simple');
        }),
      ],
      ui.button('admin_queue_status_button', () => {
        ui.view(message, ui.t('admin_queue_status_info', {
          user_queue_size: this.empty ? 0 : ui.host.data.stats.userQueue, user_processing: `❌ ${ui.t('no_button')}`, user_recent: this.sentRecently,
          group_queue_size: this.empty ? 0 : ui.host.data.stats.groupQueue, group_processing: `❌ ${ui.t('no_button')}`, group_recent: 0,
        }), [ui.button('back_to_main_menu_button', () => this.system(message))]);
      }),
      this.back(message),
    ]);
  }

  private syncStatus() {
    const { ui } = this;
    const stats = ui.host.data.stats;
    const date = this.lastSync?.toISOString() ?? (this.empty ? '' : stats.lastSync);
    if (!date) return ui.t('admin_sync_status_never_run');
    return [
      `<b>${ui.t('admin_stats_last_sync_header')}</b>`,
      `${ui.t('admin_stats_sync_time')}: ${formatDemoDate(date)} UTC`,
      `${ui.t('admin_status')}: ${this.lastSync ? 'success' : escape(stats.syncStatus)}`,
      `${ui.t('admin_stats_sync_users_processed')}: ${this.lastSync ? this.users.records.length : stats.syncedUsers}`,
      `${ui.t('admin_stats_sync_subs_synced')}: ${this.lastSync ? this.users.records.filter((user) => user.days > 0).length : stats.syncedSubscriptions}`,
    ].join('\n');
  }

  private broadcast(message: ChatMessage) {
    this.ui.prompt(message, this.ui.t('admin_broadcast_enter_message'), (input) => this.broadcastPreview(input), [this.ui.button('cancel_button', () => this.system(message))]);
    this.ui.acceptsAttachment = true;
  }

  broadcastAttachment(filename: string, caption: string) {
    this.broadcastPreview([ `📎 ${filename}`, caption ].filter(Boolean).join('\n'));
  }

  private broadcastPreview(input: string) {
    const { ui } = this;
    ui.clearInput();
    ui.host.append(escape(input));
    const confirmation = ui.host.append('');
    let completed = false;
    const choose = (target: Audience) => {
      const choices = audiences.map((audience): Button => ({
        label: `${target === audience ? '• ' : ''}${ui.t(`broadcast_target_${audience}_button`)}`,
        activate: () => { if (!completed) choose(audience); },
      }));
      ui.confirmation(confirmation, ui.t('admin_broadcast_confirm_prompt_short'), [
        choices.slice(0, 2), choices.slice(2),
        [
          ui.button('confirm_broadcast_send_button', () => {
            if (completed) return;
            const count = this.users.audienceSize(target);
            completed = true;
            this.sentRecently += count;
            ui.view(confirmation, ui.t('admin_broadcast_started'));
            const done = ui.host.append('');
            ui.view(done, ui.t('broadcast_queue_result', {
              sent_count: count, failed_count: 0, user_queue_size: 0, group_queue_size: 0,
            }), [ui.button('back_to_main_menu_button', () => this.system(done))]);
          }),
          ui.button('cancel_button', () => {
            completed = true;
            this.system(confirmation);
            ui.alert('admin_broadcast_cancelled');
          }),
        ],
      ]);
    };
    choose('all');
  }

  private ads(message: ChatMessage, page = 0) {
    const { ui } = this;
    const rows = this.campaigns.slice(page * 5, (page + 1) * 5);
    const totals = this.campaigns.reduce((sum, campaign) => ({
      revenue: sum.revenue + campaign.revenue, cost: sum.cost + campaign.cost,
    }), { revenue: 0, cost: 0 });
    const extra: ButtonRow[] = [
      ui.button('admin_ads_create_button', () => this.createAd(message, page)),
      this.back(message),
    ];
    const overview = ui.t('admin_ads_overview', { revenue: totals.revenue.toFixed(2), cost: totals.cost.toFixed(2) });
    ui.view(message, `${overview}\n\n${ui.t(this.campaigns.length ? 'admin_ads_header' : 'admin_ads_empty')}`, [
      ...rows.map((row): Button => ({ label: row.source, activate: () => this.adCard(message, row, page) })),
      ...ui.pager(page, Math.ceil(this.campaigns.length / 5), (next) => this.ads(message, next)),
      ...extra,
    ]);
  }

  private adCard(message: ChatMessage, campaign: DemoCampaign, page: number) {
    const { ui } = this;
    ui.view(message, ui.t('admin_ads_card', {
      ...campaign, source: escape(campaign.source), start_param: campaign.param, active: ui.t(campaign.active ? 'yes_button' : 'no_button'),
      cost: campaign.cost.toFixed(2), revenue: campaign.revenue.toFixed(2),
    }), [
      ui.button('admin_ads_delete_button', () => {
        ui.confirmation(message, ui.t('admin_ads_delete_confirm', { id: campaign.id }), [[
          ui.button('yes_button', () => {
            this.campaigns = this.campaigns.filter((row) => row !== campaign);
            ui.alert('admin_ads_deleted_success');
            this.ads(message, Math.min(page, Math.max(0, Math.ceil(this.campaigns.length / 5) - 1)));
          }),
          ui.button('no_button', () => this.adCard(message, campaign, page)),
        ]]);
      }),
      ui.button('back_to_ads_list_button', () => this.ads(message, page)),
      this.back(message),
    ]);
  }

  private createAd(message: ChatMessage, page: number) {
    const { ui } = this;
    const cancel = (target: ChatMessage) => ui.button('cancel_button', () => this.ads(target, page));
    ui.prompt(message, ui.t('admin_ads_create_source_prompt'), (source) => {
      if (source.length > 64) return void ui.answer('admin_ads_invalid_source');
      const parameters = ui.host.append('');
      ui.prompt(parameters, ui.t('admin_ads_create_start_param_prompt'), (param) => {
        if (!/^[A-Za-z0-9_-]{2,64}$/.test(param)) return void ui.answer('admin_ads_invalid_start_param');
        const costPrompt = ui.host.append('');
        ui.prompt(costPrompt, ui.t('admin_ads_create_cost_prompt'), (value) => {
          const cost = Number(value.replace(',', '.'));
          if (!Number.isFinite(cost) || cost < 0 || cost > 1e8) return void ui.answer('admin_ads_invalid_cost');
          if (this.campaigns.some((campaign) => campaign.param === param)) return void ui.answer('admin_ads_start_param_exists');
          const campaign = { id: ++this.campaignId, source, param, cost, starts: 0, trials: 0, payers: 0, revenue: 0, active: true };
          this.campaigns.unshift(campaign);
          ui.clearInput();
          ui.answer('admin_ads_created_success', { id: campaign.id, source: escape(source), start_param: param, cost: cost.toFixed(2) });
          const done = ui.answer('admin_ads_back_to_menu_hint');
          done.rows = [
            ui.button('back_to_main_menu_button', () => this.ads(done, page)),
          ];
        }, [cancel(costPrompt)]);
      }, [cancel(parameters)]);
    }, [cancel(message)]);
  }
}
