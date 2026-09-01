<script
  lang="ts"
  generics="Row extends { id: number; kind: string; label: string; url: string; promoCode: string; section: string; labels?: Record<string, string> }"
>
  import { AdminButton, AdminCombobox, AdminSelect } from "$components/patterns/admin/index.js";
  import { Input, Sortable } from "$components/ui/index.js";
  import { Plus, Trash2 } from "$components/ui/icons.js";
  import { CUSTOMER_WEBAPP_SECTIONS } from "$lib/admin/messageButtonTargets.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type SelectOption = { value: string; label: string; disabled?: boolean; group?: string };

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

<div class="admin-row-editor">
  <Sortable
    items={buttons}
    class="admin-row-editor-line admin-row-editor-broadcast"
    getKey={(button: Row) => button.id}
    handleLabel={at("broadcast_button_reorder", {}, "Drag to reorder buttons")}
    {onReorder}
  >
    {#snippet children(button: Row, index: number)}
      <AdminSelect
        value={button.kind}
        items={kindOptions}
        ariaLabel={at("broadcast_buttons_label", {}, "Buttons")}
        onValueChange={(value) => onUpdate(index, { kind: value } as Partial<Row>)}
      />
      <Input
        class="input"
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
          value={button.section}
          items={sectionOptions}
          placeholder={at("broadcast_button_section_select", {}, "Select a screen")}
          ariaLabel={at("broadcast_button_section_select", {}, "Select a screen")}
          onValueChange={(value) => onUpdate(index, { section: value } as Partial<Row>)}
        />
      {:else if button.kind === "url"}
        <Input
          class="input"
          value={button.url}
          placeholder={at("broadcast_button_url_placeholder", {}, "https://…")}
          oninput={(event) =>
            onUpdate(index, {
              url: (event.currentTarget as HTMLInputElement).value,
            } as Partial<Row>)}
        />
      {:else}
        <span class="admin-muted admin-row-editor-static">
          {at("broadcast_button_no_target", {}, "Target is chosen automatically")}
        </span>
      {/if}
      <AdminButton
        size="sm"
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
    <AdminButton variant="ghost" onclick={onAdd}>
      <Plus size={14} />
      {at("broadcast_button_add", {}, "Add button")}
    </AdminButton>
  </div>
{/if}

<style>
  .admin-row-editor-static {
    font-size: 12px;
    align-self: center;
  }
</style>
