<script lang="ts">
  import "./partnerProgramSettings.css";
  import { ArrowRight, ShieldCheck, TriangleAlert } from "$components/ui/icons.js";
  import { Checkbox, Input } from "$components/ui/index.js";
  import { Switch } from "$components/ui/primitives.js";
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";
  import type { Snippet } from "svelte";
  import { getSettingsStore } from "$lib/admin/context.js";
  import type { SettingField, SettingsSection } from "$lib/admin/stores/settingsStore.js";
  import { valueForKey, type SettingsDirtyState } from "$lib/admin/tariffSettings.js";
  import PartnerClientBonusSettings from "./PartnerClientBonusSettings.svelte";
  import PartnerEncryptionDiagnostic from "./PartnerEncryptionDiagnostic.svelte";
  import PartnerSettingsDialogs from "./PartnerSettingsDialogs.svelte";
  import PartnerWithdrawalMethods from "./PartnerWithdrawalMethods.svelte";
  import {
    normalizeWithdrawalMethods,
    partnerSettingsScenario as initialSettingsScenario,
    previewWithdrawalMethods,
    type CryptoNetwork,
    type MethodType,
    type WithdrawalMethod,
  } from "./partnerProgramMethods";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  let {
    at,
    onNavigateSection = () => {},
  }: {
    at: TranslateFn;
    onNavigateSection?: (section: string) => void;
  } = $props();

  const settingsScenario = initialSettingsScenario();
  const previewMode = Boolean(settingsScenario);
  const settingsStore = getSettingsStore();
  const encryptionAvailable = $derived(
    previewMode ? settingsScenario !== "missing_key" : settingsStore.partnerEncryptionAvailable
  );
  const settingsSections: SettingsSection[] = settingsStore.settingsSections || [];
  const settingsFieldMap = new Map<string, SettingField>(
    settingsSections.flatMap((section) => section.fields || []).map((field) => [field.key, field])
  );
  const cleanSettings: SettingsDirtyState = {};

  function settingValue(key: string, fallback: unknown): unknown {
    if (previewMode || !settingsFieldMap.has(key)) return fallback;
    return valueForKey(key, cleanSettings, settingsFieldMap);
  }

  function settingBoolean(key: string, fallback: boolean): boolean {
    const value = settingValue(key, fallback);
    if (typeof value === "string") {
      return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
    }
    return Boolean(value);
  }

  function settingNumber(key: string, fallback: number): number {
    const value = Number(settingValue(key, fallback));
    return Number.isFinite(value) ? value : fallback;
  }

  function settingArray(key: string, fallback: unknown[]): unknown[] {
    const value = settingValue(key, fallback);
    if (Array.isArray(value)) return value;
    try {
      const parsed = JSON.parse(String(value || "[]"));
      return Array.isArray(parsed) ? parsed : fallback;
    } catch {
      return fallback;
    }
  }

  let config = $state({
    enabled: previewMode
      ? settingsScenario === "program_on" || settingsScenario === "dirty"
      : settingBoolean("PARTNER_PROGRAM_ENABLED", false),
    autoEnrollment: settingBoolean("PARTNER_AUTO_ENROLLMENT_ENABLED", false),
    referralProgramDisabled: settingBoolean("PARTNER_REFERRAL_PROGRAM_DISABLED", false),
    withdrawalsEnabled: settingBoolean("PARTNER_WITHDRAWALS_ENABLED", true),
    balancePaymentEnabled: settingBoolean("PARTNER_BALANCE_PAYMENT_ENABLED", true),
    clientWelcomeBonusEnabled: settingBoolean("PARTNER_CLIENT_WELCOME_BONUS_ENABLED", false),
    clientPaymentBonusEnabled: settingBoolean("PARTNER_CLIENT_PAYMENT_BONUS_ENABLED", false),
    oneBonusPerClient: settingBoolean("PARTNER_ONE_BONUS_PER_CLIENT", true),
    defaultRate: settingNumber("PARTNER_DEFAULT_COMMISSION_BPS", 3000) / 100,
    holdDays: settingNumber("PARTNER_COMMISSION_HOLD_DAYS", 0),
    telegramLinks: previewMode
      ? settingsScenario !== "invalid_links"
      : settingBoolean("PARTNER_TELEGRAM_LINK_ENABLED", true),
    webLinks: previewMode
      ? settingsScenario !== "invalid_links"
      : settingBoolean("PARTNER_WEBAPP_LINK_ENABLED", true),
    reapplication: settingBoolean("PARTNER_REAPPLICATION_ENABLED", false),
    reapplicationCooldown: settingNumber("PARTNER_REAPPLICATION_COOLDOWN_DAYS", 0),
    applicationMax: settingNumber("PARTNER_APPLICATION_MESSAGE_MAX_LENGTH", 2000),
    maxWithdrawals: settingNumber("PARTNER_MAX_ACTIVE_WITHDRAWALS", 3),
    listPageLimit: settingNumber("PARTNER_LIST_PAGE_LIMIT", 50),
    applicationRateLimitHours: settingNumber("PARTNER_APPLICATION_RATE_LIMIT_HOURS", 24),
    withdrawalRateLimitSeconds: settingNumber("PARTNER_WITHDRAWAL_RATE_LIMIT_SECONDS", 10),
    auditRetentionDays: settingNumber("PARTNER_AUDIT_RETENTION_DAYS", 0),
    requisitesRetentionDays: settingNumber("PARTNER_REQUISITES_RETENTION_DAYS", 90),
    eligibleCurrencies: settingArray("PARTNER_ELIGIBLE_CURRENCIES", ["RUB"]).map(String),
    excludedSaleModes: settingArray("PARTNER_EXCLUDED_SALE_MODES", []).map(String),
  });
  const configuredMethods = normalizeWithdrawalMethods(
    settingArray("PARTNER_WITHDRAWAL_METHODS_JSON", [])
  );
  let methods = $state<WithdrawalMethod[]>(
    settingsScenario === "empty_methods"
      ? []
      : !previewMode
        ? configuredMethods
        : previewWithdrawalMethods(settingsScenario)
  );
  let methodEditor = $state<number | null>(null);
  let pendingToggle = $state<"enabled" | "withdrawalsEnabled" | "balancePaymentEnabled" | "">("");
  let autoEnrollmentConfirmation = $state(false);

  const linksValid = $derived(config.telegramLinks || config.webLinks);
  const duplicateMethodIds = $derived(
    methods
      .filter(
        (method, index) =>
          methods.findIndex(
            (item) => item.id.trim().toLowerCase() === method.id.trim().toLowerCase()
          ) !== index
      )
      .map((method) => method.id)
  );
  const cryptoInvalid = $derived(methods.some((method) => networkConfigurationInvalid(method)));
  const enabledMethods = $derived(methods.filter((method) => method.enabled));
  function settingsPayload(): Record<string, unknown> {
    return {
      PARTNER_PROGRAM_ENABLED: config.enabled,
      PARTNER_AUTO_ENROLLMENT_ENABLED: config.autoEnrollment,
      PARTNER_REFERRAL_PROGRAM_DISABLED: config.referralProgramDisabled,
      PARTNER_WITHDRAWALS_ENABLED: config.withdrawalsEnabled,
      PARTNER_BALANCE_PAYMENT_ENABLED: config.balancePaymentEnabled,
      PARTNER_CLIENT_WELCOME_BONUS_ENABLED: config.clientWelcomeBonusEnabled,
      PARTNER_CLIENT_PAYMENT_BONUS_ENABLED: config.clientPaymentBonusEnabled,
      PARTNER_ONE_BONUS_PER_CLIENT: config.oneBonusPerClient,
      PARTNER_DEFAULT_COMMISSION_BPS: Math.round(config.defaultRate * 100),
      PARTNER_COMMISSION_HOLD_DAYS: Math.round(config.holdDays),
      PARTNER_ELIGIBLE_CURRENCIES: JSON.stringify(config.eligibleCurrencies),
      PARTNER_EXCLUDED_SALE_MODES: JSON.stringify(config.excludedSaleModes),
      PARTNER_TELEGRAM_LINK_ENABLED: config.telegramLinks,
      PARTNER_WEBAPP_LINK_ENABLED: config.webLinks,
      PARTNER_APPLICATION_MESSAGE_MAX_LENGTH: Math.round(config.applicationMax),
      PARTNER_MAX_ACTIVE_WITHDRAWALS: Math.round(config.maxWithdrawals),
      PARTNER_REAPPLICATION_ENABLED: config.reapplication,
      PARTNER_REAPPLICATION_COOLDOWN_DAYS: Math.round(config.reapplicationCooldown),
      PARTNER_LIST_PAGE_LIMIT: Math.round(config.listPageLimit),
      PARTNER_APPLICATION_RATE_LIMIT_HOURS: Math.round(config.applicationRateLimitHours),
      PARTNER_WITHDRAWAL_RATE_LIMIT_SECONDS: Math.round(config.withdrawalRateLimitSeconds),
      PARTNER_AUDIT_RETENTION_DAYS: Math.round(config.auditRetentionDays),
      PARTNER_REQUISITES_RETENTION_DAYS: Math.round(config.requisitesRetentionDays),
      PARTNER_WITHDRAWAL_METHODS_JSON: JSON.stringify(
        methods.map((method, index) => {
          const scale = Math.max(0, Math.min(8, Math.round(method.scale)));
          const fieldId =
            method.type === "crypto" ? "address" : method.type === "sbp" ? "phone" : "card_number";
          return {
            id: method.id.trim(),
            type: method.type,
            enabled: method.enabled,
            label: method.label.trim(),
            debit_currency: method.currency.trim().toUpperCase(),
            currency_scale: scale,
            min_amount_minor: Math.round(method.minimum * 10 ** scale),
            max_amount_minor:
              method.maximum == null ? null : Math.round(method.maximum * 10 ** scale),
            fields: [{ id: fieldId, label: "", required: true, placeholder: "" }],
            settlement_asset: method.type === "crypto" ? method.label.trim() || "USDT" : null,
            networks: method.networks.map((network) => ({
              id: network.id.trim().toLowerCase(),
              label: network.label.trim(),
            })),
            sort_order: index,
            help_text: "",
          };
        })
      ),
    };
  }

  let lastSettingsSnapshot = "";
  $effect(() => {
    if (previewMode) return;
    const payload = settingsPayload();
    const snapshot = JSON.stringify(payload);
    if (!lastSettingsSnapshot) {
      lastSettingsSnapshot = snapshot;
      return;
    }
    if (snapshot === lastSettingsSnapshot) return;
    lastSettingsSnapshot = snapshot;
    for (const [key, value] of Object.entries(payload)) settingsStore.markDirty(key, value);
  });

  function requestToggle(key: "enabled" | "withdrawalsEnabled" | "balancePaymentEnabled"): void {
    if (config[key]) pendingToggle = key;
    else config[key] = true;
  }

  function confirmToggle(): void {
    if (!pendingToggle) return;
    config[pendingToggle] = false;
    pendingToggle = "";
  }

  function requestAutoEnrollment(checked: boolean): void {
    if (checked && !config.autoEnrollment) {
      autoEnrollmentConfirmation = true;
      return;
    }
    config.autoEnrollment = false;
  }

  function confirmAutoEnrollment(): void {
    config.enabled = true;
    config.autoEnrollment = true;
    autoEnrollmentConfirmation = false;
  }

  function setLinkChannel(channel: "telegramLinks" | "webLinks", enabled: boolean): void {
    config[channel] = enabled;
  }

  function toggleCurrency(currency: string): void {
    config.eligibleCurrencies = config.eligibleCurrencies.includes(currency)
      ? config.eligibleCurrencies.filter((item) => item !== currency)
      : [...config.eligibleCurrencies, currency];
  }

  function toggleExcludedMode(mode: string): void {
    config.excludedSaleModes = config.excludedSaleModes.includes(mode)
      ? config.excludedSaleModes.filter((item) => item !== mode)
      : [...config.excludedSaleModes, mode];
  }

  function addMethod(type: MethodType): void {
    const index = methods.length + 1;
    methods = [
      ...methods,
      {
        id: `${type.replace("bank_", "")}-${index}`,
        type,
        enabled: false,
        label: "",
        currency: "RUB",
        scale: 2,
        minimum: type === "crypto" ? 3000 : 500,
        maximum: null,
        networks: [],
      },
    ];
    methodEditor = methods.length - 1;
  }

  function duplicateMethod(index: number): void {
    const source = methods[index];
    const copy: WithdrawalMethod = {
      ...source,
      id: `${source.id}-copy`,
      label: source.label ? `${source.label} copy` : "",
      enabled: false,
      networks: source.networks.map((network) => ({ ...network })),
    };
    methods = [...methods.slice(0, index + 1), copy, ...methods.slice(index + 1)];
    methodEditor = index + 1;
  }

  function deleteMethod(index: number): void {
    methods = methods.filter((_, itemIndex) => itemIndex !== index);
    methodEditor = null;
  }

  function moveMethod(index: number, offset: -1 | 1): void {
    const target = index + offset;
    if (target < 0 || target >= methods.length) return;
    const next = [...methods];
    [next[index], next[target]] = [next[target], next[index]];
    methods = next;
    methodEditor = target;
  }

  function updateMethod(index: number, updates: Partial<WithdrawalMethod>): void {
    methods = methods.map((method, itemIndex) =>
      itemIndex === index ? { ...method, ...updates } : method
    );
  }

  function addNetwork(index: number): void {
    const method = methods[index];
    const sequence = method.networks.length + 1;
    updateMethod(index, {
      networks: [...method.networks, { id: `network-${sequence}`, label: "" }],
    });
  }

  function updateNetwork(
    methodIndex: number,
    networkIndex: number,
    updates: Partial<CryptoNetwork>
  ): void {
    const method = methods[methodIndex];
    updateMethod(methodIndex, {
      networks: method.networks.map((network, index) =>
        index === networkIndex ? { ...network, ...updates } : network
      ),
    });
  }

  function removeNetwork(methodIndex: number, networkIndex: number): void {
    const method = methods[methodIndex];
    updateMethod(methodIndex, {
      networks: method.networks.filter((_, index) => index !== networkIndex),
    });
  }

  function networkConfigurationInvalid(method: WithdrawalMethod): boolean {
    if (method.type !== "crypto" || !method.enabled) return false;
    if (!method.networks.length) return true;
    const normalizedIds = method.networks.map((network) => network.id.trim().toLowerCase());
    return method.networks.some(
      (network, index) =>
        !network.id.trim() ||
        !network.label.trim() ||
        normalizedIds.indexOf(normalizedIds[index]) !== index
    );
  }

  function methodTitle(method: WithdrawalMethod): string {
    return method.label || at(`partner_settings_method_${method.type}`, {}, method.type);
  }

  function switchStateLabel(checked: boolean): string {
    return checked ? at("enabled", {}, "Enabled") : at("disabled", {}, "Disabled");
  }
</script>

<!-- The section reuses the settings screen's own field-group / setting-row
     structure, so a program section reads exactly like every other settings
     section: label + env key on the left, control on the right. -->
{#snippet settingRow(label: string, envKey: string, control: Snippet)}
  <div class="admin-setting">
    <div class="admin-setting-meta">
      <strong>{label}</strong>
      {#if envKey}<code>{envKey}</code>{/if}
    </div>
    <div class="admin-setting-control">{@render control()}</div>
  </div>
{/snippet}

{#snippet switchControl(checked: boolean, label: string, onChange: (next: boolean) => void)}
  <div class="admin-setting-switch">
    <Switch.Root {checked} aria-label={label} onCheckedChange={onChange} class="admin-switch-root">
      <Switch.Thumb class="admin-switch-thumb" />
    </Switch.Root>
    <span>{switchStateLabel(checked)}</span>
  </div>
{/snippet}

<div class="admin-settings-field-groups partner-settings-page">
  <section class="admin-settings-field-group">
    <header class="admin-settings-field-group-head">
      <strong>{at("partner_settings_state_title", {}, "Program state")}</strong>
      <small>
        {at(
          "partner_settings_state_hint",
          {},
          "Global switches stop new actions without hiding history or obligations."
        )}
      </small>
    </header>
    <div class="admin-settings-field-group-body">
      {#snippet enabledControl()}
        {@render switchControl(
          config.enabled,
          at("partner_settings_enabled", {}, "Partner program enabled"),
          () => requestToggle("enabled")
        )}
      {/snippet}
      {@render settingRow(
        at("partner_settings_enabled", {}, "Partner program enabled"),
        "PARTNER_PROGRAM_ENABLED",
        enabledControl
      )}

      <div class="admin-setting">
        <div class="admin-setting-meta">
          <strong>
            {at("partner_settings_auto_enrollment", {}, "Automatic enrollment for all users")}
          </strong>
          <code>PARTNER_AUTO_ENROLLMENT_ENABLED</code>
          <small>
            {at(
              "partner_settings_auto_enrollment_hint",
              {},
              "Creates active profiles without applications. Paused and closed profiles keep their status."
            )}
          </small>
        </div>
        <div class="admin-setting-control">
          {@render switchControl(
            config.autoEnrollment,
            at("partner_settings_auto_enrollment", {}, "Automatic enrollment for all users"),
            requestAutoEnrollment
          )}
        </div>
      </div>

      {#snippet withdrawalsControl()}
        {@render switchControl(
          config.withdrawalsEnabled,
          at("partner_settings_withdrawals_enabled", {}, "Withdrawal requests enabled"),
          () => requestToggle("withdrawalsEnabled")
        )}
      {/snippet}
      {@render settingRow(
        at("partner_settings_withdrawals_enabled", {}, "Withdrawal requests enabled"),
        "PARTNER_WITHDRAWALS_ENABLED",
        withdrawalsControl
      )}

      {#snippet balancePaymentControl()}
        {@render switchControl(
          config.balancePaymentEnabled,
          at("partner_settings_balance_payment_enabled", {}, "Subscription renewal from balance"),
          () => requestToggle("balancePaymentEnabled")
        )}
      {/snippet}
      {@render settingRow(
        at("partner_settings_balance_payment_enabled", {}, "Subscription renewal from balance"),
        "PARTNER_BALANCE_PAYMENT_ENABLED",
        balancePaymentControl
      )}
    </div>
  </section>

  <PartnerClientBonusSettings
    {at}
    welcomeEnabled={config.clientWelcomeBonusEnabled}
    paymentEnabled={config.clientPaymentBonusEnabled}
    oneBonusPerClient={config.oneBonusPerClient}
    onWelcomeChange={(checked) => (config.clientWelcomeBonusEnabled = checked)}
    onPaymentChange={(checked) => (config.clientPaymentBonusEnabled = checked)}
    onOneBonusPerClientChange={(checked) => (config.oneBonusPerClient = checked)}
  />

  <section class="admin-settings-field-group">
    <header class="admin-settings-field-group-head">
      <strong>{at("partner_settings_limits_title", {}, "Operational limits")}</strong>
      <small>
        {at(
          "partner_settings_limits_hint",
          {},
          "Rate limits, pagination, and retention are enforced by the server."
        )}
      </small>
    </header>
    <div class="admin-settings-field-group-body">
      {#snippet reapplicationCooldownControl()}
        <Input
          class="input"
          type="number"
          min="0"
          max="3650"
          value={config.reapplicationCooldown}
          oninput={(event) => (config.reapplicationCooldown = Number(event.currentTarget.value))}
        />
      {/snippet}
      {@render settingRow(
        at("partner_settings_reapplication_cooldown", {}, "Reapplication cooldown (days)"),
        "PARTNER_REAPPLICATION_COOLDOWN_DAYS",
        reapplicationCooldownControl
      )}

      {#snippet listPageLimitControl()}
        <Input
          class="input"
          type="number"
          min="10"
          max="200"
          value={config.listPageLimit}
          oninput={(event) => (config.listPageLimit = Number(event.currentTarget.value))}
        />
      {/snippet}
      {@render settingRow(
        at("partner_settings_list_limit", {}, "Rows per list request"),
        "PARTNER_LIST_PAGE_LIMIT",
        listPageLimitControl
      )}

      {#snippet applicationRateControl()}
        <Input
          class="input"
          type="number"
          min="1"
          max="8760"
          value={config.applicationRateLimitHours}
          oninput={(event) =>
            (config.applicationRateLimitHours = Number(event.currentTarget.value))}
        />
      {/snippet}
      {@render settingRow(
        at("partner_settings_application_rate", {}, "Application rate limit (hours)"),
        "PARTNER_APPLICATION_RATE_LIMIT_HOURS",
        applicationRateControl
      )}

      {#snippet withdrawalRateControl()}
        <Input
          class="input"
          type="number"
          min="1"
          max="3600"
          value={config.withdrawalRateLimitSeconds}
          oninput={(event) =>
            (config.withdrawalRateLimitSeconds = Number(event.currentTarget.value))}
        />
      {/snippet}
      {@render settingRow(
        at("partner_settings_withdrawal_rate", {}, "Withdrawal rate limit (seconds)"),
        "PARTNER_WITHDRAWAL_RATE_LIMIT_SECONDS",
        withdrawalRateControl
      )}

      {#snippet auditRetentionControl()}
        <Input
          class="input"
          type="number"
          min="0"
          max="3650"
          value={config.auditRetentionDays}
          oninput={(event) => (config.auditRetentionDays = Number(event.currentTarget.value))}
        />
      {/snippet}
      {@render settingRow(
        at("partner_settings_audit_retention", {}, "Audit retention (days, 0 = forever)"),
        "PARTNER_AUDIT_RETENTION_DAYS",
        auditRetentionControl
      )}

      {#snippet requisitesRetentionControl()}
        <Input
          class="input"
          type="number"
          min="1"
          max="3650"
          value={config.requisitesRetentionDays}
          oninput={(event) => (config.requisitesRetentionDays = Number(event.currentTarget.value))}
        />
      {/snippet}
      {@render settingRow(
        at("partner_settings_requisites_retention", {}, "Requisites retention (days)"),
        "PARTNER_REQUISITES_RETENTION_DAYS",
        requisitesRetentionControl
      )}
    </div>
  </section>

  <section class="admin-settings-field-group">
    <header class="admin-settings-field-group-head">
      <strong>{at("partner_settings_commission_title", {}, "Commissions")}</strong>
      <small>
        {at(
          "partner_settings_commission_hint",
          {},
          "The rate is snapshotted when each payment succeeds."
        )}
      </small>
    </header>
    <div class="admin-settings-field-group-body">
      {#snippet rateControl()}
        <Input
          class="input"
          type="number"
          min="0"
          max="100"
          step="0.01"
          value={config.defaultRate}
          oninput={(event) => (config.defaultRate = Number(event.currentTarget.value))}
        />
      {/snippet}
      {@render settingRow(
        at("partner_settings_default_rate", {}, "Default commission, %"),
        "PARTNER_DEFAULT_COMMISSION_BPS",
        rateControl
      )}

      {#snippet holdControl()}
        <Input
          class="input"
          type="number"
          min="0"
          step="1"
          value={config.holdDays}
          oninput={(event) => (config.holdDays = Number(event.currentTarget.value))}
        />
      {/snippet}
      {@render settingRow(
        at("partner_settings_hold_days", {}, "Commission hold, days"),
        "PARTNER_COMMISSION_HOLD_DAYS",
        holdControl
      )}
    </div>
    {#if config.defaultRate === 0 || config.defaultRate >= 70}
      <div class="partner-settings-warning">
        <TriangleAlert size={16} />{at(
          "partner_settings_rate_warning",
          {},
          "Confirm that this unusual rate is intentional."
        )}
      </div>
    {/if}
  </section>

  <section class="admin-settings-field-group">
    <header class="admin-settings-field-group-head">
      <strong>{at("partner_settings_attribution_title", {}, "Attribution and links")}</strong>
      <small>
        {at(
          "partner_settings_attribution_hint",
          {},
          "At least one partner link channel must remain available."
        )}
      </small>
    </header>
    <div class="admin-settings-field-group-body">
      {#snippet referralProgramControl()}
        {@render switchControl(
          config.referralProgramDisabled,
          at(
            "partner_settings_referral_program_disabled",
            {},
            "Disable referral program for partners"
          ),
          (checked) => (config.referralProgramDisabled = checked)
        )}
      {/snippet}
      {@render settingRow(
        at(
          "partner_settings_referral_program_disabled",
          {},
          "Disable referral program for partners"
        ),
        "PARTNER_REFERRAL_PROGRAM_DISABLED",
        referralProgramControl
      )}

      {#snippet telegramLinksControl()}
        {@render switchControl(
          config.telegramLinks,
          at("partner_settings_telegram_links", {}, "Telegram partner links"),
          (checked) => setLinkChannel("telegramLinks", checked)
        )}
      {/snippet}
      {@render settingRow(
        at("partner_settings_telegram_links", {}, "Telegram partner links"),
        "PARTNER_TELEGRAM_LINK_ENABLED",
        telegramLinksControl
      )}

      {#snippet webLinksControl()}
        {@render switchControl(
          config.webLinks,
          at("partner_settings_web_links", {}, "Web partner links"),
          (checked) => setLinkChannel("webLinks", checked)
        )}
      {/snippet}
      {@render settingRow(
        at("partner_settings_web_links", {}, "Web partner links"),
        "PARTNER_WEBAPP_LINK_ENABLED",
        webLinksControl
      )}
    </div>
    {#if !linksValid}
      <div class="partner-settings-error">
        <TriangleAlert size={16} />{at(
          "partner_settings_links_error",
          {},
          "Enable at least one partner link channel."
        )}
      </div>
    {/if}
  </section>

  <section class="admin-settings-field-group">
    <header class="admin-settings-field-group-head">
      <strong>{at("partner_settings_applications_title", {}, "Applications")}</strong>
      <small>
        {at(
          config.autoEnrollment
            ? "partner_settings_applications_auto_hint"
            : "partner_settings_applications_hint",
          {},
          config.autoEnrollment
            ? "Automatic enrollment is active; these limits are preserved for manual mode."
            : "Conservative defaults reduce repeated submissions and queue abuse."
        )}
      </small>
    </header>
    <div class="admin-settings-field-group-body">
      {#snippet applicationMaxControl()}
        <Input
          class="input"
          type="number"
          min="10"
          max="10000"
          value={config.applicationMax}
          oninput={(event) => (config.applicationMax = Number(event.currentTarget.value))}
        />
      {/snippet}
      {@render settingRow(
        at("partner_settings_application_length", {}, "Message limit"),
        "PARTNER_APPLICATION_MESSAGE_MAX_LENGTH",
        applicationMaxControl
      )}

      {#snippet maxWithdrawalsControl()}
        <Input
          class="input"
          type="number"
          min="1"
          max="20"
          value={config.maxWithdrawals}
          oninput={(event) => (config.maxWithdrawals = Number(event.currentTarget.value))}
        />
      {/snippet}
      {@render settingRow(
        at("partner_settings_max_withdrawals", {}, "Maximum active withdrawals"),
        "PARTNER_MAX_ACTIVE_WITHDRAWALS",
        maxWithdrawalsControl
      )}

      {#snippet reapplicationControl()}
        <label class="partner-settings-check">
          <Checkbox
            checked={config.reapplication}
            ariaLabel={at(
              "partner_settings_reapplication",
              {},
              "Allow reapplication after rejection"
            )}
            onCheckedChange={(checked) => (config.reapplication = checked)}
          />
          <span>{switchStateLabel(config.reapplication)}</span>
        </label>
      {/snippet}
      {@render settingRow(
        at("partner_settings_reapplication", {}, "Allow reapplication after rejection"),
        "PARTNER_REAPPLICATION_ENABLED",
        reapplicationControl
      )}
    </div>
  </section>

  <section class="admin-settings-field-group">
    <header class="admin-settings-field-group-head">
      <strong>{at("partner_settings_eligible_title", {}, "Eligible payments")}</strong>
      <small>
        {at(
          "partner_settings_eligible_hint",
          {},
          "Currencies stay separate; excluded sale modes create explicit decisions."
        )}
      </small>
    </header>
    <div class="admin-settings-field-group-body">
      {#snippet currenciesControl()}
        <div
          class="partner-settings-chips"
          role="group"
          aria-label={at("partner_settings_currencies", {}, "Currencies")}
        >
          {#each ["RUB", "USD", "EUR", "USDT"] as item (item)}
            <button
              type="button"
              class:active={config.eligibleCurrencies.includes(item)}
              aria-pressed={config.eligibleCurrencies.includes(item)}
              onclick={() => toggleCurrency(item)}>{item}</button
            >
          {/each}
        </div>
      {/snippet}
      {@render settingRow(
        at("partner_settings_currencies", {}, "Currencies"),
        "PARTNER_ELIGIBLE_CURRENCIES",
        currenciesControl
      )}

      {#snippet modesControl()}
        <div
          class="partner-settings-chips"
          role="group"
          aria-label={at("partner_settings_excluded_modes", {}, "Excluded sale modes")}
        >
          {#each ["traffic", "hwid", "upgrade", "auto_renew"] as item (item)}
            <button
              type="button"
              class:active={config.excludedSaleModes.includes(item)}
              aria-pressed={config.excludedSaleModes.includes(item)}
              onclick={() => toggleExcludedMode(item)}
              >{at(`partner_settings_mode_${item}`, {}, item)}</button
            >
          {/each}
        </div>
      {/snippet}
      {@render settingRow(
        at("partner_settings_excluded_modes", {}, "Excluded sale modes"),
        "PARTNER_EXCLUDED_SALE_MODES",
        modesControl
      )}
    </div>
  </section>

  <PartnerWithdrawalMethods
    {at}
    {methods}
    bind:methodEditor
    {duplicateMethodIds}
    {cryptoInvalid}
    {addMethod}
    {moveMethod}
    {duplicateMethod}
    {deleteMethod}
    {updateMethod}
    {addNetwork}
    {updateNetwork}
    {removeNetwork}
    {networkConfigurationInvalid}
    {methodTitle}
    {switchStateLabel}
  />

  <section class="admin-settings-field-group">
    <header class="admin-settings-field-group-head">
      <strong>{at("partner_settings_security_title", {}, "Security and diagnostics")}</strong>
      <small>
        {at(
          "partner_settings_security_hint",
          {},
          "Payout requisites are stored encrypted; the key is read only from the secret environment."
        )}
      </small>
    </header>
    <div class="partner-diagnostics">
      <PartnerEncryptionDiagnostic {at} {encryptionAvailable} />
      <div class={enabledMethods.length ? "success" : "warning"}>
        <ShieldCheck size={18} />
        <span>
          <strong>{at("partner_settings_methods_diagnostic", {}, "Payout coverage")}</strong>
          <small>
            {enabledMethods.length
              ? at(
                  "partner_settings_methods_ready",
                  { count: enabledMethods.length },
                  "{count} methods enabled"
                )
              : at("partner_settings_methods_not_ready", {}, "No methods enabled")}
          </small>
        </span>
        <AdminBadge variant={enabledMethods.length ? "success" : "warning"}>
          {enabledMethods.length
            ? at("partner_settings_ready", {}, "Ready")
            : at("partner_settings_warning", {}, "Warning")}
        </AdminBadge>
      </div>
    </div>
  </section>

  <div class="partner-settings-footnote">
    <span>
      {at(
        "partner_settings_operations_hint",
        {},
        "Applications, balances, and the payout queue live in the partner program section."
      )}
    </span>
    <AdminButton onclick={() => onNavigateSection("partners")}>
      {at("partner_settings_open_operations", {}, "Open partners")}<ArrowRight size={15} />
    </AdminButton>
  </div>
</div>

<PartnerSettingsDialogs
  {at}
  {pendingToggle}
  {autoEnrollmentConfirmation}
  oncloseToggle={() => (pendingToggle = "")}
  onconfirmToggle={confirmToggle}
  oncloseAutoEnrollment={() => (autoEnrollmentConfirmation = false)}
  onconfirmAutoEnrollment={confirmAutoEnrollment}
/>
