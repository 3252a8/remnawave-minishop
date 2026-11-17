import { AdminDemo, adminMessages, type AdminMessages } from './botDemoAdmin';
import type { BotDemoData, DemoPlan, DemoTariff } from './botDemoData';
import { DEMO_TRIAL_CAPTCHA_ANSWER } from '../../../frontend/src/lib/webapp/previewMock/devMock';
import type { PaymentHistoryItem } from '../../../frontend/src/lib/webapp/paymentHistory';

const messageKeys = [
  'autorenew_enable_button', 'autorenew_disable_button', 'autorenew_confirm_enable', 'autorenew_confirm_disable',
  'subscription_autorenew_updated', 'yes_button', 'no_button', 'telegram_confirmation_expired',
  'payment_methods_manage_button', 'payment_methods_title', 'payment_method_bind_button',
  'payment_method_card_title', 'payment_method_added_at', 'payment_method_last_tx',
  'payment_method_delete_button', 'payment_method_delete_confirm', 'payment_method_deleted_success',
  'payment_method_none', 'payment_method_tx_history_title', 'payment_method_no_history',
  'payment_method_bound_success',
  'menu_app_sections_button', 'menu_account_settings_button', 'menu_account_security_button',
  'menu_account_notifications_button', 'menu_account_gifts_button', 'menu_account_partner_button',
  'menu_support_tickets_button', 'menu_admin_panel_button', 'bot_payment_history_item',
  'bot_payment_history_resume', 'bot_payment_history_page', 'wa_payment_history_empty',
  'wa_payment_history_state_awaiting_payment', 'wa_payment_history_state_processing',
  'wa_payment_history_state_crediting', 'wa_payment_history_state_review', 'wa_payment_history_state_completed',
  'wa_payment_history_state_refunded', 'wa_payment_history_state_failed', 'prev_page_button', 'next_page_button',
  'welcome', 'main_menu_greeting', 'bot_interface_menu_title', 'bot_interface_menu_webapp_hint',
  'bot_command_start_description', 'bot_command_tg_description', 'menu_activate_trial_button',
  'menu_personal_account_button', 'menu_bot_interface_button', 'menu_subscribe_inline',
  'menu_my_subscription_inline', 'menu_payment_history_button', 'menu_referral_inline',
  'menu_apply_promo_button', 'menu_language_settings_inline', 'menu_server_status_button',
  'menu_support_button', 'menu_info_button', 'info_links_message', 'privacy_policy_button',
  'user_agreement_button', 'back_to_main_menu_button', 'choose_language', 'language_set_alert',
  'subscription_not_active', 'my_subscription_details', 'traffic_period_month', 'traffic_period_no_reset',
  'traffic_period_unknown', 'traffic_period_week', 'traffic_unlimited', 'traffic_used_with_period',
  'connect_button', 'install_guide_share_button', 'install_guide_share_link_line', 'devices_button',
  'my_devices_details', 'no_devices_details_found_message', 'device_details', 'disconnect_device_button',
  'device_disconnected', 'rename_device_menu_button', 'rename_device_pick_prompt',
  'rename_device_pick_button', 'rename_device_prompt', 'rename_device_invalid', 'rename_device_saved',
  'rename_device_reset_button', 'rename_device_reset_done', 'select_hwid_device_package',
  'buy_hwid_devices_button', 'buy_hwid_devices_menu_button', 'choose_payment_method_hwid_devices',
  'device_topup_unavailable_menu_button', 'device_topup_unavailable_trial_subscription',
  'tariff_change_button', 'wa_tariffs_choose', 'wa_tariff_change_recalc_days', 'wa_tariff_change_pay_diff',
  'wa_tariff_change_confirm_title', 'wa_tariff_change_confirm_target', 'wa_tariff_change_confirm_recalc',
  'wa_tariff_change_confirm_action', 'payment_successful_tariff_upgrade_full',
  'wa_tariff_change_confirm_payment', 'wa_tariff_change_applied', 'tariff_change_confirm_button',
  'tariff_change_confirm_pay_button', 'select_subscription_period', 'wa_checkout_price_from',
  'subscribe_for_months_button', 'subscribe_for_period_button', 'wa_sub_term_month_one', 'wa_sub_term_month_few', 'wa_sub_term_month_many',
  'choose_payment_method', 'cancel_button', 'pay_button', 'payment_description_subscription_days',
  'payment_description_hwid_devices', 'payment_invoice_sent_message', 'payment_link_message',
  'payment_successful_full', 'payment_successful_hwid_devices_full', 'promo_code_prompt',
  'promo_code_not_found', 'promo_code_already_used_by_user', 'promo_code_applied_success_full',
  'promo_code_requires_checkout', 'open_mini_app', 'referral_program_info_new',
  'referral_webapp_link_line', 'referral_bonus_per_period', 'referral_share_message_button',
  'referral_friend_message', 'referral_friend_message_with_webapp', 'trial_activated_details_message',
  'trial_already_had_subscription_or_trial', 'wa_trial_activated',
  'trial_confirm_activate_button',
  'trial_captcha_bot_prompt', 'trial_captcha_bot_cancel', 'trial_captcha_bot_success',
  'trial_captcha_bot_continue', 'trial_captcha_invalid', 'trial_captcha_expired',
  'payment_hwid_renewal_toggle_on', 'payment_hwid_renewal_toggle_off',
  'select_traffic_package', 'buy_traffic_package_button', 'choose_payment_method_traffic',
  'payment_description_traffic', 'payment_invoice_sent_message_traffic', 'payment_link_message_traffic',
  'payment_successful_traffic_full', 'traffic_topup_button', 'traffic_topup_regular_package_button',
  'traffic_topup_premium_package_button', 'traffic_topup_carryover_note',
  'referral_bonus_days_range', 'referral_bonus_tariff_range',
  'wa_sub_term_year_one', 'wa_tariff_change_convert_gb', 'wa_tariff_change_buy_package',
  'wa_tariff_change_confirm_convert', 'my_traffic_details', 'traffic_no_expiry',
  'subscription_premium_details', 'premium_usage_of', 'premium_status_limited', 'premium_status_active',
  'premium_servers_generic',
] as const;

type MessageKey = (typeof messageKeys)[number];
export type Messages = Record<MessageKey, string> & AdminMessages;
export type Language = 'ru' | 'en';
export type BotRole = 'user' | 'admin' | 'owner';
export type Menu = 'main' | 'bot' | 'admin';
export type Format = Record<string, string | number>;
export type Activate = () => Popup | void;

export type Popup =
  | { kind: 'app'; title: string; route: string; start?: string }
  | { kind: 'browser'; title: string; address: string; body?: string; route?: string; confirm?: Activate; total?: string }
  | { kind: 'support'; title: string; address: string }
  | { kind: 'profile'; title: string; address: string; username?: string }
  | { kind: 'download'; filename: string; content: string }
  | { kind: 'stars'; title: string; total: number; confirm?: Activate };

export type Button = { label: string; activate: Activate; external?: boolean; pay?: boolean };
export type ButtonRow = Button | Button[];
export type ChatMessage = {
  text: string;
  outgoing?: boolean;
  rows?: ButtonRow[];
  invoice?: boolean;
  image?: string;
};

export function chatMessages(locale: Record<string, string>): Messages {
  const user = Object.fromEntries(messageKeys.map((key) => {
    if (!locale[key]) throw new Error(`Missing Telegram demo locale key: ${key}`);
    return [key, locale[key]];
  })) as Record<MessageKey, string>;
  return { ...user, ...adminMessages(locale) };
}

export const scenarios = {
  new: { app: true, active: false, description: 'Новый пользователь. Пробный период открывается в Mini App.' },
  active: { app: true, active: true, description: 'Действующая подписка и устройства из веб-демо.' },
  'without-app': { app: false, active: true, description: 'Действующая подписка. Личный кабинет открывает подписку в чате.' },
  'auto-renew': { app: false, active: true, description: 'Действующая подписка с автопродлением из веб-демо.' },
  'new-without-app': { app: false, active: false, description: 'Новый пользователь. Бот активирует пробный период прямо в чате.' },
  'trial-captcha': { app: false, active: false, description: 'Проверка перед активацией пробного периода в чате.' },
  stars: { app: true, active: true, description: 'Тариф и способы оплаты из веб-сценария с Telegram Stars.' },
  'account-tools': { app: true, active: true, description: 'Разделы Mini App с партнёрским кабинетом и встроенным статусом.' },
} as const;

export type Scenario = keyof typeof scenarios;

export function parseScenario(value: string | null): Scenario {
  return value && Object.hasOwn(scenarios, value) ? value as Scenario : 'new';
}

type Order = {
  description: string;
  months: number;
  price: number;
  currency: string;
  stars?: number;
  back: () => void;
  receiptBack?: (message: ChatMessage) => void;
  complete: (renewDevices: boolean) => string;
  completed?: boolean;
  devices?: boolean;
  gb?: number;
  mode?: string;
  methods?: string[];
  renewal?: { count: number; price: number; stars: number; selected: boolean };
};

export function escape(value: string) {
  return value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
}

export class BotDemoConversation {
  messages: ChatMessage[] = [];
  language: Language;
  role: BotRole;
  menu: Menu = 'main';
  scenario: Scenario;
  subscribed = false;
  private autoRenewEnabled = false;
  private savedCardAvailable = false;
  completedPayments: PaymentHistoryItem[] = [];
  notice = '';
  private trial = false;
  private trialProofUntil = 0;
  private trialUsed = false;
  private promoUsed = new Set<string>();
  private tariff: DemoTariff;
  private limit = 0;
  private extraDevices = 0;
  private days = 0;
  private expiryLabel = '';
  private trafficLimit = '';
  private trafficUsed = '';
  private premiumLimit = 0;
  private premiumUsed = 0;
  private premiumBalance = 0;
  private devices: (BotDemoData['current']['devices'][number] & { name?: string })[] = [];
  private inputAction?: (value: string) => void;
  private activeOrder?: Order;
  private readonly admin: AdminDemo;

  constructor(readonly locales: Record<Language, Messages>, readonly data: BotDemoData, language: Language, scenario: Scenario, role: BotRole, firstMenu: Menu, public emptyAdmin: boolean, private readonly captchaImage: string) {
    this.language = language;
    this.scenario = scenario;
    this.role = role;
    this.tariff = this.tariffs[0];
    this.admin = new AdminDemo({
      data,
      phrases: () => this.locales[this.language],
      language: () => this.language,
      hasMiniApp: () => this.settings.app,
      mainMenu: (message) => this.showMenu(message, 'main'),
      append: (text, rows) => this.append(text, rows),
      edit: (message, text, rows) => this.edit(message, text, rows),
      setInput: (next) => { this.inputAction = next; },
      isInput: (next) => this.inputAction === next,
      notify: (text) => { this.notice = text; },
    });
    this.reset(scenario);
    this.send(firstMenu === 'admin' ? '/admin' : firstMenu === 'bot' ? '/tg' : '/start');
  }

  get settings() {
    return scenarios[this.scenario];
  }

  private get tariffs() {
    return this.scenario === 'stars' ? this.data.starsTariffs : this.data.tariffs;
  }

  private get methods() {
    return this.scenario === 'stars' ? this.data.starsMethods : this.data.methods;
  }

  get canAdmin() {
    return this.role !== 'user';
  }

  get canAttach() {
    return this.canAdmin && this.admin.acceptsAttachment;
  }

  sendAttachment(filename: string, caption: string) {
    if (!this.canAttach) return;
    this.messages.push({ text: [`📎 ${filename}`, caption].filter(Boolean).join('\n'), outgoing: true });
    this.admin.broadcastAttachment(filename, caption);
  }

  get webMock() {
    if (this.scenario === 'auto-renew' || this.scenario === 'trial-captcha') return this.scenario;
    if (this.scenario === 'stars') return 'checkout-addons';
    if (this.scenario === 'account-tools') return 'partner-referral-enabled';
    return this.subscribed ? 'tariffs' : this.trialUsed ? 'no-subscription' : 'trial';
  }

  t = (key: MessageKey, values: Format = {}) =>
    this.locales[this.language][key].replace(/\{([a-z_0-9]+)\}/gi, (match, name) =>
      Object.hasOwn(values, name) ? String(values[name]) : match);

  private get name() {
    return this.data.current.name;
  }

  private get expiry() {
    if (this.expiryLabel) return this.expiryLabel;
    const date = new Date();
    date.setDate(date.getDate() + this.days);
    return date.toISOString().slice(0, 10);
  }

  reset(scenario = this.scenario) {
    this.scenario = scenario;
    this.trialProofUntil = 0;
    this.autoRenewEnabled = this.autoRenewDemo.enabled;
    this.savedCardAvailable = this.autoRenewDemo.enabled;
    this.clearConversation();
    const { current } = this.data;
    this.subscribed = this.settings.active;
    this.completedPayments = [];
    this.trial = false;
    this.trialUsed = this.settings.active;
    this.promoUsed.clear();
    this.tariff = this.tariffs.find((item) => item.key === current.tariff) ?? this.tariffs[0];
    this.days = this.subscribed ? current.days : 0;
    this.expiryLabel = this.subscribed ? current.expiry : '';
    this.limit = this.subscribed ? current.deviceLimit : 0;
    this.extraDevices = this.subscribed ? current.deviceExtra : 0;
    this.trafficUsed = this.subscribed ? current.used : '0 GB';
    this.trafficLimit = scenario === 'stars' ? `${this.tariff.limit} GB` : current.limit;
    this.premiumLimit = scenario === 'stars' ? this.tariff.premiumLimit : this.subscribed ? current.premiumLimit : 0;
    this.premiumUsed = this.subscribed ? current.premiumUsed : 0;
    this.premiumBalance = this.subscribed ? current.premiumBalance : 0;
    this.devices = this.subscribed ? current.devices.map((device) => ({ ...device })) : [];
    this.resetAdmin();
  }

  clearConversation() {
    this.messages = [];
    this.menu = 'main';
    this.admin.clearInput();
    this.notice = '';
  }

  resetAdmin() {
    this.admin.reset(this.emptyAdmin);
  }

  send(input: string) {
    this.notice = '';
    this.messages.push({ text: input, outgoing: true });
    if (this.canAdmin && this.admin.handleCommand(input)) {
      this.menu = 'admin';
      return;
    }
    switch (input) {
      case '/start':
        this.admin.clearInput();
        this.inputAction = undefined;
        this.append(this.t('welcome', { user_name: escape(this.name) }));
        this.showMenu(this.append(''), 'main');
        break;
      case '/tg':
        this.admin.clearInput();
        this.inputAction = undefined;
        this.showMenu(this.append(''), 'bot');
        break;
      case '/start trial': {
        this.showMenu(this.append(''), 'main');
        const prompt = this.append('');
        if (this.settings.app) {
          this.edit(prompt, this.t('menu_activate_trial_button'), [this.app('open_mini_app', '/trial')]);
        } else {
          this.confirmation(prompt, this.t('menu_activate_trial_button'), [
            this.button('trial_confirm_activate_button', () => this.activateTrial(prompt)),
            this.button('cancel_button', () => this.showMenu(prompt, 'main')),
          ]);
        }
        break;
      }
      case '/language':
        this.languages(this.append(''), 'main');
        break;
      case '/referral':
        this.referral(this.append(''), 'main');
        break;
      default:
        this.inputAction?.(input);
    }
  }

  private append(text: string, rows?: ButtonRow[]): ChatMessage {
    const message = { text, rows };
    this.messages.push(message);
    return message;
  }

  private edit(message: ChatMessage, text: string, rows?: ButtonRow[]) {
    this.admin.clearInput();
    this.activeOrder = undefined;
    Object.assign(message, { text, rows });
  }

  private confirmation(message: ChatMessage, text: string, rows: ButtonRow[]) {
    const pending = () => {};
    const guard = (button: Button): Button => ({
      ...button,
      activate: () => {
        if (this.inputAction !== pending) {
          this.notice = this.t('telegram_confirmation_expired');
          return;
        }
        this.inputAction = undefined;
        return button.activate();
      },
    });
    this.edit(message, text, rows.map((row) => Array.isArray(row) ? row.map(guard) : guard(row)));
    this.inputAction = pending;
  }

  private button(label: MessageKey, activate: Activate, values?: Format): Button {
    return { label: this.t(label, values), activate };
  }

  private back(activate: Activate) {
    return this.button('back_to_main_menu_button', activate);
  }

  private app(label: MessageKey, route: string, start?: string): Button {
    const title = this.t(label);
    return { label: title, external: true, activate: () => ({ kind: 'app', title, route, start }) };
  }

  private link(label: MessageKey, target: Popup): Button {
    return { label: this.t(label), external: true, activate: () => target };
  }

  private showMenu(message: ChatMessage, menu: Exclude<Menu, 'admin'>) {
    this.menu = menu;
    this.inputAction = undefined;
    const rows: ButtonRow[] = [];
    if (!this.trialUsed && !this.subscribed) {
      rows.push(this.settings.app ? this.app('menu_activate_trial_button', '/trial', 'trial')
        : this.button('menu_activate_trial_button', () => this.activateTrial(message, menu)));
    }
    if (this.settings.app) rows.push(this.app('menu_personal_account_button', '/home'));
    if (menu === 'main') {
      if (!this.settings.app) rows.push(this.button('menu_my_subscription_inline', () => this.subscription(message, 'main')));
      rows.push(this.button('menu_bot_interface_button', () => this.showMenu(message, 'bot')));
    } else {
      rows.push([
        this.button('menu_subscribe_inline', () => this.catalog(message, 'bot')),
        this.button('menu_my_subscription_inline', () => this.subscription(message, 'bot')),
      ]);
      rows.push(this.settings.app ? this.app('menu_payment_history_button', '/settings/payments')
        : this.button('menu_payment_history_button', () => this.paymentHistory(message, 0)));
      rows.push(
        this.button('menu_referral_inline', () => this.referral(message, 'bot')),
        [
          this.button('menu_apply_promo_button', () => this.promo(message)),
          this.button('menu_language_settings_inline', () => this.languages(message, 'bot')),
        ],
      );
      if (this.settings.app) rows.push(this.button('menu_app_sections_button', () => this.appSections(message)));
    }
    const { current } = this.data;
    if (this.scenario === 'account-tools') rows.push(this.app('menu_server_status_button', '/status'));
    else if (current.statusUrl) rows.push(this.link('menu_server_status_button', {
      kind: 'browser', title: this.t('menu_server_status_button'), address: current.statusUrl, route: '/status',
    }));
    if (current.supportTickets && this.settings.app) rows.push(this.app('menu_support_tickets_button', '/support'));
    if (current.supportUrl) rows.push(this.link('menu_support_button', {
        kind: 'support', title: this.language === 'ru' ? 'Поддержка Minishop' : 'Minishop Support',
        address: current.supportUrl,
    }));
    if (current.privacyUrl || current.agreementUrl) rows.push(this.button('menu_info_button', () => this.information(message, menu)));
    if (menu === 'bot') rows.push(this.back(() => this.showMenu(message, 'main')));
    if (menu === 'main' && this.canAdmin) rows.push(this.button('menu_admin_panel_button', () => {
      this.menu = 'admin';
      this.admin.panel(message);
    }));
    const text = menu === 'main' ? this.t('main_menu_greeting', { user_name: escape(this.name) })
      : [this.t('bot_interface_menu_title'), this.settings.app ? this.t('bot_interface_menu_webapp_hint') : ''].filter(Boolean).join('\n\n');
    this.edit(message, text, rows);
  }

  private appSections(message: ChatMessage) {
    const { current } = this.data;
    this.edit(message, this.t('menu_app_sections_button'), [
      this.app('menu_account_settings_button', '/settings'),
      this.app('menu_account_security_button', '/settings/security'),
      this.app('menu_account_notifications_button', '/settings/notifications'),
      ...(current.giftsEnabled ? [this.app('menu_account_gifts_button', '/invite/gifts')] : []),
      ...(current.partnerEnabled || this.scenario === 'account-tools' ? [this.app('menu_account_partner_button', '/partner')] : []),
      this.back(() => this.showMenu(message, 'bot')),
    ]);
  }

  private paymentHistory(message: ChatMessage, page: number) {
    const previous = this.settings.active ? this.data.payments.filter((row) => row.userId === this.data.current.id) : [];
    const current = this.completedPayments.map((row) => ({
      id: row.payment_id, amount: row.amount, currency: row.currency ?? '', provider: row.provider ?? '',
      status: row.status ?? '', date: row.created_at ?? '', checkoutUrl: '', checkoutExpires: '',
    }));
    const history = [...current, ...previous].filter((row) =>
      !/^(pending(_|$)|active$|created$|new$|open$|waiting$)/.test(row.status)
      || (row.checkoutUrl && Date.parse(row.checkoutExpires) > Date.now()),
    );
    const pageSize = 5;
    const pages = Math.max(1, Math.ceil(history.length / pageSize));
    const visible = history.slice(page * pageSize, (page + 1) * pageSize);
    const lines = [`<b>${this.t('menu_payment_history_button')}</b>`];
    const rows: ButtonRow[] = [];
    for (const row of visible) {
      let state: MessageKey = 'wa_payment_history_state_failed';
      if (row.status === 'succeeded') state = 'wa_payment_history_state_completed';
      else if (['refunded', 'reversed'].includes(row.status)) state = 'wa_payment_history_state_refunded';
      else if (row.status === 'succeeded_pending_finalization') state = 'wa_payment_history_state_crediting';
      else if (row.status === 'succeeded_pending_review') state = 'wa_payment_history_state_review';
      else if (row.checkoutUrl && Date.parse(row.checkoutExpires) > Date.now()) state = 'wa_payment_history_state_awaiting_payment';
      else if (['processing', 'process', 'paying', 'authorized', 'awaitingauthentication', 'waiting_for_capture', 'underpaid', 'refunding'].includes(row.status))
        state = 'wa_payment_history_state_processing';
      lines.push(this.t('bot_payment_history_item', {
        number: row.id, amount: row.amount, currency: escape(row.currency), provider: escape(
          [...this.methods, ...this.data.starsMethods].find((item) => item.id === row.provider)?.label
            ?? (row.provider === 'telegram_stars' ? 'Telegram Stars' : row.provider || '—'),
        ),
        date: row.date.slice(0, 16).replace('T', ' ') || '—', status: this.t(state),
      }));
      if (state === 'wa_payment_history_state_awaiting_payment') {
        const title = this.t('bot_payment_history_resume', { number: row.id });
        rows.push({ label: title, external: true, activate: () => ({ kind: 'browser', title, address: row.checkoutUrl }) });
      }
    }
    if (!visible.length) lines.push(this.t('wa_payment_history_empty'));
    if (pages > 1) {
      lines.push(this.t('bot_payment_history_page', { page: page + 1, pages }));
      rows.push([
        ...(page ? [this.button('prev_page_button', () => this.paymentHistory(message, page - 1))] : []),
        ...(page + 1 < pages ? [this.button('next_page_button', () => this.paymentHistory(message, page + 1))] : []),
      ]);
    }
    rows.push(this.back(() => this.showMenu(message, 'bot')));
    this.edit(message, lines.join('\n\n'), rows);
  }

  private information(message: ChatMessage, menu: Exclude<Menu, 'admin'>) {
    const privacy = this.language === 'ru'
      ? 'В магазине данные аккаунта используются для управления подпиской, обработки платежей и поддержки. В этом демо используются вымышленные данные.'
      : 'A shop uses account data to manage subscriptions, payments and support. The data in this demo is fictional.';
    const terms = this.language === 'ru'
      ? 'Стоимость и срок подписки указываются перед оплатой. После оплаты бот отправляет подтверждение и инструкцию подключения.'
      : 'The price and subscription period are shown before payment. After payment the bot sends a confirmation and connection instructions.';
    this.edit(message, this.t('info_links_message'), [
      ...(this.data.current.privacyUrl ? [this.link('privacy_policy_button', {
        kind: 'browser', title: this.t('privacy_policy_button'), address: this.data.current.privacyUrl, body: privacy,
      })] : []),
      ...(this.data.current.agreementUrl ? [this.link('user_agreement_button', {
        kind: 'browser', title: this.t('user_agreement_button'), address: this.data.current.agreementUrl, body: terms,
      })] : []),
      this.back(() => this.showMenu(message, menu)),
    ]);
  }

  private languages(message: ChatMessage, menu: Exclude<Menu, 'admin'>) {
    this.edit(message, this.t('choose_language'), [
      ...(['ru', 'en'] as const).map((language): Button => ({
        label: (language === 'ru' ? '🇷🇺 Русский' : '🇬🇧 English') + (language === this.language ? ' ✅' : ''),
        activate: () => {
          this.language = language;
          this.notice = this.t('language_set_alert');
          this.showMenu(message, menu);
        },
      })),
      this.back(() => this.showMenu(message, menu)),
    ]);
  }

  private duration(months: number) {
    const unit = months === 1 ? 'wa_sub_term_month_one'
      : this.language === 'ru' && months >= 2 && months <= 4 ? 'wa_sub_term_month_few'
        : 'wa_sub_term_month_many';
    return `${months} ${this.t(unit)}`;
  }

  private catalog(message: ChatMessage, menu: Exclude<Menu, 'admin'>, back = () => this.showMenu(message, menu), receiptBack?: Order['receiptBack']) {
    if (this.tariffs.length === 1) return this.periods(message, this.tariffs[0], back, receiptBack);
    this.edit(message, this.purchaseDescription(this.t('select_subscription_period')), [
      ...this.tariffs.map((tariff): Button => ({
        label: `${tariff.names[this.language]} ${this.t('wa_checkout_price_from', { price: tariff.periods[0].price })}${tariff.isTraffic ? ` / ${tariff.periods[0].gb} GB` : ''}`,
        activate: () => this.periods(message, tariff, () => this.catalog(message, menu, back, receiptBack), receiptBack),
      })),
      this.back(back),
    ]);
  }

  private purchaseDescription(text: string) {
    return [this.data.current.purchaseDescription, text].filter(Boolean).join('\n\n');
  }

  private periods(message: ChatMessage, tariff: DemoTariff, back: () => void, receiptBack?: Order['receiptBack']) {
    const text = this.tariffs.length > 1 ? `${tariff.names[this.language]}\n${tariff.descriptions[this.language]}`.trim()
      : this.t(tariff.isTraffic ? 'select_traffic_package' : 'select_subscription_period');
    this.edit(message, tariff.isTraffic ? text : this.purchaseDescription(text), [
      ...tariff.periods.map((period) => this.button(tariff.isTraffic ? 'buy_traffic_package_button' : 'subscribe_for_period_button',
        () => this.checkoutPlan(message, tariff, period, () => this.periods(message, tariff, back, receiptBack), receiptBack), {
          period: period.days === 365 ? `1 ${this.t('wa_sub_term_year_one')}` : this.duration(period.months),
          traffic_gb: period.gb, price: period.price, currency_symbol: period.currency,
        })),
      this.back(back),
    ]);
  }

  private checkoutPlan(message: ChatMessage, tariff: DemoTariff, period: DemoPlan, back: () => void, receiptBack?: Order['receiptBack']) {
    const packagePlan = this.data.devicePlans.find((item) => item.count === this.extraDevices);
    const renewal = !tariff.isTraffic && this.data.current.renewDevices && packagePlan
      ? { count: this.extraDevices, price: packagePlan.price, stars: packagePlan.stars ?? 0, selected: true } : undefined;
    this.paymentMethods(message, {
      ...period,
      gb: period.gb || undefined,
      mode: period.kind,
      renewal,
      description: tariff.isTraffic ? this.t('payment_description_traffic', { traffic_gb: period.gb })
        : this.t('payment_description_subscription_days', { days: period.days }),
      back,
      receiptBack,
      complete: (renewDevices) => {
        this.expiryLabel = '';
        this.days = tariff.isTraffic ? 0 : (this.subscribed && !this.trial && !this.tariff.isTraffic ? this.days : 0) + period.days;
        this.tariff = tariff;
        this.extraDevices = renewDevices ? renewal?.count ?? 0 : 0;
        this.limit = tariff.deviceLimit + this.extraDevices;
        this.trafficLimit = `${tariff.isTraffic ? period.gb : tariff.limit} GB`;
        this.premiumLimit = tariff.premiumLimit + this.premiumBalance;
        this.subscribed = this.trialUsed = true;
        this.trial = false;
        return this.t(tariff.isTraffic ? 'payment_successful_traffic_full' : 'payment_successful_full', {
          traffic_gb: period.gb, months: period.months, end_date: this.expiry,
        });
      },
    });
  }

  private paymentMethods(message: ChatMessage, order: Order) {
    if (order.completed) {
      if (order.receiptBack) order.receiptBack(message);
      else order.back();
      return;
    }
    const renewal = order.renewal;
    const renewDevices = Boolean(renewal?.selected);
    const rows: Button[] = [];
    if (renewal) rows.push(this.button(renewal.selected ? 'payment_hwid_renewal_toggle_on' : 'payment_hwid_renewal_toggle_off', () => {
      renewal.selected = !renewal.selected;
      this.paymentMethods(message, order);
    }, { count: renewal.count, price: renewal.price, currency_symbol: order.currency }));
    const amount = order.price + (renewDevices ? renewal?.price ?? 0 : 0);
    for (const method of this.methods) {
      if (order.methods?.length && !order.methods.includes(method.id)) continue;
      if (method.id === 'stars' || method.id === 'telegram_stars') {
        if (!order.stars || (renewDevices && !renewal?.stars)) continue;
        const stars = order.stars + (renewDevices ? renewal?.stars ?? 0 : 0);
        rows.push({ label: method.label, activate: () => this.sendInvoice(message, order, stars, renewDevices) });
      } else if (method.minCurrency !== order.currency || amount >= method.min) {
        rows.push({ label: method.label, activate: () => this.sendPaymentLink(message, order, method, amount, renewDevices) });
      }
    }
    rows.push(this.button('cancel_button', order.back));
    this.edit(message, this.t(order.devices ? 'choose_payment_method_hwid_devices'
      : order.gb ? 'choose_payment_method_traffic' : 'choose_payment_method'), rows);
    this.activeOrder = order;
  }

  private sendInvoice(message: ChatMessage, order: Order, stars: number, renewDevices: boolean) {
    if (!this.canPay(order)) return;
    this.edit(message, this.t(order.gb ? 'payment_invoice_sent_message_traffic' : 'payment_invoice_sent_message', { traffic_gb: order.gb ?? 0 }), [
      this.back(() => this.paymentMethods(message, order)),
    ]);
    const invoice: ChatMessage = { text: `<b>${order.description}</b>\n${order.description}`, invoice: true };
    this.activeOrder = order;
    const popup = (): Popup => ({
      kind: 'stars', title: order.description, total: stars,
      confirm: !this.canPay(order) ? undefined : () => {
        if (!this.canPay(order)) return;
        invoice.rows = [{
          label: this.language === 'ru' ? 'Посмотреть квитанцию' : 'View receipt',
          activate: popup,
        }];
        this.finishPayment(order, renewDevices, 'telegram_stars', stars, 'XTR');
      },
    });
    invoice.rows = [{
      label: `${this.t('pay_button').replace(/^💳\s*/, '')} ⭐ ${stars}`,
      activate: popup,
      pay: true,
    }];
    this.messages.push(invoice);
  }

  private sendPaymentLink(message: ChatMessage, order: Order, method: BotDemoData['methods'][number], amount: number, renewDevices: boolean) {
    if (!this.canPay(order)) return;
    this.edit(message, this.t(order.gb ? 'payment_link_message_traffic' : 'payment_link_message', {
      months: order.months, traffic_gb: order.gb ?? 0,
    }), [
      {
        ...this.button('pay_button', () => ({
          kind: 'browser', title: method.label, address: `checkout.demo.example/${method.id}`,
          body: order.description, total: `${amount} ${order.currency === 'RUB' ? '₽' : order.currency}`,
          confirm: !this.canPay(order) ? undefined : () => {
            this.finishPayment(order, renewDevices, method.id, amount, order.currency);
          },
        })),
        external: true,
      },
      this.back(() => this.paymentMethods(message, order)),
    ]);
    this.activeOrder = order;
  }

  private canPay(order: Order) {
    return this.activeOrder === order && !order.completed;
  }

  private finishPayment(order: Order, renewDevices: boolean, provider: string, amount: number, currency: string) {
    if (!this.canPay(order)) return;
    order.completed = true;
    this.activeOrder = undefined;
    const text = order.complete(renewDevices);
    const date = new Date().toISOString();
    const mode = order.mode || 'subscription';
    const id = this.admin.recordPayment({
      userId: this.data.current.id, userLabel: this.name, provider, amount, currency,
      status: 'succeeded', description: order.description, date,
      checkoutUrl: '', checkoutExpires: '',
      months: order.months, days: 0, gb: order.gb ?? 0,
      mode, tariff: this.tariff.key,
    });
    this.completedPayments.unshift({
      payment_id: id, provider, amount, currency, status: 'succeeded', history_state: 'completed',
      checkout_url: null, description: order.description, created_at: date,
      subscription_duration_months: order.months, sale_mode: mode, purchased_gb: order.gb ?? null,
      subscription_duration_days: null, period_semantics: null, subscription_days_spent: null,
      traffic_regular_gb: null, traffic_premium_gb: null, purchased_hwid_devices: null,
      checkout_discount_amount: null, purchases: [], funding_source: 'external',
    });
    const message = this.append(text + this.installDetails());
    const { receiptBack } = order;
    message.rows = receiptBack
      ? [...this.connectRows(), this.back(() => receiptBack(this.append('')))]
      : this.connectAndBack(message, true);
  }

  private installDetails() {
    const { installUrl } = this.data.current;
    return this.settings.app && installUrl ? this.t('install_guide_share_link_line', { install_share_link: installUrl }) : '';
  }

  private connectRows(): Button[] {
    const { connectUrl, configUrl, installUrl } = this.data.current;
    if (!this.settings.app) {
      return [this.link('connect_button', { kind: 'browser', title: this.t('connect_button'),
        address: connectUrl || configUrl, body: configUrl })];
    }
    return [
      this.app('connect_button', '/install'),
      this.link('install_guide_share_button', { kind: 'browser', title: this.t('install_guide_share_button'), address: installUrl, route: '/install' }),
    ];
  }

  private connectAndBack(message: ChatMessage, preserve = false, menu: Exclude<Menu, 'admin'> = 'main') {
    return [...this.connectRows(), this.back(() => {
      this.showMenu(preserve ? this.append('') : message, menu);
    })];
  }

  private verifyTrial(menu: Exclude<Menu, 'admin'>) {
    const challenge = this.append(this.t('trial_captcha_bot_prompt'));
    const expiresAt = Date.now() + 180_000;
    challenge.image = this.captchaImage;
    const answer = (input: string) => {
      this.admin.clearInput();
      const expired = expiresAt <= Date.now();
      const valid = !expired && input === DEMO_TRIAL_CAPTCHA_ANSWER;
      if (valid) this.trialProofUntil = Date.now() + 600_000;
      const reply = this.append('');
      this.edit(reply, this.t(valid ? 'trial_captcha_bot_success'
        : expired ? 'trial_captcha_expired' : 'trial_captcha_invalid'), [
        this.button('trial_captcha_bot_continue', () => this.activateTrial(reply, menu)),
      ]);
    };
    challenge.rows = [this.button('trial_captcha_bot_cancel', () => {
      const active = this.inputAction === answer;
      this.messages.splice(this.messages.indexOf(challenge), 1);
      if (active) this.showMenu(this.append(''), menu);
    })];
    this.inputAction = answer;
  }

  activateTrial(message?: ChatMessage, menu: Exclude<Menu, 'admin'> = 'main') {
    if (this.trialUsed || this.subscribed) {
      this.notice = this.t('trial_already_had_subscription_or_trial');
      return;
    }
    if (this.scenario === 'trial-captcha' && this.trialProofUntil <= Date.now()) {
      this.verifyTrial(menu);
      return;
    }
    this.subscribed = this.trial = this.trialUsed = true;
    this.days = this.data.current.trialDays;
    this.limit = this.data.current.deviceLimit;
    this.trafficLimit = `${this.data.current.trialGb} GB`;
    if (message) this.edit(message, this.t('trial_activated_details_message', {
      days: this.days, end_date: this.expiry, config_link: this.data.current.configUrl,
    }) + this.installDetails(), this.connectAndBack(message, false, menu));
  }

  private subscription(message: ChatMessage, menu: Exclude<Menu, 'admin'>) {
    const backToSubscription = (target = message) => this.subscription(target, menu);
    if (!this.subscribed) {
      this.edit(message, this.t('subscription_not_active'), [
        this.button('menu_subscribe_inline', () => this.catalog(message, menu, backToSubscription, backToSubscription)),
        this.back(() => this.showMenu(message, menu)),
      ]);
      return;
    }
    const displayGb = (value: number) => `${value.toFixed(2)} GB`;
    const trafficPeriod = this.tariff.isTraffic || this.trial ? this.t('traffic_period_no_reset') : this.t('traffic_period_month');
    const limit = parseFloat(this.trafficLimit);
    const used = parseFloat(this.trafficUsed) || 0;
    const tariffPrefix = !this.tariff.isTraffic && this.tariffs.length > 1 && !this.trial
      ? `🎟 ${escape(this.tariff.names[this.language])}\n${escape(this.tariff.descriptions[this.language])}\n\n` : '';
    const account = this.t(this.tariff.isTraffic ? 'my_traffic_details' : 'my_subscription_details', {
      status: 'Active', end_date: this.tariff.isTraffic ? this.t('traffic_no_expiry') : this.expiry, days_left: this.days,
      config_link: this.data.current.configUrl, traffic_period: trafficPeriod,
      traffic_limit: limit ? displayGb(limit) : this.t('traffic_unlimited'),
      traffic_used: this.t('traffic_used_with_period', { traffic_used: displayGb(used), traffic_period: trafficPeriod }),
      traffic_left: displayGb(Math.max(0, (limit || 0) - used)),
    });
    const current = this.data.current;
    const premium = this.premiumLimit > 0 ? '\n\n' + this.t('subscription_premium_details', {
      status: this.t(current.premiumLimited ? 'premium_status_limited' : 'premium_status_active'),
      usage: this.t('premium_usage_of', { used: displayGb(this.premiumUsed), limit: displayGb(this.premiumLimit) }),
      remaining: displayGb(Math.max(0, this.premiumLimit - this.premiumUsed)), balance: displayGb(this.premiumBalance),
      servers: current.premiumServers.map((server) => `• ${escape(server)}`).join('\n') || this.t('premium_servers_generic'),
      traffic_period: this.scenario === 'stars' || current.premiumStrategy === 'WEEK'
        ? this.t('traffic_period_week') : this.t('traffic_period_unknown'),
    }) : '';
    const tariffActions: Button[] = [];
    if (!this.trial && this.scenario !== 'stars') {
      if (this.data.tariffChanges.length) tariffActions.push(this.button('tariff_change_button', () => this.chooseTariffChange(message, backToSubscription)));
      if (this.data.trafficPlans.length) tariffActions.push(this.button('traffic_topup_button', () => this.trafficPackages(message, backToSubscription)));
    }
    this.edit(message, tariffPrefix + account + premium + this.installDetails(), [
      ...this.connectRows(),
      ...(this.data.current.deviceSection ? [
        this.button('devices_button', () => this.deviceList(message, backToSubscription), { current_devices: this.devices.length, max_devices: this.limit }),
      ] : []),
      ...(this.devicePurchaseAvailable ? [this.devicePurchaseButton(message, backToSubscription)] : []),
      ...(this.autoRenewDemo.available && !this.trial && !this.tariff.isTraffic ? [
        this.button(this.autoRenewEnabled ? 'autorenew_disable_button' : 'autorenew_enable_button',
          () => this.confirmAutoRenew(message, backToSubscription)),
      ] : []),
      ...(this.scenario === 'auto-renew' && !this.trial && !this.tariff.isTraffic ? [
        this.button('payment_methods_manage_button', () => this.savedPaymentMethods(message, backToSubscription)),
      ] : []),
      ...(tariffActions.length ? [tariffActions] : []),
      this.back(() => this.showMenu(message, menu)),
    ]);
  }

  private savedPaymentMethods(message: ChatMessage, back: () => void) {
    const title = this.t('payment_methods_title');
    const bind = this.t('payment_method_bind_button');
    const card = this.t('payment_method_card_title', { network: 'Visa', last4: '4242' });
    const showList = () => this.savedPaymentMethods(message, back);
    const history = this.data.payments.filter((row) => row.userId === this.data.current.id
      && row.provider === 'yookassa' && row.status === 'succeeded');
    const latest = history[0]?.date?.slice(0, 10) || '—';
    const details = () => this.edit(message, [
      card, this.t('payment_method_added_at', { date: '—' }), this.t('payment_method_last_tx', { date: latest }),
    ].join('\n'), [
      this.button('payment_method_tx_history_title', () => this.edit(message, [
        this.t('payment_method_tx_history_title'),
        ...history.map((row) => [row.date.slice(0, 10), escape(row.description), row.amount + ' ' + row.currency].join(' — ')),
        ...(history.length ? [] : [this.t('payment_method_no_history')]),
      ].join('\n\n'), [this.back(details)])),
      this.button('payment_method_delete_button', () => this.confirmation(message, this.t('payment_method_delete_confirm'), [[
        this.button('yes_button', () => {
          this.savedCardAvailable = false;
          this.notice = this.t('payment_method_deleted_success');
          showList();
        }),
        this.button('cancel_button', details),
      ]])),
      this.back(showList),
    ]);
    this.edit(message, this.savedCardAvailable ? title : title + '\n\n' + this.t('payment_method_none'), [
      ...(this.savedCardAvailable ? [{ label: card, activate: details }] : []),
      this.button('payment_method_bind_button', () => this.edit(message, title, [
        { label: bind, external: true, activate: () => ({
          kind: 'browser', title: bind, address: 'checkout.demo.example/yookassa',
          confirm: () => {
            this.savedCardAvailable = true;
            this.notice = this.t('payment_method_bound_success');
            showList();
          },
        }) },
        this.back(showList),
      ])),
      this.back(back),
    ]);
  }

  private get autoRenewDemo() {
    return this.scenario === 'auto-renew' ? this.data.recurring : this.data.current.autoRenew;
  }

  private confirmAutoRenew(message: ChatMessage, back: () => void) {
    const enable = !this.autoRenewEnabled;
    this.confirmation(message, this.t(enable ? 'autorenew_confirm_enable' : 'autorenew_confirm_disable'), [[
      this.button('yes_button', () => {
        this.autoRenewEnabled = enable;
        this.notice = this.t('subscription_autorenew_updated');
        back();
      }),
      this.button('no_button', back),
    ]]);
  }

  private get devicePurchaseAvailable() {
    return this.scenario !== 'stars' && this.data.devicePlans.length > 0;
  }

  private devicePurchaseButton(message: ChatMessage, back: (target?: ChatMessage) => void) {
    return this.trial
      ? this.button('device_topup_unavailable_menu_button', () => {
        this.notice = this.t('device_topup_unavailable_trial_subscription');
      })
      : this.button('buy_hwid_devices_menu_button', () => this.devicePackages(message, back));
  }

  private deviceList(message: ChatMessage, back: (target?: ChatMessage) => void) {
    this.inputAction = undefined;
    const showDevices = (target = message) => this.deviceList(target, back);
    const text = this.devices.length ? this.t('my_devices_details', {
      current_devices: this.devices.length, max_devices: this.limit,
      devices: this.devices.map((device, index) => this.t('device_details', {
        index: index + 1, device_model: escape(device.name ?? device.model), platform: device.platform,
        os_version: escape(device.version), created_at_str: device.since,
        user_agent: escape(device.client), hwid: device.hwid,
      })).join('\n\n'),
    }) : this.t('no_devices_details_found_message', { max_devices: this.limit });
    this.edit(message, text + (this.trial ? `\n\n${this.t('device_topup_unavailable_trial_subscription')}` : ''), [
      ...(this.devicePurchaseAvailable ? [this.devicePurchaseButton(message, showDevices)] : []),
      ...(this.devices.length ? [this.button('rename_device_menu_button', () => this.chooseDeviceName(message, showDevices))] : []),
      ...this.devices.map((device, index) => this.button('disconnect_device_button', () => {
        this.devices = this.devices.filter((other) => other !== device);
        this.notice = this.t('device_disconnected');
        showDevices();
      }, { hwid: device.hwid, index: index + 1 })),
      this.back(() => back(message)),
    ]);
  }

  private chooseDeviceName(message: ChatMessage, back: () => void) {
    this.inputAction = undefined;
    this.edit(message, this.t('rename_device_pick_prompt'), [
      ...this.devices.map((device, index) => this.button('rename_device_pick_button', () => {
        this.edit(message, this.t('rename_device_prompt', { device: escape(device.name ?? device.model), max: 32 }), [
          ...(device.name ? [this.button('rename_device_reset_button', () => {
            delete device.name;
            this.notice = this.t('rename_device_reset_done');
            back();
          })] : []),
          this.button('cancel_button', () => this.chooseDeviceName(message, back)),
        ]);
        this.inputAction = (name) => {
          if ([...name].length > 32) {
            this.append(this.t('rename_device_invalid', { max: 32 }));
            return;
          }
          device.name = name;
          this.inputAction = undefined;
          this.append(this.t('rename_device_saved', { name: escape(name) }));
          back();
        };
      }, { index: index + 1, name: device.name ?? device.model })),
      this.back(back),
    ]);
  }

  private devicePackages(message: ChatMessage, back: (target?: ChatMessage) => void) {
    this.edit(message, this.t('select_hwid_device_package', { date: this.expiry }), [
      ...this.data.devicePlans.map((plan) => this.button('buy_hwid_devices_button', () => this.paymentMethods(message, {
        ...plan, devices: true, mode: plan.kind,
        description: this.t('payment_description_hwid_devices', { count: plan.count }),
        back: () => this.devicePackages(message, back),
        receiptBack: back,
        complete: () => {
          this.limit += plan.count;
          this.extraDevices += plan.count;
          return this.t('payment_successful_hwid_devices_full', { count: plan.count });
        },
      }), { count: plan.count, price: plan.price, currency_symbol: plan.currency })),
      this.back(back),
    ]);
  }

  private trafficPackages(message: ChatMessage, back: (target?: ChatMessage) => void) {
    this.edit(message, `${this.t('select_traffic_package')}\n\n${this.t('traffic_topup_carryover_note')}`, [
      ...this.data.trafficPlans.map((plan) => this.button(
        plan.kind === 'premium_topup' ? 'traffic_topup_premium_package_button' : 'traffic_topup_regular_package_button',
        () => this.paymentMethods(message, {
          ...plan, mode: plan.kind,
          description: this.t('payment_description_traffic', { traffic_gb: plan.gb }),
          back: () => this.trafficPackages(message, back),
          receiptBack: back,
          complete: () => {
            if (plan.kind === 'premium_topup') {
              this.premiumBalance += plan.gb;
              this.premiumLimit += plan.gb;
            } else {
              this.trafficLimit = `${parseFloat(this.trafficLimit) + plan.gb} GB`;
            }
            return this.t('payment_successful_traffic_full', { traffic_gb: plan.gb });
          },
        }), { gb: plan.gb, price: plan.price, currency: plan.currency },
      )),
      this.back(back),
    ]);
  }

  private chooseTariffChange(message: ChatMessage, back: (target?: ChatMessage) => void) {
    type Change = BotDemoData['tariffChanges'][number];
    const names: Record<string, MessageKey> = {
      recalc_days: 'wa_tariff_change_recalc_days', paid_diff: 'wa_tariff_change_pay_diff',
      convert_days_to_gb: 'wa_tariff_change_convert_gb', buy_package: 'wa_tariff_change_buy_package',
    };
    const options = (target: DemoTariff, change: Change) => {
      const title = target.names[this.language];
      this.edit(message, `<b>${escape(title)}</b>\n${escape(target.descriptions[this.language])}`, [
        ...change.actions.filter((action) => names[action.mode]).map((action) => this.button(
          names[action.mode], () => confirm(target, change, action),
          { days: action.days, gb: action.gb, price: `${action.price} ${action.currency}` },
        )),
        this.back(() => this.chooseTariffChange(message, back)),
      ]);
    };
    const confirm = (target: DemoTariff, change: Change, action: Change['actions'][number]) => {
      const { days, gb, price, currency } = action;
      const title = target.names[this.language];
      const apply = () => {
        this.tariff = target;
        if (days || target.isTraffic) {
          this.expiryLabel = '';
          this.days = days;
        }
        this.trafficLimit = `${target.isTraffic ? gb : target.limit} GB`;
        this.premiumLimit = target.premiumLimit + this.premiumBalance;
      };
      const pay = (returnTo: () => void) => this.paymentMethods(message, {
        description: `${this.t('tariff_change_button')} · ${escape(title)}`,
        months: 0, price, currency, gb, mode: action.mode,
        back: returnTo, receiptBack: back, complete: () => {
          apply();
          return gb ? this.t('payment_successful_traffic_full', { traffic_gb: gb })
            : this.t('payment_successful_tariff_upgrade_full', { end_date: this.expiry });
        },
      });
      if (action.mode === 'buy_package') {
        pay(() => options(target, change));
        return;
      }
      this.confirmation(message, [
        this.t('wa_tariff_change_confirm_title'),
        '',
        this.t('wa_tariff_change_confirm_target', { tariff: escape(title) }),
        this.t('wa_tariff_change_confirm_action', { action: price
          ? this.t('wa_tariff_change_confirm_payment', { price: `${price} ${currency}` })
          : gb ? this.t('wa_tariff_change_confirm_convert', { gb }) : this.t('wa_tariff_change_confirm_recalc', { days }) }),
      ].join('\n'), [
        !price ? this.button('tariff_change_confirm_button', () => {
          apply();
          this.notice = this.t('wa_tariff_change_applied');
          back();
        }) : this.button('tariff_change_confirm_pay_button', () => pay(() => confirm(target, change, action))),
        this.back(() => options(target, change)),
      ]);
    };
    const fromTraffic = this.tariff.isTraffic;
    const periodOptions = (target: DemoTariff) => {
      const title = target.names[this.language];
      this.edit(message, `<b>${escape(title)}</b>\n${escape(target.descriptions[this.language])}`, [
        ...target.periods.map((period) => this.button('subscribe_for_months_button',
          () => this.checkoutPlan(message, target, period, () => periodOptions(target), back), {
            months: period.months, price: period.price, currency_symbol: period.currency,
          })),
        this.back(() => this.chooseTariffChange(message, back)),
      ]);
    };
    const targets = fromTraffic ? this.tariffs.filter((target) => !target.isTraffic).map((target) => ({
      label: target.names[this.language], activate: () => periodOptions(target),
    })) : this.data.tariffChanges.flatMap((change) => {
      const target = this.tariffs.find((item) => item.key === change.key && item !== this.tariff);
      return target ? [{ label: target.names[this.language], activate: () => options(target, change) }] : [];
    });
    this.edit(message, this.t('wa_tariffs_choose'), [
      ...targets,
      this.back(back),
    ]);
  }

  private referral(message: ChatMessage, menu: Exclude<Menu, 'admin'>) {
    const referral = this.data.referral;
    const webappLink = this.settings.app ? this.t('referral_webapp_link_line', { webapp_referral_link: referral.webapp }) : '';
    this.edit(message, this.t('referral_program_info_new', {
      invited_count: this.settings.active ? referral.invited : 0, purchased_count: this.settings.active ? referral.paid : 0,
      referral_link: referral.telegram, webapp_link_section: webappLink,
      bonus_details: referral.bonuses.map((bonus) => [`🎁 <b>${escape(bonus.name)}</b>`,
        ...bonus.periods.map((period) => this.t('referral_bonus_per_period', {
          months: period.months, inviter_bonus_days: period.inviter, referee_bonus_days: period.friend,
        }).trim()),
      ].join('\n')).join('\n\n'),
    }), [
      this.button('referral_share_message_button', () => {
        this.append(this.t(this.settings.app ? 'referral_friend_message_with_webapp' : 'referral_friend_message', {
          referral_link: referral.telegram, webapp_referral_link: referral.webapp,
        }));
      }),
      this.back(() => this.showMenu(message, menu)),
    ]);
  }

  private promo(message: ChatMessage) {
    this.edit(message, this.t('promo_code_prompt'), [this.button('cancel_button', () => this.showMenu(message, 'bot'))]);
    this.inputAction = (input) => {
      this.inputAction = undefined;
      const code = input.trim().toUpperCase();
      const promo = this.admin.findPromo(code);
      const available = promo?.enabled && promo.count < promo.limit && (!promo.expires || Date.parse(promo.expires) > Date.now());
      if (code === this.data.checkoutPromoCode || (available && !promo.bonus)) {
        const reply = this.append('');
        this.edit(reply, this.t('promo_code_requires_checkout'), [
          ...(this.settings.app ? [this.app('open_mini_app', '/home', 'promo_' + code)] : []),
          this.back(() => this.showMenu(reply, 'bot')),
        ]);
        return;
      }
      const reply = this.append('');
      if (available && !this.promoUsed.has(code)) {
        if (!this.subscribed) this.limit = this.tariff.deviceLimit;
        this.days = (this.subscribed ? this.days : 0) + promo.bonus;
        this.expiryLabel = '';
        this.subscribed = this.trialUsed = true;
        this.promoUsed.add(code);
        this.admin.recordPromoActivation(promo.id);
        this.edit(reply, this.t('promo_code_applied_success_full', { end_date: this.expiry, config_link: this.data.current.configUrl })
          + this.installDetails(), this.connectAndBack(reply, false, 'bot'));
      } else {
        const key = this.promoUsed.has(code) ? 'promo_code_already_used_by_user' : 'promo_code_not_found';
        this.edit(reply, this.t(key, { code: escape(input) }), [this.back(() => this.showMenu(reply, 'bot'))]);
      }
    };
  }
}
