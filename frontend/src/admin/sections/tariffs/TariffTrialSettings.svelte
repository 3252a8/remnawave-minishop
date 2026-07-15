<script lang="ts">
  import { getSettingsStore, getTariffsStore } from "$lib/admin/context";
  import { Input } from "$components/ui/index.js";
  import { ChevronRight, Save, X } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton, AdminSelect } from "$components/patterns/admin/index.js";
  import { Switch } from "$components/ui/primitives.js";
  import {
    TRIAL_GENERAL_KEYS,
    TRIAL_RESET_KEYS,
    TRIAL_SETTING_KEYS,
    TRIAL_SQUAD_KEYS,
    TRIAL_SWITCH_KEYS,
    boolValue as resolveBoolValue,
    csvList as resolveCsvList,
    dirtyCount as resolveDirtyCount,
    inputValueForKey as resolveInputValueForKey,
    isSettingDirty as resolveIsSettingDirty,
    valueForKey as resolveValueForKey,
    trafficStrategyOptions as buildTrafficStrategyOptions,
    type SelectOption,
    type SettingsDirtyState,
  } from "$lib/admin/tariffSettings";
  import type { SettingField, SettingsSavedPayload } from "$lib/admin/stores/settingsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at,
    settingsDirty = {},
    settingsFieldMap = new Map<string, SettingField>(),
    settingsSaving = false,
    panelSquadOptions = [],
    panelSquadsLoading = false,
    onSettingsSaved = () => {},
  }: {
    at: TranslateFn;
    settingsDirty?: SettingsDirtyState;
    settingsFieldMap?: Map<string, SettingField>;
    settingsSaving?: boolean;
    panelSquadOptions?: SelectOption[];
    panelSquadsLoading?: boolean;
    onSettingsSaved?: (payload: SettingsSavedPayload) => void | Promise<void>;
  } = $props();

  const settingsStore = getSettingsStore();
  const tariffsStore = getTariffsStore();

  let trialSettingsOpen = $state(false);
  let selectedTrialSquad = $state("");
  let selectedTrialPremiumSquad = $state("");
  let trialSquadSelectKey = $state(0);
  let trialPremiumSquadSelectKey = $state(0);
  const trialDirtyCount = $derived(
    TRIAL_SETTING_KEYS.filter((key) => Boolean(settingsDirty[key])).length
  );
  const trafficStrategyOptions = $derived(buildTrafficStrategyOptions(at));

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

  function isSettingDirty(key: string, dirty: SettingsDirtyState = settingsDirty): boolean {
    return resolveIsSettingDirty(key, dirty);
  }

  function dirtyCount(keys: readonly string[], dirty: SettingsDirtyState = settingsDirty): number {
    return resolveDirtyCount(keys, dirty);
  }

  function csvList(
    key: string,
    dirty: SettingsDirtyState = settingsDirty,
    fieldMap = settingsFieldMap
  ): string[] {
    return resolveCsvList(key, dirty, fieldMap);
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

  function setCsvList(key: string, values: string[]): void {
    const normalized = Array.from(
      new Set((values || []).map((item) => String(item).trim()).filter(Boolean))
    );
    settingsStore.markDirty(key, normalized.join(","));
  }

  function addTrialSquad(uuid: string): void {
    const next = String(uuid || "").trim();
    if (!next) return;
    const current = csvList("TRIAL_SQUAD_UUIDS");
    if (!current.includes(next)) {
      setCsvList("TRIAL_SQUAD_UUIDS", [...current, next]);
    }
    selectedTrialSquad = "";
  }

  function handleTrialSquadSelect(uuid: string): void {
    addTrialSquad(uuid);
    selectedTrialSquad = "";
    trialSquadSelectKey += 1;
  }

  function addTrialPremiumSquad(uuid: string): void {
    const next = String(uuid || "").trim();
    if (!next) return;
    const current = csvList("TRIAL_PREMIUM_SQUAD_UUIDS");
    if (!current.includes(next)) {
      setCsvList("TRIAL_PREMIUM_SQUAD_UUIDS", [...current, next]);
    }
    selectedTrialPremiumSquad = "";
  }

  function handleTrialPremiumSquadSelect(uuid: string): void {
    addTrialPremiumSquad(uuid);
    selectedTrialPremiumSquad = "";
    trialPremiumSquadSelectKey += 1;
  }

  const handleTrialTrafficStrategySelect = (value: string) =>
    setSetting("TRIAL_TRAFFIC_STRATEGY", value);
  const handleTrialSquadSelectChange = handleTrialSquadSelect;
  const handleTrialPremiumSquadSelectChange = handleTrialPremiumSquadSelect;

  function removeTrialSquad(uuid: string): void {
    setCsvList(
      "TRIAL_SQUAD_UUIDS",
      csvList("TRIAL_SQUAD_UUIDS").filter((item) => item !== uuid)
    );
  }

  function removeTrialPremiumSquad(uuid: string): void {
    setCsvList(
      "TRIAL_PREMIUM_SQUAD_UUIDS",
      csvList("TRIAL_PREMIUM_SQUAD_UUIDS").filter((item) => item !== uuid)
    );
  }

  function trialSquadLabel(uuid: string): string {
    return tariffsStore.squadLabel(uuid);
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
        data-state={trialSettingsOpen ? "open" : "closed"}
        aria-expanded={trialSettingsOpen}
        aria-controls="admin-trial-settings-content"
        onclick={() => (trialSettingsOpen = !trialSettingsOpen)}
      >
        <span class="admin-accordion-title">{at("tariffs_trial_title", {}, "Trial access")}</span>
        <span class="admin-accordion-meta">
          {at(
            "tariffs_trial_subtitle",
            {},
            "Configure trial duration, traffic limit, and Remnawave squads from the tariff page."
          )}
          · {boolValue("TRIAL_ENABLED", settingsDirty, settingsFieldMap)
            ? at("enabled", {}, "Enabled")
            : at("disabled", {}, "Disabled")}{#if trialDirtyCount}
            · {at("settings_dirty_count", { count: trialDirtyCount }, "Changes: {count}")}{/if}
        </span>
        <ChevronRight size={16} class="admin-accordion-chev" />
      </button>
    </div>
    {#if trialSettingsOpen}
      <div id="admin-trial-settings-content" class="admin-accordion-content" data-state="open">
        <div class="admin-card-body admin-trial-settings-body">
          {#if trialDirtyCount}
            <div class="admin-editor-section-actions admin-tariff-settings-save-row">
              <AdminBadge variant="warning">
                {at("settings_dirty_count", { count: trialDirtyCount }, "Changes: {count}")}
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
              class:is-dirty={dirtyCount(TRIAL_SWITCH_KEYS, settingsDirty)}
            >
              <header class="admin-settings-field-group-head">
                <div class="admin-settings-field-group-head-copy">
                  <strong>{at("tariffs_trial_group_switch", {}, "Access")}</strong>
                  <small>
                    {at(
                      "tariffs_trial_group_switch_hint",
                      {},
                      "Turns trial activation on or off for users."
                    )}
                  </small>
                </div>
                {#if dirtyCount(TRIAL_SWITCH_KEYS, settingsDirty)}
                  <AdminBadge variant="warning">
                    {at(
                      "settings_dirty_count",
                      { count: dirtyCount(TRIAL_SWITCH_KEYS, settingsDirty) },
                      "Changes: {count}"
                    )}
                  </AdminBadge>
                {/if}
              </header>
              <div class="admin-settings-field-group-body">
                <div
                  class="admin-setting admin-trial-setting-row"
                  class:is-dirty={isSettingDirty("TRIAL_ENABLED", settingsDirty)}
                >
                  <div class="admin-setting-meta">
                    <strong>
                      {at("tariffs_trial_enabled", {}, "Trial enabled")}
                      {#if isSettingDirty("TRIAL_ENABLED", settingsDirty)}
                        <AdminBadge variant="warning"
                          >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                        >
                      {/if}
                    </strong>
                    <code>TRIAL_ENABLED</code>
                  </div>
                  <div class="admin-setting-control">
                    <div class="admin-setting-switch">
                      <Switch.Root
                        aria-label={at("tariffs_trial_enabled", {}, "Trial enabled")}
                        checked={boolValue("TRIAL_ENABLED", settingsDirty, settingsFieldMap)}
                        onCheckedChange={(checked) => setSetting("TRIAL_ENABLED", checked)}
                        class="admin-switch-root"
                      >
                        <Switch.Thumb class="admin-switch-thumb" />
                      </Switch.Root>
                      <span
                        >{boolValue("TRIAL_ENABLED", settingsDirty, settingsFieldMap)
                          ? at("enabled", {}, "Enabled")
                          : at("disabled", {}, "Disabled")}</span
                      >
                    </div>
                    {#if isSettingDirty("TRIAL_ENABLED", settingsDirty)}
                      <AdminButton
                        size="sm"
                        variant="ghost"
                        onclick={() => resetSetting("TRIAL_ENABLED")}
                      >
                        <X size={12} />
                        {at("reset", {}, "Reset")}
                      </AdminButton>
                    {/if}
                  </div>
                </div>
                <div
                  class="admin-setting admin-trial-setting-row"
                  class:is-dirty={isSettingDirty("TRIAL_WITHOUT_TELEGRAM_ENABLED", settingsDirty)}
                >
                  <div class="admin-setting-meta">
                    <strong>
                      {at("tariffs_trial_without_telegram_enabled", {}, "Trial without Telegram")}
                      {#if isSettingDirty("TRIAL_WITHOUT_TELEGRAM_ENABLED", settingsDirty)}
                        <AdminBadge variant="warning"
                          >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                        >
                      {/if}
                    </strong>
                    <code>TRIAL_WITHOUT_TELEGRAM_ENABLED</code>
                  </div>
                  <div class="admin-setting-control">
                    <div class="admin-setting-switch">
                      <Switch.Root
                        aria-label={at(
                          "tariffs_trial_without_telegram_enabled",
                          {},
                          "Trial without Telegram"
                        )}
                        checked={boolValue(
                          "TRIAL_WITHOUT_TELEGRAM_ENABLED",
                          settingsDirty,
                          settingsFieldMap
                        )}
                        onCheckedChange={(checked) =>
                          setSetting("TRIAL_WITHOUT_TELEGRAM_ENABLED", checked)}
                        class="admin-switch-root"
                      >
                        <Switch.Thumb class="admin-switch-thumb" />
                      </Switch.Root>
                      <span
                        >{boolValue(
                          "TRIAL_WITHOUT_TELEGRAM_ENABLED",
                          settingsDirty,
                          settingsFieldMap
                        )
                          ? at("enabled", {}, "Enabled")
                          : at("disabled", {}, "Disabled")}</span
                      >
                    </div>
                    {#if isSettingDirty("TRIAL_WITHOUT_TELEGRAM_ENABLED", settingsDirty)}
                      <AdminButton
                        size="sm"
                        variant="ghost"
                        onclick={() => resetSetting("TRIAL_WITHOUT_TELEGRAM_ENABLED")}
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
              class:is-dirty={dirtyCount(TRIAL_GENERAL_KEYS, settingsDirty)}
            >
              <header class="admin-settings-field-group-head">
                <div class="admin-settings-field-group-head-copy">
                  <strong>{at("tariffs_trial_group_general", {}, "General settings")}</strong>
                  <small>
                    {at(
                      "tariffs_trial_group_general_hint",
                      {},
                      "Trial duration and traffic volume granted to the user."
                    )}
                  </small>
                </div>
                {#if dirtyCount(TRIAL_GENERAL_KEYS, settingsDirty)}
                  <AdminBadge variant="warning">
                    {at(
                      "settings_dirty_count",
                      { count: dirtyCount(TRIAL_GENERAL_KEYS, settingsDirty) },
                      "Changes: {count}"
                    )}
                  </AdminBadge>
                {/if}
              </header>
              <div class="admin-settings-field-group-body">
                <div
                  class="admin-setting admin-trial-setting-row"
                  class:is-dirty={isSettingDirty("TRIAL_DURATION_DAYS", settingsDirty)}
                >
                  <div class="admin-setting-meta">
                    <strong>
                      {at("tariffs_trial_days", {}, "Duration, days")}
                      {#if isSettingDirty("TRIAL_DURATION_DAYS", settingsDirty)}
                        <AdminBadge variant="warning"
                          >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                        >
                      {/if}
                    </strong>
                    <code>TRIAL_DURATION_DAYS</code>
                  </div>
                  <div class="admin-setting-control">
                    <Input
                      class="input"
                      type="number"
                      min="0"
                      step="1"
                      value={inputValueForKey("TRIAL_DURATION_DAYS")}
                      oninput={settingInputHandler("TRIAL_DURATION_DAYS")}
                    />
                    {#if isSettingDirty("TRIAL_DURATION_DAYS", settingsDirty)}
                      <AdminButton
                        size="sm"
                        variant="ghost"
                        onclick={() => resetSetting("TRIAL_DURATION_DAYS")}
                      >
                        <X size={12} />
                        {at("reset", {}, "Reset")}
                      </AdminButton>
                    {/if}
                  </div>
                </div>
                <div
                  class="admin-setting admin-trial-setting-row"
                  class:is-dirty={isSettingDirty("TRIAL_TRAFFIC_LIMIT_GB", settingsDirty)}
                >
                  <div class="admin-setting-meta">
                    <strong>
                      {at("tariffs_trial_traffic", {}, "Traffic limit, GB")}
                      {#if isSettingDirty("TRIAL_TRAFFIC_LIMIT_GB", settingsDirty)}
                        <AdminBadge variant="warning"
                          >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                        >
                      {/if}
                    </strong>
                    <code>TRIAL_TRAFFIC_LIMIT_GB</code>
                  </div>
                  <div class="admin-setting-control">
                    <Input
                      class="input"
                      type="number"
                      min="0"
                      step="0.1"
                      value={inputValueForKey("TRIAL_TRAFFIC_LIMIT_GB")}
                      oninput={settingInputHandler("TRIAL_TRAFFIC_LIMIT_GB")}
                    />
                    {#if isSettingDirty("TRIAL_TRAFFIC_LIMIT_GB", settingsDirty)}
                      <AdminButton
                        size="sm"
                        variant="ghost"
                        onclick={() => resetSetting("TRIAL_TRAFFIC_LIMIT_GB")}
                      >
                        <X size={12} />
                        {at("reset", {}, "Reset")}
                      </AdminButton>
                    {/if}
                  </div>
                </div>
                <div
                  class="admin-setting admin-trial-setting-row"
                  class:is-dirty={isSettingDirty("TRIAL_PREMIUM_TRAFFIC_LIMIT_GB", settingsDirty)}
                >
                  <div class="admin-setting-meta">
                    <strong>
                      {at("tariffs_trial_premium_traffic", {}, "Premium traffic limit, GB")}
                      {#if isSettingDirty("TRIAL_PREMIUM_TRAFFIC_LIMIT_GB", settingsDirty)}
                        <AdminBadge variant="warning"
                          >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                        >
                      {/if}
                    </strong>
                    <code>TRIAL_PREMIUM_TRAFFIC_LIMIT_GB</code>
                  </div>
                  <div class="admin-setting-control">
                    <Input
                      class="input"
                      type="number"
                      min="0"
                      step="0.1"
                      value={inputValueForKey("TRIAL_PREMIUM_TRAFFIC_LIMIT_GB")}
                      oninput={settingInputHandler("TRIAL_PREMIUM_TRAFFIC_LIMIT_GB")}
                    />
                    {#if isSettingDirty("TRIAL_PREMIUM_TRAFFIC_LIMIT_GB", settingsDirty)}
                      <AdminButton
                        size="sm"
                        variant="ghost"
                        onclick={() => resetSetting("TRIAL_PREMIUM_TRAFFIC_LIMIT_GB")}
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
              class:is-dirty={dirtyCount(TRIAL_RESET_KEYS, settingsDirty)}
            >
              <header class="admin-settings-field-group-head">
                <div class="admin-settings-field-group-head-copy">
                  <strong>{at("tariffs_trial_group_reset", {}, "Traffic reset")}</strong>
                  <small>
                    {at(
                      "tariffs_trial_group_reset_hint",
                      {},
                      "Strategy Remnawave uses to refresh the trial traffic limit."
                    )}
                  </small>
                </div>
                {#if dirtyCount(TRIAL_RESET_KEYS, settingsDirty)}
                  <AdminBadge variant="warning">
                    {at(
                      "settings_dirty_count",
                      { count: dirtyCount(TRIAL_RESET_KEYS, settingsDirty) },
                      "Changes: {count}"
                    )}
                  </AdminBadge>
                {/if}
              </header>
              <div class="admin-settings-field-group-body">
                <div
                  class="admin-setting admin-trial-setting-row"
                  class:is-dirty={isSettingDirty("TRIAL_TRAFFIC_STRATEGY", settingsDirty)}
                >
                  <div class="admin-setting-meta">
                    <strong>
                      {at("tariffs_trial_strategy", {}, "Traffic reset strategy")}
                      {#if isSettingDirty("TRIAL_TRAFFIC_STRATEGY", settingsDirty)}
                        <AdminBadge variant="warning"
                          >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                        >
                      {/if}
                    </strong>
                    <code>TRIAL_TRAFFIC_STRATEGY</code>
                  </div>
                  <div class="admin-setting-control">
                    <AdminSelect
                      class="admin-setting-select"
                      value={String(
                        valueForKey("TRIAL_TRAFFIC_STRATEGY", settingsDirty, settingsFieldMap) ||
                          "NO_RESET"
                      )}
                      items={trafficStrategyOptions}
                      ariaLabel={at("tariffs_trial_strategy", {}, "Traffic reset strategy")}
                      onValueChange={handleTrialTrafficStrategySelect}
                    />
                    {#if isSettingDirty("TRIAL_TRAFFIC_STRATEGY", settingsDirty)}
                      <AdminButton
                        size="sm"
                        variant="ghost"
                        onclick={() => resetSetting("TRIAL_TRAFFIC_STRATEGY")}
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
              class:is-dirty={dirtyCount(TRIAL_SQUAD_KEYS, settingsDirty)}
            >
              <header class="admin-settings-field-group-head">
                <div class="admin-settings-field-group-head-copy">
                  <strong>{at("tariffs_trial_group_squads", {}, "Squads")}</strong>
                  <small>
                    {at(
                      "tariffs_trial_group_squads_hint",
                      {},
                      "Squads assigned to the user when trial access is activated."
                    )}
                  </small>
                </div>
                {#if dirtyCount(TRIAL_SQUAD_KEYS, settingsDirty)}
                  <AdminBadge variant="warning">
                    {at(
                      "settings_dirty_count",
                      { count: dirtyCount(TRIAL_SQUAD_KEYS, settingsDirty) },
                      "Changes: {count}"
                    )}
                  </AdminBadge>
                {/if}
              </header>
              <div class="admin-settings-field-group-body">
                <div
                  class="admin-setting admin-trial-setting-row"
                  class:is-dirty={isSettingDirty("TRIAL_SQUAD_UUIDS", settingsDirty)}
                >
                  <div class="admin-setting-meta">
                    <strong>
                      {at("tariffs_trial_squads", {}, "Regular Trial Internal Squads")}
                      {#if isSettingDirty("TRIAL_SQUAD_UUIDS", settingsDirty)}
                        <AdminBadge variant="warning"
                          >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                        >
                      {/if}
                    </strong>
                    <code>TRIAL_SQUAD_UUIDS</code>
                    <small>
                      {at(
                        "tariffs_trial_squads_hint",
                        {},
                        "These squads are applied as regular trial access. Empty value falls back to USER_SQUAD_UUIDS."
                      )}
                    </small>
                  </div>
                  <div class="admin-setting-control admin-trial-squad-control">
                    {#key trialSquadSelectKey}
                      <AdminSelect
                        value={selectedTrialSquad}
                        items={panelSquadOptions}
                        disabled={panelSquadsLoading || !panelSquadOptions.length}
                        placeholder={panelSquadsLoading
                          ? at("loading", {}, "Loading…")
                          : at("tariffs_trial_add_squad", {}, "Add squad from panel")}
                        ariaLabel={at("tariffs_trial_add_squad", {}, "Add squad from panel")}
                        onValueChange={handleTrialSquadSelectChange}
                      />
                    {/key}
                    {#if isSettingDirty("TRIAL_SQUAD_UUIDS", settingsDirty)}
                      <AdminButton
                        size="sm"
                        variant="ghost"
                        onclick={() => resetSetting("TRIAL_SQUAD_UUIDS")}
                      >
                        <X size={12} />
                        {at("reset", {}, "Reset")}
                      </AdminButton>
                    {/if}
                    <div class="admin-chip-list">
                      {#each csvList("TRIAL_SQUAD_UUIDS", settingsDirty, settingsFieldMap) as uuid}
                        <button
                          type="button"
                          class="admin-chip"
                          onclick={() => removeTrialSquad(uuid)}
                        >
                          {trialSquadLabel(uuid)}
                          <X size={12} />
                        </button>
                      {/each}
                    </div>
                  </div>
                </div>
                <div
                  class="admin-setting admin-trial-setting-row"
                  class:is-dirty={isSettingDirty("TRIAL_PREMIUM_SQUAD_UUIDS", settingsDirty)}
                >
                  <div class="admin-setting-meta">
                    <strong>
                      {at("tariffs_trial_premium_squads", {}, "Trial Premium Internal Squads")}
                      {#if isSettingDirty("TRIAL_PREMIUM_SQUAD_UUIDS", settingsDirty)}
                        <AdminBadge variant="warning"
                          >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                        >
                      {/if}
                    </strong>
                    <code>TRIAL_PREMIUM_SQUAD_UUIDS</code>
                    <small>
                      {at(
                        "tariffs_trial_premium_squads_hint",
                        {},
                        "These squads are added to regular trial squads. Empty value disables premium access for trials."
                      )}
                    </small>
                  </div>
                  <div class="admin-setting-control admin-trial-squad-control">
                    {#key trialPremiumSquadSelectKey}
                      <AdminSelect
                        value={selectedTrialPremiumSquad}
                        items={panelSquadOptions}
                        disabled={panelSquadsLoading || !panelSquadOptions.length}
                        placeholder={panelSquadsLoading
                          ? at("loading", {}, "Loading…")
                          : at(
                              "tariffs_trial_add_premium_squad",
                              {},
                              "Add premium squad from panel"
                            )}
                        ariaLabel={at(
                          "tariffs_trial_add_premium_squad",
                          {},
                          "Add premium squad from panel"
                        )}
                        onValueChange={handleTrialPremiumSquadSelectChange}
                      />
                    {/key}
                    {#if isSettingDirty("TRIAL_PREMIUM_SQUAD_UUIDS", settingsDirty)}
                      <AdminButton
                        size="sm"
                        variant="ghost"
                        onclick={() => resetSetting("TRIAL_PREMIUM_SQUAD_UUIDS")}
                      >
                        <X size={12} />
                        {at("reset", {}, "Reset")}
                      </AdminButton>
                    {/if}
                    <div class="admin-chip-list">
                      {#each csvList("TRIAL_PREMIUM_SQUAD_UUIDS", settingsDirty, settingsFieldMap) as uuid}
                        <button
                          type="button"
                          class="admin-chip"
                          onclick={() => removeTrialPremiumSquad(uuid)}
                        >
                          {trialSquadLabel(uuid)}
                          <X size={12} />
                        </button>
                      {/each}
                    </div>
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
