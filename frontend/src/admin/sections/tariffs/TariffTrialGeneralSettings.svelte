<script lang="ts">
  import { Input } from "$components/ui/index.js";
  import { X } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";
  import {
    TRIAL_GENERAL_KEYS,
    dirtyCount,
    inputValueForKey as resolveInputValueForKey,
    isSettingDirty,
    type SettingsDirtyState,
  } from "$lib/admin/tariffSettings";
  import type { SettingField } from "$lib/admin/stores/settingsStore";
  import type { TranslateFn } from "./tariffEditorTabUtils";

  let {
    at,
    settingsDirty,
    settingsFieldMap,
    setSetting,
    resetSetting,
  }: {
    at: TranslateFn;
    settingsDirty: SettingsDirtyState;
    settingsFieldMap: Map<string, SettingField>;
    setSetting: (key: string, value: unknown) => void;
    resetSetting: (key: string) => void;
  } = $props();

  function inputValueForKey(key: string): string | number {
    return resolveInputValueForKey(key, settingsDirty, settingsFieldMap);
  }

  function settingInputHandler(key: string): (event: Event) => void {
    return (event) => {
      const input = event.currentTarget as HTMLInputElement | null;
      setSetting(key, input?.value ?? "");
    };
  }
</script>

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
          "Trial duration, traffic volume, and device limit granted to the user."
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
            <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Changed")}</AdminBadge>
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
            <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Changed")}</AdminBadge>
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
            <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Changed")}</AdminBadge>
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
    <div
      class="admin-setting admin-trial-setting-row"
      class:is-dirty={isSettingDirty("TRIAL_PREMIUM_TITLE", settingsDirty)}
    >
      <div class="admin-setting-meta">
        <strong>
          {at("settings_field_trial_premium_title_label", {}, "Trial premium section title")}
          {#if isSettingDirty("TRIAL_PREMIUM_TITLE", settingsDirty)}
            <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Changed")}</AdminBadge>
          {/if}
        </strong>
        <code>TRIAL_PREMIUM_TITLE</code>
        <small>
          {at(
            "settings_field_trial_premium_title_description",
            {},
            "Custom title on the trial subscription's home screen. Empty uses the default in the user's language."
          )}
        </small>
      </div>
      <div class="admin-setting-control">
        <Input
          class="input"
          type="text"
          value={inputValueForKey("TRIAL_PREMIUM_TITLE")}
          aria-label={at(
            "settings_field_trial_premium_title_label",
            {},
            "Trial premium section title"
          )}
          oninput={settingInputHandler("TRIAL_PREMIUM_TITLE")}
        />
        {#if isSettingDirty("TRIAL_PREMIUM_TITLE", settingsDirty)}
          <AdminButton
            size="sm"
            variant="ghost"
            onclick={() => resetSetting("TRIAL_PREMIUM_TITLE")}
          >
            <X size={12} />
            {at("reset", {}, "Reset")}
          </AdminButton>
        {/if}
      </div>
    </div>
    <div
      class="admin-setting admin-trial-setting-row"
      class:is-dirty={isSettingDirty("TRIAL_HWID_DEVICE_LIMIT", settingsDirty)}
    >
      <div class="admin-setting-meta">
        <strong>
          {at("tariffs_trial_devices", {}, "Device limit")}
          {#if isSettingDirty("TRIAL_HWID_DEVICE_LIMIT", settingsDirty)}
            <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Changed")}</AdminBadge>
          {/if}
        </strong>
        <code>TRIAL_HWID_DEVICE_LIMIT</code>
        <small>
          {at(
            "tariffs_trial_devices_hint",
            {},
            "Device top-ups are unavailable during the trial. They become available after switching to a tariff with configured device packages."
          )}
        </small>
      </div>
      <div class="admin-setting-control">
        <Input
          class="input"
          type="number"
          min="0"
          step="1"
          value={inputValueForKey("TRIAL_HWID_DEVICE_LIMIT")}
          oninput={settingInputHandler("TRIAL_HWID_DEVICE_LIMIT")}
        />
        {#if isSettingDirty("TRIAL_HWID_DEVICE_LIMIT", settingsDirty)}
          <AdminButton
            size="sm"
            variant="ghost"
            onclick={() => resetSetting("TRIAL_HWID_DEVICE_LIMIT")}
          >
            <X size={12} />
            {at("reset", {}, "Reset")}
          </AdminButton>
        {/if}
      </div>
    </div>
  </div>
</section>
