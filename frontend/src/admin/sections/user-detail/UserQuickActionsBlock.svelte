<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import {
    AdminButton,
    AdminSectionHeader,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { Checkbox, Input } from "$components/ui/index.js";
  import { Label } from "$components/ui/primitives.js";
  import { Plus, RefreshCw } from "$components/ui/icons.js";
  import type { SelectOption, TranslateFn } from "./userDetailTypes";

  let {
    at,
    userActionBusy = false,
    extendTariffItems = [],
    extendTariffsLoading = false,
    userExtendDaysValid = false,
    userExtendTariffValid = false,
    extendTariffRequired = false,
    extraHwidDevices = 0,
    selectExtendTariff,
  }: {
    at: TranslateFn;
    userActionBusy?: boolean;
    extendTariffItems?: SelectOption[];
    extendTariffsLoading?: boolean;
    userExtendDaysValid?: boolean;
    userExtendTariffValid?: boolean;
    extendTariffRequired?: boolean;
    extraHwidDevices?: number;
    selectExtendTariff: (value: string) => void;
  } = $props();

  const usersStore = getUsersStore();
</script>

<div class="admin-user-quick-actions">
  <section class="admin-user-action-sheet admin-user-action-sheet--extend">
    <AdminSectionHeader title={at("user_label_extend", {}, "Extend Subscription")} />
    <div class="admin-user-action-sheet-body admin-user-extend-stack">
      <div class="admin-user-extend-grid">
        <Label.Root class="admin-field-label admin-extend-field admin-user-extend-days-field">
          <span>{at("user_label_extend_days", {}, "Days")}</span>
          <Input
            class="input"
            type="number"
            min="1"
            max="3650"
            step="1"
            bind:value={usersStore.userExtendDays}
            aria-label={at("user_label_extend_days", {}, "Days")}
          />
        </Label.Root>
        {#if extendTariffItems.length}
          <Label.Root class="admin-field-label admin-extend-field admin-user-extend-tariff-field">
            <span>{at("user_tariff_select_label", {}, "Tariff")}</span>
            <AdminSelect
              class="admin-user-tariff-select admin-user-extend-tariff-select"
              value={usersStore.userExtendTariffKey}
              items={extendTariffItems}
              placeholder={at("user_tariff_select_placeholder", {}, "Select tariff")}
              ariaLabel={at("user_tariff_select_label", {}, "Tariff")}
              disabled={userActionBusy || extendTariffItems.length === 1}
              onValueChange={selectExtendTariff}
            />
          </Label.Root>
        {/if}
        <AdminButton
          class="admin-user-extend-submit"
          variant="primary"
          onclick={usersStore.extendUser}
          disabled={userActionBusy ||
            extendTariffsLoading ||
            !userExtendDaysValid ||
            !userExtendTariffValid ||
            (extendTariffRequired && !usersStore.userExtendTariffKey)}
        >
          <Plus size={14} />
          {at("user_btn_extend", {}, "Extend")}
        </AdminButton>
      </div>
      {#if extendTariffItems.length && !userExtendTariffValid}
        <small class="admin-muted"
          >{at("user_extend_tariff_required", {}, "Select a tariff before adding days")}</small
        >
      {:else if extendTariffRequired && !usersStore.userExtendTariffKey}
        <small class="admin-muted"
          >{at("user_extend_tariff_required", {}, "Select a tariff before adding days")}</small
        >
      {/if}
      {#if extraHwidDevices > 0}
        <label class="admin-extend-hwid-option">
          <Checkbox
            bind:checked={usersStore.userExtendHwidDevices}
            disabled={userActionBusy}
            ariaLabel={at("user_extend_hwid_devices_aria", {}, "Extend purchased HWID devices")}
          />
          <span>
            <strong>
              {at(
                "user_extend_hwid_devices",
                {
                  count: extraHwidDevices,
                },
                "Also extend +{count} HWID devices"
              )}
            </strong>
            <small>
              {at(
                "user_extend_hwid_devices_hint",
                {},
                "Active device top-ups will receive the same number of extra days."
              )}
            </small>
          </span>
        </label>
      {/if}
    </div>
  </section>
  <AdminButton
    class="admin-reset-trial-btn"
    onclick={usersStore.resetTrialUser}
    disabled={userActionBusy}
  >
    <RefreshCw size={14} />
    {at("user_btn_reset_trial", {}, "Reset Trial")}
  </AdminButton>
</div>
