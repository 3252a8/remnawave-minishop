<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import { Label, Tabs } from "$components/ui/primitives.js";
  import { Checkbox, Input, Textarea } from "$components/ui/index.js";
  import UserSquadOverridesActionCard from "./UserSquadOverridesActionCard.svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminSectionHeader,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { Eye, Plus, RefreshCw, Send, Trash2, UserMinus, UserPlus } from "$components/ui/icons.js";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import type { AdminPanelSquadOverrides } from "$lib/admin/stores/usersStoreState";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type SelectOption = { value: string; label: string };
  type SubscriptionDetail = Record<string, unknown> & {
    extra_hwid_devices?: unknown;
    premium_unlimited_override?: unknown;
    premium_bonus_bytes?: unknown;
    regular_unlimited_override?: unknown;
    regular_bonus_bytes?: unknown;
  };
  type UserDetail = Record<string, unknown> & {
    active_subscription?: SubscriptionDetail | null;
    panel_squad_overrides?: AdminPanelSquadOverrides | null;
  };
  type Props = {
    at: TranslateFn;
    openedUser?: AdminUser | null;
    openedUserDetail?: UserDetail | null;
    userActionBusy?: boolean;
    userMessageDraft?: string;
    extendTariffItems?: SelectOption[];
    extendTariffsLoading?: boolean;
    userExtendDaysValid?: boolean;
    userExtendTariffValid?: boolean;
    extendTariffRequired?: boolean;
    selectExtendTariff: (value: string) => void;
    periodTariffItems?: SelectOption[];
    tariffActionDirty?: boolean;
    tariffHwidLimitChangeAvailable?: boolean;
    currentSubscriptionTariffLabel?: string;
    userTariffActionKey?: string;
    selectTariffAction: (value: string) => void;
    trafficStrategyItems?: SelectOption[];
    trafficStrategyDirty?: boolean;
    trafficStrategyDraftValid?: boolean;
    trafficStrategyEditable?: boolean;
    trafficStrategyCurrentLabel?: string;
    trafficStrategyLockMessage?: string;
    selectTrafficStrategy: (value: string) => void;
    premiumOverrideDirty?: boolean;
    premiumOverrideDraftValid?: boolean;
    premiumUnlimitedDraft?: boolean;
    regularOverrideDirty?: boolean;
    regularOverrideDraftValid?: boolean;
    regularUnlimitedDraft?: boolean;
    hwidLimitDirty?: boolean;
    hwidLimitDraftValid?: boolean;
    hwidUnlimitedDraft?: boolean;
    hwidLimitLabel: (sub: Record<string, unknown> | null | undefined) => string;
    selectGrantTrafficKind: (value: string) => void;
    grantTrafficGbValid?: boolean;
    panelSquadItems?: SelectOption[];
    squadLabel: (uuid: string) => string;
    userSquadOverrideDraft?: string;
    selectUserSquadOverride: (value: string) => void;
    userExternalSquadModeDraft?: "inherit" | "set" | "cleared";
    selectUserExternalSquadMode: (value: string) => void;
    userExternalSquadUuidDraft?: string;
    updateUserExternalSquadUuid: (value: string) => void;
  };

  let {
    at,
    openedUser = null,
    openedUserDetail = null,
    userActionBusy = false,
    userMessageDraft = "",
    extendTariffItems = [],
    extendTariffsLoading = false,
    userExtendDaysValid = false,
    userExtendTariffValid = false,
    extendTariffRequired = false,
    selectExtendTariff,
    periodTariffItems = [],
    tariffActionDirty = false,
    tariffHwidLimitChangeAvailable = false,
    currentSubscriptionTariffLabel = "",
    userTariffActionKey = "",
    selectTariffAction,
    trafficStrategyItems = [],
    trafficStrategyDirty = false,
    trafficStrategyDraftValid = false,
    trafficStrategyEditable = false,
    trafficStrategyCurrentLabel = "",
    trafficStrategyLockMessage = "",
    selectTrafficStrategy,
    premiumOverrideDirty = false,
    premiumOverrideDraftValid = false,
    premiumUnlimitedDraft = false,
    regularOverrideDirty = false,
    regularOverrideDraftValid = false,
    regularUnlimitedDraft = false,
    hwidLimitDirty = false,
    hwidLimitDraftValid = false,
    hwidUnlimitedDraft = false,
    hwidLimitLabel,
    selectGrantTrafficKind,
    grantTrafficGbValid = false,
    panelSquadItems = [],
    squadLabel,
    userSquadOverrideDraft = "",
    selectUserSquadOverride,
    userExternalSquadModeDraft = "inherit",
    selectUserExternalSquadMode,
    userExternalSquadUuidDraft = "",
    updateUserExternalSquadUuid,
  }: Props = $props();

  const usersStore = getUsersStore();

  const activeSubscription = $derived(openedUserDetail?.active_subscription ?? null);
  const extraHwidDevices = $derived(Number(activeSubscription?.extra_hwid_devices || 0));
  const openedUserIsBanned = $derived(Boolean(openedUser?.is_banned));
</script>

<Tabs.Content value="actions" class="admin-tabs-content admin-actions-tab">
  <div class="admin-user-quick-actions">
    <section class="admin-user-action-sheet admin-user-action-sheet--extend">
      <AdminSectionHeader title={at("user_label_extend", {}, "Продлить подписку")} />
      <div class="admin-user-action-sheet-body admin-user-extend-stack">
        <div class="admin-user-extend-grid">
          <Label.Root class="admin-field-label admin-extend-field admin-user-extend-days-field">
            <span>{at("user_label_extend_days", {}, "Дней")}</span>
            <Input
              class="input"
              type="number"
              min="1"
              max="3650"
              step="1"
              bind:value={usersStore.userExtendDays}
              aria-label={at("user_label_extend_days", {}, "Дней")}
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
            {at("user_btn_extend", {}, "Продлить")}
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
              ariaLabel={at(
                "user_extend_hwid_devices_aria",
                {},
                "Продлить докупленные HWID-устройства"
              )}
            />
            <span>
              <strong>
                {at(
                  "user_extend_hwid_devices",
                  {
                    count: extraHwidDevices,
                  },
                  `Продлить также +${extraHwidDevices} HWID-устройств`
                )}
              </strong>
              <small>
                {at(
                  "user_extend_hwid_devices_hint",
                  {},
                  "Срок действующих докупок увеличится на те же дни."
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
      {at("user_btn_reset_trial", {}, "Сбросить триал")}
    </AdminButton>
  </div>

  <UserSquadOverridesActionCard
    {at}
    panelSquadOverrides={openedUserDetail?.panel_squad_overrides || null}
    {userActionBusy}
    {panelSquadItems}
    {squadLabel}
    {userSquadOverrideDraft}
    {selectUserSquadOverride}
    {userExternalSquadModeDraft}
    {selectUserExternalSquadMode}
    {userExternalSquadUuidDraft}
    {updateUserExternalSquadUuid}
  />

  {#if openedUserDetail?.active_subscription}
    {#if periodTariffItems.length}
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
                <AdminBadge variant="warning"
                  >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                >
              {/if}
              <AdminButton
                variant="primary"
                onclick={() =>
                  tariffHwidLimitChangeAvailable
                    ? usersStore.updateState({ userTariffHwidConfirmOpen: true })
                    : usersStore.changeUserTariff()}
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
    {/if}
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
              <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
              >
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

    <section
      class="admin-user-action-sheet admin-user-action-sheet--premium-override"
      class:is-dirty={premiumOverrideDirty}
    >
      <AdminSectionHeader
        title={at("user_premium_override_card_title", {}, "Премиум-трафик")}
        description={at(
          "user_premium_override_card_hint",
          {},
          "Безлимит и дополнительный объём для премиум-сквадов поверх тарифа."
        )}
      />
      <div class="admin-user-action-sheet-body admin-user-override-stack">
        <Label.Root class="admin-field-label admin-extend-field">
          <span>{at("user_premium_override_bonus", {}, "Доп. премиум-трафик, GB")}</span>
          <small>{at("user_premium_override_bonus_hint", {}, "")}</small>
          <Input
            class="input"
            type="number"
            min="0"
            step="1"
            placeholder="0"
            disabled={premiumUnlimitedDraft}
            aria-label={at("user_premium_override_bonus", {}, "Доп. премиум-трафик, GB")}
            bind:value={usersStore.premiumBonusGbDraft}
          />
        </Label.Root>
      </div>
      <div class="admin-user-action-sheet-footer admin-override-card-footer">
        <div class="admin-override-card-toolbar">
          <label class="admin-override-unlimited-label">
            <Checkbox
              bind:checked={usersStore.premiumUnlimitedDraft}
              aria-label={at("user_override_unlimited_short", {}, "Безлимит")}
            />
            <span>{at("user_override_unlimited_short", {}, "Безлимит")}</span>
          </label>
          <div class="admin-action-save-controls">
            {#if premiumOverrideDirty}
              <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
              >
            {/if}
            <AdminButton
              variant="primary"
              onclick={usersStore.savePremiumTrafficOverride}
              disabled={userActionBusy || !premiumOverrideDirty || !premiumOverrideDraftValid}
            >
              {at("user_premium_override_save", {}, "Сохранить")}
            </AdminButton>
          </div>
        </div>
        <div class="admin-override-status-lines">
          {#if premiumOverrideDirty}
            <span class="admin-unsaved-hint">
              {at("user_action_unsaved_hint", {}, "Есть несохранённые изменения")}
            </span>
          {/if}
          {#if !premiumOverrideDraftValid}
            <span class="admin-invalid-hint">
              {at("premium_override_invalid_bonus", {}, "Некорректное значение GB")}
            </span>
          {/if}
          {#if openedUserDetail.active_subscription.premium_unlimited_override}
            <span class="admin-meta-truncate">
              {at("user_premium_override_status_unlimited", {}, "Сейчас: безлимит")}
            </span>
          {:else if Number(openedUserDetail.active_subscription.premium_bonus_bytes || 0) > 0}
            <span class="admin-meta-truncate">
              {at(
                "user_premium_override_status_bonus",
                {
                  gb: +(
                    Number(openedUserDetail.active_subscription.premium_bonus_bytes) /
                    1024 ** 3
                  ).toFixed(2),
                },
                `Премиум сейчас: +${+(Number(openedUserDetail.active_subscription.premium_bonus_bytes) / 1024 ** 3).toFixed(2)} GB`
              )}
            </span>
          {:else}
            <span class="admin-muted"
              >{at("user_premium_override_status_none", {}, "Премиум-оверрайд не задан")}</span
            >
          {/if}
        </div>
      </div>
    </section>

    <section
      class="admin-user-action-sheet admin-user-action-sheet--regular-override"
      class:is-dirty={regularOverrideDirty}
    >
      <AdminSectionHeader
        title={at("user_regular_override_card_title", {}, "Основной трафик")}
        description={at(
          "user_regular_override_card_hint",
          {},
          "Безлимит и постоянный бонус к лимиту основного трафика."
        )}
      />
      <div class="admin-user-action-sheet-body admin-user-override-stack">
        <Label.Root class="admin-field-label admin-extend-field">
          <span>{at("user_regular_override_bonus", {}, "Доп. основной трафик, GB")}</span>
          <small>{at("user_regular_override_bonus_hint", {}, "")}</small>
          <Input
            class="input"
            type="number"
            min="0"
            step="1"
            placeholder="0"
            disabled={regularUnlimitedDraft}
            aria-label={at("user_regular_override_bonus", {}, "Доп. основной трафик, GB")}
            bind:value={usersStore.regularBonusGbDraft}
          />
        </Label.Root>
      </div>
      <div class="admin-user-action-sheet-footer admin-override-card-footer">
        <div class="admin-override-card-toolbar">
          <label class="admin-override-unlimited-label">
            <Checkbox
              bind:checked={usersStore.regularUnlimitedDraft}
              aria-label={at("user_override_unlimited_short", {}, "Безлимит")}
            />
            <span>{at("user_override_unlimited_short", {}, "Безлимит")}</span>
          </label>
          <div class="admin-action-save-controls">
            {#if regularOverrideDirty}
              <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
              >
            {/if}
            <AdminButton
              variant="primary"
              onclick={usersStore.saveRegularTrafficOverride}
              disabled={userActionBusy || !regularOverrideDirty || !regularOverrideDraftValid}
            >
              {at("user_regular_override_save", {}, "Сохранить")}
            </AdminButton>
          </div>
        </div>
        <div class="admin-override-status-lines">
          {#if regularOverrideDirty}
            <span class="admin-unsaved-hint">
              {at("user_action_unsaved_hint", {}, "Есть несохранённые изменения")}
            </span>
          {/if}
          {#if !regularOverrideDraftValid}
            <span class="admin-invalid-hint">
              {at(
                "regular_override_invalid_bonus",
                {},
                "Некорректное значение GB для основного трафика"
              )}
            </span>
          {/if}
          {#if openedUserDetail.active_subscription.regular_unlimited_override}
            <span class="admin-meta-truncate">
              {at("user_regular_override_status_unlimited", {}, "Сейчас: безлимит")}
            </span>
          {:else if Number(openedUserDetail.active_subscription.regular_bonus_bytes || 0) > 0}
            <span class="admin-meta-truncate">
              {at(
                "user_regular_override_status_bonus",
                {
                  gb: +(
                    Number(openedUserDetail.active_subscription.regular_bonus_bytes) /
                    1024 ** 3
                  ).toFixed(2),
                },
                `Основной сейчас: +${+(Number(openedUserDetail.active_subscription.regular_bonus_bytes) / 1024 ** 3).toFixed(2)} GB`
              )}
            </span>
          {:else}
            <span class="admin-muted"
              >{at(
                "user_regular_override_status_none",
                {},
                "Бонус основного трафика не задан"
              )}</span
            >
          {/if}
        </div>
      </div>
    </section>

    <section
      class="admin-user-action-sheet admin-user-action-sheet--hwid-limit"
      class:is-dirty={hwidLimitDirty}
    >
      <AdminSectionHeader
        title={at("user_hwid_limit_card_title", {}, "HWID-устройства")}
        description={at(
          "user_hwid_limit_card_hint",
          {},
          "Ручной лимит устройств для пользователя. Пустое поле вернёт тарифный или default-лимит."
        )}
      />
      <div class="admin-user-action-sheet-body admin-user-override-stack">
        <Label.Root class="admin-field-label admin-extend-field">
          <span>{at("user_hwid_limit_input", {}, "Лимит устройств")}</span>
          <small
            >{at(
              "user_hwid_limit_input_hint",
              {},
              "Пусто — тариф/default; 0 или галочка — безлимит."
            )}</small
          >
          <Input
            class="input"
            type="number"
            min="0"
            step="1"
            placeholder={at("user_hwid_limit_default_placeholder", {}, "Тариф")}
            disabled={hwidUnlimitedDraft}
            aria-label={at("user_hwid_limit_input", {}, "Лимит устройств")}
            bind:value={usersStore.hwidDeviceLimitDraft}
          />
        </Label.Root>
      </div>
      <div class="admin-user-action-sheet-footer admin-override-card-footer">
        <div class="admin-override-card-toolbar">
          <label class="admin-override-unlimited-label">
            <Checkbox
              bind:checked={usersStore.hwidUnlimitedDraft}
              aria-label={at("user_override_unlimited_short", {}, "Безлимит")}
            />
            <span>{at("user_override_unlimited_short", {}, "Безлимит")}</span>
          </label>
          <div class="admin-action-save-controls">
            {#if hwidLimitDirty}
              <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
              >
            {/if}
            <AdminButton
              variant="primary"
              onclick={usersStore.saveHwidDeviceLimit}
              disabled={userActionBusy || !hwidLimitDirty || !hwidLimitDraftValid}
            >
              {at("user_hwid_limit_save", {}, "Сохранить")}
            </AdminButton>
          </div>
        </div>
        <div class="admin-override-status-lines">
          {#if hwidLimitDirty}
            <span class="admin-unsaved-hint">
              {at("user_action_unsaved_hint", {}, "Есть несохранённые изменения")}
            </span>
          {/if}
          {#if !hwidLimitDraftValid}
            <span class="admin-invalid-hint">
              {at(
                "hwid_limit_invalid",
                {},
                "Введите целое число устройств от 0 до 1 000 000 или включите безлимит"
              )}
            </span>
          {/if}
          <span class="admin-meta-truncate">
            {at(
              "user_hwid_limit_status",
              { current: hwidLimitLabel(openedUserDetail.active_subscription) },
              `Сейчас: ${hwidLimitLabel(openedUserDetail.active_subscription)}`
            )}
          </span>
        </div>
      </div>
    </section>

    <section class="admin-user-action-sheet admin-user-action-sheet--traffic-grant">
      <AdminSectionHeader
        title={at("user_traffic_grant_title", {}, "Выдать трафик")}
        description={at(
          "user_traffic_grant_hint",
          {},
          "Зачисление ГБ на баланс пользователя — как при докупке, но без оплаты. Лимит и сквады в панели обновятся сразу."
        )}
      />
      <div class="admin-user-action-sheet-body admin-user-grant-stack">
        <Label.Root class="admin-field-label admin-extend-field">
          <span>{at("user_traffic_grant_kind", {}, "Тип трафика")}</span>
          <AdminSelect
            class="admin-grant-kind-select"
            value={usersStore.grantTrafficKindDraft}
            items={[
              {
                value: "regular",
                label: at("user_traffic_grant_kind_regular", {}, "Обычный"),
              },
              {
                value: "premium",
                label: at("user_traffic_grant_kind_premium", {}, "Премиум"),
              },
            ]}
            onValueChange={selectGrantTrafficKind}
            ariaLabel={at("user_traffic_grant_kind", {}, "Тип трафика")}
          />
        </Label.Root>
        <Label.Root class="admin-field-label admin-extend-field">
          <span>{at("user_traffic_grant_gb", {}, "ГБ к выдаче")}</span>
          <div class="admin-extend-control">
            <Input
              class="input"
              type="number"
              min="0"
              step="1"
              placeholder="0"
              aria-label={at("user_traffic_grant_gb", {}, "ГБ к выдаче")}
              bind:value={usersStore.grantTrafficGbDraft}
            />
            <AdminButton
              variant="primary"
              onclick={usersStore.grantTraffic}
              disabled={userActionBusy || !grantTrafficGbValid}
            >
              <Plus size={14} />
              {at("user_traffic_grant_submit", {}, "Выдать")}
            </AdminButton>
          </div>
        </Label.Root>
      </div>
    </section>
  {/if}

  <Label.Root class="admin-field-label">
    <span>{at("user_label_telegram_msg", {}, "Сообщение в Telegram")}</span>
    <small>{at("user_hint_telegram_msg", {}, "Поддерживается HTML-разметка Telegram")}</small>
    <Textarea
      class="admin-textarea"
      rows={3}
      placeholder={at("user_placeholder_msg", {}, "Текст сообщения")}
      bind:value={usersStore.userMessageDraft}
    />
  </Label.Root>
  <div class="admin-message-actions">
    <AdminButton
      onclick={usersStore.previewUserMessage}
      disabled={userActionBusy || !userMessageDraft.trim()}
    >
      <Eye size={14} />
      {at("btn_preview_tg", {}, "Превью в Telegram")}
    </AdminButton>
    <AdminButton
      variant="primary"
      data-admin-action="request-user-message"
      onclick={usersStore.requestSendUserMessage}
      disabled={userActionBusy || !userMessageDraft.trim()}
    >
      <Send size={14} />
      {at("btn_send_msg", {}, "Отправить сообщение")}
    </AdminButton>
  </div>

  <section class="admin-danger-zone">
    <header class="admin-danger-zone-head">
      <strong>{at("user_danger_zone_title", {}, "Опасные действия")}</strong>
      <small
        >{at(
          "user_danger_zone_subtitle",
          {},
          "Эти действия требуют подтверждения и (для удаления) необратимы"
        )}</small
      >
    </header>
    <div class="admin-action-grid">
      {#if openedUserIsBanned}
        <AdminButton
          variant="dangerSoft"
          data-admin-action="request-user-ban-toggle"
          onclick={usersStore.requestBanToggle}
          disabled={userActionBusy}
        >
          <UserPlus size={14} />
          {at("btn_unban", {}, "Разбанить пользователя")}
        </AdminButton>
      {:else}
        <AdminButton
          variant="danger"
          data-admin-action="request-user-ban-toggle"
          onclick={usersStore.requestBanToggle}
          disabled={userActionBusy}
        >
          <UserMinus size={14} />
          {at("btn_ban", {}, "Заблокировать")}
        </AdminButton>
      {/if}
      <AdminButton
        variant="danger"
        data-admin-action="request-user-delete"
        onclick={() => usersStore.updateState({ userDeleteOpen: true })}
        disabled={userActionBusy}
      >
        <Trash2 size={14} />
        {at("btn_delete_account", {}, "Удалить аккаунт")}
      </AdminButton>
    </div>
  </section>
</Tabs.Content>
