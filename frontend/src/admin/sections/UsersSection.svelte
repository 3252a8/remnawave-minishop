<script lang="ts">
  import { Input } from "$components/ui/index.js";
  import {
    ArrowDown,
    ArrowUp,
    ChevronsUpDown,
    DollarSign,
    Sliders,
    X,
    UsersRound,
  } from "$components/ui/icons.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { Label } from "$components/ui/primitives.js";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminPagination,
    AdminSelect,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import { getContext, onMount } from "svelte";
  import { trafficOfLabel } from "../../lib/admin/format.js";
  import { TableHandler } from "@vincjo/datatables";
  import type { AdminUser, UsersStore } from "../../lib/admin/stores/usersStore";

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
    panelStatusBadge?: (user: AdminUser) => Record<string, string>;
    resolvedAvatarUrl?: (user: AdminUser) => string;
    userDisplayName?: (user: AdminUser) => string;
    userInitials?: (user: AdminUser) => string;
    userSecondaryName?: (user: AdminUser) => string;
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
  }: UsersSectionProps = $props();

  const usersStore = getContext<UsersStore>("usersStore");
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
    { value: "all", label: at("filter_all", {}, "Все") },
    { value: "active", label: at("filter_not_banned", {}, "Не забанены") },
    { value: "banned", label: at("filter_banned", {}, "Забанены") },
    { value: "tg_linked", label: at("filter_tg_linked", {}, "С Telegram") },
    { value: "no_tg", label: at("filter_no_tg", {}, "Без Telegram") },
    { value: "email_linked", label: at("filter_email_linked", {}, "С email") },
    { value: "no_email", label: at("filter_no_email", {}, "Без email") },
    { value: "panel_linked", label: at("filter_panel_linked", {}, "С панелью") },
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
    { value: "all", label: at("panel_status_all", {}, "Все статусы") },
    { value: "active", label: at("status_active", {}, "active") },
    { value: "expired", label: at("status_expired", {}, "expired") },
    { value: "limited", label: at("status_limited", {}, "limited") },
  ] satisfies SelectOption[]);

  const USERS_PREMIUM_TRAFFIC_OPTIONS = $derived([
    { value: "all", label: at("premium_traffic_filter_all", {}, "Все (премиум)") },
    { value: "none", label: at("premium_traffic_filter_none", {}, "Без лимита в тарифе") },
    {
      value: "unlimited",
      label: at("premium_traffic_filter_unlimited", {}, "Безлимит (оверрайд)"),
    },
    { value: "good", label: at("premium_traffic_filter_good", {}, "Премиум: норма") },
    { value: "warn", label: at("premium_traffic_filter_warn", {}, "Премиум: мало") },
    { value: "critical", label: at("premium_traffic_filter_critical", {}, "Премиум: исчерпан") },
  ] satisfies SelectOption[]);

  function optionLabel(options: SelectOption[], value: string): string {
    return options.find((item) => item.value === value)?.label || value;
  }

  function updateUsersFilterState(patch: FilterPatch): void {
    usersStore.updateState({ ...patch, usersPage: 0 });
    void usersStore.loadUsers();
  }

  const updateUsersFilter = ((value: string) =>
    updateUsersFilterState({ usersFilter: value })) as ComponentCallback;
  const updateUsersPanelStatus = ((value: string) =>
    updateUsersFilterState({ usersPanelStatus: value })) as ComponentCallback;
  const updateUsersPremiumTraffic = ((value: string) =>
    updateUsersFilterState({ usersPremiumTraffic: value })) as ComponentCallback;
  const updateToolbarUsersFilter = ((value: string) => {
    usersStore.updateState({ usersFilter: value, usersPage: 0 });
    void usersStore.loadUsers();
  }) as ComponentCallback;
  const updateToolbarPanelStatus = ((value: string) => {
    usersStore.updateState({ usersPanelStatus: value, usersPage: 0 });
    void usersStore.loadUsers();
  }) as ComponentCallback;
  const updateToolbarPremiumTraffic = ((value: string) => {
    usersStore.updateState({ usersPremiumTraffic: value, usersPage: 0 });
    void usersStore.loadUsers();
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

  function premiumTrafficBadgeVariant(pt: TrafficBadge): string {
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
      { key: "user", label: at("user", {}, "Пользователь"), sort: SORT_COLUMNS.user },
      {
        key: "premium",
        label: at("premium_traffic_filter_label", {}, "Премиум трафик"),
        sort: SORT_COLUMNS.premium,
      },
      {
        key: "paymentsTotal",
        label: at("users_col_payments_total", {}, "Сумма платежей"),
        sort: SORT_COLUMNS.paymentsTotal,
      },
      {
        key: "paymentsCount",
        label: at("users_col_payments_count", {}, "Платежи"),
        sort: SORT_COLUMNS.paymentsCount,
      },
      {
        key: "invited",
        label: at("users_col_invited", {}, "Приглашенные"),
        sort: SORT_COLUMNS.invited,
      },
      { key: "status", label: at("status", {}, "Статус") },
      {
        key: "subscriptionExpires",
        label: at("users_col_subscription_expires", {}, "Истекает"),
        sort: SORT_COLUMNS.subscriptionExpires,
      },
      {
        key: "registration",
        label: at("users_col_registration", {}, "Регистрация"),
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
    if (state === "ascending") return at("sort_ascending", {}, "По возрастанию");
    if (state === "descending") return at("sort_descending", {}, "По убыванию");
    return at("sort_off", {}, "Без сортировки");
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
          label: at("filter", {}, "Фильтр"),
          value: optionLabel(USERS_FILTER_OPTIONS, usersFilter),
        },
        usersPanelStatus !== "all" && {
          key: "usersPanelStatus",
          label: at("panel_status", {}, "Статус панели"),
          value: optionLabel(USERS_PANEL_STATUS_OPTIONS, usersPanelStatus),
        },
        usersPremiumTraffic !== "all" && {
          key: "usersPremiumTraffic",
          label: at("premium_traffic_filter_label", {}, "Премиум трафик"),
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

{#snippet renderUserFilterControls()}
  <Label.Root class="admin-toolbar-field admin-users-filter-field">
    <span class="admin-toolbar-field-label">{at("filter", {}, "Фильтр")}</span>
    <AdminSelect
      value={usersFilter}
      items={USERS_FILTER_OPTIONS}
      class="admin-toolbar-select"
      ariaLabel={at("filter", {}, "Фильтр")}
      onValueChange={updateUsersFilter}
    />
  </Label.Root>

  <Label.Root class="admin-toolbar-field admin-users-filter-field">
    <span class="admin-toolbar-field-label">{at("panel_status", {}, "Статус панели")}</span>
    <AdminSelect
      value={usersPanelStatus}
      items={USERS_PANEL_STATUS_OPTIONS}
      class="admin-toolbar-select"
      ariaLabel={at("panel_status", {}, "Статус панели")}
      onValueChange={updateUsersPanelStatus}
    />
  </Label.Root>

  <Label.Root class="admin-toolbar-field admin-users-filter-field">
    <span class="admin-toolbar-field-label"
      >{at("premium_traffic_filter_label", {}, "Премиум трафик")}</span
    >
    <AdminSelect
      value={usersPremiumTraffic}
      items={USERS_PREMIUM_TRAFFIC_OPTIONS}
      class="admin-toolbar-select"
      ariaLabel={at("premium_traffic_filter_label", {}, "Премиум трафик")}
      onValueChange={updateUsersPremiumTraffic}
    />
  </Label.Root>
{/snippet}

{#snippet renderActiveUserFilterChips()}
  {#if activeUsersFilterCount}
    <div class="admin-users-filter-chips" aria-label={at("active_filters", {}, "Активные фильтры")}>
      {#each activeUserFilterChips as chip (chip.key)}
        <span class="admin-users-filter-chip">
          <span class="admin-users-filter-chip-text">
            <strong>{chip.label}</strong>
            <span>{chip.value}</span>
          </span>
          <button
            type="button"
            aria-label={at("clear_filter", { label: chip.label }, "Сбросить фильтр")}
            onclick={() => clearUsersFilter(chip.key)}
          >
            <X size={12} />
          </button>
        </span>
      {/each}
    </div>
  {/if}
{/snippet}

<div class="admin-toolbar admin-toolbar-users">
  <div class="admin-toolbar-search">
    <Input
      type="search"
      class="input"
      placeholder={at("users_search_placeholder", {}, "ID, @username или email")}
      value={usersQuery}
      oninput={handleUsersSearchInput}
      onkeydown={handleUsersSearchKeydown}
    />
    <AdminButton
      variant="primary"
      class="admin-users-search-button"
      onclick={() => {
        usersStore.updateState({ usersPage: 0 });
        usersStore.loadUsers();
      }}>{at("find", {}, "Найти")}</AdminButton
    >
    <AdminButton
      variant={activeUsersFilterCount ? "primary" : "default"}
      class="admin-users-filter-toggle"
      aria-label={at("users_filters_open", {}, "Открыть фильтры")}
      aria-haspopup="dialog"
      aria-expanded={usersFilterSheetOpen}
      onclick={() => {
        usersFilterSheetOpen = true;
      }}
    >
      <Sliders size={15} />
      <span class="admin-users-filter-toggle-label">{at("filters", {}, "Фильтры")}</span>
      {#if activeUsersFilterCount}
        <span class="admin-users-filter-count">{activeUsersFilterCount}</span>
      {/if}
    </AdminButton>
  </div>

  <div class="admin-toolbar-controls">
    <Label.Root class="admin-toolbar-field">
      <span class="admin-toolbar-field-label">{at("filter", {}, "Фильтр")}</span>
      <AdminSelect
        value={usersFilter}
        items={USERS_FILTER_OPTIONS}
        class="admin-toolbar-select"
        ariaLabel={at("filter", {}, "Фильтр")}
        onValueChange={updateToolbarUsersFilter}
      />
    </Label.Root>

    <Label.Root class="admin-toolbar-field">
      <span class="admin-toolbar-field-label">{at("panel_status", {}, "Статус панели")}</span>
      <AdminSelect
        value={usersPanelStatus}
        items={USERS_PANEL_STATUS_OPTIONS}
        class="admin-toolbar-select"
        ariaLabel={at("panel_status", {}, "Статус панели")}
        onValueChange={updateToolbarPanelStatus}
      />
    </Label.Root>

    <Label.Root class="admin-toolbar-field">
      <span class="admin-toolbar-field-label"
        >{at("premium_traffic_filter_label", {}, "Премиум трафик")}</span
      >
      <AdminSelect
        value={usersPremiumTraffic}
        items={USERS_PREMIUM_TRAFFIC_OPTIONS}
        class="admin-toolbar-select"
        ariaLabel={at("premium_traffic_filter_label", {}, "Премиум трафик")}
        onValueChange={updateToolbarPremiumTraffic}
      />
    </Label.Root>

    <div class="admin-toolbar-summary">
      <span class="admin-toolbar-field-label">{at("total", {}, "Всего")}</span>
      <strong>{usersTotal}</strong>
    </div>
  </div>

  {@render renderActiveUserFilterChips()}
</div>

<Dialog
  open={usersFilterSheetOpen}
  class="admin-dialog admin-users-filter-dialog"
  title={at("users_filters_title", {}, "Фильтры пользователей")}
  description={at("users_filters_description", {}, "Уточните список пользователей")}
  closeLabel={at("close_menu", {}, "Закрыть меню")}
  onclose={() => {
    usersFilterSheetOpen = false;
  }}
>
  <div class="admin-users-filter-sheet-body">
    <div class="admin-users-filter-fields admin-users-filter-fields-sheet">
      {@render renderUserFilterControls()}
    </div>
    {@render renderActiveUserFilterChips()}
    <div class="admin-users-filter-sheet-actions">
      <AdminButton
        variant="ghost"
        disabled={activeUsersFilterCount === 0}
        onclick={resetUsersFilters}
      >
        {at("reset", {}, "Сбросить")}
      </AdminButton>
      <AdminButton
        variant="primary"
        onclick={() => {
          usersFilterSheetOpen = false;
        }}
      >
        {at("done", {}, "Готово")}
      </AdminButton>
    </div>
  </div>
</Dialog>

<div class="admin-users-table-wrap">
  {#if usersLoading}
    <AdminTableSkeleton
      headers={userTableHeaders}
      rows={USERS_PAGE_SIZE}
      widths={["220px", "128px", "112px", "78px", "88px", "96px", "112px", "112px"]}
    />
  {:else if !usersTable.rows.length}
    <AdminEmptyState tone="card"
      ><span class="admin-muted">{at("users_empty", {}, "Никого не найдено")}</span
      ></AdminEmptyState
    >
  {:else}
    <AdminTable class="admin-users-table">
      <thead>
        <tr>
          {#each userTableColumns() as column (column.key)}
            <th aria-sort={column.sort ? sortState(column.sort) : undefined}>
              {#if column.sort}
                <button
                  type="button"
                  class="admin-sort-header"
                  title={sortTitle(column.sort)}
                  onclick={() => toggleUsersSortForColumn(column)}
                >
                  <span>{column.label}</span>
                  <span
                    class="admin-sort-state"
                    data-state={sortState(column.sort)}
                    aria-hidden="true"
                  >
                    {#if sortState(column.sort) === "ascending"}
                      <ArrowUp size={13} />
                    {:else if sortState(column.sort) === "descending"}
                      <ArrowDown size={13} />
                    {:else}
                      <ChevronsUpDown size={13} />
                    {/if}
                  </span>
                </button>
              {:else}
                {column.label}
              {/if}
            </th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each usersTable.rows as user (user.user_id)}
          {@const avatar = resolvedAvatarUrl(user)}
          {@const badge = panelStatusBadge(user)}
          <tr
            class="is-clickable"
            role="button"
            tabindex="0"
            data-user-id={user.user_id}
            onclick={() => usersStore.openUser(user)}
            onkeydown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                usersStore.openUser(user);
              }
            }}
          >
            <td class="admin-users-cell-user" data-label={at("user", {}, "Пользователь")}>
              <div class="admin-users-cell-user-inner">
                <span class="admin-avatar admin-avatar-sm">
                  {#if avatar}
                    <img src={avatar} alt="" loading="lazy" referrerpolicy="no-referrer" />
                  {:else}
                    <span>{userInitials(user)}</span>
                  {/if}
                </span>
                <div class="admin-users-cell-user-text">
                  <span class="admin-users-cell-name">{userDisplayName(user)}</span>
                  <span class="admin-users-cell-secondary">{userSecondaryName(user)}</span>
                  <span class="admin-users-cell-id">#{user.user_id}</span>
                </div>
              </div>
            </td>
            <td
              class="admin-users-cell-premium"
              data-label={at("premium_traffic_filter_label", {}, "Премиум трафик")}
            >
              {#if user.premium_traffic && user.premium_traffic.state !== "none"}
                <AdminBadge
                  variant={premiumTrafficBadgeVariant(user.premium_traffic)}
                  class="admin-user-premium-badge"
                >
                  {premiumTrafficBadgeText(user.premium_traffic)}
                </AdminBadge>
              {:else}
                <span class="admin-user-premium-placeholder"
                  >{at("premium_traffic_na", {}, "—")}</span
                >
              {/if}
            </td>
            <td
              class="admin-users-cell-money"
              data-label={at("users_col_payments_total", {}, "Сумма платежей")}
            >
              <AdminBadge variant="success" class="admin-user-money-badge">
                {rowPaymentsTotal(user)}
              </AdminBadge>
            </td>
            <td
              class="admin-users-cell-counter"
              data-label={at("users_col_payments_count", {}, "Платежи")}
            >
              <span class="admin-user-counter">
                <DollarSign size={12} />
                <span>{user.payments_count ?? 0}</span>
              </span>
            </td>
            <td
              class="admin-users-cell-counter"
              data-label={at("users_col_invited", {}, "Приглашенные")}
            >
              <span class="admin-user-counter">
                <UsersRound size={13} />
                <span>{user.invited_users_count ?? 0}</span>
              </span>
            </td>
            <td data-label={at("status", {}, "Статус")}>
              <AdminBadge variant={badge.variant}>{badge.label}</AdminBadge>
            </td>
            <td
              class="admin-users-cell-date admin-cell-mono"
              data-label={at("users_col_subscription_expires", {}, "Истекает")}
            >
              {fmtDateShort(user.subscription_expires_at || user.panel_status_expired_at)}
            </td>
            <td
              class="admin-users-cell-date admin-cell-mono"
              data-label={at("users_col_registration", {}, "Регистрация")}
            >
              {fmtDateShort(user.registration_date)}
            </td>
          </tr>
        {/each}
      </tbody>
    </AdminTable>
  {/if}
</div>

<AdminPagination
  page={usersPage}
  pageCount={usersPageCount}
  total={usersTotal}
  pageLabel={at("page_short", {}, "Стр.")}
  ofLabel={at("pagination_of", {}, "из")}
  totalLabel={at("total", {}, "Всего")}
  jumpLabel={at("page_short", {}, "Стр.")}
  jumpAriaLabel={at("pagination_jump_aria", {}, "Перейти к странице")}
  goLabel={at("pagination_go", {}, "Перейти")}
  prevLabel={at("back", {}, "Назад")}
  nextLabel={at("next", {}, "Далее")}
  onPageChange={(page) => {
    usersStore.updateState({ usersPage: page });
    usersStore.loadUsers();
  }}
/>

<style>
  :global(.admin-toolbar-users .admin-toolbar-controls) {
    grid-template-columns: repeat(3, minmax(150px, 1fr)) minmax(82px, auto);
    gap: 10px;
  }

  :global(.admin-users-search-button) {
    min-width: 82px;
  }

  :global(.admin-btn.admin-users-filter-toggle) {
    display: none;
    position: relative;
    align-items: center;
    gap: 7px;
    min-width: 0;
  }

  .admin-users-filter-count {
    display: inline-grid;
    min-width: 18px;
    height: 18px;
    place-items: center;
    padding: 0 5px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--admin-bg) 74%, transparent);
    color: inherit;
    font-size: 11px;
    font-weight: 750;
    line-height: 1;
  }

  .admin-users-filter-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    min-width: 0;
  }

  .admin-users-filter-chip {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    max-width: 100%;
    min-height: 28px;
    padding: 3px 5px 3px 10px;
    border: 1px solid var(--admin-border);
    border-radius: 999px;
    background: color-mix(in srgb, var(--admin-muted) 8%, transparent);
    color: var(--admin-text);
    font-size: 12px;
  }

  .admin-users-filter-chip-text {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    min-width: 0;
    max-width: 260px;
  }

  .admin-users-filter-chip strong {
    color: var(--admin-muted);
    font-size: 11px;
    font-weight: 650;
  }

  .admin-users-filter-chip-text > span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-users-filter-chip button {
    display: inline-grid;
    width: 20px;
    height: 20px;
    place-items: center;
    border: 0;
    border-radius: 999px;
    background: transparent;
    color: var(--admin-muted);
    cursor: pointer;
  }

  .admin-users-filter-chip button:hover,
  .admin-users-filter-chip button:focus-visible {
    background: color-mix(in srgb, var(--admin-muted) 14%, transparent);
    color: var(--admin-text);
    outline: none;
  }

  .admin-users-filter-fields-sheet,
  .admin-users-filter-sheet-body {
    display: grid;
    gap: 12px;
  }

  .admin-users-filter-sheet-actions {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 8px;
    padding-top: 2px;
  }

  :global(.admin-users-filter-dialog) {
    width: min(100%, 420px);
  }

  .admin-users-table-wrap :global(.admin-table-wrap) {
    overflow-x: auto;
  }

  .admin-users-table-wrap :global(.admin-users-table) {
    min-width: 1080px;
  }

  .admin-sort-header {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    max-width: 100%;
    margin: -4px -6px;
    padding: 4px 6px;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: inherit;
    font: inherit;
    letter-spacing: inherit;
    text-transform: inherit;
    cursor: pointer;
  }

  .admin-sort-header:hover,
  .admin-sort-header:focus-visible {
    color: var(--admin-text);
    background: color-mix(in srgb, var(--admin-muted) 10%, transparent);
    outline: none;
  }

  .admin-sort-header:focus-visible {
    box-shadow: 0 0 0 2px var(--admin-ring);
  }

  .admin-sort-state {
    display: inline-flex;
    align-items: center;
    color: var(--admin-dim);
  }

  .admin-sort-state[data-state="ascending"],
  .admin-sort-state[data-state="descending"] {
    color: color-mix(in srgb, var(--accent) 72%, var(--admin-muted));
  }

  .admin-users-cell-user-inner {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .admin-users-cell-user-text {
    display: grid;
    gap: 2px;
    min-width: 0;
    text-align: left;
  }

  .admin-users-cell-name {
    font-weight: 650;
    font-size: 13px;
    line-height: 1.25;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-users-cell-secondary {
    font-size: 11px;
    color: var(--admin-dim);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-users-cell-id {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--admin-muted);
  }

  .admin-users-cell-premium {
    white-space: nowrap;
  }

  .admin-users-cell-premium :global(.admin-user-premium-badge) {
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 11px;
    font-variant-numeric: tabular-nums;
  }

  .admin-user-premium-placeholder {
    color: var(--admin-dim);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }

  .admin-users-cell-money,
  .admin-users-cell-counter {
    white-space: nowrap;
  }

  .admin-users-cell-money :global(.admin-user-money-badge) {
    font-variant-numeric: tabular-nums;
  }

  .admin-user-counter {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    color: var(--admin-text);
    font-size: 12px;
    font-weight: 650;
    font-variant-numeric: tabular-nums;
  }

  .admin-user-counter :global(svg) {
    color: var(--admin-muted);
    flex: 0 0 auto;
  }

  .admin-users-cell-date {
    white-space: nowrap;
    font-size: 12px;
    color: var(--admin-muted);
  }

  .admin-users-table-wrap :global(.admin-users-table tbody tr.is-clickable:focus-visible) {
    outline: 2px solid var(--admin-ring);
    outline-offset: -2px;
  }

  @media (max-width: 720px) {
    :global(.admin-toolbar-users .admin-toolbar-search) {
      grid-template-columns: minmax(0, 1fr) auto auto;
    }

    :global(.admin-toolbar-users .admin-toolbar-controls) {
      display: none;
    }

    :global(.admin-users-search-button) {
      min-width: 0;
      padding-inline: 10px;
    }

    :global(.admin-btn.admin-users-filter-toggle) {
      display: inline-flex;
      min-width: 38px;
      padding-inline: 10px;
    }

    .admin-users-filter-toggle-label {
      display: none;
    }

    .admin-users-filter-chips {
      gap: 5px;
    }

    .admin-users-filter-chip-text {
      max-width: min(250px, calc(100vw - 96px));
    }

    :global(.dialog:has(.admin-users-filter-dialog)) {
      align-items: end;
      padding: max(12px, env(safe-area-inset-top)) 0 0;
    }

    :global(.admin-users-filter-dialog) {
      width: 100%;
      max-height: min(82dvh, 620px);
      padding: 16px;
      border-right: 0;
      border-bottom: 0;
      border-left: 0;
      border-radius: 18px 18px 0 0;
    }

    .admin-users-table-wrap :global(.admin-users-table thead) {
      display: table-header-group;
    }

    .admin-users-table-wrap :global(.admin-users-table tbody tr) {
      display: table-row;
      padding: 0;
      border-bottom: 0;
    }

    .admin-users-table-wrap :global(.admin-users-table tbody tr:last-child td) {
      border-bottom: 0;
    }

    .admin-users-table-wrap :global(.admin-users-table tbody td) {
      display: table-cell;
      padding: 12px 16px;
      border-bottom: 1px solid var(--admin-border);
    }

    .admin-users-table-wrap :global(.admin-users-table tbody td::before) {
      content: none;
    }
  }
</style>
