<script lang="ts">
  import { onMount } from "svelte";
  import { Input } from "$components/ui";
  import { AdminBadge, AdminButton, AdminField } from "$components/patterns/admin";
  import { Plus, RefreshCw, Trash2 } from "$components/ui/icons";
  import {
    defaultTelegramEmojiApi,
    getEmojiLibrary,
    importEmojiSource,
    refreshEmojiSource,
    removeEmojiSource,
    telegramEmojiErrorCode,
    type TelegramEmojiApi,
  } from "./api";
  import type { EmojiLibrary, TranslateFn } from "./types";
  import { emojiLibraryIsWarming, pollEmojiLibrary } from "./libraryPolling";

  let {
    at,
    api = defaultTelegramEmojiApi,
    active = true,
    onChange = () => {},
  }: {
    at: TranslateFn;
    api?: TelegramEmojiApi;
    active?: boolean;
    onChange?: (library: EmojiLibrary) => void;
  } = $props();
  let library = $state<EmojiLibrary | null>(null);
  let source = $state("");
  let loading = $state(true);
  let busy = $state("");
  let error = $state("");
  let notice = $state("");
  let pollError = $state("");
  let element = $state<HTMLElement | null>(null);
  let visible = $state(true);
  let alive = true;
  const sourceHintId = $props.id();
  const conflict = $derived(error.includes("conflict"));

  async function load() {
    loading = true;
    error = "";
    pollError = "";
    try {
      const result = await getEmojiLibrary(api);
      if (!alive) return;
      library = result;
      onChange(result);
    } catch (failure) {
      if (alive) error = telegramEmojiErrorCode(failure, "telegram_emoji_load_failed");
    } finally {
      if (alive) loading = false;
    }
  }

  async function mutate(action: "import" | "remove" | "refresh", value: string) {
    if (!library || busy || !value.trim()) return;
    busy = `${action}:${value}`;
    error = "";
    notice = "";
    pollError = "";
    try {
      const result =
        action === "import"
          ? await importEmojiSource(api, value.trim(), library.revision)
          : action === "remove"
            ? await removeEmojiSource(api, value, library.revision)
            : await refreshEmojiSource(api, value);
      if (!alive) return;
      library = result;
      onChange(result);
      if (action === "import") source = "";
      notice = `telegram_emoji_${action}_done`;
    } catch (failure) {
      if (alive) error = telegramEmojiErrorCode(failure, "telegram_emoji_operation_failed");
    } finally {
      if (alive) busy = "";
    }
  }

  onMount(() => {
    void load();
    return () => {
      alive = false;
    };
  });

  $effect(() => {
    const node = element;
    if (!node || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      visible = entries.some((entry) => entry.isIntersecting);
    });
    observer.observe(node);
    return () => observer.disconnect();
  });

  $effect(() => {
    if (!active || !visible || loading || busy || !emojiLibraryIsWarming(library)) return;
    return pollEmojiLibrary(
      api,
      (result) => {
        library = result;
        pollError = "";
        onChange(result);
      },
      (failure) => {
        pollError = telegramEmojiErrorCode(failure, "telegram_emoji_load_failed");
      }
    );
  });
</script>

<section bind:this={element} class="emoji-library" aria-label={at("telegram_emoji_library_title")}>
  <header class="library-heading">
    <div>
      <h3>{at("telegram_emoji_library_title")}</h3>
      <p>{at("telegram_emoji_library_hint")}</p>
    </div>
    <AdminButton
      size="sm"
      controlSize="md"
      variant="ghost"
      disabled={loading || Boolean(busy)}
      onclick={() => {
        void load();
      }}
    >
      <RefreshCw size={14} />{at("refresh")}
    </AdminButton>
  </header>
  {#if error || pollError}
    <div class="library-message error" role="alert">
      <p>{at(error || pollError, {}, at("telegram_emoji_operation_failed"))}</p>
      {#if conflict}<AdminButton
          size="sm"
          controlSize="md"
          onclick={() => {
            void load();
          }}>{at("telegram_emoji_reload")}</AdminButton
        >{/if}
    </div>
  {/if}
  {#if notice}<p class="library-message" role="status">{at(notice)}</p>{/if}
  {#if loading}
    <p class="muted" role="status">{at("loading")}</p>
  {:else if library}
    <form
      class="library-import"
      onsubmit={(event) => {
        event.preventDefault();
        void mutate("import", source);
      }}
    >
      <AdminField label={at("telegram_emoji_source_label")}>
        <Input
          controlSize="md"
          aria-describedby={sourceHintId}
          value={source}
          oninput={(event) => {
            source = event.currentTarget.value;
          }}
          placeholder={at("telegram_emoji_source_placeholder")}
          autocomplete="off"
          maxlength={256}
          disabled={Boolean(busy)}
        />
      </AdminField>
      <AdminButton
        controlSize="md"
        type="submit"
        variant="primary"
        disabled={Boolean(busy) || !source.trim()}
      >
        <Plus size={15} />{busy.startsWith("import:")
          ? at("telegram_emoji_importing")
          : at("telegram_emoji_import")}
      </AdminButton>
      <p id={sourceHintId} class="muted library-import-hint">{at("telegram_emoji_source_hint")}</p>
    </form>
    {#if library.sets.length}
      <ul class="pack-list">
        {#each library.sets as pack (pack.name)}
          <li>
            <div class="pack-copy">
              <strong>{pack.title || pack.name}</strong><code>{pack.name}</code>
              <span class="pack-meta"
                >{at("telegram_emoji_count", { count: pack.count })}
                <AdminBadge
                  variant={pack.state === "ready"
                    ? "success"
                    : pack.state === "error" || pack.state === "partial"
                      ? "warning"
                      : "muted"}
                >
                  {at(`telegram_emoji_state_${pack.state}`)}
                </AdminBadge>
              </span>
              {#if pack.state === "warming" || (pack.preview_count ?? 0) > 0}
                <div class="pack-progress">
                  <span role="status"
                    >{at("telegram_emoji_preview_progress", {
                      count: pack.cached_count ?? 0,
                      total: pack.preview_count ?? 0,
                    })}</span
                  >
                  <progress
                    max={Math.max(1, pack.preview_count ?? 0)}
                    value={pack.cached_count ?? 0}
                    aria-label={at("telegram_emoji_preview_progress", {
                      count: pack.cached_count ?? 0,
                      total: pack.preview_count ?? 0,
                    })}
                  ></progress>
                </div>
              {/if}
              {#if ["ready", "warming", "partial"].includes(pack.state) && pack.preview_count !== undefined && pack.preview_count < pack.count}
                <p class="muted">
                  {at("telegram_emoji_without_preview", { count: pack.count - pack.preview_count })}
                </p>
              {/if}
              {#if pack.state === "partial"}<p class="muted">
                  {at("telegram_emoji_partial_hint")}
                </p>{/if}
            </div>
            <div class="pack-actions">
              <AdminButton
                size="sm"
                controlSize="md"
                variant="ghost"
                disabled={Boolean(busy)}
                onclick={() => {
                  void mutate("refresh", pack.name);
                }}
              >
                <RefreshCw size={14} />{busy === `refresh:${pack.name}`
                  ? at("loading")
                  : at("refresh")}
              </AdminButton>
              <AdminButton
                size="sm"
                controlSize="md"
                variant="dangerSoft"
                disabled={Boolean(busy)}
                onclick={() => {
                  void mutate("remove", pack.name);
                }}
              >
                <Trash2 size={14} />{at("telegram_emoji_remove")}
              </AdminButton>
            </div>
          </li>
        {/each}
      </ul>
    {:else if !error}<p class="library-empty">{at("telegram_emoji_library_empty")}</p>{/if}
    {#if library.library.manual_ids.length}
      <h4>{at("telegram_emoji_manual_ids")}</h4>
      <ul class="manual-list">
        {#each library.library.manual_ids as id (id)}
          <li>
            <code>{id}</code><AdminButton
              size="sm"
              controlSize="md"
              variant="ghost"
              disabled={Boolean(busy)}
              aria-label={at("telegram_emoji_remove_id", { id })}
              onclick={() => {
                void mutate("remove", id);
              }}><Trash2 size={14} /></AdminButton
            >
          </li>
        {/each}
      </ul>
    {/if}
    <p class="muted library-footnote">{at("telegram_emoji_remove_hint")}</p>
  {:else}
    <AdminButton
      controlSize="md"
      onclick={() => {
        void load();
      }}>{at("retry")}</AdminButton
    >
  {/if}
</section>

<style>
  .emoji-library {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  .library-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
  }
  .library-heading > div {
    min-width: 0;
    flex: 1;
  }
  h3,
  h4,
  p {
    margin: 0;
  }
  h3 {
    font-size: 15px;
  }
  h4 {
    font-size: 13px;
  }
  .library-heading p,
  .muted {
    margin-top: 5px;
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.5;
  }
  .library-import {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: end;
    gap: 10px;
  }
  .library-import-hint {
    grid-column: 1 / -1;
    margin: 0;
  }
  .library-import :global(.input) {
    width: 100%;
  }
  .pack-list,
  .manual-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: grid;
    gap: 8px;
  }
  .pack-list > li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px;
    border: 1px solid var(--admin-border);
    border-radius: 10px;
  }
  .pack-copy {
    min-width: 0;
    display: grid;
    gap: 4px;
    flex: 1;
  }
  .pack-progress {
    display: grid;
    gap: 5px;
    margin-top: 5px;
    color: var(--admin-muted);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }
  .pack-progress progress {
    appearance: none;
    width: 100%;
    height: 6px;
    border: 0;
    overflow: hidden;
    border-radius: 4px;
    background: var(--admin-surface-bg, var(--admin-card-bg));
    accent-color: var(--admin-accent);
  }
  .pack-progress progress::-webkit-progress-bar {
    background: var(--admin-surface-bg, var(--admin-card-bg));
  }
  .pack-progress progress::-webkit-progress-value {
    background: var(--admin-accent);
  }
  .pack-progress progress::-moz-progress-bar {
    background: var(--admin-accent);
  }
  .pack-copy strong {
    overflow-wrap: anywhere;
  }
  code {
    color: var(--admin-muted);
    font-size: 11px;
    overflow-wrap: anywhere;
  }
  .pack-meta,
  .pack-actions {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }
  .pack-meta {
    color: var(--admin-muted);
    font-size: 12px;
  }
  .pack-actions {
    flex: 0 0 auto;
  }
  .library-empty {
    padding: 20px 12px;
    text-align: center;
    color: var(--admin-muted);
    border: 1px dashed var(--admin-border);
    border-radius: 10px;
    font-size: 13px;
  }
  .manual-list {
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  }
  .manual-list li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    border: 1px solid var(--admin-border);
    border-radius: 8px;
    padding: 4px 8px;
    min-width: 0;
  }
  .library-message {
    color: var(--admin-accent);
    background: var(--admin-surface-bg, var(--admin-card-bg));
    padding: 10px 12px;
    border-radius: 8px;
    font-size: 13px;
  }
  .library-message.error {
    color: var(--admin-danger, #ef4444);
    display: grid;
    justify-items: start;
    gap: 8px;
  }
  .library-footnote {
    margin: 0;
  }
  @media (max-width: 560px) {
    .library-import {
      grid-template-columns: minmax(0, 1fr);
    }
    .library-import > :global(.admin-btn) {
      width: 100%;
    }
    .pack-list > li {
      align-items: flex-start;
      flex-direction: column;
    }
    .pack-actions {
      width: 100%;
    }
    .library-heading {
      align-items: flex-start;
    }
  }
</style>
