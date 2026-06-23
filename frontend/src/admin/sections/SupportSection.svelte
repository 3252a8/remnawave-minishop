<script lang="ts">
  import { afterUpdate, getContext, onMount, tick } from "svelte";
  import {
    AdminButton,
    AdminSelect,
    SupportComposer,
    SupportInboxRow,
    SupportTicketHeader,
    SupportUserContextPanel,
  } from "$components/patterns/admin/index.js";
  import { TicketMessageBubble } from "$components/patterns/webapp/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { Search } from "$components/ui/icons.js";
  import { Input, ScrollArea, Skeleton } from "$components/ui/index.js";
  import type {
    AdminSupportStore,
    SupportFilters,
    SupportMessage,
    SupportTicket,
    SupportUser,
  } from "../../lib/admin/stores/supportStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type ComponentCallback = () => void;
  type TicketPatch = Record<string, unknown>;

  export let at: TranslateFn = (key) => key;
  export let initialTicketId: number | string | null = null;
  export let brand: Record<string, unknown> = {};
  export let resolvedAvatarUrl: (user: SupportUser | Record<string, unknown>) => string = () => "";
  export let onOpenUserCard: (userId: number | string | undefined) => void = () => {};

  const supportStore = getContext<AdminSupportStore>("adminSupportStore");
  let reply = "";
  let messagesScrollEl: HTMLElement | null = null;
  let lastMessageScrollKey = "";
  let tickets: SupportTicket[] = [];
  let stats = {
    active: 0,
    closed: 0,
    open: 0,
    awaiting_admin: 0,
    total_unread_admin: 0,
  };
  let loading = false;
  let filters: SupportFilters = {
    status: "active",
    priority: "",
    category: "",
    search: "",
    sort: "importance_desc",
  };
  let openedTicketId: number | null = null;
  let openedTicket: SupportTicket | null = null;
  let messages: SupportMessage[] = [];
  let userSnapshot: SupportUser | null = null;
  let sending = false;
  let composerInternalNote = false;
  const priorityFilterChange = ((value: string) =>
    setFilterAndLoad("priority", value)) as ComponentCallback;
  const categoryFilterChange = ((value: string) =>
    setFilterAndLoad("category", value)) as ComponentCallback;
  const sortFilterChange = ((value: string) =>
    setFilterAndLoad("sort", value)) as ComponentCallback;
  const openTicketFromRow = ((item: SupportTicket) =>
    void supportStore.openTicket(item.ticket_id || 0)) as ComponentCallback;
  const patchTicketFromHeader = ((updates: TicketPatch) =>
    void supportStore.patchTicket(updates)) as ComponentCallback;
  const openSupportUser = ((userId: number | string | undefined) =>
    onOpenUserCard(userId)) as ComponentCallback;
  const sendComposerReply = ((body: string) => void send(body)) as ComponentCallback;

  $: ({
    tickets,
    stats,
    loading,
    filters,
    openedTicketId,
    openedTicket,
    messages,
    userSnapshot,
    sending,
    composerInternalNote,
  } = $supportStore);
  $: statusTabs = [
    {
      value: "active",
      label: at("support_filter_active", {}, "Активные"),
      count: stats?.active || 0,
    },
    {
      value: "closed",
      label: at("support_filter_closed", {}, "Закрытые"),
      count: stats?.closed || 0,
    },
  ];
  $: priorityFilterOptions = [
    { value: "all", label: at("support_filter_all_priorities", {}, "Любой приоритет") },
    { value: "low", label: at("support_priority_low", {}, "Низкий") },
    { value: "normal", label: at("support_priority_normal", {}, "Обычный") },
    { value: "high", label: at("support_priority_high", {}, "Высокий") },
    { value: "urgent", label: at("support_priority_urgent", {}, "Срочный") },
  ];
  $: categoryFilterOptions = [
    { value: "all", label: at("support_filter_all_categories", {}, "Все категории") },
    { value: "billing", label: at("support_category_billing", {}, "Оплата") },
    { value: "technical", label: at("support_category_technical", {}, "Техническое") },
    { value: "account", label: at("support_category_account", {}, "Аккаунт") },
    { value: "other", label: at("support_category_other", {}, "Другое") },
  ];
  $: sortOptions = [
    { value: "importance_desc", label: at("support_sort_importance_desc", {}, "Важные сверху") },
    { value: "updated_desc", label: at("sort_updated_desc", {}, "Сначала новые") },
    { value: "updated_asc", label: at("sort_updated_asc", {}, "Сначала старые") },
    { value: "created_desc", label: at("sort_created_desc", {}, "Созданы недавно") },
    { value: "created_asc", label: at("sort_created_asc", {}, "Созданы давно") },
  ];
  $: ticketReady = Boolean(openedTicket && openedTicket.ticket_id === openedTicketId);
  $: modalTitle = ticketReady
    ? openedTicket?.subject || ""
    : openedTicketId
      ? at("support_ticket_number", { id: openedTicketId }, `Тикет #${openedTicketId}`)
      : at("support_ticket_dialog", {}, "Диалог поддержки");
  $: modalDescription = ticketReady
    ? at("support_ticket_number", { id: openedTicketId }, `Тикет #${openedTicketId}`)
    : at("loading", {}, "Загрузка");
  $: openedTicketUser = openedTicket?.user || {};
  $: openedTicketUserAvatarUrl = resolvedAvatarUrl(openedTicketUser);
  $: openedTicketUserInitials = userInitials(openedTicketUser);
  $: if (!openedTicketId) {
    reply = "";
    lastMessageScrollKey = "";
  }

  onMount(() => {
    supportStore.loadList();
    supportStore.loadStats();
    supportStore.startStatsPolling();
    if (initialTicketId) supportStore.openTicket(initialTicketId, { skipPush: true });
  });

  async function send(body: string): Promise<void> {
    const sent = await supportStore.sendReply(body);
    if (!sent) return;
    reply = "";
  }

  function scrollMessagesToBottom(): void {
    const scrollEl = messagesScrollEl;
    if (!scrollEl) return;
    const scroll = () => {
      scrollEl.scrollTop = scrollEl.scrollHeight;
    };
    scroll();
    requestAnimationFrame(scroll);
    window.setTimeout(scroll, 80);
    window.setTimeout(scroll, 180);
  }

  function closeTicketModal(): void {
    reply = "";
    supportStore.closeTicketView();
  }

  function setFilter(key: keyof SupportFilters, value: string): void {
    supportStore.setFilter(key, value === "all" ? "" : value);
  }

  function setFilterAndLoad(key: keyof SupportFilters, value: string): void {
    setFilter(key, value);
    void supportStore.loadList();
  }

  function messageT(key: string, params: Record<string, unknown> = {}, fallback = ""): string {
    if (key.startsWith("wa_support_")) {
      return at(key.replace("wa_support_", "support_"), params, fallback || key);
    }
    return at(key, params, fallback || key);
  }

  function userInitials(user: SupportUser | Record<string, unknown>): string {
    const source =
      [user?.first_name, user?.last_name].filter(Boolean).join(" ").trim() ||
      user?.username ||
      user?.email ||
      String(user?.user_id || "");
    const clean = String(source).replace(/^@/, "").trim();
    const parts = clean.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    return (clean.slice(0, 2) || "U").toUpperCase();
  }

  function ticketUserDisplayName(): string {
    const user = openedTicketUser || {};
    const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
    return (
      snapshotName(userSnapshot) ||
      fullName ||
      user.username ||
      user.email ||
      String(user.user_id || "")
    );
  }

  function snapshotName(snapshot: SupportUser | null): string {
    return String(snapshot?.name || "").trim();
  }

  function messageAuthorName(message: SupportMessage): string {
    if (message?.author_name) return message.author_name;
    if (message?.author_role === "user") return ticketUserDisplayName();
    if (message?.author_role === "admin" && message?.author_user_id) {
      return `${at("support_role_admin", {}, "Админ")} #${message.author_user_id}`;
    }
    return "";
  }

  function handleSearchInput(event: Event): void {
    const input = event.currentTarget as HTMLInputElement | null;
    supportStore.setFilter("search", input?.value || "");
  }

  function handleSearchKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter") void supportStore.loadList();
  }

  afterUpdate(async () => {
    const lastMessage = messages.at(-1);
    const nextKey = `${openedTicketId || ""}:${ticketReady}:${messages.length}:${
      lastMessage?.message_id || lastMessage?.created_at || ""
    }`;
    if (!openedTicketId || !ticketReady || !messagesScrollEl || nextKey === lastMessageScrollKey) {
      return;
    }
    lastMessageScrollKey = nextKey;
    await tick();
    scrollMessagesToBottom();
  });
</script>

<div class="support-admin-layout">
  <div class="support-admin-summary" aria-label={at("support_summary", {}, "Сводка поддержки")}>
    <span>
      <strong>{stats?.open || 0}</strong>
      <small>{at("support_status_open", {}, "Открыт")}</small>
    </span>
    <span>
      <strong>{stats?.awaiting_admin || 0}</strong>
      <small>{at("support_status_awaiting_admin", {}, "Ждет админа")}</small>
    </span>
    <span>
      <strong>{stats?.total_unread_admin || 0}</strong>
      <small>{at("support_unread", {}, "Непрочитано")}</small>
    </span>
  </div>

  <section class="support-admin-list-panel">
    <div class="support-admin-ticket-tabs" aria-label={at("support_status", {}, "Статус")}>
      {#each statusTabs as tab (tab.value)}
        <button
          type="button"
          class:active={filters.status === tab.value}
          on:click={() => supportStore.setStatusView(tab.value)}
        >
          <span>{tab.label}</span>
          <b>{tab.count}</b>
        </button>
      {/each}
    </div>

    <div class="support-admin-toolbar admin-toolbar-card">
      <label class="support-admin-search">
        <Search size={16} />
        <Input
          class="input"
          type="search"
          placeholder={at("support_search", {}, "Поиск")}
          value={filters.search}
          on:input={handleSearchInput}
          on:keydown={handleSearchKeydown}
        />
      </label>

      <div class="support-admin-filter-row">
        <AdminSelect
          value={filters.priority || "all"}
          items={priorityFilterOptions}
          ariaLabel={at("support_priority", {}, "Приоритет")}
          onValueChange={priorityFilterChange}
        />
        <AdminSelect
          value={filters.category || "all"}
          items={categoryFilterOptions}
          ariaLabel={at("support_category", {}, "Категория")}
          onValueChange={categoryFilterChange}
        />
        <AdminSelect
          value={filters.sort || "importance_desc"}
          items={sortOptions}
          ariaLabel={at("sort", {}, "Сортировка")}
          onValueChange={sortFilterChange}
        />
        <AdminButton variant="primary" onclick={() => supportStore.loadList()}>
          {at("apply", {}, "Применить")}
        </AdminButton>
      </div>
    </div>

    {#if loading}
      <div class="support-ticket-list-skeleton" aria-label={at("loading", {}, "Загрузка")}>
        {#each Array(6) as _, index (index)}
          <article class="support-ticket-row-skeleton">
            <Skeleton variant="dot" width="38px" height="38px" />
            <span class="support-ticket-row-skeleton-main">
              <Skeleton variant="title" width="min(380px, 74%)" />
              <Skeleton variant="short" width="min(280px, 58%)" />
            </span>
            <span class="support-ticket-row-skeleton-side">
              <Skeleton variant="badge" width="92px" />
              <Skeleton variant="tiny" width="64px" />
            </span>
          </article>
        {/each}
      </div>
    {:else if !tickets.length}
      <div class="admin-empty-state">{at("support_empty", {}, "Тикетов пока нет")}</div>
    {:else}
      <ScrollArea class="support-inbox-list" maxHeight="none">
        <div class="support-inbox-list-inner">
          {#each tickets as ticket}
            <SupportInboxRow
              {ticket}
              active={openedTicketId === ticket.ticket_id}
              {at}
              onOpen={openTicketFromRow}
            />
          {/each}
        </div>
      </ScrollArea>
    {/if}
  </section>
</div>

<Dialog
  open={Boolean(openedTicketId)}
  title={modalTitle}
  description={modalDescription}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={closeTicketModal}
  class="admin-dialog support-ticket-dialog"
>
  {#if !ticketReady}
    <div class="support-ticket-dialog-skeleton">
      <Skeleton variant="title" width="70%" />
      <Skeleton variant="short" width="44%" />
      <Skeleton variant="block" height="94px" />
      <Skeleton variant="block" height="220px" />
      <Skeleton variant="block" height="132px" />
    </div>
  {:else}
    <div class="support-ticket-dialog-body">
      <SupportTicketHeader
        ticket={openedTicket}
        {at}
        onPatch={patchTicketFromHeader}
        onClose={() => supportStore.closeTicket()}
      />
      <SupportUserContextPanel
        ticket={openedTicket}
        snapshot={userSnapshot || {}}
        {at}
        onOpenUser={openSupportUser}
      />
      <ScrollArea
        bind:element={messagesScrollEl}
        maxHeight="none"
        class="support-admin-message-scroll scroll-area--mono"
      >
        <div class="support-admin-messages">
          {#if messages.length}
            {#each messages as message}
              <TicketMessageBubble
                role={message.author_role}
                body={message.body}
                createdAt={message.created_at ?? undefined}
                isInternalNote={message.is_internal_note}
                perspective="admin"
                supportBrand={brand}
                userAvatarUrl={openedTicketUserAvatarUrl}
                userInitials={openedTicketUserInitials}
                authorName={messageAuthorName(message)}
                t={messageT}
              />
            {/each}
          {:else}
            <div class="admin-empty-state">
              {at("support_no_messages", {}, "Сообщений пока нет")}
            </div>
          {/if}
        </div>
      </ScrollArea>
      <SupportComposer
        bind:value={reply}
        internal={composerInternalNote}
        {sending}
        {at}
        onToggleInternal={supportStore.toggleInternalNote}
        onSend={sendComposerReply}
      />
    </div>
  {/if}
</Dialog>
