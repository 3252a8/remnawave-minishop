<script lang="ts">
  import { AdminButton } from "$components/patterns/admin/index.js";
  import { RefreshCw } from "$components/ui/icons.js";
  import UserDetailLinks from "./UserDetailLinks.svelte";
  import UserDetailStats from "./UserDetailStats.svelte";
  import UserDetailHero from "./UserDetailHero.svelte";
  import UserQuickActionsBlock from "./UserQuickActionsBlock.svelte";
  import { Tabs } from "$components/ui/primitives.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { getSettingsStore } from "$lib/admin/context";
  import { ADMIN_USER_DETAIL_PANELS, adminExtensionRevision } from "../extensionRegistry";
  import { isFeatureBoundDescriptorVisible, requiredFeatureForDescriptor } from "../extensionTypes";
  import UserActivityTab from "./UserActivityTab.svelte";
  import UserActionsTab from "./UserActionsTab.svelte";
  import UserMessageComposerCard from "./UserMessageComposerCard.svelte";
  import UserNotificationPreferencesCard from "./UserNotificationPreferencesCard.svelte";
  import UserDetailFacts from "./UserDetailFacts.svelte";
  import UserNotificationSummaryCard from "./UserNotificationSummaryCard.svelte";
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
    onRetry,
    openedUserAvatarUrl,
    openAvatarPreview,
    userInitials,
    userDisplayName,
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
    onOpenPaymentCard,
    onOpenPartnerCard,
    userLogsRows,
    userLogsTotal,
    userLogsPage,
    userLogsPageCount,
    userLogsPageSize,
    userLogsLoading,
    userLogsLoaded,
    userActionBusy,
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
    onRetry: () => void;
    openedUserAvatarUrl: string;
    openAvatarPreview: () => void;
    userInitials: (user: AdminUser) => string;
    userDisplayName: (user: AdminUser) => string;
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
    onOpenPaymentCard: (paymentId: number) => void;
    onOpenPartnerCard: (partnerId: string) => void;
    userLogsRows: readonly UserLogRow[];
    userLogsTotal: number;
    userLogsPage: number;
    userLogsPageCount: number;
    userLogsPageSize: number;
    userLogsLoading: boolean;
    userLogsLoaded: boolean;
    userActionBusy: boolean;
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

  let notificationsOpen = $state(false);
  $effect(() => {
    void openedUser?.user_id;
    notificationsOpen = false;
  });

  const availableFeatures = $derived(new Set<string>((settingsStore.features || []) as string[]));
  const visibleExtensionPanels = $derived.by(() => {
    void $adminExtensionRevision;
    return ADMIN_USER_DETAIL_PANELS.filter((panel) =>
      isFeatureBoundDescriptorVisible(panel, availableFeatures)
    );
  });
  const visibleExtensionPanelTabs = $derived(
    new Set(visibleExtensionPanels.map((panel) => `extension:${panel.id}`))
  );

  $effect(() => {
    const selected = String(usersStore.userDetailTab || "");
    if (selected === "notifications") {
      notificationsOpen = true;
      usersStore.userDetailTab = "subscription";
    }
    if (selected.startsWith("extension:") && !visibleExtensionPanelTabs.has(selected)) {
      usersStore.userDetailTab = "subscription";
    }
  });
</script>

{#if openedUser}
  <section
    class="admin-user-detail-page"
    aria-label={at("user_detail_title", { id: openedUser.minishop_id || "—" }, "User {id}")}
  >
    <UserDetailHero
      {at}
      {usersStore}
      {openedUser}
      {openedUserDetail}
      {openedUserAvatarUrl}
      {openAvatarPreview}
      {userInitials}
      {userDisplayName}
      {fmtDate}
      {openUserTelegramProfile}
      {openedUserTelegramProfileLink}
      {openedUserTelegramProfileHint}
    >
      {#snippet details()}
        {#if openedUserDetail}
          <UserDetailFacts
            {at}
            {usersStore}
            {openedUser}
            {openedUserDetail}
            {userDisplayName}
            {fmtDate}
            {vpnLastConnectionLabel}
            {referralInviter}
            {referralInviteesTotal}
            {openRelatedUser}
            {onOpenPartnerCard}
          />
          <UserNotificationSummaryCard
            {at}
            {openedUserDetail}
            onEditNotifications={() => (notificationsOpen = true)}
          />
        {/if}
      {/snippet}
    </UserDetailHero>
    {#if openedUserDetail}
      <UserDetailLinks {at} {usersStore} {openedUserDetail} />
    {/if}
    <UserDetailStats {at} {openedUser} {openedUserDetail} {fmtMoney} />
    {#if userDetailLoading}
      <div class="admin-user-page-state" aria-busy="true" aria-live="polite">
        <p class="admin-muted">{at("loading", {}, "Loading…")}</p>
        <span class="admin-skeleton admin-skeleton-line"></span>
        <span class="admin-skeleton admin-skeleton-line"></span>
      </div>
    {:else if !openedUserDetail}
      <div class="admin-user-page-state" role="alert">
        <p>{at("user_detail_load_failed", {}, "Unable to load this user. Try again.")}</p>
        <AdminButton onclick={onRetry}
          ><RefreshCw size={14} />{at("user_detail_retry", {}, "Try again")}</AdminButton
        >
      </div>
    {:else}
      <div class="admin-user-detail-body">
        <div class="admin-user-main admin-user-detail-main">
          <Tabs.Root
            bind:value={usersStore.userDetailTab}
            class="admin-tabs-root admin-user-tabs-root"
          >
            <Tabs.List class="admin-tabs-list">
              <Tabs.Trigger value="subscription" class="admin-tabs-trigger"
                >{at("user_tab_subscription", {}, "Subscription")}</Tabs.Trigger
              >
              <Tabs.Trigger value="actions" class="admin-tabs-trigger"
                >{at("user_tab_actions", {}, "Actions")}</Tabs.Trigger
              >
              <Tabs.Trigger value="activity" class="admin-tabs-trigger"
                >{at("user_tab_activity", {}, "Payments")}</Tabs.Trigger
              >
              <Tabs.Trigger value="logs" class="admin-tabs-trigger"
                >{at("user_tab_logs", {}, "Logs")}</Tabs.Trigger
              >
              <Tabs.Trigger value="message" class="admin-tabs-trigger"
                >{at("user_tab_message", {}, "Message")}</Tabs.Trigger
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
            >
              {#snippet quickActions()}
                <UserQuickActionsBlock
                  {at}
                  {userActionBusy}
                  {extendTariffItems}
                  {extendTariffsLoading}
                  {userExtendDaysValid}
                  {userExtendTariffValid}
                  {extendTariffRequired}
                  extraHwidDevices={Number(
                    openedUserDetail.active_subscription?.extra_hwid_devices || 0
                  )}
                  activeSubscriptionEndDate={String(
                    openedUserDetail.active_subscription?.end_date || ""
                  )}
                  {selectExtendTariff}
                />
              {/snippet}
            </UserSubscriptionTab>

            <UserActivityTab
              {at}
              {openedUserDetail}
              {fmtMoney}
              {fmtDateShort}
              {paymentStatusVariant}
              {onOpenPaymentCard}
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
              {fmtDate}
              {openedUser}
              {openedUserDetail}
              {userActionBusy}
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

            <Tabs.Content value="message" class="admin-tabs-content">
              <UserMessageComposerCard
                {at}
                userId={openedUser?.user_id ?? null}
                hasTelegram={Boolean(openedUser?.telegram_id)}
                hasEmail={Boolean(openedUser?.email)}
              />
            </Tabs.Content>

            {#each visibleExtensionPanels as panel (panel.id)}
              {@const PanelComponent = panel.component}
              {@const requiredFeature = requiredFeatureForDescriptor(panel)}
              <Tabs.Content value={`extension:${panel.id}`} class="admin-tabs-content">
                {#key `${panel.id}:${panel.runtimeDigest || ""}`}
                  <PanelComponent
                    runtimeViewId={panel.runtimeViewId}
                    runtimeEntry={panel.runtimeEntry}
                    {at}
                    user={openedUser}
                    userDetail={openedUserDetail}
                    featureAvailable={!requiredFeature || availableFeatures.has(requiredFeature)}
                    active={usersStore.userDetailTab === `extension:${panel.id}`}
                    {routePrefix}
                  />
                {/key}
              </Tabs.Content>
            {/each}
          </Tabs.Root>
        </div>
      </div>
    {/if}
  </section>
{/if}

<Dialog
  open={notificationsOpen && Boolean(openedUserDetail)}
  title={at("user_notifications_title", {}, "Notification preferences")}
  closeLabel={at("close", {}, "Close")}
  onclose={() => (notificationsOpen = false)}
  class="admin-dialog admin-user-notifications-dialog"
>
  {#if openedUserDetail}
    <UserNotificationPreferencesCard {at} {usersStore} {openedUserDetail} busy={userActionBusy} />
  {/if}
</Dialog>
