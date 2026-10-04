<script lang="ts">
  import { getAdminApi } from "$lib/admin/context";
  import { Dialog, Input } from "$components/ui";
  import { AdminButton, AdminField, AdminSelect } from "$components/patterns/admin";
  import { Clock, Plus, Search, Star } from "$components/ui/icons";
  import EmojiGlyph from "./EmojiGlyph.svelte";
  import EmojiLibraryManager from "./EmojiLibraryManager.svelte";
  import {
    defaultTelegramEmojiApi,
    emojiSelectionKey,
    getEmojiAdminId,
    getEmojiCatalog,
    getEmojiLibrary,
    telegramEmojiErrorCode,
    type TelegramEmojiApi,
    type TelegramEmojiMediaApi,
  } from "./api";
  import {
    readEmojiPreferences,
    writeEmojiPreferences,
    type EmojiPreferences,
  } from "./preferences";
  import type { EmojiItem, EmojiLibrary, TranslateFn } from "./types";

  function contextApi(): TelegramEmojiApi {
    try {
      return getAdminApi();
    } catch {
      return defaultTelegramEmojiApi;
    }
  }
  let {
    open,
    onOpenChange,
    onSelect,
    at,
    api = contextApi(),
    apiBlob,
    allowOrdinary = true,
  }: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSelect: (item: EmojiItem) => void;
    at: TranslateFn;
    api?: TelegramEmojiApi;
    apiBlob?: TelegramEmojiMediaApi;
    allowOrdinary?: boolean;
  } = $props();

  type PickerTab = "ordinary" | "custom" | "recent" | "favorites" | "library";
  const ordinary = [
    "😀",
    "😊",
    "🥰",
    "😎",
    "🤩",
    "🤔",
    "🥳",
    "🤗",
    "😇",
    "😴",
    "😂",
    "🥲",
    "❤️",
    "💙",
    "💚",
    "💜",
    "🔥",
    "✨",
    "⭐",
    "💎",
    "⚡",
    "🎉",
    "🎁",
    "🎯",
    "👍",
    "👋",
    "🙌",
    "👏",
    "🙏",
    "💪",
    "👌",
    "🤝",
    "✅",
    "❌",
    "❗",
    "❓",
    "🚀",
    "🌍",
    "🌐",
    "🔑",
    "🔒",
    "🔐",
    "🛡️",
    "🤖",
    "💬",
    "📣",
    "📱",
    "💻",
    "🏠",
    "⚙️",
    "📊",
    "📈",
    "📝",
    "📅",
    "⏳",
    "🔔",
    "💳",
    "💰",
    "🎟️",
    "ℹ️",
  ].map((fallback): EmojiItem => ({
    id: "",
    fallback,
    set_name: null,
    thumbnail_url: null,
    format: "static",
  }));

  let tab = $state<PickerTab>("custom");
  let search = $state("");
  let set = $state("");
  let library = $state<EmojiLibrary | null>(null);
  let catalogItems = $state<EmojiItem[]>([]);
  let total = $state(0);
  let loading = $state(false);
  let loadingMore = $state(false);
  let error = $state("");
  let libraryError = $state("");
  let selected = $state<EmojiItem | null>(null);
  let adminId = $state("");
  let preferences = $state<EmojiPreferences>({ recent: [], favorites: [] });
  let libraryGeneration = $state(0);
  let grid = $state<HTMLDivElement | null>(null);
  let requestSequence = 0;
  const selectedKey = $derived(selected ? emojiSelectionKey(selected) : "");
  const favorite = $derived(
    Boolean(
      selected && preferences.favorites.some((item) => emojiSelectionKey(item) === selectedKey)
    )
  );
  const setItems = $derived([
    { value: "", label: at("telegram_emoji_all_sets") },
    ...(library?.sets || []).map((pack) => ({ value: pack.name, label: pack.title || pack.name })),
  ]);
  const tabs = $derived([
    ...(allowOrdinary
      ? [{ value: "ordinary" as const, label: at("telegram_emoji_ordinary") }]
      : []),
    { value: "custom" as const, label: at("telegram_emoji_sets") },
    { value: "recent" as const, label: at("telegram_emoji_recent") },
    { value: "favorites" as const, label: at("telegram_emoji_favorites") },
    { value: "library" as const, label: at("telegram_emoji_manage") },
  ]);
  const visibleItems = $derived.by(() => {
    const values =
      tab === "ordinary"
        ? ordinary
        : tab === "recent"
          ? preferences.recent
          : tab === "favorites"
            ? preferences.favorites
            : catalogItems;
    const term = search.trim().toLocaleLowerCase();
    return values.filter(
      (item) =>
        (allowOrdinary || item.id) &&
        (tab === "custom" ||
          !term ||
          `${item.id} ${item.fallback} ${item.set_name || ""}`.toLocaleLowerCase().includes(term))
    );
  });

  $effect(() => {
    if (!open) return;
    let canceled = false;
    selected = null;
    void Promise.allSettled([getEmojiLibrary(api), getEmojiAdminId(api)]).then(
      ([packs, identity]) => {
        if (canceled) return;
        if (packs.status === "fulfilled") {
          library = packs.value;
          libraryError = "";
        } else libraryError = telegramEmojiErrorCode(packs.reason, "telegram_emoji_load_failed");
        if (identity.status === "fulfilled") {
          adminId = identity.value;
          preferences = readEmojiPreferences(adminId);
        } else {
          adminId = "";
          preferences = { recent: [], favorites: [] };
        }
      }
    );
    return () => {
      canceled = true;
    };
  });

  $effect(() => {
    const showing = open && tab === "custom";
    const term = search;
    const pack = set;
    const generation = libraryGeneration;
    if (!showing) return;
    const sequence = ++requestSequence;
    const controller = new AbortController();
    loading = true;
    loadingMore = false;
    error = "";
    const timer = window.setTimeout(
      () => {
        void getEmojiCatalog(api, { set: pack, q: term }, controller.signal)
          .then((result) => {
            if (controller.signal.aborted || sequence !== requestSequence) return;
            catalogItems = result.items;
            total = result.total;
          })
          .catch((failure: unknown) => {
            if (!controller.signal.aborted && sequence === requestSequence) {
              error = telegramEmojiErrorCode(failure, "telegram_emoji_load_failed");
              catalogItems = [];
              total = 0;
            }
          })
          .finally(() => {
            if (!controller.signal.aborted && sequence === requestSequence) loading = false;
          });
      },
      generation ? 100 : 180
    );
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  });

  async function loadMore() {
    if (loading || loadingMore || catalogItems.length >= total) return;
    const sequence = requestSequence;
    loadingMore = true;
    error = "";
    try {
      const result = await getEmojiCatalog(api, { set, q: search, offset: catalogItems.length });
      if (sequence !== requestSequence || !open || tab !== "custom") return;
      catalogItems = [
        ...new Map([...catalogItems, ...result.items].map((item) => [item.id, item])).values(),
      ];
      total = result.total;
    } catch (failure) {
      if (sequence === requestSequence)
        error = telegramEmojiErrorCode(failure, "telegram_emoji_load_failed");
    } finally {
      if (sequence === requestSequence) loadingMore = false;
    }
  }

  function libraryChanged(value: EmojiLibrary) {
    library = value;
    libraryError = "";
    if (set && !value.sets.some((pack) => pack.name === set)) set = "";
    libraryGeneration += 1;
  }
  function toggleFavorite() {
    if (!selected) return;
    const values = preferences.favorites.filter((item) => emojiSelectionKey(item) !== selectedKey);
    preferences = {
      ...preferences,
      favorites: favorite ? values : [selected, ...values].slice(0, 60),
    };
    writeEmojiPreferences(adminId, preferences);
  }
  function choose() {
    if (!selected) return;
    preferences = {
      ...preferences,
      recent: [
        selected,
        ...preferences.recent.filter((item) => emojiSelectionKey(item) !== selectedKey),
      ].slice(0, 60),
    };
    writeEmojiPreferences(adminId, preferences);
    onSelect(selected);
    onOpenChange(false);
  }
  function moveFocus(event: KeyboardEvent, index: number) {
    const buttons = grid?.querySelectorAll<HTMLButtonElement>("button[data-emoji]");
    if (!buttons?.length || !grid) return;
    const gap = Number.parseFloat(getComputedStyle(grid).columnGap) || 0;
    const columns = Math.max(
      1,
      Math.round((grid.clientWidth + gap) / (buttons[0].clientWidth + gap))
    );
    const offsets: Record<string, number> = {
      ArrowRight: 1,
      ArrowLeft: -1,
      ArrowDown: columns,
      ArrowUp: -columns,
    };
    const target =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? buttons.length - 1
          : event.key in offsets
            ? Math.min(buttons.length - 1, Math.max(0, index + offsets[event.key]))
            : -1;
    if (target < 0) return;
    event.preventDefault();
    buttons[target].focus();
  }
</script>

<Dialog
  {open}
  portal
  title={at("telegram_emoji_picker_title")}
  description={at("telegram_emoji_picker_hint")}
  closeLabel={at("close")}
  onclose={() => onOpenChange(false)}
  class="admin-dialog telegram-emoji-dialog"
>
  <div class="picker-body">
    <nav class="picker-tabs" aria-label={at("telegram_emoji_views")}>
      {#each tabs as item (item.value)}
        <AdminButton
          size="sm"
          controlSize="md"
          variant={tab === item.value ? "primary" : "ghost"}
          aria-pressed={tab === item.value}
          onclick={() => {
            tab = item.value;
          }}
        >
          {#if item.value === "recent"}<Clock size={14} />{:else if item.value === "favorites"}<Star
              size={14}
            />{:else if item.value === "library"}<Plus size={14} />{/if}{item.label}
        </AdminButton>
      {/each}
    </nav>
    {#if tab === "library"}
      <EmojiLibraryManager {api} {at} onChange={libraryChanged} />
    {:else}
      <div class="picker-filters">
        <AdminField label={at("telegram_emoji_search")}>
          <div class="picker-search">
            <Search size={16} aria-hidden="true" /><Input
              type="search"
              controlSize="md"
              value={search}
              oninput={(event) => {
                search = event.currentTarget.value;
              }}
              placeholder={at("telegram_emoji_search_placeholder")}
              autocomplete="off"
            />
          </div>
        </AdminField>
        {#if tab === "custom"}<AdminField label={at("telegram_emoji_set")}
            ><AdminSelect
              controlSize="md"
              value={set}
              items={setItems}
              ariaLabel={at("telegram_emoji_set")}
              onValueChange={(value) => {
                set = value;
              }}
            /></AdminField
          >{/if}
      </div>
      {#if libraryError && tab === "custom"}<p class="picker-error" role="alert">
          {at(libraryError, {}, at("telegram_emoji_load_failed"))}
        </p>{/if}
      {#if error && tab === "custom"}
        <div class="picker-error" role="alert">
          <p>{at(error, {}, at("telegram_emoji_load_failed"))}</p>
          <AdminButton
            size="sm"
            controlSize="md"
            onclick={() => {
              libraryGeneration += 1;
            }}>{at("retry")}</AdminButton
          >
        </div>
      {/if}
      {#if loading && tab === "custom"}
        <p class="picker-muted" role="status">{at("loading")}</p>
        <div class="emoji-grid skeleton" aria-hidden="true">
          {#each Array(24) as _, index (index)}<span></span>{/each}
        </div>
      {:else if visibleItems.length}
        <div
          bind:this={grid}
          class="emoji-grid"
          role="group"
          aria-label={at("telegram_emoji_results")}
        >
          {#each visibleItems as item, index (emojiSelectionKey(item))}
            <AdminButton
              class="picker-cell"
              variant="ghost"
              data-emoji={emojiSelectionKey(item)}
              aria-label={`${item.fallback} ${item.id || at("telegram_emoji_ordinary")}`}
              aria-pressed={selectedKey === emojiSelectionKey(item)}
              title={`${item.fallback} ${item.id}${item.set_name ? ` · ${item.set_name}` : ""}`}
              onclick={() => {
                selected = item;
              }}
              ondblclick={() => {
                selected = item;
                choose();
              }}
              onkeydown={(event) => moveFocus(event, index)}
            >
              <EmojiGlyph
                fallback={item.fallback}
                url={item.thumbnail_url}
                size={30}
                loadMedia={apiBlob}
              />
              {#if preferences.favorites.some((value) => emojiSelectionKey(value) === emojiSelectionKey(item))}<span
                  class="cell-favorite"><Star size={10} fill="currentColor" /></span
                >{/if}
            </AdminButton>
          {/each}
        </div>
        {#if tab === "custom"}
          <div class="picker-pagination">
            <span>{at("telegram_emoji_loaded", { count: catalogItems.length, total })}</span
            >{#if catalogItems.length < total}<AdminButton
                size="sm"
                controlSize="md"
                disabled={loadingMore}
                onclick={() => {
                  void loadMore();
                }}>{loadingMore ? at("loading") : at("telegram_emoji_load_more")}</AdminButton
              >{/if}
          </div>
        {/if}
      {:else if tab !== "custom" || (!error && !libraryError)}
        <div class="picker-empty">
          <strong
            >{at(
              tab === "recent"
                ? "telegram_emoji_recent_empty"
                : tab === "favorites"
                  ? "telegram_emoji_favorites_empty"
                  : "telegram_emoji_empty"
            )}</strong
          >
          <p>{at("telegram_emoji_empty_hint")}</p>
          {#if tab === "custom"}<AdminButton
              size="sm"
              controlSize="md"
              onclick={() => {
                tab = "library";
              }}><Plus size={14} />{at("telegram_emoji_import")}</AdminButton
            >{/if}
        </div>
      {/if}
    {/if}
  </div>
  {#snippet footer()}
    <footer class="picker-footer">
      <div class="picker-selection" aria-live="polite">
        {#if selected}<EmojiGlyph
            loadMedia={apiBlob}
            fallback={selected.fallback}
            url={selected.thumbnail_url}
            size={32}
          />
          <div>
            <strong>{selected.fallback}</strong><code
              >{selected.id || at("telegram_emoji_ordinary")}</code
            >
          </div>
          <AdminButton
            variant="icon"
            size="icon"
            controlSize="md"
            aria-label={favorite ? at("telegram_emoji_unfavorite") : at("telegram_emoji_favorite")}
            aria-pressed={favorite}
            onclick={toggleFavorite}
            ><Star size={18} fill={favorite ? "currentColor" : "none"} /></AdminButton
          >
        {:else}<span>{at("telegram_emoji_select_hint")}</span>{/if}
      </div>
      <div class="picker-footer-actions">
        <AdminButton controlSize="md" variant="ghost" onclick={() => onOpenChange(false)}
          >{at("cancel")}</AdminButton
        ><AdminButton controlSize="md" variant="primary" disabled={!selected} onclick={choose}
          >{at("telegram_emoji_choose")}</AdminButton
        >
      </div>
    </footer>
  {/snippet}
</Dialog>

<style>
  :global(.telegram-emoji-dialog) {
    width: min(100%, 760px);
    max-width: 760px;
    max-height: min(760px, var(--dialog-available-height));
  }
  .picker-body {
    display: grid;
    gap: 18px;
    padding: 4px 0 0;
    min-width: 0;
  }
  .picker-tabs {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--admin-border);
  }
  .picker-filters {
    display: grid;
    grid-template-columns: minmax(0, 1.4fr) minmax(160px, 1fr);
    gap: 12px;
    align-items: end;
  }
  .picker-search {
    position: relative;
  }
  .picker-search > :global(svg) {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    left: 12px;
    color: var(--admin-muted);
    pointer-events: none;
  }
  .picker-search :global(.input) {
    padding-left: 36px;
    width: 100%;
  }
  .emoji-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(54px, 1fr));
    gap: 8px;
  }
  .emoji-grid :global(.picker-cell) {
    position: relative;
    aspect-ratio: 1;
    min-height: 54px;
    padding: 6px;
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    background: var(--admin-surface, var(--panel));
  }
  .emoji-grid :global(.picker-cell[aria-pressed="true"]) {
    border-color: var(--admin-accent);
    background: color-mix(in srgb, var(--admin-accent) 12%, var(--admin-surface, var(--panel)));
    box-shadow: 0 0 0 1px var(--admin-accent);
  }
  .cell-favorite {
    position: absolute;
    top: 4px;
    right: 4px;
    color: var(--admin-accent);
  }
  .skeleton span {
    aspect-ratio: 1;
    border-radius: 10px;
    background: var(--admin-border);
    opacity: 0.5;
  }
  .picker-muted,
  .picker-pagination,
  .picker-empty p {
    color: var(--admin-muted);
    font-size: 12px;
  }
  .picker-muted,
  .picker-error p {
    margin: 0;
  }
  .picker-error {
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
    color: var(--admin-danger, #ef4444);
    font-size: 13px;
  }
  .picker-pagination {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }
  .picker-empty {
    display: grid;
    justify-items: center;
    text-align: center;
    gap: 8px;
    padding: 28px 14px;
    min-height: 160px;
    border: 1px dashed var(--admin-border);
    border-radius: 12px;
  }
  .picker-empty p {
    margin: 0;
    max-width: 360px;
    line-height: 1.5;
  }
  .picker-empty strong {
    font-size: 14px;
  }
  .picker-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 14px 0 2px;
    border-top: 1px solid var(--admin-border);
  }
  .picker-selection,
  .picker-footer-actions {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .picker-selection {
    min-width: 0;
  }
  .picker-selection > span {
    color: var(--admin-muted);
    font-size: 12px;
  }
  .picker-selection > div {
    display: grid;
    min-width: 0;
    gap: 2px;
  }
  .picker-selection strong {
    font-size: 15px;
  }
  .picker-selection code {
    color: var(--admin-muted);
    font-size: 10px;
    overflow-wrap: anywhere;
  }
  .picker-footer-actions {
    flex: 0 0 auto;
  }
  @media (max-width: 560px) {
    .picker-filters {
      grid-template-columns: minmax(0, 1fr);
    }
    .picker-footer {
      flex-direction: column;
      align-items: stretch;
      gap: 12px;
    }
    .picker-footer-actions {
      justify-content: flex-end;
    }
    .picker-body {
      gap: 14px;
    }
    .emoji-grid {
      grid-template-columns: repeat(auto-fill, minmax(48px, 1fr));
      gap: 6px;
    }
    .emoji-grid :global(.picker-cell) {
      min-height: 48px;
    }
  }
</style>
