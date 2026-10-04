<script
  lang="ts"
  generics="Row extends { id: number; kind: string; label: string; url: string; promoCode: string; section: string; labels?: Record<string, string>; iconCustomEmojiId?: string | null; iconEmoji?: string }"
>
  import { tick } from "svelte";
  import { AdminButton, AdminCombobox, AdminSelect } from "$components/patterns/admin/index.js";
  import { Input, Sortable } from "$components/ui/index.js";
  import { Plus, Sparkles, Trash2, X } from "$components/ui/icons.js";
  import { getAdminApiBlob } from "$lib/admin/context";
  import { CUSTOMER_WEBAPP_SECTIONS } from "$lib/admin/messageButtonTargets.js";
  import type { CustomEmojiMediaLoader } from "$lib/richtext/types";
  import EmojiGlyph from "$lib/telegramEmoji/EmojiGlyph.svelte";
  import EmojiPicker from "$lib/telegramEmoji/EmojiPicker.svelte";
  import { defaultTelegramEmojiMediaApi } from "$lib/telegramEmoji/api";
  import { buildTelegramEmojiMediaPath } from "$lib/telegramEmoji/paths";
  import type { EmojiItem } from "$lib/telegramEmoji/types";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type SelectOption = { value: string; label: string; disabled?: boolean; group?: string };

  function mediaApi() {
    try {
      return getAdminApiBlob();
    } catch {
      return defaultTelegramEmojiMediaApi;
    }
  }
  const loadMedia = mediaApi();
  const loadCustomEmojiMedia: CustomEmojiMediaLoader = (id, signal) =>
    loadMedia(buildTelegramEmojiMediaPath(id), { signal });
  let paletteButtonId = $state<number | null>(null);
  let paletteTrigger: HTMLButtonElement | null = null;
  let chosenEmojis = $state<Record<string, EmojiItem>>({});

  /** Caption being authored: the active language's, or the shared one. */
  function captionOf(button: Row): string {
    return language ? (button.labels?.[language] ?? "") : button.label;
  }

  // Writing per language keeps the shared caption untouched, so a host that
  // never sets a language keeps editing exactly the field it always did.
  function captionPatch(button: Row, value: string): Partial<Row> {
    if (!language) return { label: value } as Partial<Row>;
    return { labels: { ...(button.labels ?? {}), [language]: value } } as Partial<Row>;
  }

  let {
    buttons,
    at,
    max = 4,
    promoOptions = [],
    promoOptionsLoading = false,
    promoOptionsLoaded = false,
    extraKinds = [],
    onAdd,
    onRemove,
    onUpdate,
    onReorder,
    onRequestPromoOptions,
    language = "",
  }: {
    buttons: Row[];
    at: TranslateFn;
    /**
     * Language whose caption is being authored. When set, the field edits that
     * language's caption and leaving it empty falls back to the prepared
     * caption for the button's kind, translated for each recipient.
     */
    language?: string;
    max?: number;
    promoOptions?: SelectOption[];
    promoOptionsLoading?: boolean;
    promoOptionsLoaded?: boolean;
    /** Extra button kinds a host offers on top of the shared ones. */
    extraKinds?: SelectOption[];
    onAdd: () => void;
    onRemove: (index: number) => void;
    onUpdate: (index: number, fields: Partial<Row>) => void;
    onReorder: (from: number, to: number) => void;
    onRequestPromoOptions?: (query?: string) => void;
  } = $props();

  const paletteButton = $derived(buttons.find((button) => button.id === paletteButtonId));
  $effect(() => {
    if (paletteButtonId !== null && !paletteButton) closePicker();
  });

  function closePicker() {
    const trigger = paletteTrigger;
    paletteTrigger = null;
    paletteButtonId = null;
    void tick().then(() => {
      if (paletteButtonId === null && trigger?.isConnected) trigger.focus();
    });
  }

  function chooseEmoji(item: EmojiItem) {
    const index = buttons.findIndex((button) => button.id === paletteButtonId);
    if (index >= 0) {
      if (item.id) chosenEmojis = { ...chosenEmojis, [item.id]: item };
      onUpdate(index, {
        iconCustomEmojiId: item.id || null,
        iconEmoji: item.fallback,
      } as Partial<Row>);
    }
    closePicker();
  }

  const kindOptions = $derived([
    { value: "url", label: at("broadcast_button_kind_url", {}, "Link") },
    {
      value: "promo_bot",
      label: at("broadcast_button_kind_promo_bot", {}, "Promo code — in bot"),
    },
    {
      value: "promo_webapp",
      label: at("broadcast_button_kind_promo_webapp", {}, "Promo code — in web app"),
    },
    {
      value: "webapp_section",
      label: at("broadcast_button_kind_webapp_section", {}, "Web app screen"),
    },
    ...extraKinds,
  ]);
  // Screens a customer-facing button may open; the admin panel is not one.
  const sectionFallbacks: Record<(typeof CUSTOMER_WEBAPP_SECTIONS)[number], string> = {
    plans: "Plans and checkout",
    home: "Home",
    install: "Install",
    trial: "Trial",
    invite: "Invite friends",
    partner: "Partner program",
    devices: "Devices",
    support: "Support",
    settings: "Settings",
    notifications: "Notification settings",
  };
  const sectionOptions = $derived(
    CUSTOMER_WEBAPP_SECTIONS.map((section) => ({
      value: section,
      label: at(`broadcast_button_section_${section}`, {}, sectionFallbacks[section]),
    }))
  );
  // A kind outside the shared ones is host-owned and carries no promo code.
  const sharedKinds = new Set(["url", "promo_bot", "promo_webapp"]);
  const hasPromoButtons = $derived(
    buttons.some((button) => button.kind !== "url" && sharedKinds.has(button.kind))
  );

  // Codes are only worth fetching once a promo button actually exists.
  $effect(() => {
    if (hasPromoButtons) onRequestPromoOptions?.();
  });

  function needsPromoCode(kind: string): boolean {
    return kind !== "url" && sharedKinds.has(kind);
  }
</script>

<div class="admin-row-editor message-buttons-editor">
  <Sortable
    items={buttons}
    class="admin-row-editor-line admin-row-editor-broadcast message-button-row"
    getKey={(button: Row) => button.id}
    handleLabel={at("broadcast_button_reorder", {}, "Drag to reorder buttons")}
    {onReorder}
  >
    {#snippet children(button: Row, index: number)}
      <AdminSelect
        class="message-button-kind"
        controlSize="md"
        value={button.kind}
        items={kindOptions}
        ariaLabel={at("broadcast_buttons_label", {}, "Buttons")}
        onValueChange={(value) => onUpdate(index, { kind: value } as Partial<Row>)}
      />
      <div class="message-button-emoji">
        <AdminButton
          class="message-button-emoji-trigger"
          size="sm"
          controlSize="md"
          variant="ghost"
          aria-label={button.iconEmoji || button.iconCustomEmojiId
            ? at("message_button_emoji_change", { emoji: button.iconEmoji || "◻️" })
            : at("message_button_emoji_choose")}
          onclick={(event) => {
            paletteTrigger =
              event.currentTarget instanceof HTMLButtonElement ? event.currentTarget : null;
            paletteButtonId = button.id;
          }}
        >
          {#if button.iconEmoji || button.iconCustomEmojiId}
            <EmojiGlyph
              fallback={button.iconEmoji || "◻️"}
              customEmojiId={button.iconCustomEmojiId}
              {loadCustomEmojiMedia}
              url={chosenEmojis[button.iconCustomEmojiId || ""]?.thumbnail_url}
              size={20}
            />
          {:else}<Sparkles size={16} />{/if}{at("message_button_emoji_label")}
        </AdminButton>
        {#if button.iconEmoji || button.iconCustomEmojiId}
          <AdminButton
            size="icon"
            controlSize="md"
            variant="ghost"
            aria-label={at("message_button_emoji_remove")}
            onclick={() =>
              onUpdate(index, { iconCustomEmojiId: null, iconEmoji: "" } as Partial<Row>)}
            ><X size={14} /></AdminButton
          >
        {/if}
      </div>
      <Input
        class="input message-button-caption"
        controlSize="md"
        aria-label={at("broadcast_button_label_auto")}
        value={captionOf(button)}
        maxlength={64}
        placeholder={at(
          "broadcast_button_label_auto",
          {},
          "Default caption in the customer's language"
        )}
        oninput={(event) =>
          onUpdate(index, captionPatch(button, (event.currentTarget as HTMLInputElement).value))}
      />
      {#if needsPromoCode(button.kind)}
        <AdminCombobox
          class="message-button-target"
          controlSize="md"
          value={button.promoCode}
          items={promoOptions}
          placeholder={at("broadcast_button_promo_search", {}, "Search or enter a promo code")}
          ariaLabel={at("broadcast_button_promo_select", {}, "Select a code")}
          loading={promoOptionsLoading || !promoOptionsLoaded}
          loadingMessage={at("broadcast_button_promo_loading", {}, "Loading codes...")}
          emptyMessage={at(
            "broadcast_button_promo_no_matches",
            {},
            "No matching active codes — enter the exact code"
          )}
          maxLength={58}
          onValueChange={(value) =>
            onUpdate(index, { promoCode: value.toUpperCase() } as Partial<Row>)}
          onInputChange={(value) => onRequestPromoOptions?.(value)}
        />
      {:else if button.kind === "webapp_section"}
        <AdminSelect
          class="message-button-target"
          controlSize="md"
          value={button.section}
          items={sectionOptions}
          placeholder={at("broadcast_button_section_select", {}, "Select a screen")}
          ariaLabel={at("broadcast_button_section_select", {}, "Select a screen")}
          onValueChange={(value) => onUpdate(index, { section: value } as Partial<Row>)}
        />
      {:else if button.kind === "url"}
        <Input
          class="input message-button-target"
          controlSize="md"
          aria-label={at("broadcast_button_url_placeholder")}
          value={button.url}
          placeholder={at("broadcast_button_url_placeholder", {}, "https://…")}
          oninput={(event) =>
            onUpdate(index, {
              url: (event.currentTarget as HTMLInputElement).value,
            } as Partial<Row>)}
        />
      {:else}
        <span class="admin-muted admin-row-editor-static message-button-target">
          {at("broadcast_button_no_target", {}, "Target is chosen automatically")}
        </span>
      {/if}
      <AdminButton
        class="message-button-remove"
        size="icon"
        controlSize="md"
        variant="danger"
        aria-label={at("broadcast_button_remove", {}, "Remove button")}
        onclick={() => onRemove(index)}
      >
        <Trash2 size={13} />
      </AdminButton>
    {/snippet}
  </Sortable>
</div>

{#if buttons.length < max}
  <div>
    <AdminButton controlSize="md" variant="ghost" onclick={onAdd}>
      <Plus size={14} />
      {at("broadcast_button_add", {}, "Add button")}
    </AdminButton>
  </div>
{/if}

<EmojiPicker
  open={paletteButtonId !== null && Boolean(paletteButton)}
  onOpenChange={(value) => {
    if (!value) closePicker();
  }}
  onSelect={chooseEmoji}
  initialTab={paletteButton?.iconCustomEmojiId ? "custom" : "ordinary"}
  {at}
/>

<style>
  .message-buttons-editor {
    container-type: inline-size;
  }
  .message-buttons-editor :global(.message-button-row) {
    grid-template-columns:
      24px minmax(120px, 0.9fr) 132px minmax(110px, 1fr) minmax(110px, 1fr)
      auto;
  }
  .message-buttons-editor :global(.message-button-kind),
  .message-buttons-editor :global(.message-button-caption),
  .message-buttons-editor :global(.message-button-target) {
    width: 100%;
    min-width: 0;
  }
  .message-button-emoji {
    display: flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
  }
  .message-button-emoji :global(.message-button-emoji-trigger) {
    flex: 1;
    min-width: 0;
    padding-inline: 6px;
  }
  .admin-row-editor-static {
    font-size: 12px;
    align-self: center;
  }
  @container (max-width: 640px) {
    .message-buttons-editor :global(.message-button-row) {
      grid-template-columns: 24px minmax(0, 1fr) auto;
      align-items: start;
      padding: 10px;
      border: 1px solid var(--admin-border);
      border-radius: var(--radius-control);
    }
    .message-buttons-editor :global(.message-button-row > .ui-sortable-handle) {
      grid-column: 1;
      grid-row: 1 / 5;
    }
    .message-buttons-editor :global(.message-button-kind) {
      grid-column: 2;
      grid-row: 1;
    }
    .message-button-emoji {
      grid-column: 2;
      grid-row: 2;
    }
    .message-buttons-editor :global(.message-button-caption) {
      grid-column: 2;
      grid-row: 3;
    }
    .message-buttons-editor :global(.message-button-target) {
      grid-column: 2;
      grid-row: 4;
    }
    .message-buttons-editor :global(.message-button-remove) {
      grid-column: 3;
      grid-row: 1;
    }
  }
</style>
