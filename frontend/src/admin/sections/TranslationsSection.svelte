<script>
  import { ChevronRight, Languages, Plus, Search, X } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton, AdminEmptyState } from "$components/patterns/admin/index.js";
  import { getContext, onDestroy, onMount } from "svelte";
  import { slide } from "svelte/transition";

  export let at;
  export let onTranslationsSaved;

  const translationsStore = getContext("translationsStore");
  const AUDIENCE_ORDER = ["user", "internal"];
  const AUDIENCE_FILTERS = ["all", ...AUDIENCE_ORDER];

  $: ({
    translationGroups,
    translationLanguages,
    translationsLoading,
    translationsDirty,
    translationsSaving,
    translationsPath,
  } = $translationsStore);

  let openGroups = [];
  let readyGroups = [];
  let openLocaleEditors = [];
  let closedLocaleEditors = [];
  let search = "";
  let audienceFilter = "all";
  let newLanguageCode = "";
  const readyTimers = new Map();

  $: openGroupSet = new Set(openGroups);
  $: readyGroupSet = new Set(readyGroups);
  $: openLocaleEditorSet = new Set(openLocaleEditors);
  $: closedLocaleEditorSet = new Set(closedLocaleEditors);
  $: filteredTranslationGroups = filteredGroups(translationGroups, search, translationLanguages);
  $: audienceSections = buildAudienceSections(filteredTranslationGroups, audienceFilter);
  $: visibleGroupKeys = audienceSections.flatMap((section) =>
    section.groups.map((group) => groupPanelId(section.id, group.id))
  );
  $: allOpen =
    visibleGroupKeys.length > 0 && visibleGroupKeys.every((key) => openGroups.includes(key));
  $: scheduleReadyGroups(openGroups);

  onMount(() => {
    translationsStore.loadTranslations();
  });

  onDestroy(() => {
    for (const timer of readyTimers.values()) clearTimeout(timer);
    readyTimers.clear();
  });

  function dirtyKey(lang, key) {
    return `${lang}:${key}`;
  }

  function dirtyFor(lang, key) {
    return translationsDirty[dirtyKey(lang, key)] || null;
  }

  function defaultBaseValue(item) {
    for (const values of Object.values(item.values || {})) {
      if (values?.fallback) return values.fallback;
    }
    const baseLanguage = (translationLanguages || []).find((language) => language.base);
    const baseCode = baseLanguage?.code || translationLanguages?.[0]?.code || "";
    const values = item.values?.[baseCode] || {};
    return values.base || values.fallback || values.effective || "";
  }

  function valueRecord(item, lang) {
    return (
      item.values?.[lang] || {
        base: "",
        fallback: defaultBaseValue(item),
        effective: defaultBaseValue(item),
        override: "",
        overridden: false,
      }
    );
  }

  function localeValue(item, lang, dirty = dirtyFor(lang, item.key)) {
    if (dirty?.deleted) return "";
    if (dirty) return dirty.value;
    return valueRecord(item, lang).override || "";
  }

  function isOverridden(item, lang, dirty = dirtyFor(lang, item.key)) {
    return Boolean(valueRecord(item, lang).overridden) && !dirty?.deleted;
  }

  function isDirty(item, lang, dirty = dirtyFor(lang, item.key)) {
    return Boolean(dirty);
  }

  function baseValue(item, lang) {
    const values = valueRecord(item, lang);
    return values.base || values.fallback || "";
  }

  function baseKind(item, lang) {
    return valueRecord(item, lang).base
      ? at("translations_base_value", {}, "Base")
      : at("translations_fallback_value", {}, "Fallback");
  }

  function effectiveValue(item, lang) {
    return valueRecord(item, lang).effective || baseValue(item, lang);
  }

  function localePreview(item, lang, dirty = dirtyFor(lang, item.key)) {
    return (
      localeValue(item, lang, dirty) || effectiveValue(item, lang) || baseValue(item, lang) || "-"
    );
  }

  function itemAudience(item, group = null) {
    return item.audience || group?.audience || "user";
  }

  function audienceLabel(id) {
    if (id === "internal") {
      return at("translations_audience_internal", {}, "Admin/internal");
    }
    if (id === "user") {
      return at("translations_audience_user", {}, "User-visible");
    }
    return at("translations_audience_all", {}, "All");
  }

  function audienceHint(id) {
    if (id === "internal") {
      return at("translations_audience_internal_hint", {}, "Admin panel, logs, and sync copy");
    }
    return at("translations_audience_user_hint", {}, "Mini App, bot, payment, and support copy");
  }

  function groupPanelId(sectionId, groupId) {
    return `${sectionId}:${groupId}`;
  }

  function localePanelId(key, lang) {
    return `${key}:${lang}`;
  }

  function toggleLocaleEditor(item, lang) {
    const id = localePanelId(item.key, lang);
    const defaultOpen = isOverridden(item, lang) || isDirty(item, lang);
    const openByUser = openLocaleEditors.includes(id);
    const closedByUser = closedLocaleEditors.includes(id);
    const currentlyOpen = openByUser || (defaultOpen && !closedByUser);

    if (currentlyOpen) {
      openLocaleEditors = openLocaleEditors.filter((itemId) => itemId !== id);
      if (!closedByUser) closedLocaleEditors = [...closedLocaleEditors, id];
      return;
    }

    closedLocaleEditors = closedLocaleEditors.filter((itemId) => itemId !== id);
    if (!openByUser) openLocaleEditors = [...openLocaleEditors, id];
  }

  function groupDirtyCount(
    group,
    dirtyState = translationsDirty,
    languages = translationLanguages
  ) {
    return (group.items || []).reduce(
      (count, item) =>
        count +
        languages.filter((lang) => Boolean(dirtyState[dirtyKey(lang.code, item.key)])).length,
      0
    );
  }

  function groupOverrideCount(
    group,
    dirtyState = translationsDirty,
    languages = translationLanguages
  ) {
    return (group.items || []).reduce(
      (count, item) =>
        count +
        languages.filter((lang) =>
          isOverridden(item, lang.code, dirtyState[dirtyKey(lang.code, item.key)])
        ).length,
      0
    );
  }

  function itemHasOverride(item, dirtyState = translationsDirty, languages = translationLanguages) {
    return languages.some((lang) =>
      isOverridden(item, lang.code, dirtyState[dirtyKey(lang.code, item.key)])
    );
  }

  function itemHasDirty(item, dirtyState = translationsDirty, languages = translationLanguages) {
    return languages.some((lang) => Boolean(dirtyState[dirtyKey(lang.code, item.key)]));
  }

  function filteredGroups(groups, query, languages = translationLanguages) {
    const needle = String(query || "")
      .trim()
      .toLowerCase();
    if (!needle) return groups || [];
    return (groups || [])
      .map((group) => ({
        ...group,
        items: (group.items || []).filter((item) => itemMatches(item, group, needle, languages)),
      }))
      .filter((group) => group.items.length);
  }

  function itemMatches(item, group, needle, languages = translationLanguages) {
    if (
      String(item.key || "")
        .toLowerCase()
        .includes(needle)
    )
      return true;
    if (audienceLabel(itemAudience(item, group)).toLowerCase().includes(needle)) return true;
    return languages.some((lang) => {
      const values = valueRecord(item, lang.code);
      return [values.base, values.fallback, values.override, values.effective]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(needle));
    });
  }

  function buildAudienceSections(groups, filter) {
    return AUDIENCE_ORDER.map((audience) => ({
      id: audience,
      title: audienceLabel(audience),
      hint: audienceHint(audience),
      groups: (groups || [])
        .map((group) => ({
          ...group,
          audience,
          items: (group.items || []).filter((item) => itemAudience(item, group) === audience),
        }))
        .filter((group) => group.items.length),
    })).filter((section) => (filter === "all" || section.id === filter) && section.groups.length);
  }

  function toggleAllGroups() {
    openGroups = allOpen ? [] : visibleGroupKeys;
  }

  function isGroupOpen(id) {
    return openGroups.includes(id);
  }

  function toggleGroup(id) {
    if (isGroupOpen(id)) {
      openGroups = openGroups.filter((groupId) => groupId !== id);
      return;
    }
    openGroups = [...openGroups, id];
    queueGroupReady(id);
  }

  function scheduleReadyGroups(groups) {
    const openSet = new Set(groups);
    const nextReady = readyGroups.filter((id) => openSet.has(id));
    if (nextReady.length !== readyGroups.length) readyGroups = nextReady;
    for (const [id, timer] of readyTimers.entries()) {
      if (!openSet.has(id)) {
        clearTimeout(timer);
        readyTimers.delete(id);
      }
    }
    for (const id of groups) {
      queueGroupReady(id);
    }
  }

  function queueGroupReady(id) {
    if (readyGroups.includes(id) || readyTimers.has(id)) return;
    readyTimers.set(
      id,
      setTimeout(() => {
        readyTimers.delete(id);
        if (!readyGroups.includes(id)) {
          readyGroups = [...readyGroups, id];
        }
      }, 70)
    );
  }

  function groupTitle(group) {
    return group.title_key ? at(group.title_key, {}, group.title) : group.title;
  }

  function groupDescription(group) {
    return group.description_key
      ? at(group.description_key, {}, group.description)
      : group.description;
  }

  function canAddLanguage(code) {
    const normalized = String(code || "")
      .trim()
      .toLowerCase()
      .replace(/_/g, "-");
    return (
      /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/.test(normalized) &&
      normalized.length >= 2 &&
      normalized.length <= 16 &&
      !translationLanguages.some((lang) => lang.code === normalized)
    );
  }

  function addLanguage() {
    if (translationsStore.addTranslationLanguage(newLanguageCode)) {
      newLanguageCode = "";
    }
  }
</script>

{#snippet renderTranslationsSkeleton()}
  <div class="admin-translations-skeleton">
    <div class="admin-translations-toolbar">
      <span class="admin-skeleton admin-skeleton-line"></span>
      <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span>
    </div>
    {#each Array(4) as _, index (index)}
      <div class="admin-card admin-translation-skeleton-card">
        <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"></span>
        <span class="admin-skeleton admin-skeleton-line"></span>
        <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-soft"></span>
      </div>
    {/each}
  </div>
{/snippet}

{#snippet renderGroupSkeleton(group)}
  <div class="admin-translation-group-skeleton" aria-label={at("loading", {}, "Loading")}>
    <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span>
    {#each Array(Math.min(3, Math.max(1, group.items.length))) as _, index (index)}
      <div class="admin-translation-row admin-translation-row-skeleton">
        <span>
          <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"></span>
          <span class="admin-skeleton admin-skeleton-line"></span>
        </span>
        <span>
          <span class="admin-skeleton admin-skeleton-line"></span>
          <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-soft"></span>
        </span>
      </div>
    {/each}
  </div>
{/snippet}

{#snippet renderLocaleEditor(item, language)}
  {@const lang = language.code}
  {@const dirtyEntry = translationsDirty[dirtyKey(lang, item.key)] || null}
  {@const overridden = isOverridden(item, lang, dirtyEntry)}
  {@const dirty = isDirty(item, lang, dirtyEntry)}
  {@const localeId = localePanelId(item.key, lang)}
  {@const expanded =
    openLocaleEditorSet.has(localeId) ||
    ((overridden || dirty) && !closedLocaleEditorSet.has(localeId))}
  <div
    class="admin-translation-locale"
    class:is-overridden={overridden}
    class:is-dirty={dirty}
    class:is-expanded={expanded}
  >
    <button
      type="button"
      class="admin-translation-locale-toggle"
      aria-expanded={expanded}
      onclick={() => toggleLocaleEditor(item, lang)}
    >
      <span class="admin-translation-locale-main">
        <strong>{language.label}</strong>
        <code>{lang}</code>
      </span>
      <span class="admin-translation-locale-badges">
        {#if !language.base}
          <AdminBadge variant="muted">{at("translations_language_custom", {}, "Custom")}</AdminBadge
          >
        {/if}
        {#if overridden}
          <AdminBadge variant="success">{at("settings_badge_override", {}, "Override")}</AdminBadge>
        {/if}
        {#if dirty}
          <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Dirty")}</AdminBadge>
        {/if}
        <ChevronRight size={14} class="admin-accordion-chev" />
      </span>
      <small>{localePreview(item, lang, dirtyEntry)}</small>
    </button>

    {#if expanded}
      <div class="admin-translation-locale-body" transition:slide={{ duration: 130 }}>
        <textarea
          class="admin-setting-textarea admin-translation-textarea"
          rows="3"
          spellcheck="false"
          placeholder={baseValue(item, lang)}
          value={localeValue(item, lang, dirtyEntry)}
          oninput={(event) =>
            translationsStore.markDirty(lang, item.key, event.currentTarget.value)}
        ></textarea>
        <div class="admin-translation-base">
          <small>{baseKind(item, lang)}</small>
          <span title={baseValue(item, lang)}>{baseValue(item, lang) || "-"}</span>
        </div>
        {#if overridden || dirty}
          <AdminButton
            size="sm"
            variant="ghost"
            onclick={() => translationsStore.resetField(lang, item.key, overridden)}
          >
            <X size={12} />
            {at("reset", {}, "Reset")}
          </AdminButton>
        {/if}
      </div>
    {/if}
  </div>
{/snippet}

{#snippet renderTranslationItem(item, group)}
  {@const audience = itemAudience(item, group)}
  <div class="admin-translation-row">
    <div class="admin-setting-meta">
      <strong>
        {item.key}
        <AdminBadge variant={audience === "internal" ? "warning" : "success"}>
          {audienceLabel(audience)}
        </AdminBadge>
        {#if itemHasOverride(item, translationsDirty, translationLanguages)}
          <AdminBadge variant="success">{at("settings_badge_override", {}, "Override")}</AdminBadge>
        {/if}
        {#if itemHasDirty(item, translationsDirty, translationLanguages)}
          <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Dirty")}</AdminBadge>
        {/if}
      </strong>
      <code>{item.key}</code>
      <small>{effectiveValue(item, translationLanguages[0]?.code)}</small>
    </div>
    <div class="admin-translation-locales">
      {#each translationLanguages as language (language.code)}
        {@render renderLocaleEditor(item, language)}
      {/each}
    </div>
  </div>
{/snippet}

{#if translationsLoading || !translationGroups.length}
  {@render renderTranslationsSkeleton()}
{:else}
  <div class="admin-translations-toolbar">
    <label class="admin-translations-search">
      <Search size={15} />
      <input
        bind:value={search}
        class="input"
        type="text"
        placeholder={at("translations_search_placeholder", {}, "Search keys and text")}
      />
    </label>
    <div class="admin-translations-actions">
      <AdminButton size="sm" variant="ghost" onclick={toggleAllGroups}>
        {allOpen ? at("collapse_all", {}, "Collapse all") : at("expand_all", {}, "Expand all")}
      </AdminButton>
      {#if Object.keys(translationsDirty).length > 0}
        <AdminButton
          size="sm"
          variant="primary"
          onclick={() => translationsStore.saveTranslations(onTranslationsSaved)}
          disabled={translationsSaving}
        >
          {translationsSaving ? at("saving", {}, "Saving...") : at("save", {}, "Save")}
        </AdminButton>
      {/if}
    </div>
  </div>

  <div class="admin-translations-language-panel">
    <div class="admin-translations-language-head">
      <Languages size={17} />
      <strong>{at("translations_languages_title", {}, "Languages")}</strong>
      <small>{at("translations_languages_hint", {}, "Override any locale code")}</small>
    </div>
    <div class="admin-translations-language-list">
      {#each translationLanguages as language (language.code)}
        <span class="admin-translations-language-chip" class:is-custom={!language.base}>
          <strong>{language.label}</strong>
          <code>{language.code}</code>
        </span>
      {/each}
    </div>
    <form
      class="admin-translations-language-add"
      onsubmit={(event) => {
        event.preventDefault();
        addLanguage();
      }}
    >
      <input
        bind:value={newLanguageCode}
        class="input"
        type="text"
        inputmode="latin"
        placeholder={at("translations_language_placeholder", {}, "de, uk, pt-BR")}
      />
      <AdminButton type="submit" size="sm" disabled={!canAddLanguage(newLanguageCode)}>
        <Plus size={14} />
        {at("add", {}, "Add")}
      </AdminButton>
    </form>
  </div>

  <div class="admin-translations-audience-tabs" role="tablist">
    {#each AUDIENCE_FILTERS as option (option)}
      <button
        type="button"
        class:is-active={audienceFilter === option}
        onclick={() => {
          audienceFilter = option;
          openGroups = [];
        }}
      >
        {audienceLabel(option)}
      </button>
    {/each}
  </div>

  <p class="admin-muted admin-translations-path">
    {at(
      "translations_hint",
      { path: translationsPath },
      `Overrides are stored in DB and mirrored to ${translationsPath}.`
    )}
  </p>

  {#if audienceSections.length}
    <div class="admin-translations-accordion-root">
      {#each audienceSections as section (section.id)}
        <section class="admin-translations-audience-section">
          <div class="admin-translations-audience-head">
            <span>
              <strong>{section.title}</strong>
              <small>{section.hint}</small>
            </span>
            <AdminBadge variant={section.id === "internal" ? "warning" : "success"}>
              {section.groups.reduce((count, group) => count + group.items.length, 0)}
            </AdminBadge>
          </div>
          <div class="admin-accordion">
            {#each section.groups as group (groupPanelId(section.id, group.id))}
              {@const dirtyCount = groupDirtyCount(group, translationsDirty, translationLanguages)}
              {@const overrideCount = groupOverrideCount(
                group,
                translationsDirty,
                translationLanguages
              )}
              {@const panelId = groupPanelId(section.id, group.id)}
              {@const groupOpen = openGroupSet.has(panelId)}
              {@const groupReady = readyGroupSet.has(panelId)}
              <div
                class="admin-accordion-item admin-card"
                data-state={groupOpen ? "open" : "closed"}
              >
                <div class="admin-accordion-header">
                  <button
                    type="button"
                    class="admin-accordion-trigger"
                    data-state={groupOpen ? "open" : "closed"}
                    aria-expanded={groupOpen}
                    onclick={() => toggleGroup(panelId)}
                  >
                    <span class="admin-accordion-title admin-translation-title-line">
                      {groupTitle(group)}
                      <AdminBadge variant={section.id === "internal" ? "warning" : "success"}>
                        {section.title}
                      </AdminBadge>
                    </span>
                    <span class="admin-accordion-meta">
                      {at(
                        "translations_keys_count",
                        { count: group.items.length },
                        `${group.items.length} keys`
                      )}{#if overrideCount}
                        / {at(
                          "settings_overridden_count",
                          { count: overrideCount },
                          `${overrideCount} override`
                        )}{/if}{#if dirtyCount}
                        / {at(
                          "settings_dirty_count",
                          { count: dirtyCount },
                          `${dirtyCount} changed`
                        )}
                      {/if}
                    </span>
                    <ChevronRight size={16} class="admin-accordion-chev" />
                  </button>
                </div>
                {#if groupOpen}
                  <div
                    class="admin-accordion-content"
                    data-state="open"
                    transition:slide={{ duration: 140 }}
                  >
                    {#if groupReady}
                      {#if groupDescription(group)}
                        <p class="admin-muted admin-translation-group-description">
                          {groupDescription(group)}
                        </p>
                      {/if}
                      <div class="admin-translation-list">
                        {#each group.items as item (item.key)}
                          {@render renderTranslationItem(item, group)}
                        {/each}
                      </div>
                    {:else}
                      {@render renderGroupSkeleton(group)}
                    {/if}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        </section>
      {/each}
    </div>
  {:else}
    <AdminEmptyState>{at("translations_no_matches", {}, "No matching strings")}</AdminEmptyState>
  {/if}
{/if}
