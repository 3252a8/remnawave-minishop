<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import {
    AdminBadge,
    AdminButton,
    AdminSectionHeader,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { Label } from "$components/ui/primitives.js";
  import { RefreshCw } from "$components/ui/icons.js";
  import type { SelectOption, TranslateFn } from "./userDetailTypes";

  let {
    at,
    userActionBusy = false,
    periodTariffItems = [],
    tariffActionDirty = false,
    tariffHwidLimitChangeAvailable = false,
    currentSubscriptionTariffLabel = "",
    userTariffActionKey = "",
    selectTariffAction,
  }: {
    at: TranslateFn;
    userActionBusy?: boolean;
    periodTariffItems?: SelectOption[];
    tariffActionDirty?: boolean;
    tariffHwidLimitChangeAvailable?: boolean;
    currentSubscriptionTariffLabel?: string;
    userTariffActionKey?: string;
    selectTariffAction: (value: string) => void;
  } = $props();

  const usersStore = getUsersStore();

  function saveTariff() {
    if (tariffHwidLimitChangeAvailable) {
      usersStore.updateState({ userTariffHwidConfirmOpen: true });
      return;
    }
    usersStore.changeUserTariff();
  }
</script>

<section
  class="admin-user-action-sheet admin-user-action-sheet--tariff"
  class:is-dirty={tariffActionDirty}
>
  <AdminSectionHeader
    title={at("user_tariff_card_title", {}, "Tariff")}
    description={at(
      "user_tariff_card_hint",
      {},
      "Change the user's tariff and sync panel squads immediately."
    )}
  />
  <div class="admin-user-action-sheet-body admin-user-tariff-stack">
    <Label.Root class="admin-field-label admin-extend-field">
      <span>{at("user_tariff_select_label", {}, "Tariff")}</span>
      <AdminSelect
        class="admin-user-tariff-select"
        value={usersStore.userTariffActionKey}
        items={periodTariffItems}
        placeholder={at("user_tariff_select_placeholder", {}, "Select tariff")}
        ariaLabel={at("user_tariff_select_label", {}, "Tariff")}
        disabled={userActionBusy}
        onValueChange={selectTariffAction}
      />
    </Label.Root>
  </div>
  <div class="admin-user-action-sheet-footer admin-override-card-footer">
    <div class="admin-override-card-toolbar">
      <span class="admin-meta-truncate">
        {at(
          "user_tariff_current",
          { tariff: currentSubscriptionTariffLabel },
          `Current: ${currentSubscriptionTariffLabel}`
        )}
      </span>
      <div class="admin-action-save-controls">
        {#if tariffActionDirty}
          <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge>
        {/if}
        <AdminButton
          variant="primary"
          onclick={saveTariff}
          disabled={userActionBusy || !userTariffActionKey || !tariffActionDirty}
        >
          <RefreshCw size={14} />
          {at("user_tariff_save", {}, "Save tariff")}
        </AdminButton>
      </div>
    </div>
    {#if tariffActionDirty}
      <div class="admin-override-status-lines">
        <span class="admin-unsaved-hint">
          {at("user_action_unsaved_hint", {}, "Есть несохранённые изменения")}
        </span>
        {#if tariffHwidLimitChangeAvailable}
          <span class="admin-muted">
            {at(
              "user_tariff_hwid_confirm_hint",
              {},
              "Ручной HWID-лимит будет сохранён; можно применить лимит тарифа перед сохранением."
            )}
          </span>
        {/if}
      </div>
    {/if}
  </div>
</section>
