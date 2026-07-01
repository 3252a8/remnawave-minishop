<script lang="ts">
  import { getTranslationsStore } from "$lib/admin/context";
  import { Input, Textarea } from "$components/ui/index.js";
  import { ChevronRight, Languages, Plus, Search, X } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton, AdminEmptyState } from "$components/patterns/admin/index.js";
  import { onDestroy, onMount, untrack } from "svelte";
  import { slide } from "svelte/transition";
  import type {
    TranslationDirtyEntry,
    TranslationDirtyState,
    TranslationGroup,
    TranslationItem,
    TranslationLanguage,
    TranslationsSavedPayload,
    TranslationValue,
  } from "../../lib/admin/stores/translationsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type TranslationGroupWithItems = TranslationGroup & { items: TranslationItem[] };
  type AudienceSection = {
    id: string;
    title: string;
    hint: string;
    groups: TranslationGroupWithItems[];
  };

  type TranslationsSectionProps = {
    at: TranslateFn;
    onTranslationsSaved?: (payload: TranslationsSavedPayload) => void | Promise<void>;
  };

  let { at, onTranslationsSaved }: TranslationsSectionProps = $props();

  const translationsStore = getTranslationsStore();
  const AUDIENCE_ORDER = ["user", "internal"];
  const AUDIENCE_FILTERS = ["all", ...AUDIENCE_ORDER];
  const translationGroups = $derived(translationsStore.translationGroups as TranslationGroup[]);
  const translationLanguages = $derived(
    translationsStore.translationLanguages as TranslationLanguage[]
  );
  const translationsLoading = $derived(Boolean(translationsStore.translationsLoading));
  const translationsDirty = $derived(translationsStore.translationsDirty as TranslationDirtyState);
  const translationsSaving = $derived(Boolean(translationsStore.translationsSaving));
  const translationsPath = $derived(String(translationsStore.translationsPath || ""));

  let openGroups = $state<string[]>([]);
  let readyGroups = $state<string[]>([]);
  let openLocaleEditors = $state<string[]>([]);
  let closedLocaleEditors = $state<string[]>([]);
  let search = $state("");
  let audienceFilter = $state("all");
  let newLanguageCode = $state("");
  const readyTimers = new Map<string, number>();

  const openGroupSet = $derived(new Set(openGroups));
  const readyGroupSet = $derived(new Set(readyGroups));
  const openLocaleEditorSet = $derived(new Set(openLocaleEditors));
  const closedLocaleEditorSet = $derived(new Set(closedLocaleEditors));
  const filteredTranslationGroups = $derived(
    filteredGroups(translationGroups, search, translationLanguages)
  );
  const audienceSections = $derived(
    buildAudienceSections(filteredTranslationGroups, audienceFilter)
  );
  const visibleGroupKeys = $derived(
    audienceSections.flatMap((section) =>
      section.groups.map((group) => groupPanelId(section.id, group.id))
    )
  );
  const allOpen = $derived(
    visibleGroupKeys.length > 0 && visibleGroupKeys.every((key) => openGroups.includes(key))
  );

  $effect(() => {
    const groups = openGroups;
    untrack(() => scheduleReadyGroups(groups));
  });

  onMount(() => {
    translationsStore.loadTranslations();
  });

  onDestroy(() => {
    for (const timer of readyTimers.values()) clearTimeout(timer);
    readyTimers.clear();
  });

  function dirtyKey(lang: string, key: string): string {
    return `${lang}:${key}`;
  }

  function dirtyFor(lang: string, key: string): TranslationDirtyEntry | null {
    return translationsDirty[dirtyKey(lang, key)] || null;
  }

  function defaultBaseValue(item: TranslationItem): string {
    for (const values of Object.values(item.values || {})) {
      if (values?.fallback) return values.fallback;
    }
    const baseLanguage = (translationLanguages || []).find((language) => language.base);
    const baseCode = baseLanguage?.code || translationLanguages?.[0]?.code || "";
    const values = item.values?.[baseCode] || {};
    return values.base || values.fallback || values.effective || "";
  }

  function valueRecord(item: TranslationItem, lang: string): TranslationValue {
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

  function localeValue(
    item: TranslationItem,
    lang: string,
    dirty = dirtyFor(lang, item.key)
  ): string {
    if (dirty?.deleted) return "";
    if (dirty) return dirty.value;
    return valueRecord(item, lang).override || "";
  }

  function isOverridden(
    item: TranslationItem,
    lang: string,
    dirty = dirtyFor(lang, item.key)
  ): boolean {
    return Boolean(valueRecord(item, lang).overridden) && !dirty?.deleted;
  }

  function isDirty(item: TranslationItem, lang: string, dirty = dirtyFor(lang, item.key)): boolean {
    return Boolean(dirty);
  }

  function baseValue(item: TranslationItem, lang: string): string {
    const values = valueRecord(item, lang);
    return values.base || values.fallback || "";
  }

  function baseKind(item: TranslationItem, lang: string): string {
    return valueRecord(item, lang).base
      ? at("translations_base_value", {}, "Base")
      : at("translations_fallback_value", {}, "Fallback");
  }

  function effectiveValue(item: TranslationItem, lang: string): string {
    return valueRecord(item, lang).effective || baseValue(item, lang);
  }

  function localePreview(
    item: TranslationItem,
    lang: string,
    dirty = dirtyFor(lang, item.key)
  ): string {
    return (
      localeValue(item, lang, dirty) || effectiveValue(item, lang) || baseValue(item, lang) || "-"
    );
  }

  function itemAudience(item: TranslationItem, group: TranslationGroup | null = null): string {
    return item.audience || group?.audience || "user";
  }

  function audienceLabel(id: string): string {
    if (id === "internal") {
      return at("translations_audience_internal", {}, "Admin/internal");
    }
    if (id === "user") {
      return at("translations_audience_user", {}, "User-visible");
    }
    return at("translations_audience_all", {}, "All");
  }

  function audienceHint(id: string): string {
    if (id === "internal") {
      return at("translations_audience_internal_hint", {}, "Admin panel, logs, and sync copy");
    }
    return at("translations_audience_user_hint", {}, "Mini App, bot, payment, and support copy");
  }

  function groupPanelId(sectionId: string, groupId: string): string {
    return `${sectionId}:${groupId}`;
  }

  function localePanelId(key: string, lang: string): string {
    return `${key}:${lang}`;
  }

  function toggleLocaleEditor(item: TranslationItem, lang: string): void {
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
    group: TranslationGroupWithItems,
    dirtyState = translationsDirty,
    languages = translationLanguages
  ): number {
    return (group.items || []).reduce(
      (count, item) =>
        count +
        languages.filter((lang) => Boolean(dirtyState[dirtyKey(lang.code, item.key)])).length,
      0
    );
  }

  function groupOverrideCount(
    group: TranslationGroupWithItems,
    dirtyState = translationsDirty,
    languages = translationLanguages
  ): number {
    return (group.items || []).reduce(
      (count, item) =>
        count +
        languages.filter((lang) =>
          isOverridden(item, lang.code, dirtyState[dirtyKey(lang.code, item.key)])
        ).length,
      0
    );
  }

  function itemHasOverride(
    item: TranslationItem,
    dirtyState = translationsDirty,
    languages = translationLanguages
  ): boolean {
    return languages.some((lang) =>
      isOverridden(item, lang.code, dirtyState[dirtyKey(lang.code, item.key)])
    );
  }

  function itemHasDirty(
    item: TranslationItem,
    dirtyState = translationsDirty,
    languages = translationLanguages
  ): boolean {
    return languages.some((lang) => Boolean(dirtyState[dirtyKey(lang.code, item.key)]));
  }

  function withItems(group: TranslationGroup): TranslationGroupWithItems {
    return { ...group, items: group.items || [] };
  }

  function filteredGroups(
    groups: TranslationGroup[],
    query: string,
    languages = translationLanguages
  ): TranslationGroupWithItems[] {
    const needle = String(query || "")
      .trim()
      .toLowerCase();
    if (!needle) return (groups || []).map(withItems);
    return (groups || [])
      .map((group) => ({
        ...group,
        items: (group.items || []).filter((item) => itemMatches(item, group, needle, languages)),
      }))
      .filter((group) => group.items.length);
  }

  function itemMatches(
    item: TranslationItem,
    group: TranslationGroup,
    needle: string,
    languages = translationLanguages
  ): boolean {
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

  function buildAudienceSections(
    groups: TranslationGroupWithItems[],
    filter: string
  ): AudienceSection[] {
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

  function toggleAllGroups(): void {
    openGroups = allOpen ? [] : visibleGroupKeys;
  }

  function isGroupOpen(id: string): boolean {
    return openGroups.includes(id);
  }

  function toggleGroup(id: string): void {
    if (isGroupOpen(id)) {
      openGroups = openGroups.filter((groupId) => groupId !== id);
      return;
    }
    openGroups = [...openGroups, id];
    queueGroupReady(id);
  }

  function scheduleReadyGroups(groups: string[]): void {
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

  function queueGroupReady(id: string): void {
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

  function groupTitle(group: TranslationGroup): string {
    return group.title_key ? at(group.title_key, {}, group.title) : group.title;
  }

  function groupDescription(group: TranslationGroup): string {
    return group.description_key
      ? at(group.description_key, {}, group.description || "")
      : group.description || "";
  }

  function canAddLanguage(code: string): boolean {
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

  function addLanguage(): void {
    if (translationsStore.addTranslationLanguage(newLanguageCode)) {
      newLanguageCode = "";
    }
  }

  function handleLocaleInput(lang: string, key: string, event: Event): void {
    const textarea = event.currentTarget as HTMLTextAreaElement | null;
    translationsStore.markDirty(lang, key, textarea?.value || "");
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

{#snippet renderGroupSkeleton(group: TranslationGroupWithItems)}
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

{#snippet renderLocaleEditor(item: TranslationItem, language: TranslationLanguage)}
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
      data-admin-translation-locale={localeId}
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
        <Textarea
          class="admin-setting-textarea admin-translation-textarea"
          rows={3}
          spellcheck="false"
          placeholder={baseValue(item, lang)}
          value={localeValue(item, lang, dirtyEntry)}
          oninput={(event: Event) => handleLocaleInput(lang, item.key, event)}
        />
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

{#snippet renderTranslationItem(item: TranslationItem, group: TranslationGroup)}
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
      <Input
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
      <Input
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
        data-admin-translation-audience={option}
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
                    data-admin-translation-group={panelId}
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
