<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import {
    AdminButton,
    AdminSectionHeader,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { Checkbox, Input } from "$components/ui/index.js";
  import { Label } from "$components/ui/primitives.js";
  import { CalendarDays, Minus, Plus, RefreshCw } from "$components/ui/icons.js";
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
    activeSubscriptionEndDate = "",
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
    activeSubscriptionEndDate?: string;
    selectExtendTariff: (value: string) => void;
  } = $props();

  const usersStore = getUsersStore();

  const tomorrow = new Date();
  tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
  const minEndDateIso = tomorrow.toISOString().slice(0, 10);
  const currentEndDateIso = $derived(
    activeSubscriptionEndDate ? activeSubscriptionEndDate.slice(0, 10) : ""
  );
  const extensionMovesForward = $derived(
    usersStore.userExtendMode === "days"
      ? Number(usersStore.userExtendDays) > 0
      : Boolean(usersStore.userExtendEndDate) && usersStore.userExtendEndDate > currentEndDateIso
  );

  function selectExtendMode(mode: "days" | "date") {
    usersStore.userExtendMode = mode;
    if (mode === "date" && !usersStore.userExtendEndDate) {
      usersStore.userExtendEndDate = currentEndDateIso >= minEndDateIso ? currentEndDateIso : "";
    }
  }

  function setDaysSign(sign: 1 | -1) {
    const magnitude = Math.max(1, Math.abs(Number(usersStore.userExtendDays) || 1));
    usersStore.userExtendDays = sign * magnitude;
  }
</script>

<div class="admin-user-quick-actions">
  <section class="admin-user-action-sheet admin-user-action-sheet--extend">
    <AdminSectionHeader title={at("user_label_extend", {}, "Extend Subscription")} />
    <div class="admin-user-action-sheet-body admin-user-extend-stack">
      <div
        class="admin-user-extend-mode"
        role="group"
        aria-label={at("user_extend_mode", {}, "Change mode")}
      >
        <AdminButton
          size="sm"
          variant={usersStore.userExtendMode === "days" ? "primary" : "default"}
          aria-pressed={usersStore.userExtendMode === "days"}
          onclick={() => selectExtendMode("days")}
        >
          <Plus size={14} />
          {at("user_extend_mode_days", {}, "Adjust days")}
        </AdminButton>
        <AdminButton
          size="sm"
          variant={usersStore.userExtendMode === "date" ? "primary" : "default"}
          aria-pressed={usersStore.userExtendMode === "date"}
          disabled={!activeSubscriptionEndDate}
          onclick={() => selectExtendMode("date")}
        >
          <CalendarDays size={14} />
          {at("user_extend_mode_date", {}, "Set date")}
        </AdminButton>
      </div>
      <div class="admin-user-extend-grid">
        {#if usersStore.userExtendMode === "days"}
          <Label.Root class="admin-field-label admin-extend-field admin-user-extend-days-field">
            <span>{at("user_label_extend_days", {}, "Days")}</span>
            <div class="admin-user-extend-days-control">
              <AdminButton
                size="icon"
                variant={Number(usersStore.userExtendDays) < 0 ? "primary" : "default"}
                aria-label={at("user_extend_subtract", {}, "Subtract days")}
                onclick={() => setDaysSign(-1)}><Minus size={14} /></AdminButton
              >
              <Input
                class="input"
                type="number"
                min="-3650"
                max="3650"
                step="1"
                bind:value={usersStore.userExtendDays}
                aria-label={at("user_label_extend_days", {}, "Days")}
              />
              <AdminButton
                size="icon"
                variant={Number(usersStore.userExtendDays) > 0 ? "primary" : "default"}
                aria-label={at("user_extend_add", {}, "Add days")}
                onclick={() => setDaysSign(1)}><Plus size={14} /></AdminButton
              >
            </div>
          </Label.Root>
        {:else}
          <Label.Root class="admin-field-label admin-extend-field admin-user-extend-days-field">
            <span>{at("user_extend_end_date", {}, "New end date")}</span>
            <Input
              class="input"
              type="date"
              min={minEndDateIso}
              bind:value={usersStore.userExtendEndDate}
              aria-label={at("user_extend_end_date", {}, "New end date")}
            />
          </Label.Root>
        {/if}
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
          {#if usersStore.userExtendMode === "date"}<CalendarDays
              size={14}
            />{:else if Number(usersStore.userExtendDays) < 0}<Minus size={14} />{:else}<Plus
              size={14}
            />{/if}
          {at("user_btn_change_term", {}, "Change term")}
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
      {#if extraHwidDevices > 0 && extensionMovesForward}
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
