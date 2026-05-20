<script>
  import { afterUpdate, getContext, tick } from "svelte";
  import { Badge, Button, ScrollArea, Skeleton } from "$components/ui/index.js";
  import Card from "$components/ui/card.svelte";
  import { ArrowLeft } from "$components/ui/icons.js";
  import { TicketComposer, TicketMessageBubble } from "$components/patterns/webapp/index.js";

  export let t = (key) => key;
  export let maxBodyLength = 4000;
  export let brand = {};
  export let userAvatarUrl = "";
  export let userInitials = "";

  const supportStore = getContext("supportStore");
  let reply = "";
  let messagesScrollEl;
  let lastMessageKey = "";

  $: ({ openedTicket, messages, detailLoading, sending } = $supportStore);
  $: closed = ["resolved", "closed"].includes(openedTicket?.status);

  async function send(body) {
    await supportStore.sendReply(body);
    reply = "";
  }

  function scrollMessagesToBottom() {
    if (!messagesScrollEl) return;
    const scroll = () => {
      messagesScrollEl.scrollTop = messagesScrollEl.scrollHeight;
    };
    scroll();
    requestAnimationFrame(scroll);
    window.setTimeout(scroll, 80);
    window.setTimeout(scroll, 180);
  }

  function messageAuthorName(message) {
    if (message?.author_name) return message.author_name;
    return message?.author_role === "user" ? t("wa_support_role_user") : "";
  }

  afterUpdate(async () => {
    const nextKey = `${openedTicket?.ticket_id || ""}:${messages.length}:${messages.at(-1)?.message_id || ""}`;
    if (!messagesScrollEl || nextKey === lastMessageKey) return;
    lastMessageKey = nextKey;
    await tick();
    scrollMessagesToBottom();
  });
</script>

<main class="content with-nav support-ticket-screen">
  {#if detailLoading && !openedTicket}
    <Card class="support-ticket-card">
      <header class="ticket-detail-header support-ticket-detail-header">
        <Button
          variant="ghost"
          size="sm"
          class="support-back-button"
          onclick={() => supportStore.closeTicketView()}
        >
          <ArrowLeft size={16} />
          <span>{t("wa_back")}</span>
        </Button>

        <div class="ticket-detail-title">
          <small>{t("wa_loading")}</small>
          <h1>{t("wa_support_title")}</h1>
        </div>
      </header>
    </Card>

    <Card class="support-conversation-card support-conversation-card--loading">
      <ScrollArea
        bind:element={messagesScrollEl}
        maxHeight="none"
        class="support-message-scroll scroll-area--mono"
      >
        <div class="ticket-message-list ticket-message-list--loading" aria-label={t("wa_loading")}>
          {#each Array(4) as _, index (index)}
            <div
              class:ticket-message-skeleton-row--outgoing={index % 2 === 1}
              class="ticket-message-skeleton-row"
            >
              <Skeleton variant="dot" width="32px" height="32px" />
              <span class="ticket-message-skeleton-content">
                <Skeleton variant="tiny" width={index % 2 === 1 ? "72px" : "96px"} />
                <Skeleton variant="block" height={index === 1 ? "72px" : "54px"} />
              </span>
            </div>
          {/each}
        </div>
      </ScrollArea>
    </Card>
  {:else if !openedTicket}
    <Card class="support-ticket-card support-ticket-state-card">
      <div class="empty-card">{t("wa_support_not_found")}</div>
    </Card>
  {:else}
    <Card class="support-ticket-card">
      <header class="ticket-detail-header support-ticket-detail-header">
        <Button
          variant="ghost"
          size="sm"
          class="support-back-button"
          onclick={() => supportStore.closeTicketView()}
        >
          <ArrowLeft size={16} />
          <span>{t("wa_back")}</span>
        </Button>

        <div class="ticket-detail-title">
          <small>{t("wa_support_ticket_number", { id: openedTicket.ticket_id })}</small>
          <h1>{openedTicket.subject}</h1>
        </div>

        <div class="ticket-badges">
          <Badge
            variant="outline"
            class={`ticket-status-badge ticket-status-badge--${openedTicket.status}`}
          >
            {t(`wa_support_status_${openedTicket.status}`)}
          </Badge>
          <Badge
            variant="muted"
            class={`ticket-priority-badge ticket-priority-badge--${openedTicket.priority}`}
          >
            {t(`wa_support_priority_${openedTicket.priority}`)}
          </Badge>
        </div>
      </header>
    </Card>

    <Card class="support-conversation-card">
      <ScrollArea
        bind:element={messagesScrollEl}
        maxHeight="none"
        class="support-message-scroll scroll-area--mono"
      >
        <div class="ticket-message-list">
          {#if messages.length}
            {#each messages as message}
              <TicketMessageBubble
                role={message.author_role}
                body={message.body}
                createdAt={message.created_at}
                isInternalNote={message.is_internal_note}
                supportBrand={brand}
                {userAvatarUrl}
                {userInitials}
                authorName={messageAuthorName(message)}
                {t}
              />
            {/each}
          {:else}
            <div class="support-messages-empty">{t("wa_support_no_messages")}</div>
          {/if}
        </div>
      </ScrollArea>

      <TicketComposer
        bind:value={reply}
        maxLength={maxBodyLength}
        disabled={closed}
        {sending}
        placeholder={closed ? t("wa_support_closed_hint") : t("wa_support_reply_placeholder")}
        sendLabel={t("wa_support_send")}
        onSend={send}
      />
    </Card>
  {/if}
</main>
