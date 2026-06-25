<script lang="ts">
  import { AttentionDot, Badge } from "$components/ui/index.js";
  import { MessageSquare } from "$components/ui/icons.js";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type TicketRecord = Record<string, unknown> & {
    created_at?: string;
    last_message_at?: string;
    priority?: string;
    status?: string;
    subject?: string;
    ticket_id?: number;
    unread_user_count?: number;
    updated_at?: string;
  };

  let {
    ticket,
    t = (key) => key,
    onOpen = () => {},
  }: {
    ticket: TicketRecord;
    t?: Translate;
    onOpen?: (ticket: TicketRecord) => void;
  } = $props();

  const unread = $derived(Number(ticket?.unread_user_count || 0));
  const timeLabel = $derived(
    formatTime(ticket?.last_message_at || ticket?.updated_at || ticket?.created_at)
  );

  function formatTime(value: unknown) {
    if (!value) return "";
    const raw =
      typeof value === "string" || typeof value === "number" || value instanceof Date ? value : "";
    if (!raw) return "";
    const date = new Date(raw);
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
  class="ticket-card"
  type="button"
  data-status={ticket?.status}
  data-priority={ticket?.priority}
  onclick={() => onOpen(ticket)}
>
  <span class="ticket-card-main">
    <span class="ticket-card-title">
      <MessageSquare size={16} />
      <strong>{ticket.subject}</strong>
    </span>
    <span class="ticket-card-meta">
      <span>{t("wa_support_ticket_number", { id: ticket.ticket_id })}</span>
      {#if timeLabel}<span>{timeLabel}</span>{/if}
    </span>
  </span>

  <span class="ticket-card-side">
    <span class="ticket-card-badges">
      <Badge variant="outline" class={`ticket-status-badge ticket-status-badge--${ticket.status}`}>
        {t(`wa_support_status_${ticket.status}`)}
      </Badge>
      <Badge
        variant="muted"
        class={`ticket-priority-badge ticket-priority-badge--${ticket.priority}`}
      >
        {t(`wa_support_priority_${ticket.priority}`)}
      </Badge>
    </span>
    {#if unread}
      <AttentionDot position="inline" class="ticket-card-unread-dot" />
    {/if}
  </span>
</button>
