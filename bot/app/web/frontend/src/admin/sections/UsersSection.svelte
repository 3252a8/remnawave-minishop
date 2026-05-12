<script>
  import { Label } from "$components/ui/primitives.js";
  import { AdminBadge, AdminButton, AdminEmptyState, AdminPagination, AdminSelect } from "$components/patterns/admin/index.js";
  import { getContext, onMount } from "svelte";

  export let at = (key) => key;
  export let fmtDateShort = (value) => value;
  export let panelStatusBadge = () => ({});
  export let resolvedAvatarUrl = () => "";
  export let userDisplayName = () => "";
  export let userInitials = () => "";
  export let userSecondaryName = () => "";

  const usersStore = getContext("usersStore");

  $: ({
    users,
    usersTotal,
    usersPage,
    usersQuery,
    usersFilter,
    usersPanelStatus,
    usersSort,
    usersLoading,
  } = $usersStore);

  const USERS_PAGE_SIZE = 25;
  $: usersHasMore = users.length === USERS_PAGE_SIZE;

  const USERS_FILTER_OPTIONS = [
    { value: "all", label: at("filter_all", {}, "Все") },
    { value: "active", label: at("filter_not_banned", {}, "Не забанены") },
    { value: "banned", label: at("filter_banned", {}, "Забанены") },
    { value: "tg_linked", label: at("filter_tg_linked", {}, "С Telegram") },
    { value: "no_tg", label: at("filter_no_tg", {}, "Без Telegram") },
    { value: "email_linked", label: at("filter_email_linked", {}, "С email") },
    { value: "no_email", label: at("filter_no_email", {}, "Без email") },
    { value: "panel_linked", label: at("filter_panel_linked", {}, "С панелью") },
  ];

  const USERS_SORT_OPTIONS = [
    { value: "registered_desc", label: at("sort_registered_desc", {}, "Сначала новые") },
    { value: "registered_asc", label: at("sort_registered_asc", {}, "Сначала старые") },
    { value: "name_asc", label: at("sort_name_asc", {}, "Имя ↑") },
    { value: "name_desc", label: at("sort_name_desc", {}, "Имя ↓") },
    { value: "id_asc", label: at("sort_id_asc", {}, "ID ↑") },
    { value: "id_desc", label: at("sort_id_desc", {}, "ID ↓") },
  ];

  const USERS_PANEL_STATUS_OPTIONS = [
    { value: "all", label: at("panel_status_all", {}, "Все статусы") },
    { value: "active", label: at("status_active", {}, "active") },
    { value: "expired", label: at("status_expired", {}, "expired") },
    { value: "limited", label: at("status_limited", {}, "limited") },
  ];

  onMount(() => {
    usersStore.loadUsers();
  });
</script>

<div class="admin-toolbar admin-toolbar-users">
  <div class="admin-toolbar-search">
    <input
      type="search"
      class="input"
      placeholder={at("users_search_placeholder", {}, "ID, @username или email")}
      value={usersQuery}
      on:input={(e) => usersStore.updateState({ usersQuery: e.target.value })}
      on:keydown={(e) => e.key === "Enter" && (usersStore.updateState({ usersPage: 0 }), usersStore.loadUsers())}
    />
    <AdminButton variant="primary" onclick={() => { usersStore.updateState({ usersPage: 0 }); usersStore.loadUsers(); }}>{at("find", {}, "Найти")}</AdminButton>
  </div>

  <div class="admin-toolbar-controls">
    <Label.Root class="admin-toolbar-field">
      <span class="admin-toolbar-field-label">{at("filter", {}, "Фильтр")}</span>
      <AdminSelect
        value={usersFilter}
        items={USERS_FILTER_OPTIONS}
        class="admin-toolbar-select"
        ariaLabel={at("filter", {}, "Фильтр")}
        onValueChange={(value) => { usersStore.updateState({ usersFilter: value, usersPage: 0 }); usersStore.loadUsers(); }}
      />
    </Label.Root>

    <Label.Root class="admin-toolbar-field">
      <span class="admin-toolbar-field-label">{at("panel_status", {}, "Статус панели")}</span>
      <AdminSelect
        value={usersPanelStatus}
        items={USERS_PANEL_STATUS_OPTIONS}
        class="admin-toolbar-select"
        ariaLabel={at("panel_status", {}, "Статус панели")}
        onValueChange={(value) => { usersStore.updateState({ usersPanelStatus: value, usersPage: 0 }); usersStore.loadUsers(); }}
      />
    </Label.Root>

    <Label.Root class="admin-toolbar-field">
      <span class="admin-toolbar-field-label">{at("sort", {}, "Сортировка")}</span>
      <AdminSelect
        value={usersSort}
        items={USERS_SORT_OPTIONS}
        class="admin-toolbar-select"
        ariaLabel={at("sort", {}, "Сортировка")}
        onValueChange={(value) => { usersStore.updateState({ usersSort: value, usersPage: 0 }); usersStore.loadUsers(); }}
      />
    </Label.Root>

    <div class="admin-toolbar-summary">
      <span class="admin-toolbar-field-label">{at("total", {}, "Всего")}</span>
      <strong>{usersTotal}</strong>
    </div>
  </div>
</div>

<div class="admin-table-wrap">
  {#if usersLoading}
    <ul class="admin-user-list admin-user-list-skeleton" aria-hidden="true">
      {#each Array(USERS_PAGE_SIZE) as _, i (i)}
        <li>
          <div class="admin-user-row admin-user-row-skeleton">
            <span class="admin-skeleton admin-skeleton-avatar"></span>
            <span class="admin-user-main">
              <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"></span>
              <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-soft"></span>
            </span>
            <span class="admin-user-side">
              <span class="admin-skeleton admin-skeleton-badge"></span>
              <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span>
            </span>
          </div>
        </li>
      {/each}
    </ul>
  {:else if !users.length}
    <AdminEmptyState tone="card"><span class="admin-muted">{at("users_empty", {}, "Никого не найдено")}</span></AdminEmptyState>
  {:else}
    <ul class="admin-user-list">
      {#each users as user}
        {@const avatar = resolvedAvatarUrl(user)}
        {@const badge = panelStatusBadge(user)}
        <li>
          <button type="button" class="admin-user-row" on:click={() => usersStore.openUser(user)}>
            <span class="admin-avatar admin-avatar-sm">
              {#if avatar}
                <img src={avatar} alt="" loading="lazy" referrerpolicy="no-referrer" />
              {:else}
                <span>{userInitials(user)}</span>
              {/if}
            </span>
            <span class="admin-user-main">
              <strong>{userDisplayName(user)}</strong>
              <small>{userSecondaryName(user)}</small>
            </span>
            <span class="admin-user-side">
              <AdminBadge variant={badge.variant}>{badge.label}</AdminBadge>
              <span class="admin-user-tertiary">{fmtDateShort(user.registration_date)}</span>
            </span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<AdminPagination
  meta={`${at("page", {}, "Страница")} ${usersPage + 1}`}
  prevLabel={at("back", {}, "Назад")}
  nextLabel={at("next", {}, "Далее")}
  prevDisabled={usersPage === 0}
  nextDisabled={!usersHasMore}
  onPrev={() => { usersStore.updateState({ usersPage: Math.max(0, usersPage - 1) }); usersStore.loadUsers(); }}
  onNext={() => { usersStore.updateState({ usersPage: usersPage + 1 }); usersStore.loadUsers(); }}
/>
