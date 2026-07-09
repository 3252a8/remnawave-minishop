<script lang="ts">
  import { Tabs } from "$components/ui/primitives.js";
  import UserDangerActionsCard from "./UserDangerActionsCard.svelte";
  import UserHwidLimitActionCard from "./UserHwidLimitActionCard.svelte";
  import UserQuickActionsBlock from "./UserQuickActionsBlock.svelte";
  import UserSquadOverridesActionCard from "./UserSquadOverridesActionCard.svelte";
  import UserTariffActionCard from "./UserTariffActionCard.svelte";
  import UserTelegramMessageActionCard from "./UserTelegramMessageActionCard.svelte";
  import UserTrafficGrantActionCard from "./UserTrafficGrantActionCard.svelte";
  import UserTrafficOverrideActionCard from "./UserTrafficOverrideActionCard.svelte";
  import UserTrafficStrategyActionCard from "./UserTrafficStrategyActionCard.svelte";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState";
  import type { SelectOption, TranslateFn } from "./userDetailTypes";

  type Props = {
    at: TranslateFn;
    openedUser?: AdminUser | null;
    openedUserDetail?: AdminUserDetail | null;
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

  const activeSubscription = $derived(openedUserDetail?.active_subscription ?? null);
  const extraHwidDevices = $derived(Number(activeSubscription?.extra_hwid_devices || 0));
  const openedUserIsBanned = $derived(Boolean(openedUser?.is_banned));
</script>

<Tabs.Content value="actions" class="admin-tabs-content admin-actions-tab">
  <UserQuickActionsBlock
    {at}
    {userActionBusy}
    {extendTariffItems}
    {extendTariffsLoading}
    {userExtendDaysValid}
    {userExtendTariffValid}
    {extendTariffRequired}
    {extraHwidDevices}
    {selectExtendTariff}
  />

  {#if activeSubscription}
    {#if periodTariffItems.length}
      <UserTariffActionCard
        {at}
        {userActionBusy}
        {periodTariffItems}
        {tariffActionDirty}
        {tariffHwidLimitChangeAvailable}
        {currentSubscriptionTariffLabel}
        {userTariffActionKey}
        {selectTariffAction}
      />
    {/if}

    <UserTrafficStrategyActionCard
      {at}
      {userActionBusy}
      {trafficStrategyItems}
      {trafficStrategyDirty}
      {trafficStrategyDraftValid}
      {trafficStrategyEditable}
      {trafficStrategyCurrentLabel}
      {trafficStrategyLockMessage}
      {selectTrafficStrategy}
    />

    <UserTrafficOverrideActionCard
      {at}
      kind="premium"
      {activeSubscription}
      {userActionBusy}
      dirty={premiumOverrideDirty}
      draftValid={premiumOverrideDraftValid}
      unlimitedDraft={premiumUnlimitedDraft}
    />

    <UserTrafficOverrideActionCard
      {at}
      kind="regular"
      {activeSubscription}
      {userActionBusy}
      dirty={regularOverrideDirty}
      draftValid={regularOverrideDraftValid}
      unlimitedDraft={regularUnlimitedDraft}
    />

    <UserHwidLimitActionCard
      {at}
      {activeSubscription}
      {userActionBusy}
      {hwidLimitDirty}
      {hwidLimitDraftValid}
      {hwidUnlimitedDraft}
      {hwidLimitLabel}
    />

    <UserTrafficGrantActionCard
      {at}
      {userActionBusy}
      {grantTrafficGbValid}
      {selectGrantTrafficKind}
    />
  {/if}

  <UserTelegramMessageActionCard {at} {userActionBusy} {userMessageDraft} />

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

  <UserDangerActionsCard {at} {openedUserIsBanned} {userActionBusy} />
</Tabs.Content>
