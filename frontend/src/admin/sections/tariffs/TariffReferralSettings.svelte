<script lang="ts">
  import { getSettingsStore } from "$lib/admin/context";
  import { Input, Textarea } from "$components/ui/index.js";
  import { ChevronRight, Save, X } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";
  import { Switch } from "$components/ui/primitives.js";
  import {
    DISPOSABLE_EMAIL_DOMAINS_PLACEHOLDER,
    REFERRAL_RULE_KEYS,
    REFERRAL_SETTING_KEYS,
    REFERRAL_WELCOME_KEYS,
    boolValue as resolveBoolValue,
    dirtyCount as resolveDirtyCount,
    inputValueForKey as resolveInputValueForKey,
    isSettingDirty as resolveIsSettingDirty,
    textValueForKey as resolveTextValueForKey,
    valueForKey as resolveValueForKey,
    type SettingsDirtyState,
  } from "$lib/admin/tariffSettings";
  import type { SettingField, SettingsSavedPayload } from "$lib/admin/stores/settingsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at,
    settingsDirty = {},
    settingsFieldMap = new Map<string, SettingField>(),
    settingsSaving = false,
    onSettingsSaved = () => {},
  }: {
    at: TranslateFn;
    settingsDirty?: SettingsDirtyState;
    settingsFieldMap?: Map<string, SettingField>;
    settingsSaving?: boolean;
    onSettingsSaved?: (payload: SettingsSavedPayload) => void | Promise<void>;
  } = $props();

  const settingsStore = getSettingsStore();

  let referralSettingsOpen = $state(false);
  const referralDirtyCount = $derived(
    REFERRAL_SETTING_KEYS.filter((key) => Boolean(settingsDirty[key])).length
  );
  const referralEnabled = $derived(
    Number(valueForKey("REFERRAL_WELCOME_BONUS_DAYS", settingsDirty, settingsFieldMap) || 0) > 0
  );

  function valueForKey(
    key: string,
    dirty: SettingsDirtyState = settingsDirty,
    fieldMap = settingsFieldMap
  ): unknown {
    return resolveValueForKey(key, dirty, fieldMap);
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

  function textValueForKey(key: string): string {
    return resolveTextValueForKey(key, settingsDirty, settingsFieldMap);
  }

  function isSettingDirty(key: string, dirty: SettingsDirtyState = settingsDirty): boolean {
    return resolveIsSettingDirty(key, dirty);
  }

  function dirtyCount(keys: readonly string[], dirty: SettingsDirtyState = settingsDirty): number {
    return resolveDirtyCount(keys, dirty);
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

  async function saveTariffSettings(): Promise<void> {
    await settingsStore.saveSettings(onSettingsSaved);
  }
</script>

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
            "Configure welcome bonus, grant rules, and disposable email protection."
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
        <div class="admin-card-body admin-trial-settings-body">
          {#if referralDirtyCount}
            <div class="admin-editor-section-actions admin-tariff-settings-save-row">
              <AdminBadge variant="warning">
                {at("settings_dirty_count", { count: referralDirtyCount }, "Changes: {count}")}
              </AdminBadge>
              <AdminButton
                size="sm"
                variant="primary"
                onclick={saveTariffSettings}
                disabled={settingsSaving}
              >
                <Save size={13} />
                {settingsSaving ? at("btn_saving", {}, "Saving...") : at("btn_save", {}, "Save")}
              </AdminButton>
            </div>
          {/if}
          <div class="admin-settings-field-groups admin-trial-settings-groups">
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

                <div
                  class="admin-setting admin-trial-setting-row"
                  class:is-dirty={isSettingDirty(
                    "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
                    settingsDirty
                  )}
                >
                  <div class="admin-setting-meta">
                    <strong>
                      {at(
                        "tariffs_referral_without_telegram",
                        {},
                        "Grant welcome bonus without Telegram"
                      )}
                      {#if isSettingDirty("REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED", settingsDirty)}
                        <AdminBadge variant="warning"
                          >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                        >
                      {/if}
                    </strong>
                    <code>REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED</code>
                  </div>
                  <div class="admin-setting-control">
                    <div class="admin-setting-switch">
                      <Switch.Root
                        aria-label={at(
                          "tariffs_referral_without_telegram",
                          {},
                          "Grant welcome bonus without Telegram"
                        )}
                        checked={boolValue(
                          "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
                          settingsDirty,
                          settingsFieldMap
                        )}
                        onCheckedChange={(checked) =>
                          setSetting("REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED", checked)}
                        class="admin-switch-root"
                      >
                        <Switch.Thumb class="admin-switch-thumb" />
                      </Switch.Root>
                      <span
                        >{boolValue(
                          "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
                          settingsDirty,
                          settingsFieldMap
                        )
                          ? at("enabled", {}, "Enabled")
                          : at("disabled", {}, "Disabled")}</span
                      >
                    </div>
                    {#if isSettingDirty("REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED", settingsDirty)}
                      <AdminButton
                        size="sm"
                        variant="ghost"
                        onclick={() =>
                          resetSetting("REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED")}
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
              class:is-dirty={dirtyCount(REFERRAL_RULE_KEYS, settingsDirty)}
            >
              <header class="admin-settings-field-group-head">
                <div class="admin-settings-field-group-head-copy">
                  <strong>{at("tariffs_referral_group_rules", {}, "Rules and anti-abuse")}</strong>
                  <small>
                    {at(
                      "tariffs_referral_group_rules_hint",
                      {},
                      "Repeat-bonus limits and disposable email domains for no-Telegram accounts."
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
                        >{boolValue(
                          "REFERRAL_ONE_BONUS_PER_REFEREE",
                          settingsDirty,
                          settingsFieldMap
                        )
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

                <div
                  class="admin-setting admin-trial-setting-row"
                  class:is-dirty={isSettingDirty("DISPOSABLE_EMAIL_DOMAINS", settingsDirty)}
                >
                  <div class="admin-setting-meta">
                    <strong>
                      {at("tariffs_referral_disposable_domains", {}, "Disposable email domains")}
                      {#if isSettingDirty("DISPOSABLE_EMAIL_DOMAINS", settingsDirty)}
                        <AdminBadge variant="warning"
                          >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                        >
                      {/if}
                    </strong>
                    <code>DISPOSABLE_EMAIL_DOMAINS</code>
                    <small>
                      {at(
                        "tariffs_referral_disposable_domains_hint",
                        {},
                        "One domain per line or comma-separated. Subdomains are treated as matches too."
                      )}
                    </small>
                  </div>
                  <div class="admin-setting-control">
                    <Textarea
                      class="admin-setting-textarea"
                      rows={8}
                      placeholder={DISPOSABLE_EMAIL_DOMAINS_PLACEHOLDER}
                      value={textValueForKey("DISPOSABLE_EMAIL_DOMAINS")}
                      oninput={settingInputHandler("DISPOSABLE_EMAIL_DOMAINS")}
                    />
                    {#if isSettingDirty("DISPOSABLE_EMAIL_DOMAINS", settingsDirty)}
                      <AdminButton
                        size="sm"
                        variant="ghost"
                        onclick={() => resetSetting("DISPOSABLE_EMAIL_DOMAINS")}
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
      </div>
    {/if}
  </section>
</div>
