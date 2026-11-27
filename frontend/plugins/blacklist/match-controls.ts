import type { MatchFilters, MatchPage, TariffOption } from "./api";
import { nativeTranslator } from "./match-copy";
import type { NativeKey, NativeTranslate } from "./match-copy";
import { tariffName } from "./match-table";
import { element, language, translator } from "./ui";
import type { Props } from "./ui";

export const MATCH_PAGE_SIZE = 25;
export const MATCH_FILTERS: MatchFilters = {
  q: "",
  sort: "",
  filter: "all",
  panel_status: "all",
  premium_traffic: "all",
  tariff_filter: "all",
};

type FilterKey = Exclude<keyof MatchFilters, "q" | "sort">;
type FiltersPatch = Partial<MatchFilters>;
type FiltersAction = (patch: FiltersPatch) => void;
type Option = { value: string; label: string };
type Filter = { key: FilterKey; label: string; options: Option[] };
const FILTER_KEYS = Object.keys(MATCH_FILTERS) as (keyof MatchFilters)[];

export function listAddress(): { offset: number; filters: MatchFilters } {
  const params = new URLSearchParams(typeof window === "undefined" ? "" : window.location.search);
  const filters = { ...MATCH_FILTERS };
  for (const key of FILTER_KEYS) filters[key] = params.get(`blacklist_${key}`) ?? filters[key];
  filters.q = filters.q.slice(0, 256);
  if (!/^(?:all|trial|no_subscription|no_tariff|tariff:.{1,249})$/u.test(filters.tariff_filter)) {
    filters.tariff_filter = "all";
  }
  const page = Number(params.get("blacklist_page"));
  const offset = (page - 1) * MATCH_PAGE_SIZE;
  return {
    offset:
      Number.isSafeInteger(offset) &&
      Number.isInteger(page) &&
      offset >= 0 &&
      offset <= 2_147_483_647
        ? offset
        : 0,
    filters,
  };
}

export function replaceListAddress(offset: number, filters: MatchFilters): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  for (const key of FILTER_KEYS) {
    const name = `blacklist_${key}`;
    if (filters[key] === MATCH_FILTERS[key]) url.searchParams.delete(name);
    else url.searchParams.set(name, filters[key]);
  }
  if (offset) url.searchParams.set("blacklist_page", String(offset / MATCH_PAGE_SIZE + 1));
  else url.searchParams.delete("blacklist_page");
  window.history.replaceState(window.history.state, "", url);
}

const FILTER_OPTIONS: [string, NativeKey][] = [
  ["all", "filter_all"],
  ["active", "filter_not_banned"],
  ["banned", "filter_banned"],
  ["active_today", "filter_active_today"],
  ["referred", "filter_referred"],
  ["active_subscription", "filter_active_subscription"],
  ["paid", "stats_label_paid_subs"],
  ["free", "stats_label_free_users"],
  ["trial", "stats_label_trial_users"],
  ["inactive_subscription", "filter_inactive_subscription"],
  ["expired_subscription", "filter_expired_subscription"],
  ["unmapped_tariff", "filter_unmapped_tariff"],
  ["tg_linked", "filter_tg_linked"],
  ["no_tg", "filter_no_tg"],
  ["email_linked", "filter_email_linked"],
  ["no_email", "filter_no_email"],
  ["panel_linked", "filter_panel_linked"],
];

function tariffChoices(
  options: TariffOption[],
  selected: string,
  lang: string,
  t: NativeTranslate
): Option[] {
  const choices = options
    .flatMap((option) => {
      if (!option.tariff_key) return [];
      const name = tariffName(option, lang);
      const repeated = options.some(
        (item) => item.tariff_key !== option.tariff_key && tariffName(item, lang) === name
      );
      const status = !option.is_configured
        ? t("users_tariff_deleted")
        : option.is_enabled === false
          ? t("users_tariff_disabled")
          : "";
      const label = repeated ? `${name} (${option.tariff_key})` : name;
      return [
        { value: `tariff:${option.tariff_key}`, label: status ? `${label} · ${status}` : label },
      ];
    })
    .sort((left, right) => left.label.localeCompare(right.label, lang));
  if (selected.startsWith("tariff:") && !choices.some((option) => option.value === selected)) {
    choices.push({ value: selected, label: `${selected.slice(7)} · ${t("users_tariff_deleted")}` });
  }
  return [
    { value: "all", label: t("users_tariff_all") },
    { value: "trial", label: t("users_tariff_trial") },
    { value: "no_subscription", label: t("users_tariff_no_subscription") },
    { value: "no_tariff", label: t("users_tariff_unassigned") },
    ...choices,
  ];
}

function filterDescriptions(
  page: MatchPage,
  filters: MatchFilters,
  lang: string,
  t: NativeTranslate
): Filter[] {
  const choices = (pairs: [string, NativeKey][]) =>
    pairs.map(([value, key]) => ({ value, label: t(key) }));
  return [
    {
      key: "tariff_filter",
      label: t("users_col_tariff"),
      options: tariffChoices(page.tariff_options, filters.tariff_filter, lang, t),
    },
    { key: "filter", label: t("filter"), options: choices(FILTER_OPTIONS) },
    {
      key: "panel_status",
      label: t("panel_status"),
      options: choices([
        ["all", "panel_status_all"],
        ["active", "status_active"],
        ["expired", "status_expired"],
        ["limited", "status_limited"],
      ]),
    },
    {
      key: "premium_traffic",
      label: t("premium_traffic_filter_label"),
      options: choices([
        ["all", "premium_traffic_filter_all"],
        ["none", "premium_traffic_filter_none"],
        ["unlimited", "premium_traffic_filter_unlimited"],
        ["good", "premium_traffic_filter_good"],
        ["warn", "premium_traffic_filter_warn"],
        ["critical", "premium_traffic_filter_critical"],
      ]),
    },
  ];
}

function selectFilter(
  filter: Filter,
  value: string,
  action: FiltersAction,
  prefix = ""
): HTMLElement {
  const select = element("select", undefined, "admin-select admin-toolbar-select");
  select.name = `${prefix}${filter.key}`;
  for (const option of filter.options) {
    const item = element("option", option.label);
    item.value = option.value;
    select.append(item);
  }
  select.value = value;
  select.addEventListener("change", () => action({ [filter.key]: select.value }));
  const label = element("label", undefined, "admin-toolbar-field");
  label.append(element("span", filter.label, "admin-toolbar-field-label"), select);
  return label;
}

function control(label: string, className = ""): HTMLButtonElement {
  const result = element("button", label, `admin-btn${className ? ` ${className}` : ""}`);
  result.type = "button";
  return result;
}

function referralGraph(props: Props, t: NativeTranslate): HTMLAnchorElement {
  const prefix = (props.routePrefix ?? "").replace(/\/+$/u, "");
  const graph = element("a", t("relationships_open"), "admin-btn");
  graph.dataset.adminAction = "open-relationships-graph";
  graph.href = `${prefix}/admin/users?view=relationships`;
  graph.addEventListener("click", (event) => {
    if (
      event.button !== 0 ||
      event.altKey ||
      event.ctrlKey ||
      event.metaKey ||
      event.shiftKey ||
      typeof window === "undefined"
    )
      return;
    event.preventDefault();
    const url = new URL(window.location.href);
    url.pathname = `${prefix}/admin/users`;
    url.searchParams.set("view", "relationships");
    url.searchParams.delete("graph_kind");
    url.searchParams.delete("focus");
    window.history.pushState(null, "", url);
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
  return graph;
}

function filterDialog(
  descriptions: Filter[],
  current: MatchFilters,
  action: FiltersAction,
  t: NativeTranslate
): HTMLDialogElement {
  let draft = { ...current };
  const dialog = element("dialog", undefined, "admin-dialog blacklist-native-filters-dialog");
  dialog.setAttribute("aria-label", t("users_filters_title"));
  const close = control("×", "admin-btn-icon");
  close.setAttribute("aria-label", t("close_menu"));
  close.addEventListener("click", () => dialog.close());
  const head = element("div", undefined, "blacklist-native-dialog-head");
  head.append(element("h3", t("users_filters_title")), close);
  const fields = element("div", undefined, "blacklist-native-dialog-fields");
  const renderFields = () =>
    fields.replaceChildren(
      ...descriptions.map((item) =>
        selectFilter(item, draft[item.key], (patch) => Object.assign(draft, patch), "mobile-")
      )
    );
  dialog.addEventListener("close", () => {
    draft = { ...current };
    renderFields();
  });
  renderFields();
  const reset = control(t("reset"), "admin-btn-ghost");
  reset.addEventListener("click", () => {
    for (const item of descriptions) draft[item.key] = MATCH_FILTERS[item.key];
    renderFields();
  });
  const done = control(t("done"), "admin-btn-primary");
  done.addEventListener("click", () => {
    const patch = { ...draft };
    dialog.close();
    if (descriptions.some((item) => patch[item.key] !== current[item.key])) action(patch);
  });
  const buttons = element("div", undefined, "blacklist-native-dialog-buttons");
  buttons.append(reset, done);
  dialog.append(head, fields, buttons);
  return dialog;
}

export function matchesToolbar(
  page: MatchPage,
  filters: MatchFilters,
  draft: string,
  props: Props,
  onInput: (text: string) => void,
  change: FiltersAction
): HTMLElement {
  const t = nativeTranslator(props);
  const visible = filterDescriptions(page, filters, language(props), t);
  const active = visible.filter((item) => filters[item.key] !== MATCH_FILTERS[item.key]);
  const toolbar = element("form", undefined, "admin-list-toolbar admin-users-toolbar");
  toolbar.setAttribute("role", "search");
  const input = element("input", undefined, "input");
  input.name = "search";
  input.type = "search";
  input.maxLength = 256;
  input.value = draft;
  input.placeholder = t("users_search_placeholder");
  input.setAttribute("aria-label", input.placeholder);
  input.addEventListener("input", () => onInput(input.value));
  const search = element("div", undefined, "admin-list-toolbar-search");
  const find = control(t("find"), "admin-users-search-button");
  find.type = "submit";
  toolbar.addEventListener("submit", (event) => {
    event.preventDefault();
    change({ q: input.value.trim() });
  });
  const dialog = filterDialog(visible, filters, change, t);
  const toggle = control(
    t("filters"),
    `blacklist-native-filter-toggle${active.length ? " admin-btn-primary" : ""}`
  );
  toggle.setAttribute("aria-haspopup", "dialog");
  toggle.setAttribute("aria-label", t("users_filters_open"));
  toggle.setAttribute("aria-expanded", "false");
  toggle.addEventListener("click", () => {
    dialog.showModal();
    toggle.setAttribute("aria-expanded", "true");
  });
  dialog.addEventListener("close", () => toggle.setAttribute("aria-expanded", "false"));
  search.append(input, find, toggle);
  const filtersRow = element("div", undefined, "admin-list-toolbar-filters");
  filtersRow.append(...visible.map((item) => selectFilter(item, filters[item.key], change)));
  const total = element("div", undefined, "admin-list-toolbar-summary");
  total.append(element("span", t("total")), element("strong", String(page.total)));
  const controls = element("div", undefined, "admin-list-toolbar-controls");
  controls.append(filtersRow, total, referralGraph(props, t));
  toolbar.append(search, controls);
  if (active.length) {
    const tags = element("div", undefined, "admin-users-filter-chips");
    tags.setAttribute("aria-label", t("active_filters"));
    for (const item of active) {
      const tag = element("span", undefined, "admin-users-filter-chip");
      const value = item.options.find((option) => option.value === filters[item.key]);
      const remove = element("button", "×");
      remove.type = "button";
      remove.setAttribute("aria-label", t("clear_filter", { label: item.label }));
      remove.addEventListener("click", () => change({ [item.key]: MATCH_FILTERS[item.key] }));
      tag.append(
        element("strong", item.label),
        element("span", value?.label || filters[item.key]),
        remove
      );
      tags.append(tag);
    }
    toolbar.append(tags);
  }
  toolbar.append(element("p", t("users_tariff_history_hint"), "admin-users-tariff-hint"), dialog);
  return toolbar;
}

function visiblePages(active: number, count: number): number[] {
  const pages = new Set([1, count, active - 1, active, active + 1]);
  if (active < 4) {
    pages.add(2);
    pages.add(3);
  }
  if (active > count - 3) {
    pages.add(count - 1);
    pages.add(count - 2);
  }
  return [...pages].filter((page) => page > 0 && page <= count).sort((left, right) => left - right);
}

export function matchesPagination(
  offset: number,
  total: number,
  rows: number,
  props: Props,
  load: (offset: number) => void
): HTMLElement {
  const t = nativeTranslator(props);
  const page = offset / MATCH_PAGE_SIZE + 1;
  const count = Math.max(1, Math.ceil(total / MATCH_PAGE_SIZE));
  const pagination = element("div", undefined, "admin-pagination");
  const summary = element("div", undefined, "admin-pagination-summary");
  summary.append(
    element(
      "span",
      `${t("page_short")} ${page} ${t("pagination_of")} ${count}`,
      "admin-pagination-count"
    ),
    element("span", `${t("total")} ${total}`, "admin-pagination-count")
  );
  if (rows) {
    const range = translator(props)("count_range", {
      start: offset + 1,
      end: offset + rows,
      total,
    });
    const detail = element("span", range, "blacklist-native-sr-only");
    detail.setAttribute("role", "status");
    summary.append(detail);
  }
  const go = (selected: number) => {
    if (selected !== page) load((selected - 1) * MATCH_PAGE_SIZE);
  };
  const previous = control(`‹ ${t("back")}`, "admin-pagination-nav admin-btn-sm");
  previous.name = "previous";
  previous.disabled = page === 1;
  previous.addEventListener("click", () => go(page - 1));
  const next = control(`${t("next")} ›`, "admin-pagination-nav admin-btn-sm");
  next.name = "next";
  next.disabled = page === count;
  next.addEventListener("click", () => go(page + 1));
  const pages = element("div", undefined, "admin-pagination-pages");
  let last = 0;
  for (const number of visiblePages(page, count)) {
    if (number > last + 1) pages.append(element("span", "…", "admin-pagination-ellipsis"));
    const pageButton = control(
      String(number),
      `admin-pagination-page admin-btn-sm${number === page ? " is-active" : ""}`
    );
    pageButton.name = `page-${number}`;
    pageButton.setAttribute("aria-label", `${t("page_short")} ${number}`);
    if (number === page) pageButton.setAttribute("aria-current", "page");
    pageButton.addEventListener("click", () => go(number));
    pages.append(pageButton);
    last = number;
  }
  const buttons = element("div", undefined, "admin-pagination-buttons");
  buttons.append(previous, pages, next);
  const jump = element("form", undefined, "admin-pagination-jump");
  const label = element("label", undefined, "admin-pagination-jump-label");
  const input = element("input", undefined, "admin-pagination-jump-input");
  input.name = "admin-pagination-jump";
  input.type = "number";
  input.min = "1";
  input.max = String(count);
  input.step = "1";
  input.inputMode = "numeric";
  input.placeholder = String(page);
  input.setAttribute("aria-label", t("pagination_jump_aria"));
  label.append(element("span", t("page_short")), input);
  const submit = control("→", "admin-pagination-jump-button admin-btn-sm");
  submit.type = "submit";
  submit.title = t("pagination_go");
  submit.setAttribute("aria-label", submit.title);
  submit.disabled = true;
  const canJump = () => input.value !== "" && input.checkValidity();
  input.addEventListener("input", () => {
    submit.disabled = !canJump();
  });
  jump.addEventListener("submit", (event) => {
    event.preventDefault();
    if (canJump()) go(Number(input.value));
  });
  jump.append(label, submit);
  pagination.append(summary, buttons, jump);
  return pagination;
}
