<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import { AdminBadge, AdminButton, AdminSectionHeader } from "$components/patterns/admin/index.js";
  import { Checkbox, Input } from "$components/ui/index.js";
  import { Label } from "$components/ui/primitives.js";
  import type { ActiveSubscription, TranslateFn } from "./userDetailTypes";

  let {
    at,
    activeSubscription,
    userActionBusy = false,
    hwidLimitDirty = false,
    hwidLimitDraftValid = false,
    hwidUnlimitedDraft = false,
    hwidLimitLabel,
  }: {
    at: TranslateFn;
    activeSubscription: ActiveSubscription;
    userActionBusy?: boolean;
    hwidLimitDirty?: boolean;
    hwidLimitDraftValid?: boolean;
    hwidUnlimitedDraft?: boolean;
    hwidLimitLabel: (sub: Record<string, unknown> | null | undefined) => string;
  } = $props();

  const usersStore = getUsersStore();
</script>

<section
  class="admin-user-action-sheet admin-user-action-sheet--hwid-limit"
  class:is-dirty={hwidLimitDirty}
>
  <AdminSectionHeader
    title={at("user_hwid_limit_card_title", {}, "HWID devices")}
    description={at(
      "user_hwid_limit_card_hint",
      {},
      "Manual device limit for the user. Leave the field empty to restore the tariff or default limit."
    )}
  />
  <div class="admin-user-action-sheet-body admin-user-override-stack">
    <Label.Root class="admin-field-label admin-extend-field">
      <span>{at("user_hwid_limit_input", {}, "Device limit")}</span>
      <small
        >{at(
          "user_hwid_limit_input_hint",
          {},
          "Empty means tariff/default; 0 or the checkbox means unlimited."
        )}</small
      >
      <Input
        class="input"
        type="number"
        min="0"
        step="1"
        placeholder={at("user_hwid_limit_default_placeholder", {}, "Tariff")}
        disabled={hwidUnlimitedDraft}
        aria-label={at("user_hwid_limit_input", {}, "Device limit")}
        bind:value={usersStore.hwidDeviceLimitDraft}
      />
    </Label.Root>
  </div>
  <div class="admin-user-action-sheet-footer admin-override-card-footer">
    <div class="admin-override-card-toolbar">
      <label class="admin-override-unlimited-label">
        <Checkbox
          bind:checked={usersStore.hwidUnlimitedDraft}
          aria-label={at("user_override_unlimited_short", {}, "Unlimited")}
        />
        <span>{at("user_override_unlimited_short", {}, "Unlimited")}</span>
      </label>
      <div class="admin-action-save-controls">
        {#if hwidLimitDirty}
          <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Changed")}</AdminBadge>
        {/if}
        <AdminButton
          variant="primary"
          onclick={usersStore.saveHwidDeviceLimit}
          disabled={userActionBusy || !hwidLimitDirty || !hwidLimitDraftValid}
        >
          {at("user_hwid_limit_save", {}, "Save")}
        </AdminButton>
      </div>
    </div>
    <div class="admin-override-status-lines">
      {#if hwidLimitDirty}
        <span class="admin-unsaved-hint">
          {at("user_action_unsaved_hint", {}, "Unsaved changes in this card")}
        </span>
      {/if}
      {#if !hwidLimitDraftValid}
        <span class="admin-invalid-hint">
          {at("hwid_limit_invalid", {}, "❌ Enter an integer device count from 0 to 1,000,000.")}
        </span>
      {/if}
      <span class="admin-meta-truncate">
        {at(
          "user_hwid_limit_status",
          { current: hwidLimitLabel(activeSubscription) },
          "Current: {current}"
        )}
      </span>
    </div>
  </div>
</section>
