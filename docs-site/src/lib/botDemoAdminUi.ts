import type { Activate, Button, ButtonRow, ChatMessage, Format, Language } from './botDemoConversation';
import type { BotDemoData } from './botDemoData';

export type AdminMessages = Record<string, string>;

export type AdminHost = {
  data: BotDemoData;
  phrases: () => AdminMessages;
  language: () => Language;
  hasMiniApp: () => boolean;
  mainMenu: (message: ChatMessage) => void;
  append: (text: string, rows?: ButtonRow[]) => ChatMessage;
  edit: (message: ChatMessage, text: string, rows?: ButtonRow[]) => void;
  setInput: (next?: (value: string) => void) => void;
  isInput: (next: (value: string) => void) => boolean;
  notify: (text: string) => void;
};

export type AdminView = (message: ChatMessage) => void;

export function formatDemoDate(value: string) {
  return value ? value.slice(0, 16).replace('T', ' ') : '—';
}

export function csvCell(value: string | number) {
  const text = String(value);
  const field = /^[=+@-]/.test(text) ? `'${text}` : text;
  return `"${field.replaceAll('"', '""')}"`;
}

export class AdminUi {
  acceptsAttachment = false;

  constructor(readonly host: AdminHost) {}

  t = (key: string, values: Format = {}) =>
    (this.host.phrases()[key] ?? key).replace(/\{([a-z_0-9]+)\}/gi, (match, name) =>
      Object.hasOwn(values, name) ? String(values[name]) : match);

  button(key: string, activate: Activate, values?: Format): Button {
    return { label: this.t(key, values), activate };
  }

  clearInput() {
    this.acceptsAttachment = false;
    this.host.setInput();
  }

  view(message: ChatMessage, text: string, rows?: ButtonRow[]) {
    this.clearInput();
    this.host.edit(message, text, rows);
  }

  confirmation(message: ChatMessage, text: string, rows: ButtonRow[]) {
    const pending = () => {};
    const guard = (button: Button): Button => ({
      ...button,
      activate: () => {
        if (!this.host.isInput(pending)) {
          this.alert('telegram_confirmation_expired');
          return;
        }
        this.clearInput();
        return button.activate();
      },
    });
    this.view(message, text, rows.map((row) => Array.isArray(row) ? row.map(guard) : guard(row)));
    this.host.setInput(pending);
  }

  prompt(message: ChatMessage | undefined, text: string, next: (value: string) => void, rows?: ButtonRow[]) {
    this.clearInput();
    if (message) this.host.edit(message, text, rows);
    else this.host.append(text, rows);
    this.host.setInput(next);
  }

  answer(key: string, values?: Format, rows?: ButtonRow[]) {
    return this.host.append(this.t(key, values), rows);
  }

  alert(key: string, values?: Format) {
    this.host.notify(this.t(key, values));
  }

  pager(page: number, total: number, go: (page: number) => void, arrowsOnly = false, always = false): ButtonRow[] {
    if (total <= 1 && !always) return [];
    return [[
      ...(page > 0 ? [{ label: arrowsOnly ? '⬅️' : this.t('prev_page_button'), activate: () => go(page - 1) }] : []),
      { label: `${page + 1}/${total}`, activate: () => {} },
      ...(page < total - 1 ? [{ label: arrowsOnly ? '➡️' : this.t('next_page_button'), activate: () => go(page + 1) }] : []),
    ]];
  }

  document(filename: string, cells: (string | number)[][], caption = '') {
    const content = cells.map((row) => row.map(csvCell).join(',')).join('\r\n') + '\r\n';
    this.host.append(caption || filename, [{
      label: `📎 ${filename}`,
      activate: () => ({ kind: 'download', filename, content }),
    }]);
  }
}
