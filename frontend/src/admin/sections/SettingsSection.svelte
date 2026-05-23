<script>
  import {
    Check,
    ChevronRight,
    Copy,
    Eye,
    EyeOff,
    FileText,
    Search,
    X,
  } from "$components/ui/icons.js";
  import * as UiIcons from "$components/ui/icons.js";
  import { Accordion, Switch } from "$components/ui/primitives.js";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { getContext, onDestroy, onMount } from "svelte";

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
  let copiedWebhookKey = "";
  let copiedWebhookTimer = null;

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

  onDestroy(() => {
    if (copiedWebhookTimer && typeof window !== "undefined") {
      window.clearTimeout(copiedWebhookTimer);
    }
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
    if (settingsDirty[field.key]?.deleted) return fieldPlaceholderText(field) || "********";
    if (field.has_value) return at("settings_secret_configured", {}, "Secret is set");
    return fieldPlaceholderText(field) || at("settings_secret_empty", {}, "Not set");
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

  async function handleJsonFile(field, event) {
    const file = event?.currentTarget?.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      settingsStore.markDirty(field.key, text);
    } finally {
      event.currentTarget.value = "";
    }
  }

  function normalizeWebhookPath(path) {
    const normalized = String(path || "").trim();
    if (!normalized) return "";
    return normalized.startsWith("/") ? normalized : `/${normalized}`;
  }

  function webhookUrlForField(field) {
    const explicit = String(field?.webhook_url || "").trim();
    if (explicit) return explicit;
    const path = normalizeWebhookPath(field?.webhook_path);
    if (!path) return "";
    if (field?.webhook_requires_base_url && field?.webhook_base_url_configured === false) {
      return "";
    }
    if (typeof window !== "undefined" && window.location?.origin) {
      return `${window.location.origin}${path}`;
    }
    return path;
  }

  function groupWebhook(fields) {
    const field = (fields || []).find((item) => item.webhook_path || item.webhook_url);
    if (!field) return null;
    const path = normalizeWebhookPath(field.webhook_path);
    const url = webhookUrlForField(field);
    if (!url && !path) return null;
    return {
      key: `${field.provider_id || field.key || "provider"}:${path || url}`,
      path,
      url,
      requiresBaseUrl: Boolean(field.webhook_requires_base_url),
      baseConfigured: field.webhook_base_url_configured !== false,
    };
  }

  async function copyWebhookUrl(webhook) {
    if (!webhook?.url) return;
    try {
      await navigator.clipboard.writeText(webhook.url);
      copiedWebhookKey = webhook.key;
      if (copiedWebhookTimer && typeof window !== "undefined") {
        window.clearTimeout(copiedWebhookTimer);
      }
      if (typeof window !== "undefined") {
        copiedWebhookTimer = window.setTimeout(() => {
          copiedWebhookKey = "";
          copiedWebhookTimer = null;
        }, 1400);
      }
    } catch {
      copiedWebhookKey = "";
    }
  }

  function groupSectionFields(section) {
    const groups = new Map();
    for (const field of section.fields || []) {
      const key = field.subsection || "_root";
      if (!groups.has(key)) {
        groups.set(key, { fields: [], i18nLabelKey: field.i18n_subsection_key || null });
      }
      const group = groups.get(key);
      group.fields.push(field);
      if (!group.i18nLabelKey && field.i18n_subsection_key) {
        group.i18nLabelKey = field.i18n_subsection_key;
      }
    }
    return Array.from(groups.entries()).map(([id, group]) => ({
      id,
      label: id === "_root" ? null : id,
      i18nLabelKey: group.i18nLabelKey,
      webhook: groupWebhook(group.fields),
      fields: group.fields,
    }));
  }

  function adminLocaleKey(key) {
    const raw = String(key || "");
    return raw.startsWith("admin_") ? raw.slice("admin_".length) : raw;
  }

  function adminText(key, params = {}, fallback = "") {
    return key ? at(adminLocaleKey(key), params, fallback) : fallback;
  }

  function sectionTitle(id) {
    const map = {
      general: "Общие",
      appearance: "Внешний вид",
      pricing: "Тарифы и цены",
      payments: "Платёжные системы",
      trial: "Триал",
      referral: "Реферальная программа",
      notifications: "Уведомления",
      support: "Поддержка",
      devices: "Устройства",
      subscription_guides: "Connection guides",
    };
    return adminText(`settings_section_${id}`, {}, map[id] || id);
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
    return field.i18n_label_key ? adminText(field.i18n_label_key, {}, fallback) : fallback;
  }

  function fieldDescriptionText(field) {
    if (!field.description) return "";
    return field.i18n_description_key
      ? adminText(field.i18n_description_key, {}, field.description)
      : field.description;
  }

  function fieldPlaceholderText(field) {
    const fallback = field.placeholder || "";
    return field.i18n_placeholder_key
      ? adminText(field.i18n_placeholder_key, {}, fallback)
      : fallback;
  }

  function subsectionTitle(group) {
    if (!group?.label) return "";
    return group.i18nLabelKey ? adminText(group.i18nLabelKey, {}, group.label) : group.label;
  }

  function choiceItems(field) {
    return (field.choices || []).map((choice) => ({
      ...choice,
      label: choice.i18n_label_key
        ? adminText(choice.i18n_label_key, {}, choice.label)
        : choice.label,
    }));
  }
</script>

{#snippet renderWebhookHint(webhook)}
  {@const displayValue = webhook.url || webhook.path}
  <div class="admin-webhook-hint">
    <div class="admin-webhook-hint-meta">
      <strong>{at("settings_provider_webhook_url", {}, "Webhook URL")}</strong>
      <small>
        {webhook.url
          ? at(
              "settings_provider_webhook_url_hint",
              {},
              "Use this URL in the provider webhook settings."
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
      {#if fieldDescriptionText(field)}
        <small>{fieldDescriptionText(field)}</small>
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
          items={choiceItems(field)}
          ariaLabel={fieldLabelText(field)}
          placeholder={fieldPlaceholderText(field) || fieldLabelText(field)}
          onValueChange={(value) => settingsStore.markDirty(field.key, value)}
        />
      {:else if field.type === "int" || field.type === "float"}
        <input
          class="input"
          type="number"
          step={field.type === "float" ? "0.1" : "1"}
          placeholder={fieldPlaceholderText(field)}
          value={valueFor(field) ?? ""}
          oninput={(e) => settingsStore.markDirty(field.key, e.currentTarget.value)}
        />
      {:else if field.type === "text"}
        <textarea
          class="admin-setting-textarea"
          rows="4"
          placeholder={fieldPlaceholderText(field)}
          value={valueFor(field) ?? ""}
          oninput={(e) => settingsStore.markDirty(field.key, e.currentTarget.value)}
        ></textarea>
      {:else if field.type === "json"}
        <div class="admin-json-toolbar">
          <input
            id={"json-file-" + field.key}
            class="admin-json-file-input"
            type="file"
            accept="application/json,.json"
            onchange={(event) => handleJsonFile(field, event)}
          />
          <label
            class="admin-btn admin-btn-sm admin-btn-ghost admin-json-upload"
            for={"json-file-" + field.key}
          >
            <FileText size={13} />
            {at("settings_json_upload", {}, "Load .json")}
          </label>
          {#if valueFor(field)}
            <AdminButton
              size="sm"
              variant="ghost"
              onclick={() => settingsStore.markDirty(field.key, "")}
            >
              <X size={12} />
              {at("clear", {}, "Clear")}
            </AdminButton>
          {/if}
        </div>
        <textarea
          class="admin-setting-textarea admin-setting-json-textarea"
          rows="10"
          spellcheck="false"
          placeholder={fieldPlaceholderText(field)}
          value={valueFor(field) ?? ""}
          oninput={(e) => settingsStore.markDirty(field.key, e.currentTarget.value)}
        ></textarea>
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
          placeholder={fieldPlaceholderText(field)}
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
              {#if rootGroup.webhook}
                {@render renderWebhookHint(rootGroup.webhook)}
              {/if}
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
                        <strong>{subsectionTitle(group)}</strong>
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
                        {#if group.webhook}
                          {@render renderWebhookHint(group.webhook)}
                        {/if}
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
