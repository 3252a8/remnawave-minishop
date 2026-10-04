<script lang="ts">
  import { getAdminApiBlob } from "$lib/admin/context";
  import { Skeleton } from "$components/ui";
  import { defaultTelegramEmojiMediaApi, type TelegramEmojiMediaApi } from "./api";
  import { buildTelegramEmojiMediaUrlPath } from "./paths";
  import { isEmojiPreviewBlob, rejectEmojiPreviewBlob } from "./media";

  function contextMediaApi(): TelegramEmojiMediaApi {
    try {
      return getAdminApiBlob();
    } catch {
      return defaultTelegramEmojiMediaApi;
    }
  }
  let {
    fallback = "◻️",
    url = null,
    size = 28,
    loadMedia = contextMediaApi(),
  }: {
    fallback?: string;
    url?: string | null;
    size?: number;
    loadMedia?: TelegramEmojiMediaApi;
  } = $props();
  let element = $state<HTMLSpanElement | null>(null);
  let visible = $state(false);
  let objectUrl = $state("");
  let failed = $state(false);
  let decoded = $state(false);
  let loadedBlob: Blob | null = null;
  const mediaPath = $derived(url ? buildTelegramEmojiMediaUrlPath(url) : null);
  const loading = $derived(Boolean(mediaPath) && !failed && !decoded);

  $effect(() => {
    const node = element;
    if (!node) return;
    if (typeof IntersectionObserver === "undefined") {
      visible = true;
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        visible = true;
        observer.disconnect();
      },
      { rootMargin: "100px" }
    );
    observer.observe(node);
    return () => observer.disconnect();
  });

  $effect(() => {
    const path = mediaPath;
    const loader = loadMedia;
    objectUrl = "";
    failed = false;
    decoded = false;
    loadedBlob = null;
    if (!path || !visible) return;
    const controller = new AbortController();
    let resolved = "";
    void loader(path, { signal: controller.signal })
      .then((blob) => {
        if (controller.signal.aborted) return;
        if (!isEmojiPreviewBlob(blob)) {
          failed = true;
          return;
        }
        loadedBlob = blob;
        resolved = URL.createObjectURL(blob);
        objectUrl = resolved;
      })
      .catch(() => {
        if (!controller.signal.aborted) failed = true;
      });
    return () => {
      controller.abort();
      if (resolved) URL.revokeObjectURL(resolved);
    };
  });
</script>

<span bind:this={element} class="emoji-glyph" style={`--emoji-size: ${size}px`} aria-hidden="true">
  <span class:covered={loading || (decoded && !failed)}>{fallback || "◻️"}</span>
  {#if loading}<Skeleton class="emoji-skeleton" width={`${size}px`} height={`${size}px`} />{/if}
  {#if objectUrl && !failed}
    <img
      src={objectUrl}
      alt=""
      decoding="async"
      class:covered={!decoded}
      onload={(event) => {
        if (event.currentTarget.getAttribute("src") !== objectUrl) return;
        decoded = true;
      }}
      onerror={(event) => {
        if (event.currentTarget.getAttribute("src") !== objectUrl) return;
        if (loadedBlob) rejectEmojiPreviewBlob(loadedBlob);
        failed = true;
      }}
    />
  {/if}
</span>

<style>
  .emoji-glyph {
    display: inline-grid;
    flex: 0 0 auto;
    width: var(--emoji-size);
    height: var(--emoji-size);
    place-items: center;
    font-size: var(--emoji-size);
    line-height: 1;
  }
  .emoji-glyph > span,
  .emoji-glyph > img,
  .emoji-glyph :global(.emoji-skeleton) {
    grid-area: 1 / 1;
  }
  .emoji-glyph > img {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
  .covered {
    opacity: 0;
  }
  .emoji-glyph :global(.emoji-skeleton) {
    border-radius: 6px;
  }
</style>
