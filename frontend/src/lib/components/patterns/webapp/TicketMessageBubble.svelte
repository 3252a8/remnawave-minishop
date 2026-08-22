<script lang="ts">
  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import {
    Check,
    CheckCheck,
    LifeBuoy,
    Lock,
    MessageSquare,
    UserRound,
  } from "$components/ui/icons.js";
  import { messageDisplayHtml } from "$lib/richtext/telegramHtml";

  import type { TicketMessageButtonLike } from "./types.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Props = {
    role?: string;
    body?: string;
    bodyFormat?: string;
    imageUrl?: string;
    buttons?: TicketMessageButtonLike[];
    createdAt?: string;
    isInternalNote?: boolean;
    perspective?: "admin" | "user";
    userAvatarUrl?: string;
    userInitials?: string;
    authorName?: string;
    readByUserAt?: string | null;
    readByAdminAt?: string | null;
    supportBrand?: Record<string, unknown>;
    t?: TranslateFn;
  };

  let {
    role = "user",
    body = "",
    bodyFormat = "text",
    imageUrl = "",
    buttons = [],
    createdAt = "",
    isInternalNote = false,
    perspective = "user",
    userAvatarUrl = "",
    userInitials = "",
    authorName = "",
    readByUserAt = null,
    readByAdminAt = null,
    supportBrand = {},
    t = (key, _params = {}, fallback = "") => fallback || key,
  }: Props = $props();

  const messageRole = $derived(role || "system");
  const serviceMessage = $derived(isInternalNote || messageRole === "system");
  const outgoing = $derived(
    (perspective === "admin" && (messageRole === "admin" || serviceMessage)) ||
      (!serviceMessage && perspective !== "admin" && messageRole === "user")
  );
  const roleLabel = $derived(
    isInternalNote
      ? [authorName, t("wa_support_internal_note", {}, "Internal note")].filter(Boolean).join(" / ")
      : authorName || t(`wa_support_role_${messageRole}`, {}, messageRole)
  );
  const timeLabel = $derived(formatTime(createdAt));
  // Built from the parsed structure, never from the raw string: only the tags
  // the whitelist knows can reach the DOM, and bare URLs become tappable.
  const bodyHtml = $derived(messageDisplayHtml(body, bodyFormat));
  const messageButtons = $derived((buttons || []).filter((button) => button?.label && button?.url));
  const showSupportAvatar = $derived(!isInternalNote && messageRole === "admin");
  const showUserAvatar = $derived(!isInternalNote && messageRole === "user");
  const showReceipt = $derived(outgoing && !serviceMessage);
  const messageRead = $derived(
    messageRole === "user" ? Boolean(readByAdminAt) : Boolean(readByUserAt)
  );
  const receiptLabel = $derived(
    t(messageRead ? "wa_support_message_read" : "wa_support_message_sent")
  );

  function formatTime(value: string): string {
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

<article
  class={`ticket-message-row ticket-message-row--${messageRole}`.trim()}
  class:ticket-message-row--outgoing={outgoing}
  class:ticket-message-row--incoming={!outgoing}
  class:ticket-message-row--internal={isInternalNote}
>
  <span class="ticket-message-avatar" aria-hidden="true">
    {#if isInternalNote}
      <Lock size={15} />
    {:else if showSupportAvatar}
      <BrandMark brand={supportBrand} size="sm" />
    {:else if showUserAvatar && userAvatarUrl}
      <img src={userAvatarUrl} alt="" loading="lazy" referrerpolicy="no-referrer" />
    {:else if showUserAvatar && userInitials}
      <strong>{userInitials}</strong>
    {:else if messageRole === "admin"}
      <LifeBuoy size={15} />
    {:else if messageRole === "user"}
      <UserRound size={15} />
    {:else}
      <MessageSquare size={15} />
    {/if}
  </span>

  <div class="ticket-message-content">
    <div class="ticket-message-meta">
      <span class="ticket-message-author">{roleLabel}</span>
      {#if timeLabel}
        <time datetime={createdAt}>{timeLabel}</time>
      {/if}
      {#if showReceipt}
        <span
          class:ticket-message-receipt--read={messageRead}
          class="ticket-message-receipt"
          title={receiptLabel}
          aria-label={receiptLabel}
        >
          {#if messageRead}<CheckCheck size={15} />{:else}<Check size={15} />{/if}
        </span>
      {/if}
    </div>

    <div class="ticket-message-bubble">
      {#if imageUrl}
        <img
          class="ticket-message-image"
          src={imageUrl}
          alt={t("wa_message_image_alt", {}, "Attached image")}
          loading="lazy"
        />
      {/if}
      {#if bodyHtml}
        <!-- eslint-disable-next-line svelte/no-at-html-tags -->
        <div class="ticket-message-text">{@html bodyHtml}</div>
      {/if}
      {#if messageButtons.length}
        <div class="ticket-message-buttons">
          {#each messageButtons as button, index (`${index}:${button.url}`)}
            <a
              class="ticket-message-button"
              href={button.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {button.label}
            </a>
          {/each}
        </div>
      {/if}
    </div>
  </div>
</article>
