<script>
  import { ChevronRight, Eye, EyeOff, X } from "$components/ui/icons.js";
  import { Accordion, Switch } from "$components/ui/primitives.js";
  import { AdminBadge, AdminButton, AdminEmptyState } from "$components/patterns/admin/index.js";
  import { getContext, onMount } from "svelte";

  export let at;
  export let onSettingsSaved;
  export let isCompact = false;

  const settingsStore = getContext("settingsStore");

  $: ({
    settingsSections,
    settingsLoading,
    settingsDirty,
    settingsSaving,
  } = $settingsStore);

  let settingsOpenSections = [];
  let settingsOpenSubsections = {};
  let revealedSecrets = new Set();

  $: settingsAllOpen = settingsSections.length > 0 && settingsOpenSections.length === settingsSections.length;

  onMount(() => {
    settingsStore.loadSettings().then(() => {
      if ($settingsStore.settingsSections.length) {
        const ids = $settingsStore.settingsSections.map((s) => s.id);
        settingsOpenSections = isCompact ? ids.slice(0, 1) : ids.slice();
      }
    });
  });

  function toggleAllSections() {
    if (settingsOpenSections.length === settingsSections.length) {
      settingsOpenSections = [];
    } else {
      settingsOpenSections = settingsSections.map((s) => s.id);
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
      general: at("settings_section_general", {}, "Общие"),
      appearance: at("settings_section_appearance", {}, "Внешний вид"),
      pricing: at("settings_section_pricing", {}, "Тарифы и цены"),
      payments: at("settings_section_payments", {}, "Платёжные системы"),
      trial: at("settings_section_trial", {}, "Триал"),
      referral: at("settings_section_referral", {}, "Реферальная программа"),
      notifications: at("settings_section_notifications", {}, "Уведомления"),
      devices: at("settings_section_devices", {}, "Устройства"),
    };
    return map[id] || id;
  }
</script>

{#snippet renderField(field)}
  {@const revealed = isSecretRevealed(field.key)}
  <div class="admin-setting" class:is-overridden={isOverridden(field)}>
    <div class="admin-setting-meta">
      <strong>
        {field.label}
          <AdminBadge variant="warning">{at("settings_badge_secret", {}, "Secret")}</AdminBadge>
        {#if isOverridden(field)}
          <AdminBadge variant="success">{at("settings_badge_override", {}, "Override")}</AdminBadge>
        {/if}
      </strong>
      <code>{field.key}</code>
      {#if field.description}
        <small>{field.description}</small>
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
          <span>{Boolean(valueFor(field)) ? at("enabled", {}, "Включено") : at("disabled", {}, "Выключено")}</span>
        </div>
      {:else if field.type === "color"}
        <input
          class="admin-color"
          type="color"
          value={valueFor(field) || "#00fe7a"}
          on:input={(e) => settingsStore.markDirty(field.key, e.currentTarget.value)}
        />
        <input
          class="input"
          type="text"
          value={valueFor(field) || ""}
          on:input={(e) => settingsStore.markDirty(field.key, e.currentTarget.value)}
        />
      {:else if field.type === "int" || field.type === "float"}
        <input
          class="input"
          type="number"
          step={field.type === "float" ? "0.1" : "1"}
          placeholder={field.placeholder}
          value={valueFor(field) ?? ""}
          on:input={(e) => settingsStore.markDirty(field.key, e.currentTarget.value)}
        />
      {:else if field.secret}
        <input
          class="input"
          type={revealed ? "text" : "password"}
          placeholder={field.placeholder || "••••••••"}
          autocomplete="off"
          value={valueFor(field) ?? ""}
          on:input={(e) => settingsStore.markDirty(field.key, e.currentTarget.value)}
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
          on:input={(e) => settingsStore.markDirty(field.key, e.currentTarget.value)}
        />
      {/if}
      {#if isOverridden(field) || settingsDirty[field.key]}
        <AdminButton size="sm" variant="ghost" onclick={() => settingsStore.resetField(field)}>
          <X size={12} /> {at("reset", {}, "Сбросить")}
        </AdminButton>
      {/if}
    </div>
  </div>
{/snippet}

{#if settingsLoading || !settingsSections.length}
  <AdminEmptyState>{settingsLoading ? at("loading", {}, "Загрузка…") : at("no_data", {}, "Нет данных")}</AdminEmptyState>
{:else}
  <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;">
    <p class="admin-muted" style="margin:0;">
      {at("settings_hint", {}, "Изменения в админке имеют приоритет над .env. Кнопка «Сбросить» возвращает значение из переменных окружения.")}
    </p>
    <div style="display:flex; gap:8px;">
      <AdminButton size="sm" variant="ghost" onclick={toggleAllSections}>
        {settingsAllOpen ? at("collapse_all", {}, "Свернуть всё") : at("expand_all", {}, "Развернуть всё")}
      </AdminButton>
      {#if Object.keys(settingsDirty).length > 0}
        <AdminButton size="sm" variant="primary" onclick={() => settingsStore.saveSettings(onSettingsSaved)} disabled={settingsSaving}>
          {settingsSaving ? at("saving", {}, "Сохранение...") : at("save", {}, "Сохранить")}
        </AdminButton>
      {/if}
    </div>
  </div>
  <Accordion.Root type="multiple" bind:value={settingsOpenSections} class="admin-accordion">
    {#each settingsSections as section}
      {@const dirtyInSection = section.fields.filter((f) => Boolean(settingsDirty[f.key])).length}
      {@const overriddenInSection = section.fields.filter((f) => isOverridden(f)).length}
      <Accordion.Item value={section.id} class="admin-accordion-item admin-card">
        <Accordion.Header class="admin-accordion-header">
          <Accordion.Trigger class="admin-accordion-trigger">
            <span class="admin-accordion-title">{sectionTitle(section.id)}</span>
            <span class="admin-accordion-meta">
              {at("settings_params_count", { count: section.fields.length }, `${section.fields.length} параметров`)}{#if overriddenInSection} · {at("settings_overridden_count", { count: overriddenInSection }, `${overriddenInSection} override`)}{/if}{#if dirtyInSection} · {at("settings_dirty_count", { count: dirtyInSection }, `${dirtyInSection} изм.`)}{/if}
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
                onValueChange={(v) => (settingsOpenSubsections = { ...settingsOpenSubsections, [section.id]: v })}
                class="admin-subsection-accordion"
              >
                {#each labelGroups as group}
                  {@const subDirty = group.fields.filter((f) => Boolean(settingsDirty[f.key])).length}
                  {@const subOverridden = group.fields.filter((f) => isOverridden(f)).length}
                  <Accordion.Item value={group.id} class="admin-settings-subsection">
                    <Accordion.Header class="admin-accordion-header">
                      <Accordion.Trigger class="admin-settings-subsection-trigger">
                        <strong>{group.label}</strong>
                        <span class="admin-settings-subsection-meta">
                          {at("settings_fields_count", { count: group.fields.length }, `${group.fields.length} полей`)}{#if subOverridden} · {at("settings_overridden_count", { count: subOverridden }, `${subOverridden} override`)}{/if}{#if subDirty} · {at("settings_dirty_count", { count: subDirty }, `${subDirty} изм.`)}{/if}
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
