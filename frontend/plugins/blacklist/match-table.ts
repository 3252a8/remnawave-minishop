import type { MatchPage, MatchProfile, MatchRow, TariffOption } from "./api";
import { nativeTranslator } from "./match-copy";
import type { NativeKey, NativeTranslate } from "./match-copy";
import { cross, element, language, reasonList, translator } from "./ui";
import type { Props } from "./ui";

type Badge = "danger" | "success" | "warning" | "muted";

export interface MatchProps extends Props {
  onOpenUserCard?: (identifier: MatchProfile | string) => void;
  resolvedAvatarUrl?: (profile: MatchProfile) => string;
  userDisplayName?: (profile: MatchProfile) => string;
  userSecondaryName?: (profile: MatchProfile) => string;
  userInitials?: (profile: MatchProfile) => string;
  panelStatusBadge?: (profile: MatchProfile) => { label: string; variant: Badge };
  fmtDateShort?: (date: string | null) => string;
  fmtMoney?: (number: number, currency: string) => string;
}

type Column = {
  key: string;
  label: string;
  content: (row: MatchRow) => Node;
  sort?: { key: string; first: "asc" | "desc" };
};

function badge(text: string, variant: Badge): HTMLElement {
  return element("span", text, `admin-badge admin-badge-${variant}`);
}

function profileIdentity(row: MatchRow, props: MatchProps): HTMLElement {
  const profile = row.profile;
  const username = row.username ? `@${row.username}` : "";
  const name =
    (profile && props.userDisplayName?.(profile)) ||
    row.name ||
    username ||
    profile?.email ||
    row.userId;
  const secondary =
    (profile && props.userSecondaryName?.(profile)) ||
    (username && name !== username ? username : "");
  const avatarUrl =
    profile &&
    (props.resolvedAvatarUrl?.(profile) || profile.avatar_url || profile.telegram_photo_url);
  const initials =
    (profile && props.userInitials?.(profile)) ||
    name
      .split(/\s+/u)
      .slice(0, 2)
      .map((part) => part[0])
      .join("")
      .toUpperCase() ||
    "U";
  const avatar = element("span", undefined, "admin-avatar admin-avatar-sm");
  if (avatarUrl) {
    const image = element("img");
    image.src = avatarUrl;
    image.alt = "";
    image.loading = "lazy";
    image.referrerPolicy = "no-referrer";
    image.addEventListener("error", () => avatar.replaceChildren(element("span", initials)));
    avatar.append(image);
  } else {
    avatar.append(element("span", initials));
  }
  const link = element("a", name, "admin-user-cell-name");
  const prefix = (props.routePrefix ?? "").replace(/\/+$/u, "");
  link.href = `${prefix}/admin/users/${encodeURIComponent(row.userId)}`;
  link.addEventListener("click", (event) => {
    if (!plainClick(event) || !props.onOpenUserCard) return;
    event.preventDefault();
    props.onOpenUserCard(profile ?? row.userId);
  });
  const details = element("div", undefined, "admin-user-cell-text");
  const headline = element("span", undefined, "blacklist-native-user-headline");
  headline.append(link, cross(translator(props)("match")));
  details.append(headline);
  if (secondary) details.append(element("span", secondary, "admin-user-cell-secondary"));
  details.append(element("span", row.userId, "admin-user-cell-id"));
  const cell = element("div", undefined, "admin-user-cell");
  cell.append(avatar, details);
  return cell;
}

function plainClick(event: MouseEvent): boolean {
  return (
    event.button === 0 &&
    !event.defaultPrevented &&
    !event.altKey &&
    !event.ctrlKey &&
    !event.metaKey &&
    !event.shiftKey
  );
}

function clickableRow(node: HTMLElement): void {
  node.classList.add("is-clickable");
  node.addEventListener("click", (event) => {
    const target = event.target as Element | null;
    if (plainClick(event) && !target?.closest("a, button, input, select")) {
      node.querySelector<HTMLAnchorElement>(".admin-user-cell-name")?.click();
    }
  });
}

export function tariffName(tariff: TariffOption, lang: string): string {
  const names = tariff.tariff_names;
  return (
    names[lang] ||
    names.en ||
    names.ru ||
    Object.values(names).find(Boolean) ||
    tariff.tariff_key ||
    "—"
  );
}

function subscriptionPlan(profile: MatchProfile | null, t: NativeTranslate, lang: string): Node {
  const plan = profile?.subscription_plan;
  const value = element("span", undefined, "admin-subscription-plan-name");
  const node = element("div", undefined, "admin-subscription-plan");
  node.append(value);
  if (!plan) {
    node.classList.add("is-empty");
    value.textContent = t("users_tariff_no_subscription");
    return node;
  }
  const metadata = element("span", undefined, "admin-subscription-plan-meta");
  if (plan.kind === "tariff") {
    value.textContent = tariffName(plan, lang);
    value.title = plan.tariff_key || value.textContent;
    if (!plan.is_configured) metadata.append(element("span", t("users_tariff_deleted")));
    else if (plan.is_enabled === false)
      metadata.append(element("span", t("users_tariff_disabled")));
  } else {
    value.append(
      badge(t(plan.kind === "trial" ? "users_tariff_trial" : "users_tariff_unassigned"), "warning")
    );
  }
  if (!plan.is_active) metadata.append(element("span", t("users_tariff_inactive")));
  if (metadata.childNodes.length) node.append(metadata);
  return node;
}

function premiumTraffic(profile: MatchProfile | null, t: NativeTranslate): Node {
  const premium = profile?.premium_traffic;
  if (!premium || premium.state === "none")
    return element("span", "—", "admin-user-premium-placeholder");
  const gb = (bytes: number) =>
    `${Number((bytes / 2 ** 30).toFixed(bytes >= 10 * 2 ** 30 ? 1 : 2))} GB`;
  const limit = premium.limit_bytes
    ? gb(premium.limit_bytes)
    : t("premium_traffic_filter_unlimited");
  const variant =
    premium.state === "critical" ? "danger" : premium.state === "warn" ? "warning" : "success";
  const span = badge(`${gb(premium.used_bytes)} / ${limit}`, variant);
  span.classList.add("admin-user-premium-badge");
  return span;
}

function profileStatus(profile: MatchProfile | null, props: MatchProps, t: NativeTranslate): Node {
  if (!profile) return badge("—", "muted");
  const native = props.panelStatusBadge?.(profile);
  if (native) return badge(native.label, native.variant);
  if (profile.is_banned) return badge(t("status_banned"), "danger");
  switch (profile.panel_status) {
    case "active":
      return badge(t("status_active"), "success");
    case "expired":
      return badge(t("status_expired"), "warning");
    case "limited":
      return badge(t("status_limited"), "warning");
    case "disabled":
      return badge(t("status_disabled"), "muted");
    case "bot_only":
      return badge(t("status_bot_only"), "muted");
    default:
      return badge(profile.panel_status || "—", "muted");
  }
}

function reasonCell(row: MatchRow, props: MatchProps): Node {
  const t = translator(props);
  const box = element("div", undefined, "blacklist-native-reasons");
  const identity = element("span", undefined, "blacklist-native-match");
  identity.textContent = row.telegramId;
  identity.setAttribute("aria-label", `${t("telegram_id")} ${row.telegramId}`);
  box.append(identity);
  const comments = reasonList(row.reasons, t);
  if (comments.childNodes.length) box.append(comments);
  if (row.stale) box.append(element("p", t("stale"), "blacklist-muted"));
  return box;
}

function columns(page: MatchPage, props: MatchProps, t: NativeTranslate): Column[] {
  const date = (value: string | null) =>
    element(
      "span",
      props.fmtDateShort?.(value) ??
        (value ? new Date(value).toLocaleDateString(language(props)) : "—")
    );
  const money = (value: number | undefined, currency: string) =>
    element(
      "span",
      value === undefined
        ? "—"
        : (props.fmtMoney?.(value, currency) ??
            new Intl.NumberFormat(language(props), { style: "currency", currency }).format(value)),
      "admin-user-balance-value"
    );
  const count = (value: number | undefined) =>
    element("span", value === undefined ? "—" : String(value), "admin-user-counter");
  const balance = (value: number | undefined) =>
    money(
      value === undefined ? undefined : value / 10 ** page.balance_currency_scale,
      page.balance_currency
    );
  const col = (
    key: string,
    name: NativeKey,
    content: Column["content"],
    sort?: Column["sort"]
  ): Column => ({ key, label: t(name), content, ...(sort && { sort }) });
  return [
    col("user", "user", (row) => profileIdentity(row, props), { key: "name", first: "asc" }),
    {
      key: "reasons",
      label: translator(props)("reason_column"),
      content: (row) => reasonCell(row, props),
    },
    col("tariff", "users_col_tariff", (row) => subscriptionPlan(row.profile, t, language(props))),
    ...(page.user_balance_enabled
      ? [
          col("balance", "users_col_user_balance", (row) =>
            balance(row.profile?.user_balance_amount_minor)
          ),
        ]
      : []),
    ...(page.partner_balance_enabled
      ? [
          col("partner-balance", "users_col_partner_balance", (row) =>
            balance(row.profile?.partner_balance_amount_minor)
          ),
        ]
      : []),
    col("premium", "premium_traffic_filter_label", (row) => premiumTraffic(row.profile, t), {
      key: "premium_ratio",
      first: "desc",
    }),
    col(
      "paid",
      "users_col_payments_total",
      (row) => money(row.profile?.payments_total_amount, row.profile?.payments_currency || "RUB"),
      { key: "payments_total", first: "desc" }
    ),
    col("payments", "users_col_payments_count", (row) => count(row.profile?.payments_count), {
      key: "payments_count",
      first: "desc",
    }),
    col("invited", "users_col_invited", (row) => count(row.profile?.invited_users_count), {
      key: "invited_users_count",
      first: "desc",
    }),
    col("status", "status", (row) => profileStatus(row.profile, props, t), {
      key: "status",
      first: "asc",
    }),
    col(
      "expiry",
      "users_col_subscription_expires",
      (row) =>
        date(row.profile?.subscription_expires_at ?? row.profile?.panel_status_expired_at ?? null),
      { key: "subscription_expires_at", first: "asc" }
    ),
    col(
      "registration",
      "users_col_registration",
      (row) => date(row.profile?.registration_date ?? null),
      { key: "registered", first: "desc" }
    ),
  ];
}

function tableHeader(
  column: Column,
  sort: string,
  t: NativeTranslate,
  setSort: (value: string) => void
): HTMLElement {
  const cell = element("th");
  cell.scope = "col";
  if (!column.sort) {
    cell.textContent = column.label;
    return cell;
  }
  const { key, first } = column.sort;
  const direction =
    sort === `${key}_asc` ? "ascending" : sort === `${key}_desc` ? "descending" : "none";
  const second = first === "asc" ? "desc" : "asc";
  cell.setAttribute("aria-sort", direction);
  const control = element("button", undefined, "admin-sort-header");
  control.type = "button";
  control.name = `sort-${key}`;
  control.title = t(
    direction === "ascending"
      ? "sort_ascending"
      : direction === "descending"
        ? "sort_descending"
        : "sort_off"
  );
  const arrow = element(
    "span",
    direction === "ascending" ? "↑" : direction === "descending" ? "↓" : "↕",
    "admin-sort-state"
  );
  arrow.setAttribute("aria-hidden", "true");
  arrow.dataset.state = direction;
  control.append(element("span", column.label), arrow);
  control.addEventListener("click", () =>
    setSort(
      direction === "none"
        ? `${key}_${first}`
        : sort === `${key}_${first}`
          ? `${key}_${second}`
          : ""
    )
  );
  cell.append(control);
  return cell;
}

function mobileFact(column: Column, row: MatchRow): HTMLElement {
  const box = element("div", undefined, `blacklist-native-${column.key}`);
  const value = element("dd");
  value.append(column.content(row));
  box.append(element("dt", column.label), value);
  return box;
}

export function matchesTable(
  page: MatchPage,
  props: MatchProps,
  sort: string,
  setSort: (value: string) => void
): HTMLElement {
  const t = nativeTranslator(props);
  const fields = columns(page, props, t);
  const wrapper = element("div", undefined, "admin-users-table-wrap");
  wrapper.classList.toggle("has-user-balance", page.user_balance_enabled);
  wrapper.classList.toggle("has-partner-balance", page.partner_balance_enabled);
  const tableWrap = element("div", undefined, "admin-table-wrap");
  const table = element("table", undefined, "admin-table admin-users-table");
  table.setAttribute("aria-label", translator(props)("title"));
  const header = element("tr");
  header.append(...fields.map((column) => tableHeader(column, sort, t, setSort)));
  const thead = element("thead");
  thead.append(header);
  const tbody = element("tbody");
  const mobile = element("ul", undefined, "admin-users-mobile-list");
  for (const row of page.rows) {
    const desktop = element("tr");
    desktop.dataset.userId = String(row.profile?.user_id ?? row.userId);
    clickableRow(desktop);
    for (const field of fields) {
      const td = element("td", undefined, `blacklist-native-${field.key}`);
      td.dataset.label = field.label;
      td.append(field.content(row));
      desktop.append(td);
    }
    tbody.append(desktop);

    const card = element("div", undefined, "admin-user-mobile-card");
    card.dataset.mobileUserId = desktop.dataset.userId;
    clickableRow(card);
    const head = element("div", undefined, "admin-user-mobile-head");
    head.append(profileIdentity(row, props), profileStatus(row.profile, props, t));
    const metrics = element("dl", undefined, "admin-user-mobile-metrics");
    const dates = element("dl", undefined, "admin-user-mobile-dates");
    for (const field of fields) {
      if (field.key === "user" || field.key === "status" || field.key === "reasons") continue;
      const target = field.key === "registration" || field.key === "expiry" ? dates : metrics;
      target.append(mobileFact(field, row));
    }
    card.append(head, metrics, dates, reasonCell(row, props));
    const item = element("li");
    item.append(card);
    mobile.append(item);
  }
  table.append(thead, tbody);
  tableWrap.append(table);
  wrapper.append(tableWrap, mobile);
  return wrapper;
}
