<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import { onMount } from "svelte";
  import { trafficOfLabel } from "../../lib/admin/format.js";
  import { TableHandler } from "@vincjo/datatables";
  import UsersView from "./users/UsersView.svelte";
  import type { AdminUser } from "../../lib/admin/stores/usersStore";
  import {
    normalizeUsersRouteFilters,
    type UsersRouteFilters,
  } from "../../lib/admin/usersRouteFilters";
  import type { AdminBadgeVariant } from "$components/patterns/admin/types";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type SelectOption = { value: string; label: string };
  type SortColumn = {
    asc: string;
    desc: string;
    defaultDirection: "asc" | "desc";
  };
  type UserTableColumn = {
    key: string;
    label: string;
    sort?: SortColumn;
  };
  type ComponentCallback = () => void;
  type FilterKey = "usersFilter" | "usersPanelStatus" | "usersPremiumTraffic";
  type FilterPatch = Partial<Record<FilterKey, string>> & { usersPage?: number };
  type FilterChip = { key: FilterKey; label: string; value: string };
  type UsersSectionProps = {
    at?: TranslateFn;
    fmtDateShort?: (value: string | null | undefined) => string;
    fmtMoney?: (value: number, currency?: string | null) => string;
    panelStatusBadge?: (user: AdminUser) => { label?: string; variant?: AdminBadgeVariant };
    resolvedAvatarUrl?: (user: AdminUser) => string;
    userDisplayName?: (user: AdminUser) => string;
    userInitials?: (user: AdminUser) => string;
    userSecondaryName?: (user: AdminUser) => string;
    onUsersFiltersChange?: (filters: UsersRouteFilters) => void;
  };
  type TrafficBadge =
    | {
        state?: string;
        used_bytes?: number | string | null;
        limit_bytes?: number | string | null;
      }
    | null
    | undefined;

  let {
    at = (key) => key,
    fmtDateShort = (value) => String(value || ""),
    fmtMoney = (value) => String(value),
    panelStatusBadge = () => ({}),
    resolvedAvatarUrl = () => "",
    userDisplayName = () => "",
    userInitials = () => "",
    userSecondaryName = () => "",
    onUsersFiltersChange = () => {},
  }: UsersSectionProps = $props();

  const usersStore = getUsersStore();
  const usersTable = new TableHandler<AdminUser>();
  const usersState = $derived(usersStore);
  const users = $derived(usersState.users);
  const usersTotal = $derived(usersState.usersTotal);
  const usersPage = $derived(usersState.usersPage);
  const usersQuery = $derived(usersState.usersQuery);
  const usersFilter = $derived(usersState.usersFilter);
  const usersPanelStatus = $derived(usersState.usersPanelStatus);
  const usersPremiumTraffic = $derived(usersState.usersPremiumTraffic);
  const usersSort = $derived(usersState.usersSort);
  const usersLoading = $derived(usersState.usersLoading);

  $effect(() => {
    usersTable.setRows(users);
  });

  const USERS_PAGE_SIZE = 25;
  let usersFilterSheetOpen = $state(false);
  const usersPageCount = $derived(
    Math.max(1, Math.ceil(Number(usersTotal || 0) / USERS_PAGE_SIZE))
  );

  const USERS_FILTER_OPTIONS = $derived([
    { value: "all", label: at("filter_all", {}, "All") },
    { value: "active", label: at("filter_not_banned", {}, "Not banned") },
    { value: "banned", label: at("filter_banned", {}, "Banned") },
    { value: "active_today", label: at("filter_active_today", {}, "Registered today") },
    { value: "referred", label: at("filter_referred", {}, "Referred users") },
    {
      value: "active_subscription",
      label: at("filter_active_subscription", {}, "With active subscription"),
    },
    { value: "paid", label: at("stats_label_paid_subs", {}, "Paid users") },
    { value: "free", label: at("stats_label_free_users", {}, "With free subscription") },
    { value: "trial", label: at("stats_label_trial_users", {}, "With trial subscription") },
    {
      value: "inactive_subscription",
      label: at("filter_inactive_subscription", {}, "Without active subscription"),
    },
    {
      value: "expired_subscription",
      label: at("filter_expired_subscription", {}, "With expired subscription"),
    },
    { value: "tg_linked", label: at("filter_tg_linked", {}, "With Telegram") },
    { value: "no_tg", label: at("filter_no_tg", {}, "No Telegram") },
    { value: "email_linked", label: at("filter_email_linked", {}, "With email") },
    { value: "no_email", label: at("filter_no_email", {}, "No email") },
    { value: "panel_linked", label: at("filter_panel_linked", {}, "With panel") },
  ] satisfies SelectOption[]);

  const SORT_COLUMNS = {
    user: { asc: "name_asc", desc: "name_desc", defaultDirection: "asc" },
    premium: { asc: "premium_ratio_asc", desc: "premium_ratio_desc", defaultDirection: "desc" },
    paymentsTotal: {
      asc: "payments_total_asc",
      desc: "payments_total_desc",
      defaultDirection: "desc",
    },
    paymentsCount: {
      asc: "payments_count_asc",
      desc: "payments_count_desc",
      defaultDirection: "desc",
    },
    invited: {
      asc: "invited_users_count_asc",
      desc: "invited_users_count_desc",
      defaultDirection: "desc",
    },
    subscriptionExpires: {
      asc: "subscription_expires_at_asc",
      desc: "subscription_expires_at_desc",
      defaultDirection: "asc",
    },
    registration: { asc: "registered_asc", desc: "registered_desc", defaultDirection: "desc" },
  } satisfies Record<string, SortColumn>;

  const USERS_PANEL_STATUS_OPTIONS = $derived([
    { value: "all", label: at("panel_status_all", {}, "All statuses") },
    { value: "active", label: at("status_active", {}, "active") },
    { value: "expired", label: at("status_expired", {}, "expired") },
    { value: "limited", label: at("status_limited", {}, "limited") },
  ] satisfies SelectOption[]);

  const USERS_PREMIUM_TRAFFIC_OPTIONS = $derived([
    { value: "all", label: at("premium_traffic_filter_all", {}, "All") },
    { value: "none", label: at("premium_traffic_filter_none", {}, "No tariff limit") },
    {
      value: "unlimited",
      label: at("premium_traffic_filter_unlimited", {}, "Unlimited (override)"),
    },
    { value: "good", label: at("premium_traffic_filter_good", {}, "Premium: OK") },
    { value: "warn", label: at("premium_traffic_filter_warn", {}, "Premium: low") },
    { value: "critical", label: at("premium_traffic_filter_critical", {}, "Premium: depleted") },
  ] satisfies SelectOption[]);

  function optionLabel(options: SelectOption[], value: string): string {
    return options.find((item) => item.value === value)?.label || value;
  }

  function updateUsersFilterState(patch: FilterPatch): void {
    const filters = normalizeUsersRouteFilters({
      usersFilter: patch.usersFilter ?? usersFilter,
      usersPanelStatus: patch.usersPanelStatus ?? usersPanelStatus,
      usersPremiumTraffic: patch.usersPremiumTraffic ?? usersPremiumTraffic,
    });
    usersStore.updateState({ ...patch, usersPage: 0 });
    onUsersFiltersChange(filters);
    void usersStore.loadUsers();
  }

  const updateUsersFilter = ((value: string) =>
    updateUsersFilterState({ usersFilter: value })) as ComponentCallback;
  const updateUsersPanelStatus = ((value: string) =>
    updateUsersFilterState({ usersPanelStatus: value })) as ComponentCallback;
  const updateUsersPremiumTraffic = ((value: string) =>
    updateUsersFilterState({ usersPremiumTraffic: value })) as ComponentCallback;
  const updateToolbarUsersFilter = ((value: string) => {
    updateUsersFilterState({ usersFilter: value });
  }) as ComponentCallback;
  const updateToolbarPanelStatus = ((value: string) => {
    updateUsersFilterState({ usersPanelStatus: value });
  }) as ComponentCallback;
  const updateToolbarPremiumTraffic = ((value: string) => {
    updateUsersFilterState({ usersPremiumTraffic: value });
  }) as ComponentCallback;

  function resetUsersFilters(): void {
    updateUsersFilterState({
      usersFilter: "all",
      usersPanelStatus: "all",
      usersPremiumTraffic: "all",
    });
  }

  function clearUsersFilter(key: FilterKey): void {
    if (key === "usersFilter") updateUsersFilterState({ usersFilter: "all" });
    if (key === "usersPanelStatus") updateUsersFilterState({ usersPanelStatus: "all" });
    if (key === "usersPremiumTraffic") updateUsersFilterState({ usersPremiumTraffic: "all" });
  }

  function isFilterChip(value: FilterChip | false): value is FilterChip {
    return Boolean(value);
  }

  function premiumTrafficBadgeVariant(pt: TrafficBadge): AdminBadgeVariant {
    if (!pt || pt.state === "none") return "muted";
    if (pt.state === "unlimited" || pt.state === "good") return "success";
    if (pt.state === "warn") return "warning";
    return "danger";
  }

  function premiumTrafficBadgeText(pt: TrafficBadge): string {
    if (!pt || pt.state === "none") return "";
    if (pt.state === "unlimited") return trafficOfLabel(pt.used_bytes, 0);
    return trafficOfLabel(pt.used_bytes, pt.limit_bytes);
  }

  function userTableColumns(): UserTableColumn[] {
    return [
      { key: "user", label: at("user", {}, "User"), sort: SORT_COLUMNS.user },
      {
        key: "premium",
        label: at("premium_traffic_filter_label", {}, "Premium traffic"),
        sort: SORT_COLUMNS.premium,
      },
      {
        key: "paymentsTotal",
        label: at("users_col_payments_total", {}, "Paid total"),
        sort: SORT_COLUMNS.paymentsTotal,
      },
      {
        key: "paymentsCount",
        label: at("users_col_payments_count", {}, "Payments"),
        sort: SORT_COLUMNS.paymentsCount,
      },
      {
        key: "invited",
        label: at("users_col_invited", {}, "Invited"),
        sort: SORT_COLUMNS.invited,
      },
      { key: "status", label: at("status", {}, "Status") },
      {
        key: "subscriptionExpires",
        label: at("users_col_subscription_expires", {}, "Expires"),
        sort: SORT_COLUMNS.subscriptionExpires,
      },
      {
        key: "registration",
        label: at("users_col_registration", {}, "Registered"),
        sort: SORT_COLUMNS.registration,
      },
    ];
  }

  function sortState(column: SortColumn | undefined): "none" | "ascending" | "descending" {
    if (!column) return "none";
    if (usersSort === column.asc) return "ascending";
    if (usersSort === column.desc) return "descending";
    return "none";
  }

  function nextSortValue(column: SortColumn): string {
    const state = sortState(column);
    const defaultValue = column[column.defaultDirection] || column.asc;
    if (state === "none") return defaultValue;
    if (usersSort === defaultValue) {
      return column.defaultDirection === "asc" ? column.desc : column.asc;
    }
    return "";
  }

  function toggleUsersSort(column: SortColumn): void {
    usersStore.updateState({ usersSort: nextSortValue(column), usersPage: 0 });
    void usersStore.loadUsers();
  }

  function toggleUsersSortForColumn(column: UserTableColumn): void {
    if (column.sort) toggleUsersSort(column.sort);
  }

  function sortTitle(column: SortColumn): string {
    const state = sortState(column);
    if (state === "ascending") return at("sort_ascending", {}, "Sorted ascending");
    if (state === "descending") return at("sort_descending", {}, "Sorted descending");
    return at("sort_off", {}, "Not sorted");
  }

  function rowPaymentsTotal(user: AdminUser): string {
    return fmtMoney(user?.payments_total_amount ?? 0, user?.payments_currency || "RUB");
  }

  function handleUsersSearchInput(event: Event): void {
    const input = event.currentTarget as HTMLInputElement | null;
    usersStore.updateState({ usersQuery: input?.value || "" });
  }

  function handleUsersSearchKeydown(event: KeyboardEvent): void {
    if (event.key !== "Enter") return;
    usersStore.updateState({ usersPage: 0 });
    void usersStore.loadUsers();
  }

  const activeUserFilterChips = $derived(
    (
      [
        usersFilter !== "all" && {
          key: "usersFilter",
          label: at("filter", {}, "Filter"),
          value: optionLabel(USERS_FILTER_OPTIONS, usersFilter),
        },
        usersPanelStatus !== "all" && {
          key: "usersPanelStatus",
          label: at("panel_status", {}, "Panel status"),
          value: optionLabel(USERS_PANEL_STATUS_OPTIONS, usersPanelStatus),
        },
        usersPremiumTraffic !== "all" && {
          key: "usersPremiumTraffic",
          label: at("premium_traffic_filter_label", {}, "Premium traffic"),
          value: optionLabel(USERS_PREMIUM_TRAFFIC_OPTIONS, usersPremiumTraffic),
        },
      ] satisfies (FilterChip | false)[]
    ).filter(isFilterChip)
  );
  const activeUsersFilterCount = $derived(activeUserFilterChips.length);
  const userTableHeaders = $derived(userTableColumns().map((column) => column.label));

  onMount(() => {
    usersStore.loadUsers();
  });
</script>

<UsersView
  {at}
  {usersStore}
  {usersTable}
  bind:usersFilterSheetOpen
  {usersFilter}
  {usersPanelStatus}
  {usersPremiumTraffic}
  {usersQuery}
  {usersTotal}
  {usersPage}
  {usersPageCount}
  {usersLoading}
  {USERS_PAGE_SIZE}
  {USERS_FILTER_OPTIONS}
  {USERS_PANEL_STATUS_OPTIONS}
  {USERS_PREMIUM_TRAFFIC_OPTIONS}
  {activeUsersFilterCount}
  {activeUserFilterChips}
  {userTableHeaders}
  {updateUsersFilter}
  {updateUsersPanelStatus}
  {updateUsersPremiumTraffic}
  {updateToolbarUsersFilter}
  {updateToolbarPanelStatus}
  {updateToolbarPremiumTraffic}
  {resetUsersFilters}
  {clearUsersFilter}
  {handleUsersSearchInput}
  {handleUsersSearchKeydown}
  {userTableColumns}
  {sortState}
  {sortTitle}
  {toggleUsersSortForColumn}
  {resolvedAvatarUrl}
  {panelStatusBadge}
  {userInitials}
  {userDisplayName}
  {userSecondaryName}
  {premiumTrafficBadgeVariant}
  {premiumTrafficBadgeText}
  {rowPaymentsTotal}
  {fmtDateShort}
/>
