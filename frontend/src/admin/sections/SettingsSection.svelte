<script lang="ts">
  import { ColorInput, FileInput, Input, Textarea } from "$components/ui/index.js";
  import { Check, ChevronRight, Copy, Eye, EyeOff, FileText, X } from "$components/ui/icons.js";
  import * as UiIcons from "$components/ui/icons.js";
  import { Accordion, Switch } from "$components/ui/primitives.js";
  import SettingsIconPicker from "./settings/SettingsIconPicker.svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { getContext, onDestroy, onMount, tick } from "svelte";
  import { withRoutePrefix } from "$lib/webapp/routes.js";
  import {
    SETTINGS_SECTION_IDS_HIDDEN_IN_GENERAL_SETTINGS,
    arrayValue,
    groupSectionFields,
    normalizeSettingsPath,
    resolveSettingsPath,
    semanticFieldGroups,
    settingsFieldGroupAnchorKey,
    settingsPathAnchorKey,
    settingsPathKey,
    settingsSectionAnchorKey,
    settingsSectionRoute,
    settingsSubsectionAnchorKey,
    settingsSubsectionRoute,
  } from "$lib/admin/settingsSections";
  import type { ComponentType, SvelteComponent } from "svelte";
  import type {
    SettingField,
    SettingsDirtyEntry,
    SettingsSavedPayload,
    SettingsSection,
    SettingsStore,
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

  export let at: TranslateFn;
  export let onSettingsSaved: (payload: SettingsSavedPayload) => void | Promise<void>;
  export let currentLang = "ru";
  export let settingsPath: SettingsPath = [];
  export let routePrefix = "";
  export let onSettingsPathChange: (path: SettingsPath) => void = () => {};

  const settingsStore = getContext<SettingsStore>("settingsStore");

  let rawSettingsSections: SettingsSection[] = [];
  let settingsSections: AdminSettingsSection[] = [];
  let settingsLoading = false;
  let settingsDirty: SettingsDirtyState = {};
  let settingsSaving = false;
  let visibleSettingsSections: SettingsSection[] = [];
  let settingsAllOpen = false;
  let iconOptions: string[] = [];
  let filteredIconOptions: string[] = [];
  let currentSettingsPathKey = "";

  $: ({
    settingsSections: rawSettingsSections,
    settingsLoading,
    settingsDirty,
    settingsSaving,
  } = $settingsStore);
  $: settingsSections = rawSettingsSections as AdminSettingsSection[];

  $: visibleSettingsSections = settingsSections.filter(
    (section) => !SETTINGS_SECTION_IDS_HIDDEN_IN_GENERAL_SETTINGS.has(section.id)
  );

  let settingsOpenSections: string[] = [];
  let settingsOpenSubsections: Record<string, string[]> = {};
  let revealedSecrets = new Set<string>();
  let iconPickerField: SettingField | null = null;
  let iconPickerSearch = "";
  let copiedWebhookKey = "";
  let copiedWebhookTimer: ReturnType<typeof window.setTimeout> | null = null;
  let lastAppliedSettingsPathKey = "";
  let settingsPathSyncing = false;
  let settingsAnchorScrollTimers: Array<ReturnType<typeof window.setTimeout>> = [];
  let settingsAnchorScrollFrames: number[] = [];
  let settingsAnchorScrollCleanup: (() => void) | null = null;

  $: settingsAllOpen =
    visibleSettingsSections.length > 0 &&
    settingsOpenSections.length === visibleSettingsSections.length;
  $: iconOptions = Object.keys(UiIcons)
    .filter((name) => /^[A-Z]/.test(name))
    .sort((a, b) => a.localeCompare(b));
  $: filteredIconOptions = iconOptions.filter((name) =>
    name.toLowerCase().includes(iconPickerSearch.trim().toLowerCase())
  );
  $: currentSettingsPathKey = settingsPathKey(settingsPath);
  $: if (visibleSettingsSections.length && currentSettingsPathKey) {
    if (currentSettingsPathKey !== lastAppliedSettingsPathKey) {
      lastAppliedSettingsPathKey = currentSettingsPathKey;
      void applySettingsPath(settingsPath);
    }
  } else if (!currentSettingsPathKey) {
    lastAppliedSettingsPathKey = "";
  }

  onMount(() => {
    settingsStore.loadSettings();
  });

  onDestroy(() => {
    if (copiedWebhookTimer && typeof window !== "undefined") {
      window.clearTimeout(copiedWebhookTimer);
    }
    cancelPendingSettingsAnchorScroll();
  });

  function toggleAllSections(): void {
    if (settingsOpenSections.length === visibleSettingsSections.length) {
      settingsOpenSections = [];
    } else {
      settingsOpenSections = visibleSettingsSections.map((s) => s.id);
    }
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

  function settingsSubsectionOpenHandler(sectionId: string): (value: string[]) => void {
    return (value: string[]) => handleSettingsSubsectionsOpenChange(sectionId, value);
  }

  function findSettingsAnchor(anchorKey: string): HTMLElement | null {
    if (typeof document === "undefined" || !anchorKey) return null;
    return (
      Array.from(document.querySelectorAll<HTMLElement>("[data-settings-anchor]")).find(
        (element) => element.dataset.settingsAnchor === anchorKey
      ) || null
    );
  }

  function prefersReducedMotion(): boolean {
    return (
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
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
        scrollSettingsAnchorIntoView(anchorKey, prefersReducedMotion() ? "auto" : "smooth", {
          focus: true,
        });
        for (const delay of [180, 360]) {
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

  function sectionTitle(id: string): string {
    const map = {
      general: "Общие",
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
    return field.i18n_label_key ? adminText(field.i18n_label_key, {}, fallback) : fallback;
  }

  function fieldDescriptionText(field: AdminSettingField): string {
    if (!field.description) return "";
    return field.i18n_description_key
      ? adminText(field.i18n_description_key, {}, field.description)
      : field.description;
  }

  function fieldPlaceholderText(field: AdminSettingField): string {
    const fallback = field.placeholder || "";
    return field.i18n_placeholder_key
      ? adminText(field.i18n_placeholder_key, {}, fallback)
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

  function fieldSelectHandler(field: AdminSettingField): (...args: never[]) => void {
    return ((value: string) => settingsStore.markDirty(field.key, value)) as (
      ...args: never[]
    ) => void;
  }

  function jsonFileHandler(field: AdminSettingField): (event: Event) => void {
    return (event: Event) => {
      void handleJsonFile(field, event);
    };
  }
</script>

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
  <Accordion.Root
    type="multiple"
    value={settingsOpenSections}
    onValueChange={handleSettingsSectionsOpenChange}
    class="admin-accordion"
  >
    {#each visibleSettingsSections as section}
      {@const dirtyInSection = section.fields.filter((f) => Boolean(settingsDirty[f.key])).length}
      {@const overriddenInSection = section.fields.filter((f) => isOverridden(f)).length}
      <Accordion.Item value={section.id} class="admin-accordion-item admin-card">
        <Accordion.Header class="admin-accordion-header">
          <Accordion.Trigger
            class="admin-accordion-trigger"
            data-settings-anchor={settingsSectionAnchorKey(section.id)}
          >
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
              {@render renderGroupedFields(section, rootGroup)}
            {/if}
            {#if labelGroups.length}
              <Accordion.Root
                type="multiple"
                value={settingsOpenSubsections[section.id] || []}
                onValueChange={settingsSubsectionOpenHandler(section.id)}
                class="admin-subsection-accordion"
              >
                {#each labelGroups as group}
                  {@const subDirty = group.fields.filter((f) =>
                    Boolean(settingsDirty[f.key])
                  ).length}
                  {@const subOverridden = group.fields.filter((f) => isOverridden(f)).length}
                  <Accordion.Item value={group.id} class="admin-settings-subsection">
                    <Accordion.Header class="admin-accordion-header">
                      <Accordion.Trigger
                        class="admin-settings-subsection-trigger"
                        data-settings-anchor={settingsSubsectionAnchorKey(section.id, group.id)}
                      >
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
                        {@render renderGroupedFields(section, group)}
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
