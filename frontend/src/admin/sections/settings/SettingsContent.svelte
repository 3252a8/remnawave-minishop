<script lang="ts">
  import { ColorInput, FileInput, Input, Textarea } from "$components/ui/index.js";
  import {
    Check,
    Copy,
    ExternalLink,
    Eye,
    EyeOff,
    FileText,
    Search,
    X,
  } from "$components/ui/icons.js";
  import { Switch } from "$components/ui/primitives.js";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import SettingsDisclosureTrigger from "./SettingsDisclosureTrigger.svelte";
  import {
    groupSectionFields,
    semanticFieldGroups,
    settingsFieldAnchorKey,
    settingsFieldGroupAnchorKey,
    settingsSectionAnchorKey,
    settingsSubsectionAnchorKey,
  } from "$lib/admin/settingsSections";
  import {
    settingsDirtyCountLabel,
    settingsFieldsCountLabel,
    settingsOverriddenCountLabel,
    settingsParamsCountLabel,
  } from "./disclosureLabels";
  import type { ComponentType, SvelteComponent } from "svelte";
  import type { SettingsSearchEntry } from "$lib/admin/settingsSearch";
  import type { SettingsDirtyEntry } from "$lib/admin/stores/settingsStore";
  import type {
    AdminSettingField,
    AdminSettingsSection,
    GroupProviderInfo,
    GroupWebhook,
    SemanticFieldGroup,
    SettingsSubsection,
  } from "$lib/admin/settingsSections";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type SettingsDirtyState = Record<string, SettingsDirtyEntry>;
  type DynamicComponent = ComponentType<SvelteComponent<Record<string, unknown>>>;

  let {
    at,
    settingsLoading,
    visibleSettingsSections,
    settingsDirty,
    settingsSaving,
    settingsAllOpen,
    settingsOpenSections,
    settingsOpenSubsections,
    settingsSearchQuery = $bindable(""),
    settingsSearchResults,
    highlightedSettingKey,
    copiedWebhookKey,
    toggleAllSections,
    clearSettingsSearch,
    selectSettingsSearchResult,
    saveSettings,
    toggleSettingsSection,
    toggleSettingsSubsection,
    settingsDisclosureId,
    copyWebhookUrl,
    adminLocaleKey,
    sectionTitle,
    subsectionTitle,
    fieldGroupTitle,
    fieldGroupDescription,
    fieldLabelText,
    fieldDescriptionText,
    fieldPlaceholderText,
    valueFor,
    fieldTextValue,
    fieldInputValue,
    isOverridden,
    isSecretRevealed,
    toggleSecretReveal,
    secretPlaceholder,
    iconComponent,
    iconValue,
    iconLabel,
    iconIsDefault,
    openIconPicker,
    choiceItems,
    setBoolField,
    fieldInputHandler,
    fieldSelectHandler,
    jsonFileHandler,
    markFieldDirty,
    resetField,
  }: {
    at: TranslateFn;
    settingsLoading: boolean;
    visibleSettingsSections: AdminSettingsSection[];
    settingsDirty: SettingsDirtyState;
    settingsSaving: boolean;
    settingsAllOpen: boolean;
    settingsOpenSections: string[];
    settingsOpenSubsections: Record<string, string[]>;
    settingsSearchQuery: string;
    settingsSearchResults: SettingsSearchEntry[];
    highlightedSettingKey: string;
    copiedWebhookKey: string;
    toggleAllSections: () => void;
    clearSettingsSearch: () => void;
    selectSettingsSearchResult: (result: SettingsSearchEntry) => void | Promise<void>;
    saveSettings: () => void | Promise<void>;
    toggleSettingsSection: (sectionId: string) => void;
    toggleSettingsSubsection: (sectionId: string, groupId: string) => void;
    settingsDisclosureId: (...parts: string[]) => string;
    copyWebhookUrl: (webhook: GroupWebhook) => Promise<void>;
    adminLocaleKey: (key: unknown) => string;
    sectionTitle: (id: string) => string;
    subsectionTitle: (group: SettingsSubsection) => string;
    fieldGroupTitle: (group: SemanticFieldGroup) => string;
    fieldGroupDescription: (group: SemanticFieldGroup) => string;
    fieldLabelText: (field: AdminSettingField) => string;
    fieldDescriptionText: (field: AdminSettingField) => string;
    fieldPlaceholderText: (field: AdminSettingField) => string;
    valueFor: (field: AdminSettingField) => unknown;
    fieldTextValue: (field: AdminSettingField) => string;
    fieldInputValue: (field: AdminSettingField) => string | number;
    isOverridden: (field: AdminSettingField) => boolean;
    isSecretRevealed: (key: string) => boolean;
    toggleSecretReveal: (key: string) => void;
    secretPlaceholder: (field: AdminSettingField) => string;
    iconComponent: (name: unknown) => DynamicComponent | null;
    iconValue: (field: AdminSettingField | null) => string;
    iconLabel: (field: AdminSettingField | null) => string;
    iconIsDefault: (field: AdminSettingField) => boolean;
    openIconPicker: (field: AdminSettingField) => void;
    choiceItems: (field: AdminSettingField) => Array<{ value: string; label: string }>;
    setBoolField: (field: AdminSettingField, checked: boolean) => void;
    fieldInputHandler: (field: AdminSettingField) => (event: Event) => void;
    fieldSelectHandler: (field: AdminSettingField) => (value: string) => void;
    jsonFileHandler: (field: AdminSettingField) => (event: Event) => void;
    markFieldDirty: (key: string, value: unknown) => void;
    resetField: (field: AdminSettingField) => void;
  } = $props();

  let settingsSearchOpen = $state(false);

  const settingsSearchHasQuery = $derived(settingsSearchQuery.trim().length > 0);
  const settingsSearchVisible = $derived(settingsSearchOpen && settingsSearchHasQuery);

  function openSettingsSearch(): void {
    if (settingsSearchHasQuery) settingsSearchOpen = true;
  }

  function handleSettingsSearchInput(event: Event): void {
    const input = event.currentTarget as HTMLInputElement | null;
    settingsSearchOpen = Boolean(input?.value.trim() || settingsSearchQuery.trim());
  }

  function handleSettingsSearchKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape") {
      settingsSearchOpen = false;
      return;
    }
    if (event.key !== "Enter" || !settingsSearchResults[0]) return;
    event.preventDefault();
    chooseSettingsSearchResult(settingsSearchResults[0]);
  }

  function handleSettingsSearchFocusOut(event: FocusEvent): void {
    const current = event.currentTarget as HTMLElement | null;
    const next = event.relatedTarget as Node | null;
    if (current && next && current.contains(next)) return;
    settingsSearchOpen = false;
  }

  function chooseSettingsSearchResult(result: SettingsSearchEntry): void {
    settingsSearchOpen = false;
    void selectSettingsSearchResult(result);
  }

  function resetSettingsSearch(): void {
    clearSettingsSearch();
    settingsSearchOpen = false;
  }
</script>

{#snippet renderProviderInfo(provider: NonNullable<GroupProviderInfo>)}
  {#if provider.infoUrl}
    <div class="admin-provider-info">
      <div class="admin-provider-info-meta">
        <strong>{at("settings_provider_info_title", {}, "Provider information")}</strong>
        <small>
          {at(
            "settings_provider_info_hint",
            { provider: provider.label },
            `Official ${provider.label} website and documentation.`
          )}
        </small>
      </div>
      <a
        class="admin-btn admin-btn-sm admin-btn-ghost admin-provider-info-link"
        href={provider.infoUrl}
        target="_blank"
        rel="noreferrer noopener"
      >
        <ExternalLink size={13} />
        <span>{at("settings_provider_info_open", {}, "Open provider site")}</span>
      </a>
    </div>
  {/if}
{/snippet}

{#snippet renderWebhookHint(webhook: NonNullable<GroupWebhook>)}
  {@const displayValue = webhook.url || webhook.path}
  <div class="admin-webhook-hint">
    <div class="admin-webhook-hint-meta">
      <strong>{at("settings_provider_webhook_url", {}, "Webhook URL")}</strong>
      <small>
        {webhook.url
          ? at(
              adminLocaleKey(webhook.hintI18nKey || "settings_provider_webhook_url_hint"),
              {},
              webhook.hintFallback || "Use this URL in the provider webhook settings."
            )
          : at(
              "settings_provider_webhook_base_missing",
              { path: webhook.path },
              `Set WEBHOOK_BASE_URL to show the full URL for ${webhook.path}.`
            )}
      </small>
    </div>
    <div class="admin-webhook-value">
      <code title={displayValue}>{displayValue}</code>
      <AdminButton
        class="admin-webhook-copy"
        size="sm"
        variant="ghost"
        disabled={!webhook.url}
        title={at("copy", {}, "Copy")}
        onclick={() => copyWebhookUrl(webhook)}
      >
        {#if copiedWebhookKey === webhook.key}
          <Check size={13} />
          <span>{at("copied", {}, "Copied")}</span>
        {:else}
          <Copy size={13} />
          <span>{at("copy", {}, "Copy")}</span>
        {/if}
      </AdminButton>
    </div>
  </div>
{/snippet}

{#snippet renderGroupedFields(section: AdminSettingsSection, group: SettingsSubsection)}
  {@const fieldGroups = semanticFieldGroups(section, group)}
  {#if fieldGroups.length === 1 && !fieldGroups[0].titleKey}
    {#each fieldGroups[0].fields as field}
      {@render renderField(field)}
    {/each}
  {:else}
    <div class="admin-settings-field-groups">
      {#each fieldGroups as fieldGroup}
        <section
          class="admin-settings-field-group"
          data-settings-anchor={fieldGroup.titleKey
            ? settingsFieldGroupAnchorKey(section.id, group.id, fieldGroup.id)
            : undefined}
        >
          {#if fieldGroup.titleKey}
            <header class="admin-settings-field-group-head">
              <strong>{fieldGroupTitle(fieldGroup)}</strong>
              {#if fieldGroupDescription(fieldGroup)}
                <small>{fieldGroupDescription(fieldGroup)}</small>
              {/if}
            </header>
          {/if}
          <div class="admin-settings-field-group-body">
            {#each fieldGroup.fields as field}
              {@render renderField(field)}
            {/each}
          </div>
        </section>
      {/each}
    </div>
  {/if}
{/snippet}

{#snippet renderField(field: AdminSettingField)}
  {@const revealed = isSecretRevealed(field.key)}
  <div
    class="admin-setting"
    class:is-overridden={isOverridden(field)}
    class:is-search-highlighted={highlightedSettingKey === field.key}
    data-settings-anchor={settingsFieldAnchorKey(field.key)}
    tabindex="-1"
  >
    <div class="admin-setting-meta">
      <strong>
        {fieldLabelText(field)}
        {#if field.secret}
          <AdminBadge variant="warning">{at("settings_badge_secret", {}, "Secret")}</AdminBadge>
        {/if}
        {#if isOverridden(field)}
          <AdminBadge variant="success">{at("settings_badge_override", {}, "Override")}</AdminBadge>
        {/if}
      </strong>
      <code>{field.key}</code>
      {#if fieldDescriptionText(field)}
        <small>{fieldDescriptionText(field)}</small>
      {/if}
    </div>
    <div class="admin-setting-control">
      {#if field.type === "bool"}
        <div class="admin-setting-switch">
          <Switch.Root
            aria-label={fieldLabelText(field)}
            checked={Boolean(valueFor(field))}
            onCheckedChange={(checked) => setBoolField(field, checked)}
            class="admin-switch-root"
          >
            <Switch.Thumb class="admin-switch-thumb" />
          </Switch.Root>
          <span
            >{valueFor(field)
              ? at("enabled", {}, "Включено")
              : at("disabled", {}, "Выключено")}</span
          >
        </div>
      {:else if field.type === "color"}
        <ColorInput
          class="admin-color"
          value={fieldTextValue(field) || "#00fe7a"}
          ariaLabel={fieldLabelText(field)}
          oninput={fieldInputHandler(field)}
        />
        <Input
          class="input"
          type="text"
          value={fieldInputValue(field)}
          oninput={fieldInputHandler(field)}
        />
      {:else if field.type === "icon"}
        {@const selectedIconName = iconValue(field)}
        {@const SelectedIcon = iconComponent(selectedIconName)}
        <AdminButton
          class="admin-icon-picker-trigger"
          variant="ghost"
          onclick={() => openIconPicker(field)}
        >
          {#if SelectedIcon}
            <SelectedIcon size={16} />
          {/if}
          <span>{iconLabel(field)}</span>
        </AdminButton>
        {#if !iconIsDefault(field)}
          <AdminButton size="sm" variant="ghost" onclick={() => markFieldDirty(field.key, "")}>
            <X size={12} />
            {at("clear", {}, "Clear")}
          </AdminButton>
        {/if}
      {:else if field.choices && field.choices.length > 0}
        <AdminSelect
          class="admin-setting-select"
          value={fieldTextValue(field)}
          items={choiceItems(field)}
          ariaLabel={fieldLabelText(field)}
          placeholder={fieldPlaceholderText(field) || fieldLabelText(field)}
          onValueChange={fieldSelectHandler(field)}
        />
      {:else if field.type === "int" || field.type === "float"}
        <Input
          class="input"
          type="number"
          step={field.type === "float" ? "0.1" : "1"}
          min={field.min ?? undefined}
          max={field.max ?? undefined}
          placeholder={fieldPlaceholderText(field)}
          value={fieldInputValue(field)}
          oninput={fieldInputHandler(field)}
        />
      {:else if field.type === "text"}
        <Textarea
          class="admin-setting-textarea"
          rows={4}
          placeholder={fieldPlaceholderText(field)}
          value={fieldTextValue(field)}
          oninput={fieldInputHandler(field)}
        />
      {:else if field.type === "json"}
        <div class="admin-json-toolbar">
          <FileInput
            id={"json-file-" + field.key}
            class="admin-json-file-input"
            accept="application/json,.json"
            onchange={jsonFileHandler(field)}
          />
          <label
            class="admin-btn admin-btn-sm admin-btn-ghost admin-json-upload"
            for={"json-file-" + field.key}
          >
            <FileText size={13} />
            {at("settings_json_upload", {}, "Load .json")}
          </label>
          {#if valueFor(field)}
            <AdminButton size="sm" variant="ghost" onclick={() => markFieldDirty(field.key, "")}>
              <X size={12} />
              {at("clear", {}, "Clear")}
            </AdminButton>
          {/if}
        </div>
        <Textarea
          class="admin-setting-textarea admin-setting-json-textarea"
          rows={10}
          spellcheck="false"
          placeholder={fieldPlaceholderText(field)}
          value={fieldTextValue(field)}
          oninput={fieldInputHandler(field)}
        />
      {:else if field.secret}
        <Input
          class="input"
          type={revealed ? "text" : "password"}
          placeholder={secretPlaceholder(field)}
          autocomplete="off"
          value={fieldInputValue(field)}
          oninput={fieldInputHandler(field)}
        />
        <AdminButton
          size="sm"
          variant="ghost"
          aria-label={revealed ? at("hide", {}, "Скрыть") : at("show", {}, "Показать")}
          onclick={() => toggleSecretReveal(field.key)}
        >
          {#if revealed}<EyeOff size={13} />{:else}<Eye size={13} />{/if}
        </AdminButton>
      {:else}
        <Input
          class="input"
          type="text"
          placeholder={fieldPlaceholderText(field)}
          value={fieldInputValue(field)}
          oninput={fieldInputHandler(field)}
        />
      {/if}
      {#if isOverridden(field) || settingsDirty[field.key]}
        <AdminButton size="sm" variant="ghost" onclick={() => resetField(field)}>
          <X size={12} />
          {at("reset", {}, "Сбросить")}
        </AdminButton>
      {/if}
    </div>
  </div>
{/snippet}

{#if settingsLoading || !visibleSettingsSections.length}
  <AdminEmptyState
    >{settingsLoading
      ? at("loading", {}, "Загрузка…")
      : at("no_data", {}, "Нет данных")}</AdminEmptyState
  >
{:else}
  <div class="admin-settings-search" onfocusout={handleSettingsSearchFocusOut}>
    <div class="admin-settings-search-box">
      <Search class="admin-settings-search-icon" size={16} aria-hidden="true" />
      <Input
        class="admin-settings-search-input"
        type="search"
        bind:value={settingsSearchQuery}
        autocomplete="off"
        placeholder={at(
          "settings_search_placeholder",
          {},
          "Search settings by name or description"
        )}
        aria-label={at("settings_search_aria", {}, "Search settings")}
        aria-controls="admin-settings-search-results"
        aria-expanded={settingsSearchVisible}
        onfocus={openSettingsSearch}
        oninput={handleSettingsSearchInput}
        onkeydown={handleSettingsSearchKeydown}
      />
      {#if settingsSearchHasQuery}
        <AdminButton
          class="admin-settings-search-clear"
          size="sm"
          variant="ghost"
          title={at("clear", {}, "Clear")}
          aria-label={at("clear", {}, "Clear")}
          onclick={resetSettingsSearch}
        >
          <X size={13} />
        </AdminButton>
      {/if}
    </div>
    {#if settingsSearchVisible}
      <div
        id="admin-settings-search-results"
        class="admin-settings-search-results"
        role="listbox"
        aria-label={at("settings_search_results", {}, "Settings search results")}
      >
        {#if settingsSearchResults.length}
          {#each settingsSearchResults as result (result.key)}
            <button
              type="button"
              class="admin-settings-search-result"
              class:is-active={highlightedSettingKey === result.key}
              role="option"
              aria-selected={highlightedSettingKey === result.key}
              onclick={() => chooseSettingsSearchResult(result)}
            >
              <span class="admin-settings-search-result-head">
                <strong>{result.label}</strong>
                <small>{result.pathLabel}</small>
              </span>
              {#if result.description}
                <span class="admin-settings-search-result-description">{result.description}</span>
              {/if}
              <code>{result.key}</code>
            </button>
          {/each}
        {:else}
          <div class="admin-settings-search-empty">
            {at("settings_search_no_results", {}, "No settings found")}
          </div>
        {/if}
      </div>
    {/if}
  </div>
  <div
    style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;"
  >
    <p class="admin-muted" style="margin:0;">
      {at(
        "settings_hint",
        {},
        "Изменения в админке имеют приоритет над .env. Кнопка «Сбросить» возвращает значение из переменных окружения."
      )}
    </p>
    <div style="display:flex; gap:8px;">
      <AdminButton size="sm" variant="ghost" onclick={toggleAllSections}>
        {settingsAllOpen
          ? at("collapse_all", {}, "Свернуть всё")
          : at("expand_all", {}, "Развернуть всё")}
      </AdminButton>
      {#if Object.keys(settingsDirty).length > 0}
        <AdminButton size="sm" variant="primary" onclick={saveSettings} disabled={settingsSaving}>
          {settingsSaving ? at("saving", {}, "Сохранение...") : at("save", {}, "Сохранить")}
        </AdminButton>
      {/if}
    </div>
  </div>
  <div class="admin-accordion">
    {#each visibleSettingsSections as section}
      {@const dirtyInSection = section.fields.filter((f) => Boolean(settingsDirty[f.key])).length}
      {@const overriddenInSection = section.fields.filter((f) => isOverridden(f)).length}
      {@const sectionIsOpen = settingsOpenSections.includes(section.id)}
      {@const sectionContentId = settingsDisclosureId("section", section.id)}
      <section class="admin-accordion-item admin-card">
        <SettingsDisclosureTrigger
          anchorKey={settingsSectionAnchorKey(section.id)}
          contentId={sectionContentId}
          countLabel={settingsParamsCountLabel(at, section.fields.length)}
          dirtyLabel={settingsDirtyCountLabel(at, dirtyInSection)}
          onToggle={() => toggleSettingsSection(section.id)}
          open={sectionIsOpen}
          overriddenLabel={settingsOverriddenCountLabel(at, overriddenInSection)}
          title={sectionTitle(section.id)}
        />
        {#if sectionIsOpen}
          {@const groups = groupSectionFields(section)}
          {@const rootGroup = groups.find((g) => !g.label)}
          {@const labelGroups = groups.filter((g) => g.label)}
          <div id={sectionContentId} class="admin-accordion-content" data-state="open">
            <div class="admin-settings-fields">
              {#if rootGroup}
                {#if rootGroup.providerInfo}
                  {@render renderProviderInfo(rootGroup.providerInfo)}
                {/if}
                {#if rootGroup.webhook}
                  {@render renderWebhookHint(rootGroup.webhook)}
                {/if}
                {@render renderGroupedFields(section, rootGroup)}
              {/if}
              {#if labelGroups.length}
                <div class="admin-subsection-accordion">
                  {#each labelGroups as group}
                    {@const subDirty = group.fields.filter((f) =>
                      Boolean(settingsDirty[f.key])
                    ).length}
                    {@const subOverridden = group.fields.filter((f) => isOverridden(f)).length}
                    {@const subsectionIsOpen = (settingsOpenSubsections[section.id] || []).includes(
                      group.id
                    )}
                    {@const subsectionContentId = settingsDisclosureId(
                      "subsection",
                      section.id,
                      group.id
                    )}
                    <section class="admin-settings-subsection">
                      <SettingsDisclosureTrigger
                        anchorKey={settingsSubsectionAnchorKey(section.id, group.id)}
                        contentId={subsectionContentId}
                        countLabel={settingsFieldsCountLabel(at, group.fields.length)}
                        dirtyLabel={settingsDirtyCountLabel(at, subDirty)}
                        level="subsection"
                        onToggle={() => toggleSettingsSubsection(section.id, group.id)}
                        open={subsectionIsOpen}
                        overriddenLabel={settingsOverriddenCountLabel(at, subOverridden)}
                        logoFallback={group.providerInfo?.logoFallback || ""}
                        logoLabel={group.providerInfo?.label || subsectionTitle(group)}
                        logoUrl={group.providerInfo?.logoUrl || ""}
                        title={subsectionTitle(group)}
                      />
                      {#if subsectionIsOpen}
                        <div
                          id={subsectionContentId}
                          class="admin-accordion-content"
                          data-state="open"
                        >
                          <div class="admin-settings-subsection-body">
                            {#if group.providerInfo}
                              {@render renderProviderInfo(group.providerInfo)}
                            {/if}
                            {#if group.webhook}
                              {@render renderWebhookHint(group.webhook)}
                            {/if}
                            {@render renderGroupedFields(section, group)}
                          </div>
                        </div>
                      {/if}
                    </section>
                  {/each}
                </div>
              {/if}
            </div>
          </div>
        {/if}
      </section>
    {/each}
  </div>
{/if}
