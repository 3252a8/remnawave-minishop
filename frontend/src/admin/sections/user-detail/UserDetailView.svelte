<script lang="ts">
  import { Tabs } from "$components/ui/primitives.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { getSettingsStore } from "$lib/admin/context";
  import { ADMIN_USER_DETAIL_PANELS } from "../extensionRegistry";
  import { isFeatureBoundDescriptorVisible, requiredFeatureForDescriptor } from "../extensionTypes";
  import UserActivityTab from "./UserActivityTab.svelte";
  import UserActionsTab from "./UserActionsTab.svelte";
  import UserDetailAside from "./UserDetailAside.svelte";
  import UserLogsTab from "./UserLogsTab.svelte";
  import UserSubscriptionTab from "./UserSubscriptionTab.svelte";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState";
  import type {
    BadgeVariant,
    DateFormatter,
    MoneyFormatter,
    SelectOption,
    TranslateFn,
    UserLogRow,
    UsersStoreBridge,
  } from "./userDetailTypes";

  const settingsStore = getSettingsStore();

  let {
    at,
    usersStore,
    openedUser,
    openedUserDetail,
    userDetailLoading,
    routePrefix,
    onClose,
    openedUserAvatarUrl,
    openAvatarPreview,
    userInitials,
    userDisplayName,
    userSecondaryName,
    openUserTelegramProfile,
    openedUserTelegramProfileLink,
    openedUserTelegramProfileHint,
    fmtMoney,
    fmtDate,
    vpnLastConnectionLabel,
    referralInviter,
    referralInviteesTotal,
    openRelatedUser,
    subscriptionDisplayLabel,
    pretty,
    hwidLimitLabel,
    trafficOfLabel,
    trafficLeftLabel,
    trafficPercentValue,
    trialSummaryText,
    fmtDateShort,
    paymentStatusVariant,
    userLogsRows,
    userLogsTotal,
    userLogsPage,
    userLogsPageCount,
    userLogsPageSize,
    userLogsLoading,
    userLogsLoaded,
    userActionBusy,
    userMessageDraft,
    extendTariffItems,
    extendTariffsLoading,
    userExtendDaysValid,
    userExtendTariffValid,
    extendTariffRequired,
    selectExtendTariff,
    periodTariffItems,
    tariffActionDirty,
    tariffHwidLimitChangeAvailable,
    currentSubscriptionTariffLabel,
    userTariffActionKey,
    selectTariffAction,
    trafficStrategyItems,
    trafficStrategyDirty,
    trafficStrategyDraftValid,
    trafficStrategyEditable,
    trafficStrategyCurrentLabel,
    trafficStrategyLockMessage,
    selectTrafficStrategy,
    premiumOverrideDirty,
    premiumOverrideDraftValid,
    premiumUnlimitedDraft,
    regularOverrideDirty,
    regularOverrideDraftValid,
    regularUnlimitedDraft,
    hwidLimitDirty,
    hwidLimitDraftValid,
    hwidUnlimitedDraft,
    selectGrantTrafficKind,
    grantTrafficGbValid,
    panelSquadItems,
    squadLabel,
    userSquadOverrideDraft,
    selectUserSquadOverride,
    userExternalSquadModeDraft,
    selectUserExternalSquadMode,
    userExternalSquadUuidDraft,
    updateUserExternalSquadUuid,
  }: {
    at: TranslateFn;
    usersStore: UsersStoreBridge;
    openedUser: AdminUser | null;
    openedUserDetail: AdminUserDetail | null;
    userDetailLoading: boolean;
    routePrefix: string;
    onClose: () => void;
    openedUserAvatarUrl: string;
    openAvatarPreview: () => void;
    userInitials: (user: AdminUser) => string;
    userDisplayName: (user: AdminUser) => string;
    userSecondaryName: (user: AdminUser) => string;
    openUserTelegramProfile: () => void;
    openedUserTelegramProfileLink: string;
    openedUserTelegramProfileHint: string;
    fmtMoney: MoneyFormatter;
    fmtDate: DateFormatter;
    vpnLastConnectionLabel: (detail: Record<string, unknown> | null | undefined) => string;
    referralInviter: AdminUser | null;
    referralInviteesTotal: number;
    openRelatedUser: (user: AdminUser | null | undefined) => void;
    subscriptionDisplayLabel: (sub: Record<string, unknown> | null | undefined) => string;
    pretty: (value: unknown) => string;
    hwidLimitLabel: (sub: Record<string, unknown> | null | undefined) => string;
    trafficOfLabel: (used: unknown, limit: unknown) => string;
    trafficLeftLabel: (used: unknown, limit: unknown) => string;
    trafficPercentValue: (left: unknown, total: unknown) => number;
    trialSummaryText: (trial: Record<string, unknown> | null | undefined) => string;
    fmtDateShort: DateFormatter;
    paymentStatusVariant: (status: unknown) => BadgeVariant;
    userLogsRows: readonly UserLogRow[];
    userLogsTotal: number;
    userLogsPage: number;
    userLogsPageCount: number;
    userLogsPageSize: number;
    userLogsLoading: boolean;
    userLogsLoaded: boolean;
    userActionBusy: boolean;
    userMessageDraft: string;
    extendTariffItems: SelectOption[];
    extendTariffsLoading: boolean;
    userExtendDaysValid: boolean;
    userExtendTariffValid: boolean;
    extendTariffRequired: boolean;
    selectExtendTariff: (value: string) => void;
    periodTariffItems: SelectOption[];
    tariffActionDirty: boolean;
    tariffHwidLimitChangeAvailable: boolean;
    currentSubscriptionTariffLabel: string;
    userTariffActionKey: string;
    selectTariffAction: (value: string) => void;
    trafficStrategyItems: SelectOption[];
    trafficStrategyDirty: boolean;
    trafficStrategyDraftValid: boolean;
    trafficStrategyEditable: boolean;
    trafficStrategyCurrentLabel: string;
    trafficStrategyLockMessage: string;
    selectTrafficStrategy: (value: string) => void;
    premiumOverrideDirty: boolean;
    premiumOverrideDraftValid: boolean;
    premiumUnlimitedDraft: boolean;
    regularOverrideDirty: boolean;
    regularOverrideDraftValid: boolean;
    regularUnlimitedDraft: boolean;
    hwidLimitDirty: boolean;
    hwidLimitDraftValid: boolean;
    hwidUnlimitedDraft: boolean;
    selectGrantTrafficKind: (value: string) => void;
    grantTrafficGbValid: boolean;
    panelSquadItems: SelectOption[];
    squadLabel: (uuid: string) => string;
    userSquadOverrideDraft: string;
    selectUserSquadOverride: (value: string) => void;
    userExternalSquadModeDraft: "inherit" | "set" | "cleared";
    selectUserExternalSquadMode: (value: string) => void;
    userExternalSquadUuidDraft: string;
    updateUserExternalSquadUuid: (value: string) => void;
  } = $props();

  const availableFeatures = $derived(new Set<string>((settingsStore.features || []) as string[]));
  const visibleExtensionPanels = $derived(
    ADMIN_USER_DETAIL_PANELS.filter((panel) =>
      isFeatureBoundDescriptorVisible(panel, availableFeatures)
    )
  );
  const visibleExtensionPanelTabs = $derived(
    new Set(visibleExtensionPanels.map((panel) => `extension:${panel.id}`))
  );

  $effect(() => {
    const selected = String(usersStore.userDetailTab || "");
    if (selected.startsWith("extension:") && !visibleExtensionPanelTabs.has(selected)) {
      usersStore.userDetailTab = "subscription";
    }
  });
</script>

<Dialog
  open={Boolean(openedUser)}
  title={openedUser ? at("user_detail_title", { id: openedUser.user_id }, "User #{id}") : ""}
  description={openedUser?.username ? "@" + openedUser.username : ""}
  closeLabel={at("close", {}, "Close")}
  onclose={onClose}
  class="admin-dialog admin-user-dialog"
>
  {#if openedUser}
    {#if userDetailLoading || !openedUserDetail}
      <p class="admin-muted">{at("loading", {}, "Loading…")}</p>
    {:else}
      <div class="admin-user-dialog-body">
        <UserDetailAside
          {at}
          {usersStore}
          {openedUser}
          {openedUserDetail}
          {openedUserAvatarUrl}
          {openAvatarPreview}
          {userInitials}
          {userDisplayName}
          {userSecondaryName}
          {openUserTelegramProfile}
          {openedUserTelegramProfileLink}
          {openedUserTelegramProfileHint}
          {fmtMoney}
          {fmtDate}
          {vpnLastConnectionLabel}
          {referralInviter}
          {referralInviteesTotal}
          {openRelatedUser}
        />

        <main class="admin-user-main">
          <Tabs.Root
            bind:value={usersStore.userDetailTab}
            class="admin-tabs-root admin-user-tabs-root"
          >
            <Tabs.List class="admin-tabs-list">
              <Tabs.Trigger value="subscription" class="admin-tabs-trigger"
                >{at("user_tab_subscription", {}, "Subscription")}</Tabs.Trigger
              >
              <Tabs.Trigger value="activity" class="admin-tabs-trigger"
                >{at("user_tab_activity", {}, "Activity")}</Tabs.Trigger
              >
              <Tabs.Trigger value="logs" class="admin-tabs-trigger"
                >{at("user_tab_logs", {}, "Logs")}</Tabs.Trigger
              >
              <Tabs.Trigger value="actions" class="admin-tabs-trigger"
                >{at("user_tab_actions", {}, "Actions")}</Tabs.Trigger
              >
              {#each visibleExtensionPanels as panel (panel.id)}
                <Tabs.Trigger value={`extension:${panel.id}`} class="admin-tabs-trigger">
                  {at(panel.i18nKey, {}, panel.fallbackLabel)}
                </Tabs.Trigger>
              {/each}
            </Tabs.List>

            <UserSubscriptionTab
              {at}
              {openedUserDetail}
              {fmtDate}
              {subscriptionDisplayLabel}
              {pretty}
              {hwidLimitLabel}
              {trafficOfLabel}
              {trafficLeftLabel}
              {trafficPercentValue}
              {trialSummaryText}
            />

            <UserActivityTab
              {at}
              {openedUserDetail}
              {fmtMoney}
              {fmtDateShort}
              {paymentStatusVariant}
            />

            <UserLogsTab
              {at}
              {fmtDate}
              {openedUser}
              {userLogsRows}
              {userLogsTotal}
              {userLogsPage}
              {userLogsPageCount}
              {userLogsPageSize}
              {userLogsLoading}
              {userLogsLoaded}
            />

            <UserActionsTab
              {at}
              {openedUser}
              {openedUserDetail}
              {userActionBusy}
              {userMessageDraft}
              {extendTariffItems}
              {extendTariffsLoading}
              {userExtendDaysValid}
              {userExtendTariffValid}
              {extendTariffRequired}
              {selectExtendTariff}
              {periodTariffItems}
              {tariffActionDirty}
              {tariffHwidLimitChangeAvailable}
              {currentSubscriptionTariffLabel}
              {userTariffActionKey}
              {selectTariffAction}
              {trafficStrategyItems}
              {trafficStrategyDirty}
              {trafficStrategyDraftValid}
              {trafficStrategyEditable}
              {trafficStrategyCurrentLabel}
              {trafficStrategyLockMessage}
              {selectTrafficStrategy}
              {premiumOverrideDirty}
              {premiumOverrideDraftValid}
              {premiumUnlimitedDraft}
              {regularOverrideDirty}
              {regularOverrideDraftValid}
              {regularUnlimitedDraft}
              {hwidLimitDirty}
              {hwidLimitDraftValid}
              {hwidUnlimitedDraft}
              {hwidLimitLabel}
              {selectGrantTrafficKind}
              {grantTrafficGbValid}
              {panelSquadItems}
              {squadLabel}
              {userSquadOverrideDraft}
              {selectUserSquadOverride}
              {userExternalSquadModeDraft}
              {selectUserExternalSquadMode}
              {userExternalSquadUuidDraft}
              {updateUserExternalSquadUuid}
            />

            {#each visibleExtensionPanels as panel (panel.id)}
              {@const PanelComponent = panel.component}
              {@const requiredFeature = requiredFeatureForDescriptor(panel)}
              <Tabs.Content value={`extension:${panel.id}`} class="admin-tabs-content">
                <PanelComponent
                  {at}
                  user={openedUser}
                  userDetail={openedUserDetail}
                  featureAvailable={!requiredFeature || availableFeatures.has(requiredFeature)}
                  active={usersStore.userDetailTab === `extension:${panel.id}`}
                  {routePrefix}
                />
              </Tabs.Content>
            {/each}
          </Tabs.Root>
        </main>
      </div>
    {/if}
  {/if}
</Dialog>
