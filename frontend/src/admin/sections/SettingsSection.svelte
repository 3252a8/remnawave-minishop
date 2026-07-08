<script lang="ts">
  import { getSettingsStore } from "$lib/admin/context";
  import * as UiIcons from "$components/ui/icons.js";
  import SettingsContent from "./settings/SettingsContent.svelte";
  import SettingsIconPicker from "./settings/SettingsIconPicker.svelte";
  import { onDestroy, onMount, tick } from "svelte";
  import { prefersReducedMotion } from "svelte/motion";
  import { withRoutePrefix } from "$lib/webapp/routes.js";
  import {
    SETTINGS_SECTION_IDS_HIDDEN_IN_GENERAL_SETTINGS,
    arrayValue,
    normalizeSettingsPath,
    resolveSettingsPath,
    settingsPathAnchorKey,
    settingsPathKey,
    settingsSectionRoute,
    settingsSubsectionRoute,
  } from "$lib/admin/settingsSections";
  import {
    buildSettingsSearchEntries,
    searchSettingsEntries,
    type SettingsSearchEntry,
  } from "$lib/admin/settingsSearch";
  import type { ComponentType, SvelteComponent } from "svelte";
  import type {
    SettingField,
    SettingsDirtyEntry,
    SettingsSavedPayload,
    SettingsSection,
  } from "$lib/admin/stores/settingsStore";
  import type {
    AdminSettingField,
    AdminSettingsSection,
    GroupWebhook,
    SemanticFieldGroup,
    SettingsPath,
    SettingsSubsection,
  } from "$lib/admin/settingsSections";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type SettingsDirtyState = Record<string, SettingsDirtyEntry>;
  type DynamicComponent = ComponentType<SvelteComponent<Record<string, unknown>>>;
  type ScrollOptions = { focus?: boolean };
  type WindowListenerTuple = [
    type: string,
    handler: (event: Event) => void,
    options: boolean | { passive: boolean },
  ];

  let {
    at,
    onSettingsSaved,
    currentLang = "ru",
    settingsPath = [],
    routePrefix = "",
    onSettingsPathChange = () => {},
  }: {
    at: TranslateFn;
    onSettingsSaved: (payload: SettingsSavedPayload) => void | Promise<void>;
    currentLang?: string;
    settingsPath?: SettingsPath;
    routePrefix?: string;
    onSettingsPathChange?: (path: SettingsPath) => void;
  } = $props();

  const settingsStore = getSettingsStore();

  const rawSettingsSections = $derived((settingsStore.settingsSections || []) as SettingsSection[]);
  const settingsSections = $derived(rawSettingsSections as AdminSettingsSection[]);
  const settingsLoading = $derived(Boolean(settingsStore.settingsLoading));
  const settingsDirty = $derived((settingsStore.settingsDirty || {}) as SettingsDirtyState);
  const settingsSaving = $derived(Boolean(settingsStore.settingsSaving));
  const visibleSettingsSections = $derived(
    settingsSections.filter(
      (section) => !SETTINGS_SECTION_IDS_HIDDEN_IN_GENERAL_SETTINGS.has(section.id)
    )
  );

  let settingsOpenSections = $state<string[]>([]);
  let settingsOpenSubsections = $state<Record<string, string[]>>({});
  let revealedSecrets = $state(new Set<string>());
  let iconPickerField = $state<SettingField | null>(null);
  let iconPickerSearch = $state("");
  let copiedWebhookKey = $state("");
  let copiedWebhookTimer = $state<ReturnType<typeof window.setTimeout> | null>(null);
  let lastAppliedSettingsPathKey = $state("");
  let settingsPathSyncing = $state(false);
  let settingsAnchorScrollTimers = $state<Array<ReturnType<typeof window.setTimeout>>>([]);
  let settingsAnchorScrollFrames = $state<number[]>([]);
  let settingsAnchorScrollCleanup = $state<(() => void) | null>(null);
  let settingsSearchQuery = $state("");
  let highlightedSettingKey = $state("");
  let settingsSearchHighlightTimer = $state<ReturnType<typeof window.setTimeout> | null>(null);

  const settingsAllOpen = $derived(
    visibleSettingsSections.length > 0 &&
      settingsOpenSections.length === visibleSettingsSections.length
  );
  const iconOptions = $derived(
    Object.keys(UiIcons)
      .filter((name) => /^[A-Z]/.test(name))
      .sort((a, b) => a.localeCompare(b))
  );
  const filteredIconOptions = $derived(
    iconOptions.filter((name) => name.toLowerCase().includes(iconPickerSearch.trim().toLowerCase()))
  );
  const settingsSearchEntries = $derived(
    buildSettingsSearchEntries(visibleSettingsSections, {
      sectionTitle,
      subsectionTitle,
      fieldLabelText,
      fieldDescriptionText,
    })
  );
  const settingsSearchResults = $derived(
    searchSettingsEntries(settingsSearchEntries, settingsSearchQuery, 8)
  );
  const currentSettingsPathKey = $derived(settingsPathKey(settingsPath));
  $effect(() => {
    if (visibleSettingsSections.length && currentSettingsPathKey) {
      if (currentSettingsPathKey !== lastAppliedSettingsPathKey) {
        lastAppliedSettingsPathKey = currentSettingsPathKey;
        void applySettingsPath(settingsPath);
      }
      return;
    }
    if (!currentSettingsPathKey) lastAppliedSettingsPathKey = "";
  });

  onMount(() => {
    settingsStore.loadSettings();
  });

  onDestroy(() => {
    if (copiedWebhookTimer && typeof window !== "undefined") {
      window.clearTimeout(copiedWebhookTimer);
    }
    clearSettingsSearchHighlight();
    cancelPendingSettingsAnchorScroll();
  });

  function toggleAllSections(): void {
    if (settingsOpenSections.length === visibleSettingsSections.length) {
      settingsOpenSections = [];
    } else {
      settingsOpenSections = visibleSettingsSections.map((s) => s.id);
    }
  }

  function clearSettingsSearch(): void {
    settingsSearchQuery = "";
  }

  function clearSettingsSearchHighlight(): void {
    if (settingsSearchHighlightTimer && typeof window !== "undefined") {
      window.clearTimeout(settingsSearchHighlightTimer);
    }
    settingsSearchHighlightTimer = null;
    highlightedSettingKey = "";
  }

  function highlightSettingsSearchResult(key: string): void {
    clearSettingsSearchHighlight();
    highlightedSettingKey = key;
    if (typeof window === "undefined") return;
    settingsSearchHighlightTimer = window.setTimeout(() => {
      clearSettingsSearchHighlight();
    }, 2600);
  }

  async function selectSettingsSearchResult(result: SettingsSearchEntry): Promise<void> {
    const routePath = result.subsectionId
      ? settingsSubsectionRoute(result.sectionId, result.subsectionId)
      : settingsSectionRoute(result.sectionId);
    updateSettingsRoute(routePath);

    if (!settingsOpenSections.includes(result.sectionId)) {
      settingsOpenSections = [...settingsOpenSections, result.sectionId];
    }
    if (result.subsectionId) {
      const openSubsections = settingsOpenSubsections[result.sectionId] || [];
      if (!openSubsections.includes(result.subsectionId)) {
        settingsOpenSubsections = {
          ...settingsOpenSubsections,
          [result.sectionId]: [...openSubsections, result.subsectionId],
        };
      }
    }

    highlightSettingsSearchResult(result.key);
    await tick();
    scrollToSettingsAnchor(result.anchorKey);
  }

  function currentUrlSettingsPath(): SettingsPath {
    if (typeof window === "undefined") return [];
    const prefix = String(routePrefix || "").replace(/\/+$/, "");
    const pathname = window.location.pathname;
    const routePath =
      prefix && pathname.toLowerCase().startsWith(`${prefix.toLowerCase()}/`)
        ? pathname.slice(prefix.length)
        : pathname;
    const match = routePath.match(/^\/admin\/settings(?:\/(.*))?$/i);
    if (!match?.[1]) return [];
    return normalizeSettingsPath(
      match[1].split("/").map((segment) => {
        try {
          return decodeURIComponent(segment);
        } catch {
          return segment;
        }
      })
    );
  }

  function effectiveSettingsPath(path: unknown): SettingsPath {
    const normalized = normalizeSettingsPath(path);
    const fromUrl = currentUrlSettingsPath();
    return fromUrl.length > normalized.length ? fromUrl : normalized;
  }

  function updateSettingsRoute(segments: unknown, replace = false): void {
    if (settingsPathSyncing || typeof window === "undefined") return;
    if (window.location.protocol === "file:") return;
    const pathSegments = arrayValue(segments).filter(Boolean);
    lastAppliedSettingsPathKey = settingsPathKey(pathSegments);
    cancelPendingSettingsAnchorScroll();
    const pathSuffix = pathSegments.length ? `/${pathSegments.join("/")}` : "";
    const targetPath = withRoutePrefix(`/admin/settings${pathSuffix}`, routePrefix);
    const nextUrl = `${targetPath}${window.location.search}${window.location.hash}`;
    if (`${window.location.pathname}${window.location.search}${window.location.hash}` === nextUrl) {
      return;
    }
    window.history[replace ? "replaceState" : "pushState"](null, "", nextUrl);
    onSettingsPathChange(pathSegments);
  }

  function handleSettingsSectionsOpenChange(value: unknown): void {
    const next = arrayValue(value);
    const openedSection = next.find((sectionId) => !settingsOpenSections.includes(sectionId));
    settingsOpenSections = next;
    if (!openedSection) return;
    updateSettingsRoute(settingsSectionRoute(openedSection));
  }

  function handleSettingsSubsectionsOpenChange(sectionId: string, value: unknown): void {
    const previous = settingsOpenSubsections[sectionId] || [];
    const next = arrayValue(value);
    const openedGroup = next.find((groupId) => !previous.includes(groupId));
    settingsOpenSubsections = { ...settingsOpenSubsections, [sectionId]: next };
    if (!openedGroup) return;
    updateSettingsRoute(settingsSubsectionRoute(sectionId, openedGroup));
  }

  function settingsDisclosureId(...parts: string[]): string {
    return `admin-settings-${parts
      .map((part) => String(part || "").replace(/[^a-z0-9_-]+/gi, "-"))
      .filter(Boolean)
      .join("-")}`;
  }

  function toggleSettingsSection(sectionId: string): void {
    const next = settingsOpenSections.includes(sectionId)
      ? settingsOpenSections.filter((id) => id !== sectionId)
      : [...settingsOpenSections, sectionId];
    handleSettingsSectionsOpenChange(next);
  }

  function toggleSettingsSubsection(sectionId: string, groupId: string): void {
    const current = settingsOpenSubsections[sectionId] || [];
    const next = current.includes(groupId)
      ? current.filter((id) => id !== groupId)
      : [...current, groupId];
    handleSettingsSubsectionsOpenChange(sectionId, next);
  }

  function findSettingsAnchor(anchorKey: string): HTMLElement | null {
    if (typeof document === "undefined" || !anchorKey) return null;
    return (
      Array.from(document.querySelectorAll<HTMLElement>("[data-settings-anchor]")).find(
        (element) => element.dataset.settingsAnchor === anchorKey
      ) || null
    );
  }

  function scrollSettingsAnchorIntoView(
    anchorKey: string,
    behavior: "auto" | "smooth" | "instant",
    options: ScrollOptions = {}
  ): void {
    const element = findSettingsAnchor(anchorKey);
    if (!element) return;
    const scrollParent = scrollContainerFor(element);
    if (scrollParent) {
      const parentRect = scrollParent.getBoundingClientRect();
      const elementRect = element.getBoundingClientRect();
      const targetTop = scrollParent.scrollTop + elementRect.top - parentRect.top - 12;
      scrollParent.scrollTo({ top: Math.max(0, targetTop), behavior });
    } else {
      element.scrollIntoView({ block: "start", behavior });
    }
    if (options.focus && typeof element.focus === "function") {
      try {
        element.focus({ preventScroll: true });
      } catch {
        element.focus();
      }
    }
  }

  function scrollContainerFor(element: HTMLElement): HTMLElement | null {
    let parent = element?.parentElement || null;
    while (parent) {
      const style = window.getComputedStyle(parent);
      const overflow = `${style.overflow} ${style.overflowY}`;
      const canScroll = /(auto|scroll|overlay)/.test(overflow);
      if (canScroll && parent.scrollHeight > parent.clientHeight) {
        return parent;
      }
      parent = parent.parentElement;
    }
    return null;
  }

  function clearSettingsAnchorScrollListeners(): void {
    if (!settingsAnchorScrollCleanup) return;
    settingsAnchorScrollCleanup();
    settingsAnchorScrollCleanup = null;
  }

  function cancelPendingSettingsAnchorScroll(): void {
    if (typeof window !== "undefined") {
      for (const timer of settingsAnchorScrollTimers) window.clearTimeout(timer);
      for (const frame of settingsAnchorScrollFrames) window.cancelAnimationFrame(frame);
    }
    settingsAnchorScrollTimers = [];
    settingsAnchorScrollFrames = [];
    clearSettingsAnchorScrollListeners();
  }

  function scheduleSettingsAnchorScrollTimeout(
    callback: () => void,
    delay: number
  ): ReturnType<typeof window.setTimeout> {
    const timer = window.setTimeout(() => {
      settingsAnchorScrollTimers = settingsAnchorScrollTimers.filter((id) => id !== timer);
      callback();
    }, delay);
    settingsAnchorScrollTimers = [...settingsAnchorScrollTimers, timer];
    return timer;
  }

  function scheduleSettingsAnchorScrollFrame(callback: () => void): number {
    const frame = window.requestAnimationFrame(() => {
      settingsAnchorScrollFrames = settingsAnchorScrollFrames.filter((id) => id !== frame);
      callback();
    });
    settingsAnchorScrollFrames = [...settingsAnchorScrollFrames, frame];
    return frame;
  }

  function armSettingsAnchorScrollCancel(): void {
    clearSettingsAnchorScrollListeners();
    const cancel = () => cancelPendingSettingsAnchorScroll();
    const listeners: WindowListenerTuple[] = [
      ["wheel", cancel, { passive: true }],
      ["touchstart", cancel, { passive: true }],
      ["pointerdown", cancel, false],
      ["keydown", cancel, false],
    ];
    for (const [type, handler, options] of listeners) {
      window.addEventListener(type, handler, options);
    }
    settingsAnchorScrollCleanup = () => {
      for (const [type, handler, options] of listeners) {
        window.removeEventListener(type, handler, typeof options === "boolean" ? options : false);
      }
    };
    scheduleSettingsAnchorScrollTimeout(() => {
      clearSettingsAnchorScrollListeners();
    }, 700);
  }

  function scrollToSettingsAnchor(anchorKey: string): void {
    if (typeof window === "undefined") return;
    cancelPendingSettingsAnchorScroll();
    armSettingsAnchorScrollCancel();
    scheduleSettingsAnchorScrollFrame(() => {
      scheduleSettingsAnchorScrollFrame(() => {
        scrollSettingsAnchorIntoView(anchorKey, prefersReducedMotion.current ? "auto" : "smooth", {
          focus: true,
        });
        for (const delay of [180, 360, 720]) {
          scheduleSettingsAnchorScrollTimeout(
            () => scrollSettingsAnchorIntoView(anchorKey, "auto"),
            delay
          );
        }
      });
    });
  }

  async function applySettingsPath(path: unknown): Promise<void> {
    const resolvedPath = effectiveSettingsPath(path);
    const target = resolveSettingsPath(resolvedPath, visibleSettingsSections);
    if (!target) return;

    settingsPathSyncing = true;
    try {
      if (!settingsOpenSections.includes(target.section.id)) {
        settingsOpenSections = [...settingsOpenSections, target.section.id];
      }
      if (target.group) {
        const openSubsections = settingsOpenSubsections[target.section.id] || [];
        if (!openSubsections.includes(target.group.id)) {
          settingsOpenSubsections = {
            ...settingsOpenSubsections,
            [target.section.id]: [...openSubsections, target.group.id],
          };
        }
      }
      await tick();
      scrollToSettingsAnchor(settingsPathAnchorKey(resolvedPath, target));
    } finally {
      if (typeof window !== "undefined") {
        window.setTimeout(() => {
          settingsPathSyncing = false;
        }, 0);
      } else {
        settingsPathSyncing = false;
      }
    }
  }

  function valueFor(field: AdminSettingField): unknown {
    if (settingsDirty[field.key]?.deleted) return "";
    if (Object.prototype.hasOwnProperty.call(settingsDirty, field.key)) {
      return settingsDirty[field.key].value;
    }
    return field.value ?? "";
  }

  function fieldTextValue(field: AdminSettingField): string {
    const value = valueFor(field);
    return value == null ? "" : String(value);
  }

  function fieldInputValue(field: AdminSettingField): string | number {
    const value = valueFor(field);
    return typeof value === "string" || typeof value === "number" ? value : "";
  }

  function isOverridden(field: AdminSettingField): boolean {
    return Boolean(field.overridden) && !settingsDirty[field.key]?.deleted;
  }

  function isSecretRevealed(key: string): boolean {
    return revealedSecrets.has(key);
  }

  function toggleSecretReveal(key: string): void {
    const next = new Set(revealedSecrets);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    revealedSecrets = next;
  }

  function secretPlaceholder(field: AdminSettingField): string {
    if (settingsDirty[field.key]?.deleted) return fieldPlaceholderText(field) || "********";
    if (field.has_value) return at("settings_secret_configured", {}, "Secret is set");
    return fieldPlaceholderText(field) || at("settings_secret_empty", {}, "Not set");
  }

  function iconComponent(name: unknown): DynamicComponent | null {
    const key = String(name || "").trim();
    return key ? ((UiIcons as Record<string, unknown>)[key] as DynamicComponent) || null : null;
  }

  function iconValue(field: AdminSettingField | null): string {
    if (!field) return "";
    return String(valueFor(field) || field.placeholder || "").trim();
  }

  function iconIsDefault(field: AdminSettingField): boolean {
    return !String(valueFor(field) || "").trim();
  }

  function iconLabel(field: AdminSettingField | null): string {
    const iconName = iconValue(field);
    if (!iconName) return at("settings_icon_empty", {}, "Default icon");
    if (field && iconIsDefault(field)) {
      return at("settings_icon_default_value", { icon: iconName }, `Default: ${iconName}`);
    }
    return iconName;
  }

  function openIconPicker(field: AdminSettingField): void {
    iconPickerField = field;
    iconPickerSearch = "";
  }

  function closeIconPicker(): void {
    iconPickerField = null;
    iconPickerSearch = "";
  }

  function selectIcon(name: string): void {
    if (!iconPickerField) return;
    settingsStore.markDirty(iconPickerField.key, name);
    closeIconPicker();
  }

  function clearIconPickerField(): void {
    if (!iconPickerField) return;
    settingsStore.markDirty(iconPickerField.key, "");
  }

  async function handleJsonFile(field: AdminSettingField, event: Event): Promise<void> {
    const input = event.currentTarget as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      settingsStore.markDirty(field.key, text);
    } finally {
      if (input) input.value = "";
    }
  }

  async function copyWebhookUrl(webhook: GroupWebhook): Promise<void> {
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

  function fieldGroupTitle(group: SemanticFieldGroup): string {
    return group.titleKey ? at(group.titleKey, {}, group.titleFallback) : "";
  }

  function fieldGroupDescription(group: SemanticFieldGroup): string {
    return group.descriptionKey ? at(group.descriptionKey, {}, group.descriptionFallback) : "";
  }

  function adminLocaleKey(key: unknown): string {
    const raw = String(key || "");
    return raw.startsWith("admin_") ? raw.slice("admin_".length) : raw;
  }

  function adminText(key: unknown, params: Record<string, unknown> = {}, fallback = ""): string {
    return key ? at(adminLocaleKey(key), params, fallback) : fallback;
  }

  function fieldI18nParams(field: AdminSettingField): Record<string, unknown> {
    return {
      provider: field.provider_label || field.subsection || field.provider_id || "",
    };
  }

  function sectionTitle(id: string): string {
    const map = {
      general: "Общие",
      email: "Email",
      remnawave: "Remnawave Panel",
      appearance: "Внешний вид",
      pricing: "Тарифы и цены",
      payments: "Платёжные системы",
      trial: "Триал",
      referral: "Реферальная программа",
      notifications: "Уведомления",
      backups: "Бэкапы",
      support: "Поддержка",
      devices: "Устройства",
      subscription_guides: "Connection guides",
      system: "Система",
      migrations: "Миграции",
    };
    return adminText(`settings_section_${id}`, {}, map[id as keyof typeof map] || id);
  }

  function englishFieldLabelFallback(key: string, originalLabel: string | undefined): string {
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

  function fieldLabelText(field: AdminSettingField): string {
    const isEnglish = String(currentLang || "")
      .toLowerCase()
      .startsWith("en");
    const fallback = isEnglish ? englishFieldLabelFallback(field.key, field.label) : field.label;
    return field.i18n_label_key
      ? adminText(field.i18n_label_key, fieldI18nParams(field), fallback)
      : fallback;
  }

  function fieldDescriptionText(field: AdminSettingField): string {
    if (!field.description) return "";
    return field.i18n_description_key
      ? adminText(field.i18n_description_key, fieldI18nParams(field), field.description)
      : field.description;
  }

  function fieldPlaceholderText(field: AdminSettingField): string {
    const fallback = field.placeholder || "";
    return field.i18n_placeholder_key
      ? adminText(field.i18n_placeholder_key, fieldI18nParams(field), fallback)
      : fallback;
  }

  function subsectionTitle(group: SettingsSubsection): string {
    if (!group?.label) return "";
    return group.i18nLabelKey ? adminText(group.i18nLabelKey, {}, group.label) : group.label;
  }

  function choiceItems(field: AdminSettingField): Array<{ value: string; label: string }> {
    return (field.choices || []).map((choice) => ({
      ...choice,
      label: choice.i18n_label_key
        ? adminText(choice.i18n_label_key, {}, choice.label)
        : choice.label,
    }));
  }

  function setBoolField(field: AdminSettingField, checked: boolean): void {
    settingsStore.markDirty(field.key, checked);
    if (checked && field.mutually_exclusive_key) {
      settingsStore.markDirty(field.mutually_exclusive_key, false);
    }
  }

  function fieldInputHandler(field: AdminSettingField): (event: Event) => void {
    return (event: Event) => {
      const input = event.currentTarget as HTMLInputElement | HTMLTextAreaElement | null;
      settingsStore.markDirty(field.key, input?.value ?? "");
    };
  }

  function fieldSelectHandler(field: AdminSettingField): (value: string) => void {
    return (value: string) => settingsStore.markDirty(field.key, value);
  }

  function jsonFileHandler(field: AdminSettingField): (event: Event) => void {
    return (event: Event) => {
      void handleJsonFile(field, event);
    };
  }

  function saveSettings(): void {
    void settingsStore.saveSettings(onSettingsSaved);
  }

  function markFieldDirty(key: string, value: unknown): void {
    settingsStore.markDirty(key, value);
  }

  function resetField(field: AdminSettingField): void {
    settingsStore.resetField(field);
  }
</script>

<SettingsContent
  {at}
  {settingsLoading}
  {visibleSettingsSections}
  {settingsDirty}
  {settingsSaving}
  {settingsAllOpen}
  {settingsOpenSections}
  {settingsOpenSubsections}
  bind:settingsSearchQuery
  {settingsSearchResults}
  {highlightedSettingKey}
  {copiedWebhookKey}
  {toggleAllSections}
  {clearSettingsSearch}
  {selectSettingsSearchResult}
  {saveSettings}
  {toggleSettingsSection}
  {toggleSettingsSubsection}
  {settingsDisclosureId}
  {copyWebhookUrl}
  {adminLocaleKey}
  {sectionTitle}
  {subsectionTitle}
  {fieldGroupTitle}
  {fieldGroupDescription}
  {fieldLabelText}
  {fieldDescriptionText}
  {fieldPlaceholderText}
  {valueFor}
  {fieldTextValue}
  {fieldInputValue}
  {isOverridden}
  {isSecretRevealed}
  {toggleSecretReveal}
  {secretPlaceholder}
  {iconComponent}
  {iconValue}
  {iconLabel}
  {iconIsDefault}
  {openIconPicker}
  {choiceItems}
  {setBoolField}
  {fieldInputHandler}
  {fieldSelectHandler}
  {jsonFileHandler}
  {markFieldDirty}
  {resetField}
/>

<SettingsIconPicker
  {at}
  {iconPickerField}
  bind:iconPickerSearch
  {filteredIconOptions}
  {fieldLabelText}
  {iconComponent}
  {iconValue}
  {iconLabel}
  {iconIsDefault}
  {closeIconPicker}
  {clearIconPickerField}
  {selectIcon}
/>
