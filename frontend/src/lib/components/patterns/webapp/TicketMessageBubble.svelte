<script lang="ts">
  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import TicketMessageImage from "./TicketMessageImage.svelte";
  import {
    Check,
    CheckCheck,
    LifeBuoy,
    Lock,
    MessageSquare,
    UserRound,
  } from "$components/ui/icons.js";
  import { messageDisplayHtml } from "$lib/richtext/telegramHtml";
  import { customEmojiPreviews } from "$lib/richtext/customEmojiPreview";
  import type { CustomEmojiMediaLoader } from "$lib/richtext/types";
  import EmojiGlyph from "$lib/telegramEmoji/EmojiGlyph.svelte";

  import type { TicketMessageButtonLike } from "./types.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type ImageViewerLabels = {
    open: string;
    title: string;
    close: string;
    zoomIn: string;
    zoomOut: string;
    reset: string;
  };
  type Props = {
    role?: string;
    body?: string;
    bodyFormat?: string;
    imageUrls?: string[];
    loadImage?: (url: string) => Promise<Blob>;
    loadCustomEmojiMedia?: CustomEmojiMediaLoader;
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
    imageViewerLabels?: ImageViewerLabels;
    t?: TranslateFn;
  };

  let {
    role = "user",
    body = "",
    bodyFormat = "text",
    imageUrls = [],
    loadImage = undefined,
    loadCustomEmojiMedia = undefined,
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
    imageViewerLabels = {
      open: "Open image",
      title: "Image",
      close: "Close image",
      zoomIn: "Zoom in",
      zoomOut: "Zoom out",
      reset: "Reset zoom",
    },
    t = (key, _params = {}, fallback = "") => fallback || key,
  }: Props = $props();

  const messageRole = $derived(role || "system");
  const serviceMessage = $derived(isInternalNote || messageRole === "system");
  const outgoing = $derived(
    (perspective === "admin" && (["admin", "connector"].includes(messageRole) || serviceMessage)) ||
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
  const bodyHtml = $derived(
    messageDisplayHtml(body, bodyFormat, { customEmoji: Boolean(loadCustomEmojiMedia) })
  );
  const messageButtons = $derived((buttons || []).filter((button) => button?.label && button?.url));
  const showSupportAvatar = $derived(
    !isInternalNote && ["admin", "connector"].includes(messageRole)
  );
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
      {#if imageUrls.length}
        <div class="ticket-message-images" class:is-gallery={imageUrls.length > 1}>
          {#each imageUrls as imageUrl (imageUrl)}
            <TicketMessageImage {imageUrl} {loadImage} {imageViewerLabels} {t} />
          {/each}
        </div>
      {/if}
      {#if bodyHtml}
        <div
          class="ticket-message-text"
          {@attach customEmojiPreviews(bodyHtml, loadCustomEmojiMedia)}
        >
          <!-- Rendered from the safe parsed whitelist, never the stored HTML source. -->
          <!-- eslint-disable-next-line svelte/no-at-html-tags -->
          {@html bodyHtml}
        </div>
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
              {#if button.icon_emoji || button.icon_custom_emoji_id}
                <span class="ticket-button-icon">
                  <EmojiGlyph
                    fallback={button.icon_emoji || "◻️"}
                    customEmojiId={button.icon_custom_emoji_id}
                    {loadCustomEmojiMedia}
                    size={20}
                  />
                </span>
              {/if}
              {button.label}
            </a>
          {/each}
        </div>
      {/if}
    </div>
  </div>
</article>

<style>
  .ticket-message-images {
    margin-bottom: 6px;
  }

  .ticket-message-images:last-child {
    margin-bottom: 0;
  }

  .ticket-message-images.is-gallery {
    width: min(360px, 58vw);
    max-width: 100%;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 4px;
  }

  .is-gallery :global(.ticket-message-image-trigger) {
    width: 100%;
    margin: 0;
  }

  .is-gallery :global(.ticket-message-image) {
    width: 100%;
    aspect-ratio: 4 / 3;
    object-fit: cover;
  }

  .ticket-button-icon {
    display: inline-flex;
    margin-inline-end: 4px;
    vertical-align: middle;
  }
</style>
