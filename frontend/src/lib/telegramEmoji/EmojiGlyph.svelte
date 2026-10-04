<script lang="ts">
  import { getAdminApiBlob } from "$lib/admin/context";
  import { defaultTelegramEmojiMediaApi, type TelegramEmojiMediaApi } from "./api";
  import { buildTelegramEmojiMediaPath } from "./paths";

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
  const emojiId = $derived(
    /^\/api\/admin\/telegram-emoji\/media\/([1-9]\d*)$/.exec(url || "")?.[1] || ""
  );

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
    const id = emojiId;
    const loader = loadMedia;
    objectUrl = "";
    failed = false;
    if (!id || !visible) return;
    const controller = new AbortController();
    let resolved = "";
    void loader(buildTelegramEmojiMediaPath(id), { signal: controller.signal })
      .then((blob) => {
        if (controller.signal.aborted) return;
        if (!/^image\/(png|webp|jpeg|gif)$/i.test(blob.type)) {
          failed = true;
          return;
        }
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
  <span class:covered={objectUrl && !failed}>{fallback || "◻️"}</span>
  {#if objectUrl && !failed}
    <img
      src={objectUrl}
      alt=""
      loading="lazy"
      onerror={() => {
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
  .emoji-glyph > img {
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
</style>
