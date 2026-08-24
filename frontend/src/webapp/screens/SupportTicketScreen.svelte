<script lang="ts">
  import { getSupportStore } from "$lib/webapp/context";
  import { tick } from "svelte";
  import { Badge, Button, ScrollArea, Skeleton } from "$components/ui/index.js";
  import Card from "$components/ui/card.svelte";
  import { ArrowLeft } from "$components/ui/icons.js";
  import TicketComposer from "$components/patterns/webapp/TicketComposer.svelte";
  import { TicketMessageBubble, TypingIndicator } from "$components/patterns/webapp/index.js";
  import type { TicketMessageButtonLike } from "$components/patterns/webapp/types";
  import { webappRichTextLabels } from "$lib/webapp/richTextLabels.js";
  import { wireTextLength } from "$lib/richtext/telegramHtml";
  import { supportMessageImageUrl } from "$lib/messageImage";
  import {
    clearSupportDraft,
    readSupportDraft,
    supportDraftScope,
    writeSupportDraft,
  } from "$lib/webapp/supportDrafts.js";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type MessageRecord = Record<string, unknown> & {
    author_name?: string;
    author_role?: string;
    body?: string;
    body_format?: string;
    buttons?: TicketMessageButtonLike[];
    created_at?: string;
    is_internal_note?: boolean;
    image_id?: string | null;
    message_id?: number;
    read_by_admin_at?: string | null;
    read_by_user_at?: string | null;
  };

  type Props = {
    t?: Translate;
    maxBodyLength?: number;
    brand?: Record<string, unknown>;
    user?: Record<string, unknown>;
    userAvatarUrl?: string;
    userInitials?: string;
  };

  let {
    t = (key) => key,
    maxBodyLength = 4000,
    brand = {},
    user = {},
    userAvatarUrl = "",
    userInitials = "",
  }: Props = $props();

  const supportStore = getSupportStore();
  let reply = $state("");
  let replyImage = $state<File | null>(null);
  let messagesScrollEl = $state<HTMLElement | null>(null);
  let lastMessageKey = $state("");
  let replyDraftKey = $state("");

  const labels = $derived(webappRichTextLabels(t));
  const imageLabels = $derived({
    drop: t("wa_message_image_drop"),
    choose: t("wa_message_image_choose"),
    upload: t("wa_message_image_upload"),
    remove: t("wa_message_image_remove"),
    hint: t("wa_message_image_hint"),
    invalidType: t("wa_message_image_invalid_type"),
    tooLarge: t("wa_message_image_too_large"),
    previewAlt: t("wa_message_image_preview_alt"),
  });
  const imageViewerLabels = $derived({
    open: t("wa_image_viewer_open", {}, "Open image"),
    title: t("wa_image_viewer_title", {}, "Image"),
    close: t("wa_image_viewer_close", {}, "Close image"),
    zoomIn: t("wa_image_viewer_zoom_in", {}, "Zoom in"),
    zoomOut: t("wa_image_viewer_zoom_out", {}, "Zoom out"),
    reset: t("wa_image_viewer_reset", {}, "Reset zoom"),
  });
  const openedTicket = $derived(supportStore.openedTicket);
  const messages = $derived(supportStore.messages);
  const detailLoading = $derived(supportStore.detailLoading);
  const sending = $derived(supportStore.sending);
  const peerTyping = $derived(supportStore.peerTyping);
  const closed = $derived(["resolved", "closed"].includes(String(openedTicket?.status || "")));
  const ticketId = $derived(String(openedTicket?.ticket_id || ""));
  const draftScope = $derived(supportDraftScope(user));
  const nextReplyDraftKey = $derived(ticketId ? `${draftScope}:${ticketId}` : "");

  $effect.pre(() => {
    if (!nextReplyDraftKey || nextReplyDraftKey === replyDraftKey) return;
    const draft = readSupportDraft("reply", draftScope, ticketId);
    reply = typeof draft?.body === "string" ? draft.body : "";
    replyDraftKey = nextReplyDraftKey;
  });

  $effect(() => {
    if (!nextReplyDraftKey || replyDraftKey !== nextReplyDraftKey || closed) return;
    const body = String(reply || "");
    if (wireTextLength(body, "html")) writeSupportDraft("reply", draftScope, ticketId, { body });
    else clearSupportDraft("reply", draftScope, ticketId);
  });

  async function send(body: string, image: File | null) {
    const currentTicketId = ticketId;
    const currentDraftScope = draftScope;
    const sent = await supportStore.sendReply(body, image);
    if (!sent) return;
    if (currentTicketId) clearSupportDraft("reply", currentDraftScope, currentTicketId);
    reply = "";
    replyImage = null;
  }

  function scrollMessagesToBottom() {
    if (!messagesScrollEl) return;
    const scrollEl = messagesScrollEl as HTMLElement;
    const scroll = () => {
      scrollEl.scrollTop = scrollEl.scrollHeight;
    };
    scroll();
    requestAnimationFrame(scroll);
    window.setTimeout(scroll, 80);
    window.setTimeout(scroll, 180);
  }

  function messageAuthorName(message: MessageRecord) {
    if (message?.author_name) return message.author_name;
    return message?.author_role === "user" ? t("wa_support_role_user") : "";
  }

  $effect(() => {
    const nextKey = `${openedTicket?.ticket_id || ""}:${messages.length}:${messages.at(-1)?.message_id || ""}`;
    if (!messagesScrollEl || nextKey === lastMessageKey) return;
    lastMessageKey = nextKey;
    void tick().then(scrollMessagesToBottom);
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
                bodyFormat={message.body_format}
                imageUrl={message.image_id ? supportMessageImageUrl(message.image_id) : ""}
                loadImage={supportStore.loadImage}
                buttons={message.buttons}
                createdAt={message.created_at}
                isInternalNote={message.is_internal_note}
                supportBrand={brand}
                {imageViewerLabels}
                {userAvatarUrl}
                {userInitials}
                authorName={messageAuthorName(message)}
                readByUserAt={message.read_by_user_at}
                readByAdminAt={message.read_by_admin_at}
                {t}
              />
            {/each}
          {:else}
            <div class="support-messages-empty">{t("wa_support_no_messages")}</div>
          {/if}
        </div>
      </ScrollArea>

      {#if peerTyping && !closed}
        <TypingIndicator label={t("wa_support_admin_typing")} />
      {/if}

      <TicketComposer
        bind:value={reply}
        bind:image={replyImage}
        {labels}
        {imageLabels}
        maxLength={maxBodyLength}
        disabled={closed}
        {sending}
        placeholder={closed ? t("wa_support_closed_hint") : t("wa_support_reply_placeholder")}
        sendLabel={t("wa_support_send")}
        onSend={send}
        onTyping={supportStore.notifyTyping}
      />
    </Card>
  {/if}
</main>
