<script lang="ts">
  import { getSettingsStore, getTariffsStore } from "$lib/admin/context";
  import { Input } from "$components/ui/index.js";
  import { ChevronRight, X } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton, AdminSelect } from "$components/patterns/admin/index.js";
  import { Switch } from "$components/ui/primitives.js";
  import {
    REFERRAL_LINK_KEYS,
    REFERRAL_RULE_KEYS,
    REFERRAL_SETTING_KEYS,
    REFERRAL_WELCOME_KEYS,
    boolValue as resolveBoolValue,
    dirtyCount as resolveDirtyCount,
    inputValueForKey as resolveInputValueForKey,
    isSettingDirty as resolveIsSettingDirty,
    isLastEnabledReferralLink as resolveIsLastEnabledReferralLink,
    referralLinkResetViolatesRequirement as resolveReferralLinkResetViolatesRequirement,
    type SettingsDirtyState,
  } from "$lib/admin/tariffSettings";
  import type { SettingField } from "$lib/admin/stores/settingsStore";
  import type { Tariff } from "$lib/admin/stores/tariffsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at,
    settingsDirty = {},
    settingsFieldMap = new Map<string, SettingField>(),
    standalone = false,
  }: {
    at: TranslateFn;
    settingsDirty?: SettingsDirtyState;
    settingsFieldMap?: Map<string, SettingField>;
    /** Drop the disclosure chrome when the host screen already provides one. */
    standalone?: boolean;
  } = $props();

  const settingsStore = getSettingsStore();
  const tariffsStore = getTariffsStore();
  const tariffsState = $derived(tariffsStore);
  const tariffsCatalog = $derived(tariffsState.tariffsCatalog);
  const tariffsSaving = $derived(Boolean(tariffsState.tariffsSaving));
  const defaultTariff = $derived(
    (tariffsCatalog.tariffs || []).find(
      (tariff: Tariff) => tariff.key === tariffsCatalog.default_tariff
    )
  );
  const welcomeTariffUsesInvalidDefault = $derived(
    !tariffsCatalog.referral_welcome_bonus_tariff && defaultTariff?.billing_model !== "period"
  );
  const welcomeTariffOptions = $derived([
    {
      value: "",
      label: at(
        "tariffs_referral_welcome_bonus_tariff_default",
        { tariff: tariffLabel(defaultTariff) },
        "Default tariff ({tariff})"
      ),
      disabled: defaultTariff?.billing_model !== "period",
    },
    ...(tariffsCatalog.tariffs || [])
      .filter((tariff: Tariff) => tariff.enabled !== false && tariff.billing_model === "period")
      .map((tariff: Tariff) => ({ value: tariff.key, label: tariffLabel(tariff) })),
  ]);

  let referralSettingsOpen = $state(false);
  const referralDirtyCount = $derived(
    REFERRAL_SETTING_KEYS.filter((key) => Boolean(settingsDirty[key])).length
  );
  const referralEnabled = $derived(
    boolValue("REFERRAL_PROGRAM_ENABLED", settingsDirty, settingsFieldMap)
  );

  function tariffLabel(tariff: Tariff | undefined): string {
    return tariff?.names?.ru || tariff?.names?.en || tariff?.key || "—";
  }

  function boolValue(
    key: string,
    dirty: SettingsDirtyState = settingsDirty,
    fieldMap = settingsFieldMap
  ): boolean {
    return resolveBoolValue(key, dirty, fieldMap);
  }

  function inputValueForKey(key: string): string | number {
    return resolveInputValueForKey(key, settingsDirty, settingsFieldMap);
  }

  function isSettingDirty(key: string, dirty: SettingsDirtyState = settingsDirty): boolean {
    return resolveIsSettingDirty(key, dirty);
  }

  function dirtyCount(keys: readonly string[], dirty: SettingsDirtyState = settingsDirty): number {
    return resolveDirtyCount(keys, dirty);
  }

  function isLastEnabledReferralLink(key: (typeof REFERRAL_LINK_KEYS)[number]): boolean {
    return resolveIsLastEnabledReferralLink(key, settingsDirty, settingsFieldMap);
  }

  function referralLinkResetViolatesRequirement(key: (typeof REFERRAL_LINK_KEYS)[number]): boolean {
    return resolveReferralLinkResetViolatesRequirement(key, settingsDirty, settingsFieldMap);
  }

  function setSetting(key: string, value: unknown): void {
    if (!settingsFieldMap.has(key)) return;
    settingsStore.markDirty(key, value);
  }

  function settingInputHandler(key: string): (event: Event) => void {
    return (event: Event) => {
      const input = event.currentTarget as HTMLInputElement | HTMLTextAreaElement | null;
      setSetting(key, input?.value ?? "");
    };
  }

  function resetSetting(key: string): void {
    settingsStore.clearDirty(key);
  }

  async function setReferralWelcomeBonusTariff(value: string): Promise<void> {
    await tariffsStore.setReferralWelcomeBonusTariff(value || null);
  }
</script>

{#snippet referralBody()}
  <div class="admin-card-body admin-trial-settings-body">
    <div class="admin-settings-field-groups admin-trial-settings-groups">
      <section
        class="admin-settings-field-group"
        class:is-dirty={isSettingDirty("REFERRAL_PROGRAM_ENABLED", settingsDirty)}
      >
        <div class="admin-settings-field-group-body">
          <div
            class="admin-setting admin-trial-setting-row"
            class:is-dirty={isSettingDirty("REFERRAL_PROGRAM_ENABLED", settingsDirty)}
          >
            <div class="admin-setting-meta">
              <strong>
                {at("tariffs_referral_enabled", {}, "Referral program")}
                {#if isSettingDirty("REFERRAL_PROGRAM_ENABLED", settingsDirty)}
                  <AdminBadge variant="warning"
                    >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                  >
                {/if}
              </strong>
              <code>REFERRAL_PROGRAM_ENABLED</code>
              <small>
                {at(
                  "tariffs_referral_enabled_hint",
                  {},
                  "Disable referral links, attribution and bonuses while keeping promo codes available."
                )}
              </small>
            </div>
            <div class="admin-setting-control">
              <div class="admin-setting-switch">
                <Switch.Root
                  aria-label={at("tariffs_referral_enabled", {}, "Referral program")}
                  checked={referralEnabled}
                  onCheckedChange={(checked) => setSetting("REFERRAL_PROGRAM_ENABLED", checked)}
                  class="admin-switch-root"
                >
                  <Switch.Thumb class="admin-switch-thumb" />
                </Switch.Root>
                <span>
                  {referralEnabled ? at("enabled", {}, "Enabled") : at("disabled", {}, "Disabled")}
                </span>
              </div>
              {#if isSettingDirty("REFERRAL_PROGRAM_ENABLED", settingsDirty)}
                <AdminButton
                  size="sm"
                  variant="ghost"
                  onclick={() => resetSetting("REFERRAL_PROGRAM_ENABLED")}
                >
                  <X size={12} />
                  {at("reset", {}, "Reset")}
                </AdminButton>
              {/if}
            </div>
          </div>
        </div>
      </section>

      <section
        class="admin-settings-field-group"
        class:is-dirty={dirtyCount(REFERRAL_LINK_KEYS, settingsDirty)}
      >
        <header class="admin-settings-field-group-head">
          <div class="admin-settings-field-group-head-copy">
            <strong>{at("tariffs_referral_group_links", {}, "Referral links")}</strong>
            <small>
              {at(
                "tariffs_referral_group_links_hint",
                {},
                "Choose which links are shown in the user Web App bonus section."
              )}
            </small>
          </div>
          {#if dirtyCount(REFERRAL_LINK_KEYS, settingsDirty)}
            <AdminBadge variant="warning">
              {at(
                "settings_dirty_count",
                { count: dirtyCount(REFERRAL_LINK_KEYS, settingsDirty) },
                "Changes: {count}"
              )}
            </AdminBadge>
          {/if}
        </header>
        <div class="admin-settings-field-group-body">
          <div
            class="admin-setting admin-trial-setting-row"
            class:is-dirty={isSettingDirty("REFERRAL_WEBAPP_LINK_ENABLED", settingsDirty)}
          >
            <div class="admin-setting-meta">
              <strong>
                {at("tariffs_referral_webapp_link", {}, "Website referral link")}
                {#if isSettingDirty("REFERRAL_WEBAPP_LINK_ENABLED", settingsDirty)}
                  <AdminBadge variant="warning"
                    >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                  >
                {/if}
              </strong>
              <code>REFERRAL_WEBAPP_LINK_ENABLED</code>
              <small>
                {at(
                  "tariffs_referral_webapp_link_hint",
                  {},
                  "Show the website link in the user bonus section."
                )}
              </small>
            </div>
            <div class="admin-setting-control">
              <div class="admin-setting-switch">
                <Switch.Root
                  aria-label={at("tariffs_referral_webapp_link", {}, "Website referral link")}
                  checked={boolValue(
                    "REFERRAL_WEBAPP_LINK_ENABLED",
                    settingsDirty,
                    settingsFieldMap
                  )}
                  disabled={isLastEnabledReferralLink("REFERRAL_WEBAPP_LINK_ENABLED")}
                  onCheckedChange={(checked) => setSetting("REFERRAL_WEBAPP_LINK_ENABLED", checked)}
                  class="admin-switch-root"
                >
                  <Switch.Thumb class="admin-switch-thumb" />
                </Switch.Root>
                <span>
                  {boolValue("REFERRAL_WEBAPP_LINK_ENABLED", settingsDirty, settingsFieldMap)
                    ? at("enabled", {}, "Enabled")
                    : at("disabled", {}, "Disabled")}
                </span>
              </div>
              {#if isSettingDirty("REFERRAL_WEBAPP_LINK_ENABLED", settingsDirty)}
                <AdminButton
                  size="sm"
                  variant="ghost"
                  disabled={referralLinkResetViolatesRequirement("REFERRAL_WEBAPP_LINK_ENABLED")}
                  onclick={() => resetSetting("REFERRAL_WEBAPP_LINK_ENABLED")}
                >
                  <X size={12} />
                  {at("reset", {}, "Reset")}
                </AdminButton>
              {/if}
            </div>
          </div>

          <div
            class="admin-setting admin-trial-setting-row"
            class:is-dirty={isSettingDirty("REFERRAL_TELEGRAM_LINK_ENABLED", settingsDirty)}
          >
            <div class="admin-setting-meta">
              <strong>
                {at("tariffs_referral_telegram_link", {}, "Telegram referral link")}
                {#if isSettingDirty("REFERRAL_TELEGRAM_LINK_ENABLED", settingsDirty)}
                  <AdminBadge variant="warning"
                    >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                  >
                {/if}
              </strong>
              <code>REFERRAL_TELEGRAM_LINK_ENABLED</code>
              <small>
                {at(
                  "tariffs_referral_telegram_link_hint",
                  {},
                  "Show the Telegram bot link in the user bonus section."
                )}
              </small>
            </div>
            <div class="admin-setting-control">
              <div class="admin-setting-switch">
                <Switch.Root
                  aria-label={at("tariffs_referral_telegram_link", {}, "Telegram referral link")}
                  checked={boolValue(
                    "REFERRAL_TELEGRAM_LINK_ENABLED",
                    settingsDirty,
                    settingsFieldMap
                  )}
                  disabled={isLastEnabledReferralLink("REFERRAL_TELEGRAM_LINK_ENABLED")}
                  onCheckedChange={(checked) =>
                    setSetting("REFERRAL_TELEGRAM_LINK_ENABLED", checked)}
                  class="admin-switch-root"
                >
                  <Switch.Thumb class="admin-switch-thumb" />
                </Switch.Root>
                <span>
                  {boolValue("REFERRAL_TELEGRAM_LINK_ENABLED", settingsDirty, settingsFieldMap)
                    ? at("enabled", {}, "Enabled")
                    : at("disabled", {}, "Disabled")}
                </span>
              </div>
              {#if isSettingDirty("REFERRAL_TELEGRAM_LINK_ENABLED", settingsDirty)}
                <AdminButton
                  size="sm"
                  variant="ghost"
                  disabled={referralLinkResetViolatesRequirement("REFERRAL_TELEGRAM_LINK_ENABLED")}
                  onclick={() => resetSetting("REFERRAL_TELEGRAM_LINK_ENABLED")}
                >
                  <X size={12} />
                  {at("reset", {}, "Reset")}
                </AdminButton>
              {/if}
            </div>
          </div>
          <small class="admin-muted admin-settings-field-group-note">
            {at(
              "tariffs_referral_link_required_hint",
              {},
              "At least one referral link must remain enabled."
            )}
          </small>
        </div>
      </section>

      <section
        class="admin-settings-field-group"
        class:is-dirty={dirtyCount(REFERRAL_WELCOME_KEYS, settingsDirty)}
      >
        <header class="admin-settings-field-group-head">
          <div class="admin-settings-field-group-head-copy">
            <strong>{at("tariffs_referral_group_welcome", {}, "Welcome bonus")}</strong>
            <small>
              {at(
                "tariffs_referral_group_welcome_hint",
                {},
                "Days granted to an invited user after registration via referral link."
              )}
            </small>
          </div>
          {#if dirtyCount(REFERRAL_WELCOME_KEYS, settingsDirty)}
            <AdminBadge variant="warning">
              {at(
                "settings_dirty_count",
                { count: dirtyCount(REFERRAL_WELCOME_KEYS, settingsDirty) },
                "Changes: {count}"
              )}
            </AdminBadge>
          {/if}
        </header>
        <div class="admin-settings-field-group-body">
          <div
            class="admin-setting admin-trial-setting-row"
            class:is-dirty={isSettingDirty("REFERRAL_WELCOME_BONUS_DAYS", settingsDirty)}
          >
            <div class="admin-setting-meta">
              <strong>
                {at("tariffs_referral_welcome_bonus_days", {}, "Welcome bonus, days")}
                {#if isSettingDirty("REFERRAL_WELCOME_BONUS_DAYS", settingsDirty)}
                  <AdminBadge variant="warning"
                    >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                  >
                {/if}
              </strong>
              <code>REFERRAL_WELCOME_BONUS_DAYS</code>
            </div>
            <div class="admin-setting-control">
              <Input
                class="input"
                type="number"
                min="0"
                step="1"
                value={inputValueForKey("REFERRAL_WELCOME_BONUS_DAYS")}
                oninput={settingInputHandler("REFERRAL_WELCOME_BONUS_DAYS")}
              />
              {#if isSettingDirty("REFERRAL_WELCOME_BONUS_DAYS", settingsDirty)}
                <AdminButton
                  size="sm"
                  variant="ghost"
                  onclick={() => resetSetting("REFERRAL_WELCOME_BONUS_DAYS")}
                >
                  <X size={12} />
                  {at("reset", {}, "Reset")}
                </AdminButton>
              {/if}
            </div>
          </div>

          <div class="admin-setting admin-trial-setting-row">
            <div class="admin-setting-meta">
              <strong>
                {at("tariffs_referral_welcome_bonus_tariff", {}, "Welcome bonus tariff")}
              </strong>
              <code>referral_welcome_bonus_tariff</code>
              <small>
                {at(
                  "tariffs_referral_welcome_bonus_tariff_hint",
                  {},
                  "The selected period tariff supplies traffic limits, squads, reset strategy, and device limits."
                )}
              </small>
              {#if welcomeTariffUsesInvalidDefault}
                <small class="admin-muted">
                  {at(
                    "tariffs_referral_welcome_bonus_tariff_invalid_default",
                    {},
                    "The default tariff is not period-based. Select a period tariff to avoid an unbound bonus subscription."
                  )}
                </small>
              {/if}
            </div>
            <div class="admin-setting-control">
              <AdminSelect
                class="admin-setting-select"
                value={String(tariffsCatalog.referral_welcome_bonus_tariff || "")}
                items={welcomeTariffOptions}
                ariaLabel={at("tariffs_referral_welcome_bonus_tariff", {}, "Welcome bonus tariff")}
                disabled={tariffsSaving || welcomeTariffOptions.length <= 1}
                onValueChange={setReferralWelcomeBonusTariff}
              />
            </div>
          </div>
        </div>
      </section>

      <section
        class="admin-settings-field-group"
        class:is-dirty={dirtyCount(REFERRAL_RULE_KEYS, settingsDirty)}
      >
        <header class="admin-settings-field-group-head">
          <div class="admin-settings-field-group-head-copy">
            <strong>{at("tariffs_referral_group_rules", {}, "Payment bonus rules")}</strong>
            <small>
              {at(
                "tariffs_referral_group_rules_hint",
                {},
                "Control whether payment bonuses are limited to the invited user's first successful payment."
              )}
            </small>
          </div>
          {#if dirtyCount(REFERRAL_RULE_KEYS, settingsDirty)}
            <AdminBadge variant="warning">
              {at(
                "settings_dirty_count",
                { count: dirtyCount(REFERRAL_RULE_KEYS, settingsDirty) },
                "Changes: {count}"
              )}
            </AdminBadge>
          {/if}
        </header>
        <div class="admin-settings-field-group-body">
          <div
            class="admin-setting admin-trial-setting-row"
            class:is-dirty={isSettingDirty("REFERRAL_ONE_BONUS_PER_REFEREE", settingsDirty)}
          >
            <div class="admin-setting-meta">
              <strong>
                {at(
                  "tariffs_referral_one_bonus_per_referee",
                  {},
                  "Payment bonuses only on first invited-user payment"
                )}
                {#if isSettingDirty("REFERRAL_ONE_BONUS_PER_REFEREE", settingsDirty)}
                  <AdminBadge variant="warning"
                    >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                  >
                {/if}
              </strong>
              <code>REFERRAL_ONE_BONUS_PER_REFEREE</code>
              <small>
                {at(
                  "tariffs_referral_one_bonus_per_referee_hint",
                  {},
                  "When enabled, later purchases by the same invited user do not grant referral bonuses to either side. The first successful payment still grants bonuses."
                )}
              </small>
            </div>
            <div class="admin-setting-control">
              <div class="admin-setting-switch">
                <Switch.Root
                  aria-label={at(
                    "tariffs_referral_one_bonus_per_referee",
                    {},
                    "Payment bonuses only on first invited-user payment"
                  )}
                  checked={boolValue(
                    "REFERRAL_ONE_BONUS_PER_REFEREE",
                    settingsDirty,
                    settingsFieldMap
                  )}
                  onCheckedChange={(checked) =>
                    setSetting("REFERRAL_ONE_BONUS_PER_REFEREE", checked)}
                  class="admin-switch-root"
                >
                  <Switch.Thumb class="admin-switch-thumb" />
                </Switch.Root>
                <span
                  >{boolValue("REFERRAL_ONE_BONUS_PER_REFEREE", settingsDirty, settingsFieldMap)
                    ? at("enabled", {}, "Enabled")
                    : at("disabled", {}, "Disabled")}</span
                >
              </div>
              {#if isSettingDirty("REFERRAL_ONE_BONUS_PER_REFEREE", settingsDirty)}
                <AdminButton
                  size="sm"
                  variant="ghost"
                  onclick={() => resetSetting("REFERRAL_ONE_BONUS_PER_REFEREE")}
                >
                  <X size={12} />
                  {at("reset", {}, "Reset")}
                </AdminButton>
              {/if}
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
{/snippet}

<!-- Rendered bare inside the settings screen (that section already has a
     disclosure of its own) and as a self-contained disclosure elsewhere. -->
{#if standalone}
  <div class="admin-referral-standalone">{@render referralBody()}</div>
{:else}
  <div class="admin-accordion admin-tariff-settings-accordion">
    <section class="admin-accordion-item admin-card admin-tariff-settings-card">
      <div class="admin-accordion-header">
        <button
          type="button"
          class="admin-accordion-trigger"
          data-state={referralSettingsOpen ? "open" : "closed"}
          aria-expanded={referralSettingsOpen}
          aria-controls="admin-referral-settings-content"
          onclick={() => (referralSettingsOpen = !referralSettingsOpen)}
        >
          <span class="admin-accordion-title">
            {at("tariffs_referral_title", {}, "Referral program")}
          </span>
          <span class="admin-accordion-meta">
            {at(
              "tariffs_referral_subtitle",
              {},
              "Configure links, welcome bonus, and payment bonus rules."
            )}
            · {referralEnabled
              ? at("enabled", {}, "Enabled")
              : at("disabled", {}, "Disabled")}{#if referralDirtyCount}
              · {at("settings_dirty_count", { count: referralDirtyCount }, "Changes: {count}")}{/if}
          </span>
          <ChevronRight size={16} class="admin-accordion-chev" />
        </button>
      </div>
      {#if referralSettingsOpen}
        <div id="admin-referral-settings-content" class="admin-accordion-content" data-state="open">
          {@render referralBody()}
        </div>
      {/if}
    </section>
  </div>
{/if}
