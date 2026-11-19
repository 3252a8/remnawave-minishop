<script lang="ts">
  import { AttentionDot } from "$components/ui/index.js";
  import { MessageSquare } from "$components/ui/icons.js";
  import TicketStatusBadge from "./TicketStatusBadge.svelte";
  import { formatTicketTime } from "$lib/ticketTime";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type TicketRecord = Record<string, unknown> & {
    created_at?: string;
    last_message_at?: string;
    status?: string;
    subject?: string;
    ticket_id?: number;
    unread_user_count?: number;
    updated_at?: string;
  };

  let {
    ticket,
    locale = "ru",
    t = (key) => key,
    onOpen = () => {},
  }: {
    ticket: TicketRecord;
    locale?: string;
    t?: Translate;
    onOpen?: (ticket: TicketRecord) => void;
  } = $props();

  const unread = $derived(Number(ticket?.unread_user_count || 0));
  const timeLabel = $derived(
    formatTicketTime(ticket?.last_message_at || ticket?.updated_at || ticket?.created_at, locale)
  );
</script>

<button
  class="ticket-card"
  type="button"
  data-status={ticket?.status}
  onclick={() => onOpen(ticket)}
>
  <span class="ticket-card-main">
    <span class="ticket-card-title">
      <MessageSquare size={16} />
      <strong>{ticket.subject}</strong>
      {#if unread}
        <span role="img" aria-label={t("wa_support_unread_messages", { count: unread })}>
          <AttentionDot position="inline" class="ticket-card-unread-dot" />
        </span>
      {/if}
    </span>
    <span class="ticket-card-meta">
      <span>{t("wa_support_ticket_number", { id: ticket.ticket_id })}</span>
      {#if timeLabel}<span>{timeLabel}</span>{/if}
    </span>
  </span>

  <span class="ticket-card-side">
    <span class="ticket-card-badges">
      <TicketStatusBadge status={ticket.status} {t} />
    </span>
  </span>
</button>
