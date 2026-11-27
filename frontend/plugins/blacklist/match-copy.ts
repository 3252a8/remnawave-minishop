/*! @license Minishop admin labels and interface patterns (MIT)
 * Copyright (c) 2025-2026 machka-pasla, 3252a8 and other contributors
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */
import { language } from "./ui";
import type { Props } from "./ui";

const COPY = {
  user: ["Пользователь", "User"],
  users_col_tariff: ["Тариф / триал", "Tariff / trial"],
  users_col_user_balance: ["Баланс", "Balance"],
  users_col_partner_balance: ["Баланс партнёрки", "Partner balance"],
  premium_traffic_filter_label: ["Премиум трафик", "Premium traffic"],
  users_col_payments_total: ["Сумма платежей", "Paid total"],
  users_col_payments_count: ["Платежи", "Payments"],
  users_col_invited: ["Приглашенные", "Invited"],
  status: ["Статус", "Status"],
  users_col_subscription_expires: ["Истекает", "Expires"],
  users_col_registration: ["Регистрация", "Registered"],
  users_search_placeholder: [
    "ID Minishop, @username или email",
    "Minishop ID, @username, or email",
  ],
  filter: ["Фильтр", "Filter"],
  find: ["Найти", "Find"],
  relationships_open: ["Граф рефералов", "Referral graph"],
  total: ["Всего", "Total"],
  filters: ["Фильтры", "Filters"],
  users_filters_title: ["Фильтры пользователей", "User filters"],
  users_filters_open: ["Открыть фильтры", "Open filters"],
  close_menu: ["Закрыть меню", "Close menu"],
  done: ["Готово", "Done"],
  reset: ["Сбросить", "Reset"],
  active_filters: ["Активные фильтры", "Active filters"],
  clear_filter: ["Сбросить {label}", "Clear {label}"],
  filter_all: ["Все", "All"],
  filter_not_banned: ["Не забанены", "Not banned"],
  filter_banned: ["Забанены", "Banned"],
  filter_active_today: ["Зарегистрированы сегодня", "Registered today"],
  filter_referred: ["Пришли по реферальной ссылке", "Referred users"],
  filter_active_subscription: ["С активной подпиской", "With active subscription"],
  stats_label_paid_subs: ["Платные пользователи", "Paid users"],
  stats_label_free_users: ["С бесплатной подпиской", "With free subscription"],
  stats_label_trial_users: ["С пробной подпиской", "With trial subscription"],
  filter_inactive_subscription: ["Без активной подписки", "Without active subscription"],
  filter_expired_subscription: ["С истёкшей подпиской", "With expired subscription"],
  filter_unmapped_tariff: ["Активная подписка без тарифа", "Active subscription without tariff"],
  filter_tg_linked: ["С Telegram", "With Telegram"],
  filter_no_tg: ["Без Telegram", "No Telegram"],
  filter_email_linked: ["С email", "With email"],
  filter_no_email: ["Без email", "No email"],
  filter_panel_linked: ["С панелью", "With panel"],
  panel_status: ["Статус панели", "Panel status"],
  panel_status_all: ["Все статусы", "All statuses"],
  status_active: ["Активна", "Active"],
  status_expired: ["Истёк", "Expired"],
  status_limited: ["Ограничен", "Limited"],
  status_disabled: ["Выключен", "Disabled"],
  status_bot_only: ["Только бот", "Bot Only"],
  status_banned: ["Бан", "Banned"],
  expired_badge: ["Истёк {date}", "Expired {date}"],
  premium_traffic_filter_all: ["Все", "All"],
  premium_traffic_filter_none: ["Без лимита в тарифе", "No tariff limit"],
  premium_traffic_filter_unlimited: ["Безлимит (оверрайд)", "Unlimited (override)"],
  premium_traffic_filter_good: ["Премиум: норма", "Premium: OK"],
  premium_traffic_filter_warn: ["Премиум: мало", "Premium: low"],
  premium_traffic_filter_critical: ["Премиум: исчерпан", "Premium: depleted"],
  users_tariff_all: ["Все тарифы", "All tariffs"],
  users_tariff_trial: ["Триал", "Trial"],
  users_tariff_no_subscription: ["Нет подписки", "No subscription"],
  users_tariff_unassigned: ["Без тарифа", "No tariff"],
  users_tariff_deleted: ["Удалён", "Removed"],
  users_tariff_disabled: ["Отключён", "Disabled"],
  users_tariff_inactive: ["Неактивна", "Inactive"],
  users_tariff_history_hint: [
    "Если действующей подписки нет, показан тариф последней подписки. Остальные фильтры применяются дополнительно.",
    "For users without an active subscription, the latest subscription is shown. Other filters apply in addition.",
  ],
  sort_ascending: ["Сортировка по возрастанию", "Sorted ascending"],
  sort_descending: ["Сортировка по убыванию", "Sorted descending"],
  sort_off: ["Без сортировки", "Not sorted"],
  page_short: ["Стр.", "Page"],
  pagination_of: ["из", "of"],
  pagination_jump_aria: ["Перейти к странице", "Go to page"],
  pagination_go: ["Перейти", "Go"],
  back: ["Назад", "Back"],
  next: ["Далее", "Next"],
} as const;

export type NativeKey = keyof typeof COPY;

type Values = Record<string, string | number>;
export type NativeTranslate = (key: NativeKey, values?: Values) => string;

export function nativeTranslator(props: Props): NativeTranslate {
  const index = language(props) === "ru" ? 0 : 1;
  return (key, values = {}) => {
    const fallback = COPY[key][index].replace(/\{(\w+)\}/g, (match, name: string) =>
      String(values[name] ?? match)
    );
    const value = props.at?.(key, values, fallback);
    return value && value !== key ? value : fallback;
  };
}
