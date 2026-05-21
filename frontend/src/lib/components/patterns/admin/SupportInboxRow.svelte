<script>
  import { AdminBadge } from "$components/patterns/admin/index.js";
  import { MessageSquare } from "$components/ui/icons.js";

  export let ticket;
  export let active = false;
  export let at = (key) => key;
  export let onOpen = () => {};

  $: user = ticket?.user || {};
  $: timeLabel = formatTime(ticket?.last_message_at || ticket?.updated_at || ticket?.created_at);
  $: userLabel = user.username ? `@${user.username}` : user.email || user.user_id || "-";
  $: avatarUrl = user?.avatar_url || user?.photo_url || "";
  $: avatarInitials = computeInitials(user);
  $: categoryLabel = at(`support_category_${ticket?.category}`, {}, ticket?.category || "-");
  $: statusVariant =
    ticket?.status === "closed" || ticket?.status === "resolved" ? "muted" : "success";
  $: priorityVariant =
    ticket?.priority === "urgent" ? "danger" : ticket?.priority === "high" ? "warning" : "muted";

  function computeInitials(u) {
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

  function formatTime(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString(undefined, {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }
</script>

<button
  class:active
  class="support-inbox-row"
  type="button"
  data-status={ticket?.status}
  data-priority={ticket?.priority}
  on:click={() => onOpen(ticket)}
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
      <MessageSquare size={15} />
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
        <span class="numeric-badge-value">{ticket.unread_admin_count}</span>
      </b>
    {/if}
    {#if timeLabel}<small>{timeLabel}</small>{/if}
  </span>
</button>
