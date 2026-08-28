<script lang="ts">
  import MessageLocaleTabs from "$lib/admin/components/MessageLocaleTabs.svelte";
  import type { TranslationLanguage } from "$lib/admin/stores/translationsStore";
  import {
    MAX_MENU_BUTTONS,
    createMenuButtonDraft,
    parseMenuButtonDrafts,
    reorderMenuButtonDrafts,
    serializeMenuButtonDrafts,
    type MenuButtonDraft,
    type MenuButtonKind,
  } from "$lib/admin/menuButtons.js";
  import { AdminButton, AdminSelect } from "$components/patterns/admin/index.js";
  import { Input, Sortable } from "$components/ui/index.js";
  import { Plus, Trash2, TriangleAlert } from "$components/ui/icons.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    value,
    languages,
    at,
    onValueChange,
  }: {
    value: string;
    languages: TranslationLanguage[];
    at: TranslateFn;
    onValueChange: (value: string) => void;
  } = $props();

  const availableLanguages = $derived(
    languages.length
      ? languages
      : [
          { code: "ru", label: "Russian", base: true },
          { code: "en", label: "English", base: true },
        ]
  );
  const languageCodes = $derived(availableLanguages.map((language) => language.code));
  const parsed = $derived(parseMenuButtonDrafts(value));
  const buttons = $derived(parsed.buttons);
  const writtenLanguages = $derived(
    languageCodes.filter((language) =>
      buttons.every((button) => Boolean(button.labels[language]?.trim()))
    )
  );
  const missingLabels = $derived(
    buttons.some((button) => languageCodes.some((language) => !button.labels[language]?.trim()))
  );
  let activeLanguage = $state("");

  $effect(() => {
    if (!languageCodes.includes(activeLanguage)) activeLanguage = languageCodes[0] || "ru";
  });

  const kindOptions = $derived([
    { value: "external", label: at("menu_buttons_kind_external", {}, "External link") },
    { value: "telegram", label: at("menu_buttons_kind_telegram", {}, "Telegram link") },
    { value: "webapp", label: at("menu_buttons_kind_webapp", {}, "Web App section") },
  ]);
  const iconOptions = $derived([
    { value: "", label: at("menu_buttons_icon_none", {}, "No icon") },
    { value: "ExternalLink", label: "🔗 ExternalLink" },
    { value: "Globe2", label: "🌐 Globe2" },
    { value: "Send", label: "✈️ Send" },
    { value: "MessageSquare", label: "💬 MessageSquare" },
    { value: "Users", label: "👥 Users" },
    { value: "Home", label: "🏠 Home" },
    { value: "Gift", label: "🎁 Gift" },
    { value: "Star", label: "⭐ Star" },
    { value: "Zap", label: "⚡ Zap" },
    { value: "Shield", label: "🛡️ Shield" },
    { value: "LifeBuoy", label: "🛟 LifeBuoy" },
    { value: "CircleQuestionMark", label: "❓ CircleQuestionMark" },
    { value: "🔗", label: "🔗 Emoji" },
    { value: "📢", label: "📢 Emoji" },
    { value: "💬", label: "💬 Emoji" },
    { value: "🎁", label: "🎁 Emoji" },
    { value: "⭐", label: "⭐ Emoji" },
  ]);
  const sectionOptions = $derived([
    { value: "home", label: at("menu_buttons_section_home", {}, "Home") },
    { value: "plans", label: at("menu_buttons_section_plans", {}, "Plans and checkout") },
    { value: "install", label: at("menu_buttons_section_install", {}, "Connection") },
    { value: "trial", label: at("menu_buttons_section_trial", {}, "Trial") },
    { value: "invite", label: at("menu_buttons_section_invite", {}, "Invite friends") },
    { value: "partner", label: at("menu_buttons_section_partner", {}, "Partner program") },
    { value: "devices", label: at("menu_buttons_section_devices", {}, "Devices") },
    { value: "support", label: at("menu_buttons_section_support", {}, "Support") },
    { value: "settings", label: at("menu_buttons_section_settings", {}, "Settings") },
    { value: "status", label: at("menu_buttons_section_status", {}, "Service status") },
  ]);

  function commit(next: MenuButtonDraft[]): void {
    onValueChange(serializeMenuButtonDrafts(next));
  }

  function addButton(): void {
    if (buttons.length >= MAX_MENU_BUTTONS) return;
    commit([...buttons, createMenuButtonDraft(languageCodes)]);
  }

  function removeButton(index: number): void {
    commit(buttons.filter((_, buttonIndex) => buttonIndex !== index));
  }

  function updateButton(index: number, patch: Partial<MenuButtonDraft>): void {
    commit(
      buttons.map((button, buttonIndex) =>
        buttonIndex === index ? { ...button, ...patch } : button
      )
    );
  }

  function updateKind(index: number, kind: MenuButtonKind): void {
    updateButton(index, {
      kind,
      target: kind === "webapp" ? "home" : "",
    });
  }

  function updateLabel(index: number, text: string): void {
    const button = buttons[index];
    if (!button) return;
    updateButton(index, {
      labels: { ...button.labels, [activeLanguage]: text },
    });
  }
</script>

<div class="menu-buttons-editor">
  <MessageLocaleTabs
    languages={availableLanguages}
    active={activeLanguage}
    written={writtenLanguages}
    {at}
    onSelect={(language) => (activeLanguage = language)}
  />

  {#if parsed.invalid}
    <div class="menu-buttons-warning" role="alert">
      <TriangleAlert size={16} />
      {at("menu_buttons_invalid_json", {}, "The saved button configuration is invalid JSON.")}
    </div>
  {:else if missingLabels}
    <div class="menu-buttons-warning">
      <TriangleAlert size={16} />
      {at(
        "menu_buttons_missing_locales",
        {},
        "Fill in a caption for every configured language before saving."
      )}
    </div>
  {/if}

  {#if buttons.length}
    <Sortable
      items={buttons}
      class="admin-row-editor-line menu-buttons-row"
      getKey={(button: MenuButtonDraft) => button.id}
      handleLabel={at("menu_buttons_reorder", {}, "Drag to reorder menu buttons")}
      onReorder={(from, to) => commit(reorderMenuButtonDrafts(buttons, from, to))}
    >
      {#snippet children(button: MenuButtonDraft, index: number)}
        <AdminSelect
          value={button.icon}
          items={iconOptions}
          ariaLabel={at("menu_buttons_icon", {}, "Icon or emoji")}
          onValueChange={(icon) => updateButton(index, { icon })}
        />
        <Input
          class="input"
          value={button.labels[activeLanguage] || ""}
          maxlength={64}
          placeholder={at(
            "menu_buttons_label_placeholder",
            { language: activeLanguage.toUpperCase() },
            `Button text (${activeLanguage.toUpperCase()})`
          )}
          oninput={(event) => updateLabel(index, (event.currentTarget as HTMLInputElement).value)}
        />
        <AdminSelect
          value={button.kind}
          items={kindOptions}
          ariaLabel={at("menu_buttons_target_type", {}, "Destination type")}
          onValueChange={(kind) => updateKind(index, kind as MenuButtonKind)}
        />
        {#if button.kind === "webapp"}
          <AdminSelect
            value={button.target}
            items={sectionOptions}
            ariaLabel={at("menu_buttons_webapp_section", {}, "Web App section")}
            onValueChange={(target) => updateButton(index, { target })}
          />
        {:else}
          <Input
            class="input"
            value={button.target}
            maxlength={2048}
            placeholder={button.kind === "telegram"
              ? at("menu_buttons_telegram_placeholder", {}, "https://t.me/channel or @username")
              : at("menu_buttons_external_placeholder", {}, "https://example.com")}
            oninput={(event) =>
              updateButton(index, {
                target: (event.currentTarget as HTMLInputElement).value,
              })}
          />
        {/if}
        <AdminButton
          size="sm"
          variant="danger"
          aria-label={at("menu_buttons_remove", {}, "Remove button")}
          onclick={() => removeButton(index)}
        >
          <Trash2 size={13} />
        </AdminButton>
      {/snippet}
    </Sortable>
  {:else if !parsed.invalid}
    <p class="admin-muted menu-buttons-empty">
      {at("menu_buttons_empty", {}, "No custom buttons yet.")}
    </p>
  {/if}

  {#if !parsed.invalid && buttons.length < MAX_MENU_BUTTONS}
    <AdminButton variant="ghost" onclick={addButton}>
      <Plus size={14} />
      {at("menu_buttons_add", {}, "Add button")}
    </AdminButton>
  {/if}
</div>

<style>
  .menu-buttons-editor {
    display: grid;
    width: 100%;
    gap: 12px;
  }

  :global(.menu-buttons-row) {
    grid-template-columns:
      24px minmax(150px, 0.8fr) minmax(180px, 1.25fr) minmax(160px, 0.9fr) minmax(220px, 1.5fr)
      auto;
  }

  .menu-buttons-warning {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--warning);
    font-size: 12px;
  }

  .menu-buttons-empty {
    margin: 0;
  }

  @media (max-width: 1050px) {
    :global(.menu-buttons-row) {
      grid-template-columns:
        24px minmax(130px, 0.8fr) minmax(180px, 1.2fr) minmax(160px, 0.9fr) minmax(180px, 1.2fr)
        auto;
    }
  }

  @media (max-width: 720px) {
    :global(.menu-buttons-row) {
      grid-template-columns: 1fr;
    }
  }
</style>
