import { type Button, type ButtonRow, type ChatMessage } from './botDemoConversation';
import { AdminUi, formatDemoDate, type AdminView } from './botDemoAdminUi';
import type { BotDemoData } from './botDemoData';

type Promo = BotDemoData['promos'][number] & {
  activations: { userId: number; date: string }[];
};
type Edit = {
  key: 'bonus' | 'limit' | 'discount' | 'duration' | 'traffic' | 'scope' | 'minMonths' | 'minGb' | 'validity';
  label: string;
  prompt?: string;
  min?: number;
  max?: number;
  integer?: boolean;
};

const editRows: Edit[][] = [
  [{ key: 'bonus', label: 'admin_promo_edit_bonus_days', prompt: 'admin_promo_prompt_bonus_days', min: 0, max: 365, integer: true }],
  [{ key: 'discount', label: 'Discount %', min: 0, max: 100 }],
  [{ key: 'duration', label: 'Duration x', min: 1 }, { key: 'traffic', label: 'Traffic x', min: 1 }],
  [{ key: 'scope', label: 'Scope' }],
  [{ key: 'minMonths', label: 'Min months', min: 0, integer: true }, { key: 'minGb', label: 'Min GB', min: 0 }],
  [{ key: 'limit', label: 'admin_promo_edit_max_activations', prompt: 'admin_promo_prompt_max_activations', min: 1, max: 10000, integer: true }],
  [{ key: 'validity', label: 'admin_promo_edit_validity', prompt: 'admin_promo_prompt_validity_days', min: 0, max: 365, integer: true }],
];
const scopes = ['all', 'hwid', 'subscription', 'traffic', 'traffic_topup'];

export class AdminPromoDemo {
  private records: Promo[] = [];
  private batchSequence = 0;
  private promoId = 0;

  constructor(readonly ui: AdminUi, readonly panel: AdminView) {}

  reset(empty: boolean) {
    this.records = empty ? [] : this.ui.host.data.promos.map((promo) => ({ ...promo, activations: [] }));
    this.promoId = Math.max(0, ...this.records.map(({ id }) => id));
    this.batchSequence = 0;
  }

  find(code: string) {
    return this.records.find((promo) => promo.code === code);
  }

  recordActivation(id: number, userId: number) {
    const promo = this.records.find((item) => item.id === id);
    if (!promo) return;
    promo.activations.unshift({ userId, date: new Date().toISOString() });
    promo.count++;
  }

  private back(message: ChatMessage) {
    return this.ui.button('back_to_admin_panel_button', () => this.panel(message));
  }

  menu(message: ChatMessage) {
    const { ui } = this;
    ui.view(message, ui.t('admin_promo_marketing_section'), [
      [
        ui.button('admin_create_promo_button', () => this.create(message, false)),
        ui.button('admin_create_bulk_promo_button', () => this.create(message, true)),
      ],
      ui.button('admin_promo_management_button', () => this.list(message)),
      this.back(message),
    ]);
  }

  private status(promo: Promo) {
    if (!promo.enabled) return 'admin_promo_status_inactive';
    if (promo.expires && Date.parse(promo.expires) < Date.now()) return 'admin_promo_status_expired';
    if (promo.count >= promo.limit) return 'admin_promo_status_used_up';
    return 'admin_promo_status_active';
  }

  private validity(promo: Promo) {
    if (!promo.expires) return this.ui.t('admin_promo_valid_indefinitely');
    const date = new Date(promo.expires);
    return date.toLocaleDateString(this.ui.host.language() === 'ru' ? 'ru-RU' : 'en-GB');
  }

  private list(message: ChatMessage, page = 0) {
    const { ui } = this;
    const total = Math.max(1, Math.ceil(this.records.length / 10));
    const title = ui.t('admin_promo_management_title') + (total > 1
      ? `\n${ui.t('admin_promo_list_page_info', { current: page + 1, total, count: this.records.length })}` : '');
    const nav: Button[] = [
      ...(page > 0 ? [ui.button('prev_page_button', () => this.list(message, page - 1))] : []),
      ...(page + 1 < total ? [ui.button('next_page_button', () => this.list(message, page + 1))] : []),
    ];
    ui.view(message, this.records.length ? title : ui.t('admin_promo_management_empty'), [
      ...this.records.slice(page * 10, (page + 1) * 10).map((record): Button => ({
        label: `${ui.t(this.status(record)).split(' ')[0]} ${record.code} (${record.count}/${record.limit})`,
        activate: () => this.card(message, record, page),
      })),
      ...(nav.length ? [nav] : []),
      ...(this.records.length ? [ui.button('admin_promo_export_csv_button', () => {
        ui.document('promocodes-demo.csv', this.csv(this.records), ui.t('admin_promo_export_all_caption', { count: this.records.length }));
      })] : []),
      ui.button('back_to_main_menu_button', () => this.menu(message)),
    ]);
  }

  private card(message: ChatMessage, promo: Promo, listPage: number) {
    const { ui } = this;
    const effects = [
      promo.discount ? `🏷 −${promo.discount}%` : '',
      promo.duration ? `⏱ ×${promo.duration}` : '',
      promo.traffic ? `📊 ×${promo.traffic}` : '',
      promo.scope ? `Scope: ${promo.scope}` : '',
      promo.minMonths ? `Min months: ${promo.minMonths}` : '',
      promo.minGb ? `Min GB: ${promo.minGb}` : '',
    ].filter(Boolean);
    ui.view(message, [
      ui.t('admin_promo_card_title', { code: promo.code }), '',
      ui.t('admin_promo_card_bonus_days', { days: promo.bonus }),
      ...effects,
      ui.t('admin_promo_card_activations', { current: promo.count, max: promo.limit }),
      ui.t('admin_promo_card_validity', { validity: this.validity(promo) }),
      ui.t('admin_promo_card_status', { status: ui.t(this.status(promo)) }),
      ui.t('admin_promo_card_created', { created: formatDemoDate(promo.created) }),
      ui.t('admin_promo_card_created_by', { creator: promo.creator }),
    ].join('\n'), [
      ui.button('admin_promo_edit_button', () => this.editMenu(message, promo, listPage)),
      ui.button('admin_promo_toggle_status_button', () => {
        promo.enabled = !promo.enabled;
        ui.alert('admin_promo_toggle_success', {
          code: promo.code, status: ui.t(promo.enabled ? 'admin_promo_status_activated' : 'admin_promo_status_deactivated'),
        });
        this.card(message, promo, listPage);
      }),
      ui.button('admin_promo_view_activations_button', () => this.activations(message, promo, listPage)),
      ui.button('admin_promo_delete_button', () => ui.confirmation(message,
        ui.t('admin_promo_delete_confirm', { code: escape(promo.code) }), [[
          ui.button('yes_button', () => {
            this.records = this.records.filter((item) => item !== promo);
            ui.alert('admin_promo_deleted_success', { code: promo.code });
            this.list(message, Math.min(listPage, Math.max(0, Math.ceil(this.records.length / 10) - 1)));
          }),
          ui.button('no_button', () => this.card(message, promo, listPage)),
        ]])),
      ui.button('admin_promo_back_to_list_button', () => this.list(message, listPage)),
    ]);
  }

  private activations(message: ChatMessage, promo: Promo, listPage: number, page = 0) {
    const { ui } = this;
    const format = { code: promo.code };
    const text = promo.activations.length ? ui.t('admin_promo_activations_header', format) + promo.activations
      .slice(page * 10, (page + 1) * 10).map(({ userId, date }) => ui.t('admin_promo_activation_item', {
        user_id: userId, date: formatDemoDate(date),
      })).join('\n') : ui.t('admin_promo_no_activations', format);
    const nav: Button[] = [
      ...(page > 0 ? [{ label: '⬅️', activate: () => this.activations(message, promo, listPage, page - 1) }] : []),
      ...((page + 1) * 10 < promo.activations.length ? [{ label: '➡️', activate: () => this.activations(message, promo, listPage, page + 1) }] : []),
    ];
    ui.view(message, text, [
      ...(nav.length ? [nav] : []),
      ui.button('admin_promo_export_csv_button', () => {
        ui.document(`promo-${promo.code}-demo.csv`, [
          ['code', 'user_id', 'activated_at'],
          ...promo.activations.map(({ userId, date }) => [promo.code, userId, date]),
        ], ui.t('admin_promo_export_caption', format));
      }),
      ui.button('admin_promo_back_to_detail_button', () => this.card(message, promo, listPage)),
    ]);
  }

  private editMenu(message: ChatMessage, promo: Promo, listPage: number) {
    const { ui } = this;
    const rows: ButtonRow[] = editRows.map((row) => row.map((field) => ui.button(field.label, () => this.editField(message, promo, field, listPage))));
    rows.push(ui.button('admin_promo_back_to_detail_button', () => this.card(message, promo, listPage)));
    ui.view(message, ui.t('admin_promo_edit_select_field'), rows);
  }

  private editField(message: ChatMessage, promo: Promo, field: Edit, listPage: number) {
    const { ui } = this;
    const prompt = field.prompt ? ui.t(field.prompt) : `Send new value for ${field.label}`;
    const hint = field.key === 'scope' ? `\nAllowed: ${scopes.join(', ')}`
      : field.key === 'duration' || field.key === 'traffic' ? '\nUse 1 or none to reset.'
        : ['discount', 'minMonths', 'minGb'].includes(field.key) ? '\nUse 0 or none to clear.' : '';
    ui.prompt(message, prompt + hint, (input) => {
      const value = input.trim().toLowerCase();
      if (field.key === 'scope') {
        if (!scopes.includes(value)) return void ui.answer('admin_promo_invalid_input');
        promo.scope = value;
      } else {
        const number = value === 'none' ? field.min ?? 0 : Number(value.replace(',', '.'));
        if (!Number.isFinite(number) || (field.integer && !Number.isInteger(number))
          || number < (field.min ?? 0) || number > (field.max ?? 1e6)) return void ui.answer('admin_promo_invalid_input');
        if (field.key === 'validity') promo.expires = this.expiry(number);
        else if (field.key === 'bonus' || field.key === 'limit') promo[field.key] = number;
        else promo[field.key] = number === 0 || (field.key === 'duration' || field.key === 'traffic') && number === 1
          ? undefined : number;
      }
      ui.clearInput();
      ui.answer('admin_promo_edit_success');
      this.card(ui.host.append(''), promo, listPage);
    }, [ui.button('cancel_button', () => this.editMenu(message, promo, listPage))]);
  }

  private create(message: ChatMessage, bulk: boolean) {
    const { ui } = this;
    let completed = false;
    const cancel = (target: ChatMessage) => ui.button('cancel_button', () => {
      completed = true;
      this.menu(target);
    });
    const wrong = (key: string) => { ui.answer(key); };
    const int = (input: string, max: number) => {
      const num = Number(input);
      return Number.isInteger(num) && num >= 1 && num <= max ? num : undefined;
    };
    ui.prompt(message, ui.t(bulk ? 'admin_bulk_promo_step1_quantity' : 'admin_promo_step1_code'), (input) => {
      const qty = bulk ? int(input, 100) : 1;
      const code = input.toUpperCase();
      if (!qty) return wrong('admin_bulk_promo_invalid_quantity');
      if (!bulk && !/^[\p{L}\p{N}]{3,30}$/u.test(code)) return wrong('admin_promo_invalid_code_format');
      if (!bulk && this.records.some((record) => record.code === code)) return wrong('admin_promo_code_already_exists');
      const daysPrompt = ui.host.append('');
      ui.prompt(daysPrompt, ui.t(bulk ? 'admin_bulk_promo_step2_bonus_days' : 'admin_promo_step2_bonus_days',
        { quantity: qty, code }), (days) => {
        const bonus = int(days, 365);
        if (!bonus) return wrong('admin_promo_invalid_bonus_days');
        const maxPrompt = ui.host.append('');
        ui.prompt(maxPrompt, ui.t(bulk ? 'admin_bulk_promo_step3_max_activations' : 'admin_promo_step3_max_activations',
          { quantity: qty, code, bonus_days: bonus }), (activations) => {
          const limit = int(activations, 10000);
          if (!limit) return wrong('admin_promo_invalid_max_activations');
          ui.clearInput();
          const validity = ui.host.append(ui.t(bulk ? 'admin_bulk_promo_step4_validity' : 'admin_promo_step4_validity', {
            code, quantity: qty, bonus_days: bonus, max_activations: limit,
          }));
          const finish = (validityDays?: number, fromInput = false) => {
            if (completed) return;
            completed = true;
            ui.clearInput();
            const created = Array.from({ length: qty }, (): Promo => ({
              id: ++this.promoId,
              code: bulk ? `BULKDEMO${String(++this.batchSequence).padStart(3, '0')}` : code,
              bonus, limit, enabled: true, activations: [], count: 0, expires: this.expiry(validityDays),
              created: new Date().toISOString(), creator: ui.host.data.current.id,
              discount: undefined, duration: undefined, traffic: undefined, scope: undefined,
              minMonths: undefined, minGb: undefined,
            }));
            this.records.unshift(...created);
            const validityText = validityDays
              ? ui.t('admin_promo_days_value', { days: validityDays }) : ui.t('admin_promo_unlimited');
            const text = bulk ? [
              ui.t('admin_bulk_promo_created_title'),
              ui.t('admin_bulk_promo_created_stats', { created: qty, total: qty }),
              ui.t('admin_bulk_promo_settings', {
                bonus_days: bonus, max_activations: limit, validity: validityText,
              }),
            ].join('\n\n') : ui.t('admin_promo_created_success', {
              code, bonus_days: bonus, max_activations: limit, valid_until_str: validityText,
            });
            const reply = fromInput ? ui.host.append('') : validity;
            ui.view(reply, text, [ui.button('back_to_main_menu_button', () => this.menu(reply))]);
            if (bulk) ui.document('bulk-promocodes-demo.csv', this.csv(created), ui.t('admin_bulk_promo_csv_caption', { count: qty, days: bonus }));
          };
          ui.confirmation(validity, validity.text, [
            [
              ui.button('admin_promo_unlimited', () => finish()),
              ui.button('admin_promo_set_validity_days', () => {
                if (!completed) ui.prompt(validity, ui.t(bulk ? 'admin_bulk_promo_enter_validity_days' : 'admin_promo_enter_validity_days'), (value) => {
                  const days = int(value, 365);
                  if (!days) return wrong('admin_promo_invalid_validity_days');
                  finish(days, true);
                }, [cancel(validity)]);
              }),
            ],
            cancel(validity),
          ]);
        }, [cancel(maxPrompt)]);
      }, [cancel(daysPrompt)]);
    }, [cancel(message)]);
  }

  private expiry(days = 0) {
    if (!days) return '';
    const date = new Date();
    date.setDate(date.getDate() + days);
    return date.toISOString();
  }

  private csv(rows: Promo[]) {
    return [
      ['code', 'bonus_days', 'max_activations', 'valid_until', 'uses'],
      ...rows.map((promo) => [promo.code, promo.bonus, promo.limit, this.validity(promo), promo.count]),
    ];
  }
}
