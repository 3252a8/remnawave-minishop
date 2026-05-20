<script>
  import { ChevronRight, Eye, EyeOff, Search, X } from "$components/ui/icons.js";
  import * as UiIcons from "$components/ui/icons.js";
  import { Accordion, Switch } from "$components/ui/primitives.js";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { getContext, onMount } from "svelte";

  export let at;
  export let onSettingsSaved;
  export let isCompact = false;
  export let currentLang = "ru";

  const settingsStore = getContext("settingsStore");

  $: ({ settingsSections, settingsLoading, settingsDirty, settingsSaving } = $settingsStore);
  $: visibleSettingsSections = settingsSections.filter((section) => section.id !== "appearance");

  let settingsOpenSections = [];
  let settingsOpenSubsections = {};
  let revealedSecrets = new Set();
  let iconPickerField = null;
  let iconPickerSearch = "";

  $: settingsAllOpen =
    visibleSettingsSections.length > 0 &&
    settingsOpenSections.length === visibleSettingsSections.length;
  $: iconOptions = Object.keys(UiIcons)
    .filter((name) => /^[A-Z]/.test(name))
    .sort((a, b) => a.localeCompare(b));
  $: filteredIconOptions = iconOptions.filter((name) =>
    name.toLowerCase().includes(iconPickerSearch.trim().toLowerCase())
  );

  onMount(() => {
    settingsStore.loadSettings().then(() => {
      if ($settingsStore.settingsSections.length) {
        const ids = $settingsStore.settingsSections
          .filter((s) => s.id !== "appearance")
          .map((s) => s.id);
        settingsOpenSections = isCompact ? ids.slice(0, 1) : ids.slice();
      }
    });
  });

  function toggleAllSections() {
    if (settingsOpenSections.length === visibleSettingsSections.length) {
      settingsOpenSections = [];
    } else {
      settingsOpenSections = visibleSettingsSections.map((s) => s.id);
    }
  }

  function valueFor(field) {
    if (settingsDirty[field.key]?.deleted) return "";
    if (Object.prototype.hasOwnProperty.call(settingsDirty, field.key)) {
      return settingsDirty[field.key].value;
    }
    return field.value ?? "";
  }

  function isOverridden(field) {
    return Boolean(field.overridden) && !settingsDirty[field.key]?.deleted;
  }

  function isSecretRevealed(key) {
    return revealedSecrets.has(key);
  }

  function toggleSecretReveal(key) {
    const next = new Set(revealedSecrets);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    revealedSecrets = next;
  }

  function secretPlaceholder(field) {
    if (settingsDirty[field.key]?.deleted) return field.placeholder || "••••••••";
    if (field.has_value) return at("settings_secret_configured", {}, "Secret is set");
    return field.placeholder || at("settings_secret_empty", {}, "Not set");
  }

  function iconComponent(name) {
    const key = String(name || "").trim();
    return key ? UiIcons[key] || null : null;
  }

  function iconValue(field) {
    return String(valueFor(field) || field?.placeholder || "").trim();
  }

  function iconIsDefault(field) {
    return !String(valueFor(field) || "").trim();
  }

  function iconLabel(field) {
    const iconName = iconValue(field);
    if (!iconName) return at("settings_icon_empty", {}, "Default icon");
    if (iconIsDefault(field)) {
      return at("settings_icon_default_value", { icon: iconName }, `Default: ${iconName}`);
    }
    return iconName;
  }

  function openIconPicker(field) {
    iconPickerField = field;
    iconPickerSearch = "";
  }

  function closeIconPicker() {
    iconPickerField = null;
    iconPickerSearch = "";
  }

  function selectIcon(name) {
    if (!iconPickerField) return;
    settingsStore.markDirty(iconPickerField.key, name);
    closeIconPicker();
  }

  function groupSectionFields(section) {
    const groups = new Map();
    for (const field of section.fields || []) {
      const key = field.subsection || "_root";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(field);
    }
    return Array.from(groups.entries()).map(([id, fields]) => ({
      id,
      label: id === "_root" ? null : id,
      fields,
    }));
  }

  function sectionTitle(id) {
    const map = {
      general: at("admin_settings_section_general", {}, "Общие"),
      appearance: at("admin_settings_section_appearance", {}, "Внешний вид"),
      pricing: at("admin_settings_section_pricing", {}, "Тарифы и цены"),
      payments: at("admin_settings_section_payments", {}, "Платёжные системы"),
      trial: at("admin_settings_section_trial", {}, "Триал"),
      referral: at("admin_settings_section_referral", {}, "Реферальная программа"),
      notifications: at("admin_settings_section_notifications", {}, "Уведомления"),
      support: at("admin_settings_section_support", {}, "Поддержка"),
      devices: at("admin_settings_section_devices", {}, "Устройства"),
    };
    return map[id] || id;
  }

  function englishFieldLabelFallback(key, originalLabel) {
    if (!key) return originalLabel || "";
    return String(key)
      .toLowerCase()
      .split("_")
      .filter(Boolean)
      .map((part) => {
        if (part === "id") return "ID";
        if (part === "url") return "URL";
        if (part === "api") return "API";
        if (part === "tg") return "TG";
        return part.charAt(0).toUpperCase() + part.slice(1);
      })
      .join(" ");
  }

  function fieldLabelText(field) {
    const isEnglish = String(currentLang || "")
      .toLowerCase()
      .startsWith("en");
    const fallback = isEnglish ? englishFieldLabelFallback(field.key, field.label) : field.label;
    return field.i18n_label_key ? at(field.i18n_label_key, {}, fallback) : fallback;
  }
</script>

{#snippet renderField(field)}
  {@const revealed = isSecretRevealed(field.key)}
  <div class="admin-setting" class:is-overridden={isOverridden(field)}>
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
      {#if field.description}
        <small
          >{field.i18n_description_key
            ? at(field.i18n_description_key, {}, field.description)
            : field.description}</small
        >
      {/if}
    </div>
    <div class="admin-setting-control">
      {#if field.type === "bool"}
        <div class="admin-setting-switch">
          <Switch.Root
            checked={Boolean(valueFor(field))}
            onCheckedChange={(checked) => settingsStore.markDirty(field.key, checked)}
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
        <input
          class="admin-color"
          type="color"
          value={valueFor(field) || "#00fe7a"}
          oninput={(e) => settingsStore.markDirty(field.key, e.currentTarget.value)}
        />
        <input
          class="input"
          type="text"
          value={valueFor(field) || ""}
          oninput={(e) => settingsStore.markDirty(field.key, e.currentTarget.value)}
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
            <svelte:component this={SelectedIcon} size={16} />
          {/if}
          <span>{iconLabel(field)}</span>
        </AdminButton>
        {#if !iconIsDefault(field)}
          <AdminButton
            size="sm"
            variant="ghost"
            onclick={() => settingsStore.markDirty(field.key, "")}
          >
            <X size={12} />
            {at("clear", {}, "Clear")}
          </AdminButton>
        {/if}
      {:else if field.choices && field.choices.length > 0}
        <AdminSelect
          class="admin-setting-select"
          value={valueFor(field) || ""}
          items={field.choices}
          ariaLabel={fieldLabelText(field)}
          placeholder={field.placeholder || fieldLabelText(field)}
          onValueChange={(value) => settingsStore.markDirty(field.key, value)}
        />
      {:else if field.type === "int" || field.type === "float"}
        <input
          class="input"
          type="number"
          step={field.type === "float" ? "0.1" : "1"}
          placeholder={field.placeholder}
          value={valueFor(field) ?? ""}
          oninput={(e) => settingsStore.markDirty(field.key, e.currentTarget.value)}
        />
      {:else if field.secret}
        <input
          class="input"
          type={revealed ? "text" : "password"}
          placeholder={secretPlaceholder(field)}
          autocomplete="off"
          value={valueFor(field) ?? ""}
          oninput={(e) => settingsStore.markDirty(field.key, e.currentTarget.value)}
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
        <input
          class="input"
          type="text"
          placeholder={field.placeholder}
          value={valueFor(field) ?? ""}
          oninput={(e) => settingsStore.markDirty(field.key, e.currentTarget.value)}
        />
      {/if}
      {#if isOverridden(field) || settingsDirty[field.key]}
        <AdminButton size="sm" variant="ghost" onclick={() => settingsStore.resetField(field)}>
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
        <AdminButton
          size="sm"
          variant="primary"
          onclick={() => settingsStore.saveSettings(onSettingsSaved)}
          disabled={settingsSaving}
        >
          {settingsSaving ? at("saving", {}, "Сохранение...") : at("save", {}, "Сохранить")}
        </AdminButton>
      {/if}
    </div>
  </div>
  <Accordion.Root type="multiple" bind:value={settingsOpenSections} class="admin-accordion">
    {#each visibleSettingsSections as section}
      {@const dirtyInSection = section.fields.filter((f) => Boolean(settingsDirty[f.key])).length}
      {@const overriddenInSection = section.fields.filter((f) => isOverridden(f)).length}
      <Accordion.Item value={section.id} class="admin-accordion-item admin-card">
        <Accordion.Header class="admin-accordion-header">
          <Accordion.Trigger class="admin-accordion-trigger">
            <span class="admin-accordion-title">{sectionTitle(section.id)}</span>
            <span class="admin-accordion-meta">
              {at(
                "settings_params_count",
                { count: section.fields.length },
                `${section.fields.length} параметров`
              )}{#if overriddenInSection}
                · {at(
                  "settings_overridden_count",
                  { count: overriddenInSection },
                  `${overriddenInSection} override`
                )}{/if}{#if dirtyInSection}
                · {at(
                  "settings_dirty_count",
                  { count: dirtyInSection },
                  `${dirtyInSection} изм.`
                )}{/if}
            </span>
            <ChevronRight size={16} class="admin-accordion-chev" />
          </Accordion.Trigger>
        </Accordion.Header>
        <Accordion.Content class="admin-accordion-content">
          {@const groups = groupSectionFields(section)}
          {@const rootGroup = groups.find((g) => !g.label)}
          {@const labelGroups = groups.filter((g) => g.label)}
          <div class="admin-settings-fields">
            {#if rootGroup}
              {#each rootGroup.fields as field}
                {@render renderField(field)}
              {/each}
            {/if}
            {#if labelGroups.length}
              <Accordion.Root
                type="multiple"
                value={settingsOpenSubsections[section.id] || []}
                onValueChange={(v) =>
                  (settingsOpenSubsections = { ...settingsOpenSubsections, [section.id]: v })}
                class="admin-subsection-accordion"
              >
                {#each labelGroups as group}
                  {@const subDirty = group.fields.filter((f) =>
                    Boolean(settingsDirty[f.key])
                  ).length}
                  {@const subOverridden = group.fields.filter((f) => isOverridden(f)).length}
                  <Accordion.Item value={group.id} class="admin-settings-subsection">
                    <Accordion.Header class="admin-accordion-header">
                      <Accordion.Trigger class="admin-settings-subsection-trigger">
                        <strong>{group.label}</strong>
                        <span class="admin-settings-subsection-meta">
                          {at(
                            "settings_fields_count",
                            { count: group.fields.length },
                            `${group.fields.length} полей`
                          )}{#if subOverridden}
                            · {at(
                              "settings_overridden_count",
                              { count: subOverridden },
                              `${subOverridden} override`
                            )}{/if}{#if subDirty}
                            · {at(
                              "settings_dirty_count",
                              { count: subDirty },
                              `${subDirty} изм.`
                            )}{/if}
                        </span>
                        <ChevronRight size={14} class="admin-accordion-chev" />
                      </Accordion.Trigger>
                    </Accordion.Header>
                    <Accordion.Content class="admin-accordion-content">
                      <div class="admin-settings-subsection-body">
                        {#each group.fields as field}
                          {@render renderField(field)}
                        {/each}
                      </div>
                    </Accordion.Content>
                  </Accordion.Item>
                {/each}
              </Accordion.Root>
            {/if}
          </div>
        </Accordion.Content>
      </Accordion.Item>
    {/each}
  </Accordion.Root>
{/if}

<Dialog
  open={Boolean(iconPickerField)}
  title={at("settings_icon_picker_title", {}, "Choose icon")}
  description={iconPickerField ? fieldLabelText(iconPickerField) : ""}
  closeLabel={at("close", {}, "Close")}
  onclose={closeIconPicker}
  class="admin-icon-picker-dialog"
>
  <div class="admin-icon-picker-body">
    {#if iconPickerField}
      {@const currentIconName = iconValue(iconPickerField)}
      {@const CurrentIcon = iconComponent(currentIconName)}
      <div class="admin-icon-picker-current">
        <span class="admin-icon-picker-current-preview" aria-hidden="true">
          {#if CurrentIcon}
            <svelte:component this={CurrentIcon} size={24} />
          {/if}
        </span>
        <span class="admin-icon-picker-current-meta">
          <small>{at("settings_icon_current", {}, "Current icon")}</small>
          <strong>{iconLabel(iconPickerField)}</strong>
        </span>
        {#if !iconIsDefault(iconPickerField)}
          <AdminButton
            size="sm"
            variant="ghost"
            onclick={() => settingsStore.markDirty(iconPickerField.key, "")}
          >
            <X size={12} />
            {at("settings_icon_use_default", {}, "Use default")}
          </AdminButton>
        {/if}
      </div>
    {/if}
    <div class="admin-icon-picker-toolbar">
      <label class="admin-icon-picker-search">
        <Search size={15} />
        <input
          bind:value={iconPickerSearch}
          class="input"
          type="text"
          placeholder={at("search", {}, "Search")}
        />
      </label>
    </div>
    <div class="admin-icon-picker-grid">
      {#each filteredIconOptions as iconName}
        {@const Icon = iconComponent(iconName)}
        <button
          class:active={iconPickerField && iconValue(iconPickerField) === iconName}
          class="admin-icon-picker-option"
          type="button"
          onclick={() => selectIcon(iconName)}
        >
          {#if Icon}
            <svelte:component this={Icon} size={18} />
          {/if}
          <span>{iconName}</span>
        </button>
      {/each}
    </div>
  </div>
</Dialog>
