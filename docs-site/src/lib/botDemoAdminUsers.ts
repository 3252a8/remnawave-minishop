import { escape, type Button, type ButtonRow, type ChatMessage } from './botDemoConversation';
import { AdminUi, formatDemoDate, type AdminView } from './botDemoAdminUi';
import type { DemoAdminUser } from './botDemoData';

type CardOrigin = { page?: number; banned?: boolean; viaLink?: boolean; back?: AdminView };
type LogView = (message: ChatMessage, user: DemoAdminUser, back: () => void) => void;
const trafficPeriods: Record<string, string> = { DAY: 'day', WEEK: 'week', MONTH: 'month', NO_RESET: 'no_reset' };

function separateRows(buttons: Button[], widths: number[]): ButtonRow[] {
  const rows: ButtonRow[] = [];
  let offset = 0;
  for (let index = 0; offset < buttons.length; index++) {
    const width = widths[Math.min(index, widths.length - 1)];
    rows.push(buttons.slice(offset, offset + width));
    offset += width;
  }
  return rows;
}

export class AdminUserDemo {
  records: DemoAdminUser[] = [];

  constructor(readonly ui: AdminUi, readonly panel: AdminView, readonly logs: LogView) {}

  reset(empty: boolean) {
    this.records = empty ? [] : this.ui.host.data.users.map((user) => ({ ...user }))
      .sort((first, second) => second.registration.localeCompare(first.registration));
  }

  private tariffName(key?: string) {
    return this.ui.host.data.tariffs.find((tariff) => tariff.key === key)?.names[this.ui.host.language()]
      ?? key ?? this.ui.t('admin_user_tariff_none');
  }

  find(value: string) {
    const query = value.trim().replace(/^@/, '').toLowerCase();
    return this.records.find((user) => [user.id, user.minishop, user.username, user.email, user.telegram]
      .some((identifier) => identifier !== undefined && String(identifier).toLowerCase() === query));
  }

  audienceSize(target: 'all' | 'active' | 'inactive' | 'expired') {
    return this.records.filter((user) => !user.banned && user.telegram && (
      target === 'all' || (target === 'active' && user.days > 0)
      || (target === 'inactive' && user.days <= 0) || (target === 'expired' && user.days < 0)
    )).length;
  }

  openDeepLink(reference: string) {
    this.ui.clearInput();
    const user = this.find(reference);
    if (!user) {
      this.ui.answer('admin_user_not_found', { input: escape(reference) });
      return;
    }
    this.card(this.ui.host.append(''), user, { viaLink: true });
  }

  private back(message: ChatMessage) {
    return this.ui.button('back_to_admin_panel_button', () => this.panel(message));
  }

  menu(message: ChatMessage) {
    const { ui } = this;
    ui.view(message, ui.t('admin_user_management_section'), [
      [
        ui.button('admin_users_management_button', () => this.list(message, 0)),
        ui.button('admin_users_search_button', () => this.search(message)),
      ],
      [
        ui.button('admin_ban_management_section', () => this.bans(message)),
        ui.button('admin_user_ratings_button', () => this.ratings(message)),
      ],
      this.back(message),
    ]);
  }

  private list(message: ChatMessage, page: number) {
    const { ui } = this;
    const total = Math.max(1, Math.ceil(this.records.length / 15));
    const users = this.records.slice(page * 15, (page + 1) * 15);
    ui.view(message, ui.t('admin_users_list_header', { current: page + 1, total, total_users: this.records.length }), [
      ...users.map((user): Button => ({
        label: `${user.username ? `@${user.username}` : user.email} ID: ${user.minishop} - ${user.name}`,
        activate: () => this.card(message, user, { page }),
      })),
      ...ui.pager(page, total, (index) => this.list(message, index)),
      ui.button('back_to_user_management_button', () => this.menu(message)),
    ]);
  }

  private search(message: ChatMessage, fromCard?: AdminView) {
    const { ui } = this;
    ui.prompt(message, ui.t('admin_user_management_prompt'), (input) => {
      const user = this.find(input);
      if (!user) return void ui.answer('admin_user_not_found', { input: `<code>${escape(input)}</code>` });
      this.card(ui.host.append(''), user, { back: (target) => this.search(target, fromCard) });
    }, [ui.button('cancel_button', () => fromCard ? fromCard(message) : this.menu(message))]);
  }

  private bans(message: ChatMessage) {
    const { ui } = this;
    ui.view(message, ui.t('admin_ban_management_section'), [
      [
        ui.button('admin_ban_user_button', () => this.banInput(message, true)),
        ui.button('admin_unban_user_button', () => this.banInput(message, false)),
      ],
      ui.button('admin_view_banned_users_button', () => this.bannedList(message, 0)),
      ui.button('back_to_user_management_button', () => this.menu(message)),
    ]);
  }

  private banInput(message: ChatMessage, ban: boolean) {
    const { ui } = this;
    ui.prompt(message, ui.t(ban ? 'admin_ban_user_prompt' : 'admin_unban_user_prompt'), (input) => {
      const user = this.find(input);
      if (!user) return void ui.answer('admin_user_not_found', { input: escape(input) });
      ui.clearInput();
      if (user.banned === ban) return void ui.answer(ban ? 'admin_user_already_banned' : 'admin_user_not_banned');
      user.banned = ban;
      ui.answer(ban ? 'admin_user_ban_success' : 'admin_user_unban_success', { input: `<code>${escape(input)}</code>` });
    }, [ui.button('cancel_button', () => this.bans(message))]);
  }

  private bannedList(message: ChatMessage, page: number) {
    const { ui } = this;
    const users = this.records.filter((user) => user.banned);
    page = Math.min(page, Math.max(0, Math.ceil(users.length / 10) - 1));
    const visible = users.slice(page * 10, (page + 1) * 10);
    const description = visible.map((user) =>
      `• ${escape(user.username ? `@${user.username}` : user.firstName || 'Unknown')} (ID: ${user.minishop})`).join('\n');
    ui.view(message, users.length ? ui.t('admin_banned_users_list', { count: users.length, users: description }) : ui.t('admin_banned_users_empty'), [
      ...visible.map((user) => {
        const account = user.username ? `@${user.username}` : user.email;
        return ui.button('admin_banned_user_button_text', () => this.card(message, user, { page, banned: true }), {
          user_display: [user.firstName, account ? `(${account})` : ''].filter(Boolean).join(' ') || `ID: ${user.minishop}`,
          user_id: user.minishop,
        });
      }),
      ...ui.pager(page, Math.ceil(users.length / 10), (index) => this.bannedList(message, index)),
      ui.button('back_to_main_menu_button', () => this.bans(message)),
    ]);
  }

  private ratings(message: ChatMessage) {
    const { ui } = this;
    const topLimit = 10;
    const users = this.records.filter((user) => !user.banned);
    const invitees = new Map<number, number>();
    for (const user of users) {
      if (user.referredBy) invitees.set(user.referredBy, (invitees.get(user.referredBy) ?? 0) + 1);
    }
    const ranked = (key: string, item: string, field: string, value: (user: DemoAdminUser) => number) => {
      const rows = users.map((user) => ({ user, rankValue: value(user) }))
        .filter(({ rankValue }) => rankValue > 0).sort((first, second) => second.rankValue - first.rankValue).slice(0, topLimit);
      return [
        `<b>${ui.t(key)}</b>`,
        ...(rows.length ? rows.map(({ user, rankValue }, index) => ui.t(item, {
          rank: index + 1, user: escape(user.name), [field]: Number(rankValue.toFixed(2)),
        })) : [ui.t('admin_user_ratings_empty')]),
        '',
      ];
    };
    ui.view(message, [
      ui.t('admin_user_ratings_header', { top_limit: topLimit }), '',
      ...ranked('admin_user_ratings_traffic_month_title', 'admin_user_ratings_traffic_item', 'traffic_gb', (user) => user.traffic),
      ...ranked('admin_user_ratings_traffic_lifetime_title', 'admin_user_ratings_traffic_item', 'traffic_gb', (user) => user.lifetimeTraffic),
      ...ranked('admin_user_ratings_invited_title', 'admin_user_ratings_invited_item', 'invited_count', (user) => invitees.get(user.id) ?? 0),
      ...ranked('admin_user_ratings_revenue_title', 'admin_user_ratings_revenue_item', 'revenue', (user) => user.revenue),
    ].join('\n'), [ui.button('back_to_user_management_button', () => this.menu(message))]);
  }

  private card(message: ChatMessage, user: DemoAdminUser, origin: CardOrigin = {}) {
    const { ui } = this;
    if (!this.records.includes(user)) return this.list(message, 0);
    const { current, referral, stats } = ui.host.data;
    const code = (value: string | number) => `<code>${escape(String(value))}</code>`;
    const field = (key: string, value: string | number) => `${ui.t(key)} ${code(value)}`;
    const na = ui.t('admin_user_na_value');
    const strategy = trafficPeriods[user.trafficStrategy] ?? 'unknown';
    const traffic = ui.t('traffic_used_with_period', {
      traffic_used: `${user.traffic.toFixed(2)}GB`, traffic_period: ui.t(`traffic_period_${strategy}`),
    });
    const invitees = this.records.filter((record) => record.referredBy === user.id);
    const referrer = user.referredBy ? this.find(String(user.referredBy)) : undefined;
    const deviceLimit = user.limit ?? ui.host.data.tariffs.find((tariff) => tariff.key === user.tariff)?.deviceLimit;
    const devices = deviceLimit === 0 ? ui.t('admin_hwid_limit_state_unlimited')
      : user.extraDevices && deviceLimit !== undefined ? ui.t('admin_hwid_limit_state_with_extra', {
        total: deviceLimit, base: deviceLimit - user.extraDevices, extra: user.extraDevices,
      }) : ui.t('admin_hwid_limit_state_count', { count: deviceLimit ?? 0 });
    const links = [
      ['admin_user_subscription_url_label', user.subscriptionUrl],
      ['admin_user_install_share_link_label', user.id === current.id ? current.installUrl : ''],
      ['admin_user_ref_bot_link_label', user.botReferral],
      ['admin_user_ref_webapp_link_label', user.webReferral],
    ].filter(([, value]) => value).map(([key, value]) => `${ui.t(key)} ${escape(value)}`);
    const hasProfile = user.telegram !== undefined && !origin.viaLink;
    const controls: Button[] = [
      ui.button('admin_user_reset_trial_button', () => {
        user.trialUsed = false;
        ui.alert('admin_user_trial_reset_success');
        this.card(message, user, origin);
      }),
      ui.button('admin_user_add_subscription_button', () => this.addDays(message, user, origin)),
      ui.button('admin_user_change_tariff_button', () => this.changeTariff(message, user, origin)),
      ui.button('admin_user_toggle_ban_button', () => {
        user.banned = !user.banned;
        ui.alert('admin_user_ban_toggle_success', { status: ui.t(user.banned ? 'admin_user_ban_action_banned' : 'admin_user_ban_action_unbanned') });
        this.card(message, user, origin);
      }),
      ui.button('admin_user_send_message_button', () => this.directMessage(message, user, origin)),
      ui.button('admin_user_view_logs_button', () => this.logs(message, user, () => this.card(message, user, origin))),
      ui.button('admin_user_refresh_button', () => this.card(message, user, origin)),
      ui.button('admin_user_invitees_button', () => this.invitees(message, user, 0, origin)),
      ui.button('admin_user_premium_override_button', () => this.premium(message, user, origin)),
      ui.button('admin_user_traffic_grant_button', () => this.traffic(message, user, origin)),
      ui.button('admin_user_hwid_limit_button', () => this.hwid(message, user, origin)),
    ];
    if (hasProfile) controls.push({
      ...ui.button('user_card_open_profile_button', () => ({
        kind: 'profile', title: user.name, address: `tg://user?id=${user.telegram}`, username: user.username,
      })),
      external: true,
    });
    controls.push(
      ui.button('admin_user_delete_button', () => this.deleteUser(user, origin)),
      ui.button('admin_user_search_new_button', () => this.search(message, (target) => this.card(target, user, origin))),
    );
    controls.push(this.originBack(message, origin));
    const widths = [2, 1, 2, 2, 1, 3, ...(hasProfile ? [1] : []), 1, 2];
    ui.view(message, [
      `👤 <b>${ui.t('admin_user_card_title')}</b>`, '',
      field('admin_user_id_label', user.minishop),
      field('admin_user_name_label', user.firstName || na),
      field('admin_user_username_label', user.username ? `@${user.username}` : na),
      ...(user.email ? [field('admin_user_email_label', user.email)] : []),
      ...(user.telegram ? [field('admin_user_telegram_id_label', user.telegram)] : []),
      field('admin_user_language_label', user.language || na),
      field('admin_user_registration_label', user.registration ? formatDemoDate(user.registration) : na),
      `${ui.t('admin_user_status_label')} ${ui.t(user.banned ? 'admin_user_status_banned' : 'admin_user_status_active')}`,
      ...(user.referredBy ? [field('admin_user_invited_by_label', referrer?.minishop ?? user.referredBy)] : []),
      ...(user.panelUuid ? [field('admin_user_panel_uuid_label', `${user.panelUuid.slice(0, 8)}...`)] : []),
      '',
      ...(user.days > 0 ? [
        `💳 <b>${ui.t('admin_user_subscription_info')}</b>`,
        field('admin_user_subscription_active_until', formatDemoDate(user.expiry)),
        field('admin_user_panel_status_label', user.panelStatus),
        field('admin_user_traffic_label', `${traffic} / ${user.trafficLimit ? `${user.trafficLimit.toFixed(2)}GB` : ui.t('traffic_unlimited')}`),
        ...(deviceLimit === undefined ? [] : [field('admin_user_hwid_limit_label', devices)]),
        ...(user.premium ? [field('admin_user_premium_override_label', user.premium === 'unlimited'
          ? ui.t('admin_user_premium_override_unlimited')
          : ui.t('admin_user_premium_override_bonus_value', { gb: user.premium.toFixed(2) }))] : []),
      ] : [field('admin_user_subscription_label', ui.t('admin_user_subscription_none'))]),
      field('admin_user_actions_count_label', user.logCount),
      field('admin_user_trial_label', ui.t(user.trialUsed ? 'admin_user_trial_used' : 'admin_user_trial_not_used')),
      field('admin_user_total_paid_label', `${user.revenue.toFixed(2)} ${stats.currency}`),
      field('admin_user_referral_revenue_label', `${invitees.reduce((total, item) => total + item.revenue, 0).toFixed(2)} ${stats.currency}`),
      field('admin_user_invited_friends_label', user.id === current.id ? referral.invited : invitees.length),
      field('admin_user_ref_purchased_label', user.id === current.id ? referral.paid : invitees.filter((item) => item.revenue > 0).length),
      ...(links.length ? ['', ui.t('admin_user_links_section_title'), ...links] : []),
    ].join('\n'), separateRows(controls, widths));
  }

  private originBack(message: ChatMessage, origin: CardOrigin) {
    const { ui } = this;
    const { page, back } = origin;
    return (page !== undefined
      ? origin.banned
        ? ui.button('user_card_back_to_banned_list_button', () => this.bannedList(message, page))
        : ui.button('admin_user_back_to_list_button', () => this.list(message, page))
      : back ? ui.button('back_to_main_menu_button', () => back(message)) : this.back(message));
  }

  private backToCard(message: ChatMessage, user: DemoAdminUser, origin: CardOrigin) {
    return this.ui.button('admin_user_back_to_card_button', () => this.card(message, user, origin));
  }

  private addDays(message: ChatMessage, user: DemoAdminUser, origin: CardOrigin) {
    const { ui } = this;
    ui.view(message, ui.t('admin_user_add_subscription_tariff_prompt', { user_id: user.minishop }), [
      ...ui.host.data.tariffs.filter((tariff) => !tariff.isTraffic).map((tariff): Button => ({
        label: tariff.names[ui.host.language()], activate: () => ui.prompt(message, ui.t('admin_user_add_subscription_prompt_with_tariff', {
          tariff: escape(tariff.names[ui.host.language()]), user_id: user.minishop,
        }), (input) => {
          const days = Number(input);
          if (!Number.isInteger(days) || days < 1 || days > 3650) return void ui.answer('admin_user_invalid_days');
          const end = new Date(Math.max(Date.now(), Date.parse(user.expiry) || 0) + days * 86_400_000);
          user.expiry = end.toISOString();
          user.days = Math.max(user.days, 0) + days;
          user.tariff = tariff.key;
          user.trial = false;
          user.trialUsed = true;
          user.panelStatus = 'ACTIVE';
          user.trafficLimit = tariff.limit;
          ui.clearInput();
          ui.answer('admin_user_subscription_added_success', { days, user_id: user.minishop });
          this.card(ui.host.append(''), user, origin);
        }, [ui.button('cancel_button', () => this.addDays(message, user, origin))]),
      })),
      this.backToCard(message, user, origin),
    ]);
  }

  private changeTariff(message: ChatMessage, user: DemoAdminUser, origin: CardOrigin) {
    const { ui } = this;
    if (user.days <= 0) return ui.alert('admin_user_tariff_no_subscription');
    ui.confirmation(message, [
      `<b>${ui.t('admin_user_tariff_change_title')}</b>`, '', ui.t('admin_user_tariff_change_hint'),
      ui.t('admin_user_tariff_current', { tariff: escape(this.tariffName(user.tariff)) }),
    ].join('\n'), [
      ...ui.host.data.tariffs.map((tariff): Button => ({
        label: tariff.key === user.tariff
          ? `${tariff.names[ui.host.language()]} · ${ui.t('admin_user_tariff_current_badge')}` : tariff.names[ui.host.language()],
        activate: () => {
          user.tariff = tariff.key;
          user.trafficLimit = tariff.limit;
          ui.alert('admin_user_tariff_change_success', { tariff: escape(tariff.names[ui.host.language()]) });
          this.card(message, user, origin);
        },
      })),
      this.backToCard(message, user, origin),
    ]);
  }

  private directMessage(message: ChatMessage, user: DemoAdminUser, origin: CardOrigin) {
    const { ui } = this;
    ui.prompt(message, ui.t('admin_user_send_message_prompt', { user_id: user.minishop }), (input) => {
      if (input.length > 4000) return void ui.answer('admin_user_message_too_long');
      ui.clearInput();
      ui.answer(user.telegram ? 'admin_user_message_sent_success' : 'admin_user_message_sent_error', { user_id: user.minishop });
    }, [ui.button('cancel_button', () => this.card(message, user, origin))]);
  }

  private invitees(message: ChatMessage, user: DemoAdminUser, page: number, origin: CardOrigin) {
    const { ui } = this;
    const all = this.records.filter((record) => record.referredBy === user.id);
    const totalPages = Math.max(1, Math.ceil(all.length / 10));
    const selected = all.slice(page * 10, (page + 1) * 10);
    const text = ui.t('admin_user_invitees_message_title', {
      user: escape(user.name), total: all.length, current: page + 1, total_pages: totalPages,
    });
    ui.view(message, `${text}\n\n${selected.length ? selected.map((record) =>
      `${escape(record.name)} · <code>${record.minishop}</code>`).join('\n') : ui.t('admin_user_invitees_empty')}`, [
      ...selected.map((record): Button => ({ label: record.name, activate: () => this.card(message, record, { back: (target) => this.invitees(target, user, page, origin) }) })),
      ...ui.pager(page, totalPages, (next) => this.invitees(message, user, next, origin)),
      this.backToCard(message, user, origin),
      this.back(message),
    ]);
  }

  private premium(message: ChatMessage, user: DemoAdminUser, origin: CardOrigin) {
    const { ui } = this;
    if (user.days <= 0) return ui.alert('admin_premium_override_no_subscription');
    const state = user.premium === 'unlimited' ? ui.t('admin_premium_override_state_unlimited')
      : user.premium ? ui.t('admin_premium_override_state_bonus', { gb: user.premium }) : ui.t('admin_premium_override_state_none');
    const apply = (value?: DemoAdminUser['premium']) => {
      user.premium = value;
      ui.alert('admin_premium_override_saved');
      this.card(message, user, origin);
    };
    ui.view(message, [
      `<b>${ui.t('admin_premium_override_title')}</b>`, '', ui.t('admin_premium_override_hint'), '',
      ui.t('admin_premium_override_current', { current: state }),
    ].join('\n'), [
      ui.button('admin_premium_override_btn_unlimited', () => apply('unlimited')),
      ui.button('admin_premium_override_btn_bonus', () => {
        ui.prompt(message, ui.t('admin_premium_override_bonus_prompt', { user_id: user.minishop }), (input) => {
          const gb = Number(input.replace(',', '.'));
          if (!Number.isFinite(gb) || gb < 0) return void ui.answer('admin_premium_override_invalid_gb');
          user.premium = gb;
          ui.answer('admin_premium_override_bonus_set', { gb: gb.toFixed(2), user_id: user.minishop });
          this.card(ui.host.append(''), user, origin);
        }, [ui.button('cancel_button', () => this.premium(message, user, origin))]);
      }),
      ui.button('admin_premium_override_btn_clear', () => apply()),
      this.backToCard(message, user, origin),
    ]);
  }

  private hwid(message: ChatMessage, user: DemoAdminUser, origin: CardOrigin) {
    const { ui } = this;
    if (user.days <= 0) return ui.alert('admin_hwid_limit_no_subscription');
    const current = (value?: number) => value === undefined ? ui.t('admin_hwid_limit_state_default')
      : value === 0 ? ui.t('admin_hwid_limit_state_unlimited') : ui.t('admin_hwid_limit_state_count', { count: value });
    const apply = (limit?: number) => {
      user.limit = limit;
      ui.alert('admin_hwid_limit_saved');
      this.card(message, user, origin);
    };
    ui.view(message, [
      `<b>${ui.t('admin_hwid_limit_title')}</b>`, '', ui.t('admin_hwid_limit_hint'), '',
      ui.t('admin_hwid_limit_current', { current: current(user.limit) }),
    ].join('\n'), [
      ui.button('admin_hwid_limit_btn_set_number', () => {
        ui.prompt(message, ui.t('admin_hwid_limit_prompt', { user_id: user.minishop }), (input) => {
          const limit = Number(input);
          if (!Number.isInteger(limit) || limit < 0 || limit > 1e6) return void ui.answer('admin_hwid_limit_invalid');
          ui.answer('admin_hwid_limit_set', { user_id: user.minishop, current: current(limit) });
          user.limit = limit;
          this.card(ui.host.append(''), user, origin);
        }, [ui.button('cancel_button', () => this.hwid(message, user, origin))]);
      }),
      ui.button('admin_hwid_limit_btn_unlimited', () => apply(0)),
      ui.button('admin_hwid_limit_btn_reset', () => apply()),
      this.backToCard(message, user, origin),
    ]);
  }

  private traffic(message: ChatMessage, user: DemoAdminUser, origin: CardOrigin) {
    const { ui } = this;
    const prompt = (premium: boolean) => ui.prompt(message, ui.t(
      premium ? 'admin_traffic_grant_prompt_premium' : 'admin_traffic_grant_prompt_regular', { user_id: user.minishop }), (input) => {
      const gb = Number(input.replace(',', '.'));
      if (!Number.isFinite(gb) || gb <= 0 || gb > 1e6) return void ui.answer('admin_traffic_grant_invalid_gb');
      ui.clearInput();
      const tariff = ui.host.data.tariffs.find((item) => item.key === user.tariff);
      if (user.days <= 0 || (premium && !tariff?.premiumLimit)) return void ui.answer('admin_traffic_grant_failed');
      if (premium) user.premiumTraffic += gb;
      else user.traffic += gb;
      ui.answer(premium ? 'admin_traffic_grant_premium_done' : 'admin_traffic_grant_regular_done', {
        gb, user: escape(user.name), user_id: user.minishop,
      });
      this.card(ui.host.append(''), user, origin);
    }, [ui.button('cancel_button', () => this.traffic(message, user, origin))]);
    ui.view(message, `<b>${ui.t('admin_traffic_grant_title')}</b>\n\n${ui.t('admin_traffic_grant_hint')}`, [
      ui.button('admin_traffic_grant_btn_regular', () => prompt(false)),
      ui.button('admin_traffic_grant_btn_premium', () => prompt(true)),
      this.backToCard(message, user, origin),
    ]);
  }

  private deleteUser(user: DemoAdminUser, origin: CardOrigin) {
    const { ui } = this;
    const prompt = ui.host.append('');
    ui.prompt(prompt, ui.t('admin_user_delete_confirmation_prompt', { user_id: `<code>${user.minishop}</code>` }), (input) => {
      ui.clearInput();
      if (['cancel', '/cancel'].includes(input.toLowerCase())) {
        ui.answer('admin_user_delete_cancelled');
        this.card(ui.host.append(''), user, origin);
        return;
      }
      if (input !== String(user.id) && input.toLowerCase() !== user.minishop) return void ui.answer('admin_user_delete_mismatch');
      this.records = this.records.filter((item) => item !== user);
      const done = ui.answer('admin_user_delete_success', { user_id: user.minishop });
      done.rows = [this.originBack(done, origin)];
    }, [ui.button('cancel_button', () => this.card(prompt, user, origin))]);
  }
}
