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
  import PaymentMethodsOrderField from "./PaymentMethodsOrderField.svelte";
  import NotificationDeliveryMatrix from "./NotificationDeliveryMatrix.svelte";
  import MenuButtonsField from "./MenuButtonsField.svelte";
  import ProgramSettingsSections from "./marketing/ProgramSettingsSections.svelte";
  import {
    groupSectionFields,
    semanticFieldGroups,
    settingsFieldAnchorKey,
    settingsFieldGroupAnchorKey,
    settingsSectionAnchorKey,
    settingsSubsectionAnchorKey,
  } from "$lib/admin/settingsSections";
  import { loginProviderCallbackUrl } from "$lib/admin/loginProviderSetup.js";
  import {
    settingsDirtyCountLabel,
    settingsFieldsCountLabel,
    settingsOverriddenCountLabel,
    settingsParamsCountLabel,
  } from "./disclosureLabels";
  import type { ComponentType, SvelteComponent } from "svelte";
  import type { SettingsSearchEntry } from "$lib/admin/settingsSearch";
  import type { SettingsDirtyEntry } from "$lib/admin/stores/settingsStore";
  import type { TranslationLanguage } from "$lib/admin/stores/translationsStore";
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
    appRepositoryUrl = "https://minishop.minidoc.cc/",
    settingsLoading,
    extraDirtyCount = 0,
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
    onNavigateSection = () => {},
    onOpenSettingsPath = () => {},
    menuButtonLanguages = [],
  }: {
    at: TranslateFn;
    appRepositoryUrl?: string;
    settingsLoading: boolean;
    extraDirtyCount?: number;
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
    onNavigateSection?: (section: string) => void;
    onOpenSettingsPath?: (path?: unknown) => void;
    menuButtonLanguages?: TranslationLanguage[];
  } = $props();

  let settingsSearchOpen = $state(false);
  let copiedLoginProviderKey = $state("");

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

  function releaseSettingsSearchFocus(): void {
    if (typeof document === "undefined") return;
    const activeElement = document.activeElement;
    if (activeElement instanceof HTMLElement) activeElement.blur();
  }

  function chooseSettingsSearchResult(result: SettingsSearchEntry): void {
    settingsSearchOpen = false;
    releaseSettingsSearchFocus();
    void selectSettingsSearchResult(result);
  }

  function handleSettingsSearchResultPointerDown(
    event: PointerEvent,
    result: SettingsSearchEntry
  ): void {
    if (event.button !== 0) return;
    event.preventDefault();
    chooseSettingsSearchResult(result);
  }

  function resetSettingsSearch(): void {
    clearSettingsSearch();
    settingsSearchOpen = false;
  }

  function fieldValueSourceLabel(field: AdminSettingField): string {
    const dirty = settingsDirty[field.key];
    const source = dirty?.deleted
      ? "environment"
      : dirty
        ? "database_override"
        : String(field.value_source || "").trim();
    if (source === "database_override") {
      return at("settings_source_database_override", {}, "Source: database override");
    }
    if (source === "environment") {
      return at("settings_source_environment", {}, "Source: environment (.env)");
    }
    return "";
  }

  function configuredValue(key: string): boolean {
    const field = visibleSettingsSections
      .flatMap((section) => section.fields)
      .find((item) => item.key === key);
    if (!field) return false;
    if (field.secret && !settingsDirty[key] && field.has_value) return true;
    const value = settingsDirty[key]?.value ?? valueFor(field);
    return typeof value === "boolean" ? value : Boolean(String(value ?? "").trim());
  }

  function configuredText(key: string): string {
    const field = visibleSettingsSections
      .flatMap((section) => section.fields)
      .find((item) => item.key === key);
    if (!field) return "";
    return String(settingsDirty[key]?.value ?? valueFor(field) ?? "").trim();
  }

  function loginProviderCallback(provider: "google" | "yandex"): string {
    const base = configuredText("SUBSCRIPTION_MINI_APP_URL");
    const fallbackOrigin = typeof window === "undefined" ? "" : window.location.origin;
    return loginProviderCallbackUrl(provider, base, fallbackOrigin);
  }

  async function copyLoginProviderValue(key: string, value: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(value);
      copiedLoginProviderKey = key;
    } catch {
      copiedLoginProviderKey = "";
    }
  }

  function loginProviderHelpTitle(provider: string): string {
    if (provider === "google")
      return at("settings_login_google_help_title", {}, "Google OAuth application");
    if (provider === "yandex")
      return at("settings_login_yandex_help_title", {}, "Yandex OAuth application");
    return at("settings_login_passkey_help_title", {}, "Passkey domain settings");
  }

  function loginProviderHelpHint(provider: string): string {
    if (provider === "google")
      return at(
        "settings_login_google_help_hint",
        {},
        "Create a Web OAuth client and add the exact callback URL below."
      );
    if (provider === "yandex")
      return at(
        "settings_login_yandex_help_hint",
        {},
        "Create an app for user authorization and add the callback as a Web service Redirect URI."
      );
    return at(
      "settings_login_passkey_help_hint",
      {},
      "Use HTTPS; RP ID must be the application domain and origins must contain its full origin."
    );
  }

  function loginProviderOfficialUrl(provider: string): string {
    if (provider === "google")
      return "https://developers.google.com/identity/protocols/oauth2/web-server";
    if (provider === "yandex") return "https://yandex.com/dev/id/doc/en/register-auth";
    return "https://developer.mozilla.org/en-US/docs/Web/Security/Authentication/Passkeys";
  }

  function loginProviderGuideUrl(provider: string): string {
    const section = provider === "yandex" ? "yandex-id" : provider;
    const docsBaseUrl = appRepositoryUrl.replace(/\/+$/, "");
    return `${docsBaseUrl}/features/login-methods/#${section}`;
  }
</script>

{#snippet renderLoginMethodHints()}
  {@const emailReady =
    configuredValue("QA_AUTH_ENABLED") ||
    (configuredValue("SMTP_HOST") &&
      configuredValue("SMTP_PORT") &&
      configuredValue("SMTP_USERNAME") &&
      configuredValue("SMTP_PASSWORD") &&
      configuredValue("SMTP_FROM_EMAIL"))}
  {@const telegramReady = configuredValue("TELEGRAM_OAUTH_CLIENT_ID")}
  <div class="admin-login-method-hints">
    {#if configuredValue("EMAIL_LOGIN_ENABLED") && !emailReady}
      <div class="admin-settings-warning">
        <FileText size={18} />
        <div class="admin-settings-warning-copy">
          <strong>{at("settings_login_email_setup_title", {}, "Email needs SMTP")}</strong>
          <p>
            {at(
              "settings_login_email_setup_hint",
              {},
              "Configure SMTP before enabling email codes and password recovery."
            )}
          </p>
        </div>
        <AdminButton
          class="admin-settings-warning-action"
          size="sm"
          variant="ghost"
          onclick={() => onOpenSettingsPath(["email", "smtp"])}
        >
          {at("settings_login_open_smtp", {}, "Open SMTP")}
        </AdminButton>
      </div>
    {/if}
    {#if configuredValue("TELEGRAM_LOGIN_ENABLED") && !telegramReady}
      <div class="admin-settings-warning">
        <FileText size={18} />
        <div class="admin-settings-warning-copy">
          <strong>{at("settings_login_telegram_setup_title", {}, "Telegram bot setup")}</strong>
          <p>
            {at(
              "settings_login_telegram_setup_hint",
              {},
              "A bot token and Telegram Login client are required outside Telegram Mini Apps."
            )}
          </p>
        </div>
        <AdminButton
          class="admin-settings-warning-action"
          size="sm"
          variant="ghost"
          onclick={() => onOpenSettingsPath(["login_methods", "telegram"])}
        >
          {at("settings_login_open_telegram", {}, "Open Telegram")}
        </AdminButton>
      </div>
    {/if}
  </div>
{/snippet}

{#snippet renderLoginProviderHelp(provider: string)}
  {#if provider === "google" || provider === "yandex" || provider === "passkey"}
    <div class="admin-login-provider-help">
      <div class="admin-login-provider-help-copy">
        <strong>{loginProviderHelpTitle(provider)}</strong>
        <p>{loginProviderHelpHint(provider)}</p>
        {#if provider === "google"}
          <div class="admin-login-provider-setup-values">
            <div class="admin-login-provider-setup-row">
              <span>
                {at("settings_login_google_js_origins_label", {}, "Authorized JavaScript origins")}
              </span>
              <p>
                {at(
                  "settings_login_google_js_origins_not_required",
                  {},
                  "Leave empty — Minishop uses the server-side authorization code flow and does not load the Google JavaScript SDK."
                )}
              </p>
            </div>
            <div class="admin-login-provider-setup-row">
              <span>
                {at("settings_login_google_redirect_uris_label", {}, "Authorized redirect URIs")}
              </span>
              {@render renderLoginProviderValue("google-redirect", loginProviderCallback("google"))}
            </div>
          </div>
        {:else if provider === "yandex"}
          <div class="admin-login-provider-setup-values">
            <div class="admin-login-provider-setup-row">
              <span>{at("settings_login_yandex_platform_label", {}, "Platform")}</span>
              <p>{at("settings_login_yandex_platform_value", {}, "Web services")}</p>
            </div>
            <div class="admin-login-provider-setup-row">
              <span>
                {at("settings_login_yandex_redirect_uri_label", {}, "Redirect URI")}
              </span>
              {@render renderLoginProviderValue("yandex-redirect", loginProviderCallback("yandex"))}
            </div>
            <div class="admin-login-provider-setup-row">
              <span>{at("settings_login_yandex_permissions_label", {}, "Permissions")}</span>
              <code>login:email · login:info · login:avatar</code>
            </div>
          </div>
        {/if}
        <p class="admin-login-provider-runtime-hint">
          {at(
            "settings_login_runtime_hint",
            {},
            "Saved provider settings apply immediately; a backend restart is not required."
          )}
        </p>
      </div>
      <div class="admin-login-provider-help-actions">
        <a
          class="admin-btn admin-btn-sm admin-btn-ghost"
          href={loginProviderGuideUrl(provider)}
          target="_blank"
          rel="noreferrer noopener"
        >
          <FileText size={13} />
          <span>{at("settings_login_open_guide", {}, "Setup guide")}</span>
        </a>
        <a
          class="admin-btn admin-btn-sm admin-btn-ghost"
          href={loginProviderOfficialUrl(provider)}
          target="_blank"
          rel="noreferrer noopener"
        >
          <ExternalLink size={13} />
          <span>{at("settings_login_open_official", {}, "Official docs")}</span>
        </a>
      </div>
    </div>
  {/if}
{/snippet}

{#snippet renderLoginProviderValue(key: string, value: string)}
  <div class="admin-login-provider-value">
    <code>{value}</code>
    <AdminButton
      size="sm"
      variant="ghost"
      aria-label={at("copy", {}, "Copy")}
      onclick={() => copyLoginProviderValue(key, value)}
    >
      {#if copiedLoginProviderKey === key}
        <Check size={13} />{at("copied", {}, "Copied")}
      {:else}
        <Copy size={13} />{at("copy", {}, "Copy")}
      {/if}
    </AdminButton>
  </div>
{/snippet}

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
  {#if section.id === "notifications" && group.id === "notification_delivery"}
    <NotificationDeliveryMatrix
      {at}
      fields={section.fields}
      {settingsDirty}
      {valueFor}
      onValueChange={(key, value) => markFieldDirty(key, value)}
      {resetField}
      {isOverridden}
    />
  {:else if fieldGroups.length === 1 && !fieldGroups[0].titleKey}
    {#each fieldGroups[0].fields as field}
      {#if field.key !== "TORRENT_BLOCKER_TELEGRAM_NOTIFICATIONS_ENABLED" && field.key !== "TORRENT_BLOCKER_EMAIL_NOTIFICATIONS_ENABLED"}
        {@render renderField(field)}
      {/if}
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
              {#if field.key !== "TORRENT_BLOCKER_TELEGRAM_NOTIFICATIONS_ENABLED" && field.key !== "TORRENT_BLOCKER_EMAIL_NOTIFICATIONS_ENABLED"}
                {@render renderField(field)}
              {/if}
            {/each}
          </div>
        </section>
      {/each}
    </div>
  {/if}
{/snippet}

{#snippet renderField(field: AdminSettingField)}
  {@const revealed = isSecretRevealed(field.key)}
  {@const valueSource = fieldValueSourceLabel(field)}
  <div
    class="admin-setting"
    class:admin-setting--menu-buttons={field.type === "menu_buttons"}
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
      {#if valueSource}
        <small class="admin-setting-source">{valueSource}</small>
      {/if}
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
            >{valueFor(field) ? at("enabled", {}, "Enabled") : at("disabled", {}, "Disabled")}</span
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
      {:else if field.key === "PAYMENT_METHODS_ORDER" && field.payment_method_options?.length}
        <PaymentMethodsOrderField
          {at}
          value={fieldTextValue(field)}
          options={field.payment_method_options}
          onValueChange={(value) => markFieldDirty(field.key, value)}
        />
      {:else if field.type === "menu_buttons"}
        <MenuButtonsField
          {at}
          value={fieldTextValue(field)}
          languages={menuButtonLanguages}
          onValueChange={(value) => markFieldDirty(field.key, value)}
        />
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
          aria-label={revealed ? at("hide", {}, "Hide") : at("show", {}, "Show")}
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
          {at("reset", {}, "Reset")}
        </AdminButton>
      {/if}
    </div>
  </div>
{/snippet}

{#if settingsLoading || !visibleSettingsSections.length}
  <AdminEmptyState
    >{settingsLoading
      ? at("loading", {}, "Loading…")
      : at("no_data", {}, "No data")}</AdminEmptyState
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
              onpointerdown={(event) => handleSettingsSearchResultPointerDown(event, result)}
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
        "Changes in the admin panel take precedence over .env. The 'Reset' button returns the value from environment variables."
      )}
    </p>
    <div style="display:flex; gap:8px;">
      <AdminButton size="sm" variant="ghost" onclick={toggleAllSections}>
        {settingsAllOpen
          ? at("collapse_all", {}, "Collapse all")
          : at("expand_all", {}, "Expand all")}
      </AdminButton>
      {#if Object.keys(settingsDirty).length > 0 || extraDirtyCount > 0}
        <AdminButton size="sm" variant="primary" onclick={saveSettings} disabled={settingsSaving}>
          {settingsSaving ? at("saving", {}, "Saving...") : at("save", {}, "Save")}
        </AdminButton>
      {/if}
    </div>
  </div>
  <div class="admin-accordion">
    <ProgramSettingsSections
      {at}
      {settingsOpenSections}
      {toggleSettingsSection}
      {onNavigateSection}
    />
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
              {#if section.id === "login_methods"}
                {@render renderLoginMethodHints()}
              {/if}
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
                            {#if section.id === "login_methods"}
                              {@render renderLoginProviderHelp(group.id)}
                            {/if}
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

<style>
  .admin-setting--menu-buttons {
    grid-template-columns: 1fr;
  }

  .admin-setting--menu-buttons .admin-setting-control {
    width: 100%;
  }
</style>
