<script lang="ts">
  import { getAdminSupportStore, getBroadcastStore } from "$lib/admin/context";
  import { buttonsForPayload } from "$lib/admin/stores/broadcastStore.svelte";
  import type { BroadcastButtonDraft } from "$lib/admin/stores/broadcastStore.svelte";
  import { supportMessageImageUrl } from "$lib/messageImage";
  import { onMount, tick } from "svelte";
  import {
    AdminButton,
    AdminListToolbar,
    AdminField,
    AdminSelect,
    SupportComposer,
    SupportInboxRow,
    SupportTicketHeader,
    SupportUserContextPanel,
  } from "$components/patterns/admin/index.js";
  import { TicketMessageBubble, TypingIndicator } from "$components/patterns/webapp/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { Input, ScrollArea, Skeleton } from "$components/ui/index.js";
  import { Sliders } from "$components/ui/icons.js";
  import type {
    SupportFilters,
    SupportMessage,
    SupportTicket,
    SupportUser,
  } from "../../lib/admin/stores/supportStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type ComponentCallback = () => void;
  type TicketPatch = Record<string, unknown>;

  let {
    at = (key) => key,
    initialTicketId = null,
    brand = {},
    resolvedAvatarUrl = () => "",
    onOpenUserCard = () => {},
  }: {
    at?: TranslateFn;
    initialTicketId?: number | string | null;
    brand?: Record<string, unknown>;
    resolvedAvatarUrl?: (user: SupportUser | Record<string, unknown>) => string;
    onOpenUserCard?: (userId: number | string | undefined) => void;
  } = $props();

  const supportStore = getAdminSupportStore();
  // Shortcodes and promo codes are advertised once for every authored message,
  // so the reply composer offers exactly what the broadcast screen offers.
  const broadcastStore = getBroadcastStore();
  let reply = $state("");
  let replyImage = $state<File | null>(null);
  let replyButtons = $state<BroadcastButtonDraft[]>([]);
  let messagesScrollEl = $state<HTMLElement | null>(null);
  let filtersOpen = $state(false);
  let lastMessageScrollKey = $state("");
  const tickets: SupportTicket[] = $derived(supportStore.tickets || []);
  const stats = $derived(
    supportStore.stats || {
      active: 0,
      closed: 0,
      open: 0,
      awaiting_admin: 0,
      awaiting_user: 0,
      total_unread_admin: 0,
    }
  );
  const loading = $derived(Boolean(supportStore.loading));
  const ticketFilters: SupportFilters = $derived(
    supportStore.filters || {
      status: "active",
      priority: "",
      category: "",
      search: "",
      sort: "importance_desc",
    }
  );
  const openedTicketId: number | null = $derived(supportStore.openedTicketId || null);
  const openedTicket: SupportTicket | null = $derived(supportStore.openedTicket || null);
  const messages: SupportMessage[] = $derived(supportStore.messages || []);
  const peerTyping = $derived(supportStore.peerTyping);
  const userSnapshot: SupportUser | null = $derived(supportStore.userSnapshot || null);
  const sending = $derived(Boolean(supportStore.sending));
  const composerInternalNote = $derived(Boolean(supportStore.composerInternalNote));
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
  const sendComposerReply = (body: string, image: File | null) => void send(body, image);
  const maxBodyLength = 4000;
  const imageViewerLabels = $derived({
    open: at("image_viewer_open", {}, "Open image"),
    title: at("image_viewer_title", {}, "Image"),
    close: at("image_viewer_close", {}, "Close image"),
    zoomIn: at("image_viewer_zoom_in", {}, "Zoom in"),
    zoomOut: at("image_viewer_zoom_out", {}, "Zoom out"),
    reset: at("image_viewer_reset", {}, "Reset zoom"),
  });

  const statusTabs = $derived([
    {
      value: "active",
      label: at("support_filter_active", {}, "Open"),
      count: stats?.active || 0,
    },
    {
      value: "awaiting_admin",
      label: at("support_status_awaiting_admin", {}, "Awaiting admin"),
      count: stats?.awaiting_admin || 0,
    },
    {
      value: "awaiting_user",
      label: at("support_status_awaiting_user", {}, "Awaiting user"),
      count: stats?.awaiting_user || 0,
    },
    {
      value: "closed",
      label: at("support_filter_closed", {}, "Closed"),
      count: stats?.closed || 0,
    },
  ]);
  const priorityFilterOptions = $derived([
    { value: "all", label: at("support_filter_all_priorities", {}, "Any priority") },
    { value: "low", label: at("support_priority_low", {}, "Low") },
    { value: "normal", label: at("support_priority_normal", {}, "Normal") },
    { value: "high", label: at("support_priority_high", {}, "High") },
    { value: "urgent", label: at("support_priority_urgent", {}, "Urgent") },
  ]);
  const categoryFilterOptions = $derived([
    { value: "all", label: at("support_filter_all_categories", {}, "All categories") },
    { value: "billing", label: at("support_category_billing", {}, "Billing") },
    { value: "technical", label: at("support_category_technical", {}, "Technical") },
    { value: "account", label: at("support_category_account", {}, "Account") },
    { value: "other", label: at("support_category_other", {}, "Other") },
  ]);
  const sortOptions = $derived([
    { value: "importance_desc", label: at("support_sort_importance_desc", {}, "Most important") },
    { value: "updated_desc", label: at("sort_updated_desc", {}, "Newest activity") },
    { value: "updated_asc", label: at("sort_updated_asc", {}, "Oldest activity") },
    { value: "created_desc", label: at("sort_created_desc", {}, "Newest created") },
    { value: "created_asc", label: at("sort_created_asc", {}, "Oldest created") },
  ]);
  const ticketReady = $derived(Boolean(openedTicket && openedTicket.ticket_id === openedTicketId));
  const modalTitle = $derived(
    ticketReady
      ? openedTicket?.subject || ""
      : openedTicketId
        ? at("support_ticket_number", { id: openedTicketId }, "Ticket #{id}")
        : at("support_ticket_dialog", {}, "Support conversation")
  );
  const modalDescription = $derived(
    ticketReady
      ? at("support_ticket_number", { id: openedTicketId }, "Ticket #{id}")
      : at("loading", {}, "Loading…")
  );
  const openedTicketUser = $derived(openedTicket?.user || {});
  const openedTicketUserAvatarUrl = $derived(resolvedAvatarUrl(openedTicketUser));
  const openedTicketUserInitials = $derived(userInitials(openedTicketUser));
  $effect(() => {
    if (!openedTicketId) {
      reply = "";
      replyImage = null;
      replyButtons = [];
      lastMessageScrollKey = "";
    }
  });

  onMount(() => {
    supportStore.loadList();
    // The panel already polls the counters for the sidebar badge; this only
    // refreshes them for the summary the moment the screen opens.
    supportStore.loadStats();
    if (initialTicketId) supportStore.openTicket(initialTicketId, { skipPush: true });
  });

  async function send(body: string, image: File | null): Promise<void> {
    const sent = await supportStore.sendReply(body, {
      bodyFormat: "html",
      buttons: buttonsForPayload(replyButtons),
      image,
    });
    if (!sent) return;
    reply = "";
    replyImage = null;
    replyButtons = [];
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
    replyImage = null;
    replyButtons = [];
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
    if (message?.author_role === "admin") return at("support_role_admin", {}, "Admin");
    return "";
  }

  function handleSearchInput(event: Event): void {
    const input = event.currentTarget as HTMLInputElement | null;
    supportStore.setFilter("search", input?.value || "");
  }

  function handleSearchKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter") void supportStore.loadList();
  }

  $effect(() => {
    const lastMessage = messages.at(-1);
    const nextKey = `${openedTicketId || ""}:${ticketReady}:${messages.length}:${
      lastMessage?.message_id || lastMessage?.created_at || ""
    }`;
    if (!openedTicketId || !ticketReady || !messagesScrollEl || nextKey === lastMessageScrollKey) {
      return;
    }
    lastMessageScrollKey = nextKey;
    void tick().then(scrollMessagesToBottom);
  });
</script>

{#snippet supportFilterControls()}
  <AdminField label={at("support_priority", {}, "Priority")}>
    <AdminSelect
      value={ticketFilters.priority || "all"}
      items={priorityFilterOptions}
      ariaLabel={at("support_priority", {}, "Priority")}
      onValueChange={priorityFilterChange}
    />
  </AdminField>
  <AdminField label={at("support_category", {}, "Category")}>
    <AdminSelect
      value={ticketFilters.category || "all"}
      items={categoryFilterOptions}
      ariaLabel={at("support_category", {}, "Category")}
      onValueChange={categoryFilterChange}
    />
  </AdminField>
  <AdminField label={at("sort", {}, "Sort")}>
    <AdminSelect
      value={ticketFilters.sort || "importance_desc"}
      items={sortOptions}
      ariaLabel={at("sort", {}, "Sort")}
      onValueChange={sortFilterChange}
    />
  </AdminField>
{/snippet}

<div class="support-admin-layout">
  <div class="support-admin-summary" aria-label={at("support_summary", {}, "Support summary")}>
    <span>
      <strong>{stats?.open || 0}</strong>
      <small>{at("support_status_open", {}, "Open")}</small>
    </span>
    <span>
      <strong>{stats?.awaiting_admin || 0}</strong>
      <small>{at("support_status_awaiting_admin", {}, "Awaiting admin")}</small>
    </span>
    <span>
      <strong>{stats?.total_unread_admin || 0}</strong>
      <small>{at("support_unread", {}, "Unread")}</small>
    </span>
  </div>

  <section class="support-admin-list-panel">
    <div class="support-admin-ticket-tabs" aria-label={at("support_status", {}, "Status")}>
      {#each statusTabs as tab (tab.value)}
        <button
          type="button"
          class:active={ticketFilters.status === tab.value}
          onclick={() => supportStore.setStatusView(tab.value)}
        >
          <span>{tab.label}</span>
          <b>{tab.count}</b>
        </button>
      {/each}
    </div>

    <AdminListToolbar
      class="support-list-toolbar"
      mobileFilterMode="dialog"
      onsubmit={() => supportStore.loadList()}
    >
      {#snippet search()}
        <Input
          class="input"
          type="search"
          aria-label={at("support_search", {}, "Search")}
          placeholder={at("support_search", {}, "Search")}
          value={ticketFilters.search}
          oninput={handleSearchInput}
          onkeydown={handleSearchKeydown}
        />
      {/snippet}
      {#snippet searchActions()}
        <AdminButton variant="primary" type="submit">{at("apply", {}, "Apply")}</AdminButton>
      {/snippet}
      {#snippet mobileFilters()}
        <AdminButton
          aria-label={at("filters", {}, "Filters")}
          aria-haspopup="dialog"
          aria-expanded={filtersOpen}
          onclick={() => (filtersOpen = true)}
        >
          <Sliders size={15} />
        </AdminButton>
      {/snippet}
      {#snippet filters()}
        {@render supportFilterControls()}
      {/snippet}
    </AdminListToolbar>

    {#if loading}
      <div class="support-ticket-list-skeleton" aria-label={at("loading", {}, "Loading…")}>
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
      <div class="admin-empty-state">{at("support_empty", {}, "No tickets yet")}</div>
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
  open={filtersOpen}
  title={at("filters", {}, "Filters")}
  closeLabel={at("close", {}, "Close")}
  onclose={() => (filtersOpen = false)}
  class="admin-dialog support-filter-dialog"
>
  <div class="support-filter-sheet">
    {@render supportFilterControls()}
    <AdminButton variant="primary" onclick={() => (filtersOpen = false)}>
      {at("done", {}, "Done")}
    </AdminButton>
  </div>
</Dialog>

<Dialog
  open={Boolean(openedTicketId)}
  title={modalTitle}
  description={modalDescription}
  closeLabel={at("close", {}, "Close")}
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
                bodyFormat={message.body_format}
                imageUrl={message.image_id ? supportMessageImageUrl(message.image_id, true) : ""}
                loadImage={supportStore.loadImage}
                buttons={message.buttons}
                createdAt={message.created_at ?? undefined}
                isInternalNote={message.is_internal_note}
                perspective="admin"
                supportBrand={brand}
                {imageViewerLabels}
                userAvatarUrl={openedTicketUserAvatarUrl}
                userInitials={openedTicketUserInitials}
                authorName={messageAuthorName(message)}
                readByUserAt={message.read_by_user_at}
                readByAdminAt={message.read_by_admin_at}
                t={messageT}
              />
            {/each}
          {:else}
            <div class="admin-empty-state">
              {at("support_no_messages", {}, "No messages yet")}
            </div>
          {/if}
        </div>
      </ScrollArea>
      {#if peerTyping}
        <TypingIndicator label={at("support_user_typing", {}, "User is typing…")} />
      {/if}
      <SupportComposer
        bind:value={reply}
        bind:image={replyImage}
        bind:buttons={replyButtons}
        internal={composerInternalNote}
        {sending}
        maxLength={maxBodyLength}
        {at}
        shortcodes={broadcastStore.broadcastShortcodes}
        promoOptions={broadcastStore.broadcastPromoOptions}
        promoOptionsLoading={broadcastStore.broadcastPromoOptionsLoading}
        promoOptionsLoaded={broadcastStore.broadcastPromoOptionsLoaded}
        onRequestShortcodes={broadcastStore.loadShortcodes}
        onRequestPromoOptions={broadcastStore.loadPromoOptions}
        onToggleInternal={supportStore.toggleInternalNote}
        onSend={sendComposerReply}
        onTyping={supportStore.notifyTyping}
      />
    </div>
  {/if}
</Dialog>
