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
    trafficStrategyItems = [],
    trafficStrategyDirty = false,
    trafficStrategyDraftValid = false,
    trafficStrategyEditable = false,
    trafficStrategyCurrentLabel = "",
    trafficStrategyLockMessage = "",
    selectTrafficStrategy,
  }: {
    at: TranslateFn;
    userActionBusy?: boolean;
    trafficStrategyItems?: SelectOption[];
    trafficStrategyDirty?: boolean;
    trafficStrategyDraftValid?: boolean;
    trafficStrategyEditable?: boolean;
    trafficStrategyCurrentLabel?: string;
    trafficStrategyLockMessage?: string;
    selectTrafficStrategy: (value: string) => void;
  } = $props();

  const usersStore = getUsersStore();
</script>

<section
  class="admin-user-action-sheet admin-user-action-sheet--traffic-strategy"
  class:is-dirty={trafficStrategyDirty}
>
  <AdminSectionHeader
    title={at("user_traffic_strategy_card_title", {}, "Traffic reset")}
    description={at(
      "user_traffic_strategy_card_hint",
      {},
      "Per-user Remnawave strategy for the user's period subscription."
    )}
  />
  <div class="admin-user-action-sheet-body admin-user-tariff-stack">
    <Label.Root class="admin-field-label admin-extend-field">
      <span>{at("user_traffic_strategy_select_label", {}, "Strategy")}</span>
      <AdminSelect
        class="admin-user-traffic-strategy-select"
        value={usersStore.trafficStrategyDraft}
        items={trafficStrategyItems}
        placeholder={at("user_traffic_strategy_select_placeholder", {}, "Select strategy")}
        ariaLabel={at("user_traffic_strategy_select_label", {}, "Strategy")}
        disabled={userActionBusy || !trafficStrategyEditable}
        onValueChange={selectTrafficStrategy}
      />
    </Label.Root>
  </div>
  <div class="admin-user-action-sheet-footer admin-override-card-footer">
    <div class="admin-override-card-toolbar">
      <span class="admin-meta-truncate">
        {at(
          "user_traffic_strategy_current",
          { strategy: trafficStrategyCurrentLabel },
          "Current: {strategy}"
        )}
      </span>
      <div class="admin-action-save-controls">
        {#if trafficStrategyDirty}
          <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Changed")}</AdminBadge>
        {/if}
        <AdminButton
          variant="primary"
          onclick={usersStore.saveTrafficStrategy}
          disabled={userActionBusy ||
            !trafficStrategyEditable ||
            !trafficStrategyDirty ||
            !trafficStrategyDraftValid}
        >
          <RefreshCw size={14} />
          {at("user_traffic_strategy_save", {}, "Save strategy")}
        </AdminButton>
      </div>
    </div>
    <div class="admin-override-status-lines">
      {#if trafficStrategyDirty}
        <span class="admin-unsaved-hint">
          {at("user_action_unsaved_hint", {}, "Unsaved changes in this card")}
        </span>
      {/if}
      {#if !trafficStrategyDraftValid}
        <span class="admin-invalid-hint">
          {at("user_traffic_strategy_invalid", {}, "Select an available strategy")}
        </span>
      {/if}
      {#if !trafficStrategyEditable && trafficStrategyLockMessage}
        <span class="admin-muted">{trafficStrategyLockMessage}</span>
      {/if}
    </div>
  </div>
</section>
