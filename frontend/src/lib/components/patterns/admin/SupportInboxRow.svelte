<script lang="ts">
  import { AdminBadge } from "$components/patterns/admin/index.js";
  import { formatTicketTime } from "$lib/ticketTime";
  import type { SupportTicketLike, SupportUserLike, TranslateFn } from "./types";

  type Props = {
    ticket: SupportTicketLike;
    active?: boolean;
    currentLang?: string;
    at?: TranslateFn;
    onOpen?: (ticket: SupportTicketLike) => void;
  };

  let {
    ticket,
    currentLang = "en",
    active = false,
    at = (key) => key,
    onOpen = () => {},
  }: Props = $props();

  const user = $derived(ticket?.user || {});
  const timeLabel = $derived(
    formatTicketTime(
      ticket?.last_message_at || ticket?.updated_at || ticket?.created_at,
      currentLang.replaceAll("_", "-")
    )
  );
  const userLabel = $derived(
    user.username ? `@${user.username}` : user.email || user.user_id || "-"
  );
  const avatarUrl = $derived(user?.avatar_url || user?.photo_url || "");
  const avatarInitials = $derived(computeInitials(user));
  const categoryLabel = $derived(
    at(`support_category_${ticket?.category}`, {}, ticket?.category || "-")
  );
  // Waiting on the admin needs action; waiting on the user is a calm open state.
  const statusVariant = $derived(
    ticket?.status === "closed" || ticket?.status === "resolved"
      ? "muted"
      : ticket?.status === "awaiting_admin" || ticket?.status === "open"
        ? "warning"
        : "success"
  );
  const priorityVariant = $derived(
    ticket?.priority === "urgent" ? "danger" : ticket?.priority === "high" ? "warning" : "muted"
  );

  function computeInitials(u: SupportUserLike): string {
    const source =
      [u?.first_name, u?.last_name].filter(Boolean).join(" ").trim() ||
      u?.username ||
      u?.email ||
      String(u?.user_id || "");
    const clean = String(source).replace(/^@/, "").trim();
    const parts = clean.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    return (clean.slice(0, 2) || "U").toUpperCase();
  }
</script>

<button
  class:active
  class="support-inbox-row"
  type="button"
  data-ticket-id={ticket?.ticket_id}
  data-status={ticket?.status}
  data-priority={ticket?.priority}
  onclick={() => onOpen(ticket)}
>
  <span class="support-inbox-row-avatar" aria-hidden="true">
    {#if avatarUrl}
      <img src={avatarUrl} alt="" loading="lazy" referrerpolicy="no-referrer" />
    {:else}
      {avatarInitials}
    {/if}
  </span>

  <span class="support-inbox-row-main">
    <span class="support-inbox-row-title">
      <strong>{ticket.subject}</strong>
    </span>
    <small>#{ticket.ticket_id} / {userLabel} / {categoryLabel}</small>
  </span>

  <span class="support-row-badges">
    <AdminBadge variant={statusVariant}
      >{at(`support_status_${ticket.status}`, {}, ticket.status)}</AdminBadge
    >
    <AdminBadge variant={priorityVariant}>
      {at(`support_priority_${ticket.priority}`, {}, ticket.priority)}
    </AdminBadge>
    {#if ticket.unread_admin_count}
      <b>
        <span class="sr-only">{at("support_unread", {}, "Unread")}</span>
        <span class="numeric-badge-value">{ticket.unread_admin_count}</span>
      </b>
    {/if}
    {#if timeLabel}<small>{timeLabel}</small>{/if}
  </span>
</button>
