<script lang="ts">
  import MessageLocaleTabs from "$lib/admin/components/MessageLocaleTabs.svelte";
  import {
    CUSTOMER_WEBAPP_SECTIONS,
    isTelegramMessageButtonLink,
    normalizeMessageButtonLink,
  } from "$lib/admin/messageButtonTargets.js";
  import type { TranslationLanguage } from "$lib/admin/stores/translationsStore";
  import {
    DEFAULT_MENU_WEBAPP_ICON,
    MAX_MENU_BUTTONS,
    createMenuButtonDraft,
    parseMenuButtonDrafts,
    reorderMenuButtonDrafts,
    serializeMenuButtonDrafts,
    type MenuButtonDraft,
    type MenuButtonKind,
  } from "$lib/admin/menuButtons.js";
  import IconPickerDialog from "./IconPickerDialog.svelte";
  import { AdminButton, AdminSelect } from "$components/patterns/admin/index.js";
  import { Checkbox, Input, Sortable } from "$components/ui/index.js";
  import * as UiIcons from "$components/ui/icons.js";
  import { Plus, Trash2, TriangleAlert } from "$components/ui/icons.js";
  import type { ComponentType, SvelteComponent } from "svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type DynamicComponent = ComponentType<SvelteComponent<Record<string, unknown>>>;

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
  let iconPickerButtonId = $state("");
  let iconPickerSearch = $state("");

  const iconOptions = $derived(
    Object.keys(UiIcons)
      .filter((name) => /^[A-Z]/.test(name))
      .sort((a, b) => a.localeCompare(b))
  );
  const filteredIconOptions = $derived(
    iconOptions.filter((name) => name.toLowerCase().includes(iconPickerSearch.trim().toLowerCase()))
  );
  const iconPickerButton = $derived(
    buttons.find((button) => button.id === iconPickerButtonId) || null
  );

  $effect(() => {
    if (!languageCodes.includes(activeLanguage)) activeLanguage = languageCodes[0] || "ru";
  });

  const kindOptions = $derived([
    { value: "external", label: at("menu_buttons_kind_external", {}, "Link") },
    { value: "webapp", label: at("menu_buttons_kind_webapp", {}, "Web App section") },
  ]);
  const sectionFallbacks: Record<string, string> = {
    plans: "Plans and checkout",
    home: "Home",
    install: "Connection",
    trial: "Trial",
    invite: "Invite friends",
    partner: "Partner program",
    devices: "Devices",
    support: "Support",
    settings: "Settings",
    notifications: "Notification settings",
    status: "Service status",
  };
  const sectionOptions = $derived(
    [...CUSTOMER_WEBAPP_SECTIONS, "status"].map((section) => ({
      value: section,
      label: at(`menu_buttons_section_${section}`, {}, sectionFallbacks[section]),
    }))
  );

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

  function updateButtonById(id: string, patch: Partial<MenuButtonDraft>): void {
    commit(buttons.map((button) => (button.id === id ? { ...button, ...patch } : button)));
  }

  function iconComponent(name: unknown): DynamicComponent | null {
    const key = String(name || "").trim();
    return key ? ((UiIcons as Record<string, unknown>)[key] as DynamicComponent) || null : null;
  }

  function openIconPicker(id: string): void {
    iconPickerButtonId = id;
    iconPickerSearch = "";
  }

  function closeIconPicker(): void {
    iconPickerButtonId = "";
    iconPickerSearch = "";
  }

  function selectIcon(name: string): void {
    if (!iconPickerButtonId) return;
    updateButtonById(iconPickerButtonId, { webapp_icon: name });
    closeIconPicker();
  }

  function useDefaultIcon(): void {
    if (!iconPickerButtonId) return;
    updateButtonById(iconPickerButtonId, { webapp_icon: DEFAULT_MENU_WEBAPP_ICON });
  }

  function updateKind(index: number, kind: MenuButtonKind): void {
    updateButton(index, {
      kind,
      target: kind === "webapp" ? "home" : "",
    });
  }

  function displayedKind(button: MenuButtonDraft): "external" | "webapp" {
    return button.kind === "webapp" ? "webapp" : "external";
  }

  function updateLinkTarget(index: number, target: string): void {
    updateButton(index, { kind: "external", target });
  }

  function normalizeLinkTarget(index: number): void {
    const button = buttons[index];
    if (!button || button.kind === "webapp") return;
    const target = normalizeMessageButtonLink(button.target);
    if (!target) return;
    updateButton(index, {
      kind: isTelegramMessageButtonLink(target) ? "telegram" : "external",
      target,
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
        {@const WebappIcon = iconComponent(button.webapp_icon)}
        <div class="menu-buttons-presentation">
          <div class="menu-buttons-field">
            <span class="menu-buttons-field-label">
              {at("menu_buttons_webapp_icon", {}, "Web App icon")}
            </span>
            <AdminButton
              class="admin-icon-picker-trigger menu-button-icon-trigger"
              variant="ghost"
              onclick={() => openIconPicker(button.id)}
            >
              {#if WebappIcon}
                <WebappIcon size={16} />
              {/if}
              <span>{button.webapp_icon || at("menu_buttons_icon_none", {}, "No icon")}</span>
            </AdminButton>
          </div>
          <label class="menu-buttons-field menu-buttons-emoji-field">
            <span class="menu-buttons-field-label">
              {at("menu_buttons_telegram_emoji", {}, "Telegram emoji")}
            </span>
            <Input
              class="input"
              value={button.telegram_emoji}
              maxlength={16}
              aria-label={at("menu_buttons_telegram_emoji", {}, "Telegram emoji")}
              placeholder={at("menu_buttons_telegram_emoji_placeholder", {}, "For example: 📣")}
              oninput={(event) =>
                updateButton(index, {
                  telegram_emoji: (event.currentTarget as HTMLInputElement).value,
                })}
            />
          </label>
        </div>
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
          value={displayedKind(button)}
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
            placeholder={at(
              "menu_buttons_external_placeholder",
              {},
              "https://example.com, t.me/channel or @username"
            )}
            oninput={(event) =>
              updateLinkTarget(index, (event.currentTarget as HTMLInputElement).value)}
            onblur={() => normalizeLinkTarget(index)}
          />
        {/if}
        <fieldset class="menu-buttons-visibility">
          <legend>{at("menu_buttons_visibility", {}, "Show in")}</legend>
          <label class="menu-buttons-visibility-option">
            <Checkbox
              checked={button.show_in_bot}
              ariaLabel={at("menu_buttons_visible_in_bot", {}, "Bot menu")}
              onCheckedChange={(checked) => updateButton(index, { show_in_bot: checked })}
            />
            <span>{at("menu_buttons_visible_in_bot", {}, "Bot menu")}</span>
          </label>
          <label class="menu-buttons-visibility-option">
            <Checkbox
              checked={button.show_in_telegram_webapp}
              ariaLabel={at("menu_buttons_visible_in_telegram_webapp", {}, "Telegram Mini App")}
              onCheckedChange={(checked) =>
                updateButton(index, { show_in_telegram_webapp: checked })}
            />
            <span>{at("menu_buttons_visible_in_telegram_webapp", {}, "Telegram Mini App")}</span>
          </label>
          <label class="menu-buttons-visibility-option">
            <Checkbox
              checked={button.show_in_browser}
              ariaLabel={at("menu_buttons_visible_in_browser", {}, "Web browser")}
              onCheckedChange={(checked) => updateButton(index, { show_in_browser: checked })}
            />
            <span>{at("menu_buttons_visible_in_browser", {}, "Web browser")}</span>
          </label>
        </fieldset>
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

<IconPickerDialog
  {at}
  open={Boolean(iconPickerButton)}
  description={iconPickerButton
    ? iconPickerButton.labels[activeLanguage] || iconPickerButton.id
    : ""}
  bind:search={iconPickerSearch}
  options={filteredIconOptions}
  currentIconName={iconPickerButton?.webapp_icon || ""}
  currentIconLabel={iconPickerButton?.webapp_icon || at("menu_buttons_icon_none", {}, "No icon")}
  isDefault={iconPickerButton?.webapp_icon === DEFAULT_MENU_WEBAPP_ICON}
  {iconComponent}
  onClose={closeIconPicker}
  onUseDefault={useDefaultIcon}
  onSelect={selectIcon}
/>

<style>
  .menu-buttons-editor {
    display: grid;
    width: 100%;
    gap: 12px;
  }

  :global(.menu-buttons-row) {
    grid-template-columns:
      24px minmax(230px, 1.15fr) minmax(180px, 1.25fr) minmax(160px, 0.9fr) minmax(220px, 1.5fr)
      minmax(150px, 0.8fr) auto;
  }

  .menu-buttons-presentation {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 92px;
    align-items: end;
    gap: 8px;
    min-width: 0;
  }

  .menu-buttons-field {
    display: grid;
    min-width: 0;
    gap: 5px;
  }

  .menu-buttons-field-label {
    overflow: hidden;
    font-size: 11px;
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  :global(.menu-buttons-row .menu-button-icon-trigger.admin-btn) {
    width: 100%;
    min-width: 0;
    overflow: hidden;
    padding-inline: 12px;
    justify-self: stretch;
    justify-content: flex-start;
  }

  :global(.menu-button-icon-trigger span) {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .menu-buttons-visibility {
    display: grid;
    min-width: 0;
    margin: 0;
    padding: 0;
    gap: 6px;
    border: 0;
  }

  .menu-buttons-visibility legend {
    margin-bottom: 2px;
    font-size: 11px;
    font-weight: 600;
  }

  .menu-buttons-visibility-option {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 12px;
    cursor: pointer;
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
        24px minmax(210px, 1.1fr) minmax(180px, 1.2fr) minmax(160px, 0.9fr) minmax(180px, 1.2fr)
        minmax(140px, 0.8fr) auto;
    }
  }

  @media (max-width: 720px) {
    :global(.menu-buttons-row) {
      grid-template-columns: 1fr;
    }

    .menu-buttons-presentation {
      grid-template-columns: 1fr;
      align-items: stretch;
      gap: 10px;
    }

    .menu-buttons-field-label {
      overflow: visible;
      text-overflow: clip;
      white-space: normal;
    }
  }
</style>
