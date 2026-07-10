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
    title={at("user_traffic_strategy_card_title", {}, "Сброс трафика")}
    description={at(
      "user_traffic_strategy_card_hint",
      {},
      "Индивидуальная стратегия Remnawave для period-подписки пользователя."
    )}
  />
  <div class="admin-user-action-sheet-body admin-user-tariff-stack">
    <Label.Root class="admin-field-label admin-extend-field">
      <span>{at("user_traffic_strategy_select_label", {}, "Стратегия")}</span>
      <AdminSelect
        class="admin-user-traffic-strategy-select"
        value={usersStore.trafficStrategyDraft}
        items={trafficStrategyItems}
        placeholder={at("user_traffic_strategy_select_placeholder", {}, "Выберите стратегию")}
        ariaLabel={at("user_traffic_strategy_select_label", {}, "Стратегия")}
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
          `Сейчас: ${trafficStrategyCurrentLabel}`
        )}
      </span>
      <div class="admin-action-save-controls">
        {#if trafficStrategyDirty}
          <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge>
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
          {at("user_traffic_strategy_save", {}, "Сохранить стратегию")}
        </AdminButton>
      </div>
    </div>
    <div class="admin-override-status-lines">
      {#if trafficStrategyDirty}
        <span class="admin-unsaved-hint">
          {at("user_action_unsaved_hint", {}, "Есть несохранённые изменения")}
        </span>
      {/if}
      {#if !trafficStrategyDraftValid}
        <span class="admin-invalid-hint">
          {at("user_traffic_strategy_invalid", {}, "Выберите доступную стратегию")}
        </span>
      {/if}
      {#if !trafficStrategyEditable && trafficStrategyLockMessage}
        <span class="admin-muted">{trafficStrategyLockMessage}</span>
      {/if}
    </div>
  </div>
</section>
