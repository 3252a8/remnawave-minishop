<script lang="ts">
  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import { ImageViewer } from "$components/ui/index.js";
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
    imageUrl?: string;
    loadImage?: (url: string) => Promise<Blob>;
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
    imageUrl = "",
    loadImage = undefined,
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
  let resolvedImageUrl = $state("");
  let imageLoadFailed = $state(false);
  let imageViewerOpen = $state(false);

  $effect(() => {
    const source = imageUrl;
    const loader = loadImage;
    resolvedImageUrl = "";
    imageLoadFailed = false;
    imageViewerOpen = false;
    if (!source) return;
    if (!loader) {
      resolvedImageUrl = source;
      return;
    }

    let active = true;
    let objectUrl = "";
    void loader(source)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        resolvedImageUrl = objectUrl;
      })
      .catch(() => {
        if (active) imageLoadFailed = true;
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  });

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
      {#if resolvedImageUrl}
        <button
          class="ticket-message-image-trigger"
          type="button"
          aria-label={imageViewerLabels.open}
          onclick={() => (imageViewerOpen = true)}
        >
          <img
            class="ticket-message-image"
            src={resolvedImageUrl}
            alt={t("wa_message_image_alt", {}, "Attached image")}
            loading="lazy"
          />
        </button>
      {:else if imageLoadFailed}
        <span class="ticket-message-image-error" role="alert">
          {t("wa_message_image_load_failed", {}, "The attached image could not be loaded")}
        </span>
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

<ImageViewer
  open={imageViewerOpen}
  src={resolvedImageUrl}
  alt={t("wa_message_image_alt", {}, "Attached image")}
  title={imageViewerLabels.title}
  closeLabel={imageViewerLabels.close}
  zoomInLabel={imageViewerLabels.zoomIn}
  zoomOutLabel={imageViewerLabels.zoomOut}
  resetLabel={imageViewerLabels.reset}
  onclose={() => (imageViewerOpen = false)}
/>
