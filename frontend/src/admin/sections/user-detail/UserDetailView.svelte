<script lang="ts">
  import { Separator, Tabs } from "$components/ui/primitives.js";
  import Dialog from "$components/ui/dialog.svelte";
  import UserActionsTab from "./UserActionsTab.svelte";
  import UserLogsTab from "./UserLogsTab.svelte";
  import { AdminBadge, AdminButton, AdminTrafficCard } from "$components/patterns/admin/index.js";
  import { Copy, ExternalLink, UsersRound } from "$components/ui/icons.js";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type MoneyFormatter = (value: unknown, currency?: string | null) => string;
  type DateFormatter = (value: unknown) => string;
  type BadgeVariant = "success" | "danger" | "warning" | "muted";
  type SelectOption = { value: string; label: string };
  type UserLogRow = Record<string, unknown> & { log_id?: number | string };
  type UsersStoreBridge = {
    userDetailTab: string;
    copyToClipboard: (value: string | null | undefined, message?: string) => void;
    openUserReferrals: (page?: number) => void | Promise<void>;
    addUserInternalSquadOverride: () => void | Promise<void>;
    removeUserInternalSquadOverride: (squadUuid: string) => void | Promise<void>;
    refreshUserSquadOverrides: () => void | Promise<void>;
    saveUserExternalSquadOverride: () => void | Promise<void>;
  };

  let {
    at,
    usersStore,
    openedUser,
    openedUserDetail,
    userDetailLoading,
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
</script>

<Dialog
  open={Boolean(openedUser)}
  title={openedUser
    ? at("user_detail_title", { id: openedUser.user_id }, `Пользователь #${openedUser.user_id}`)
    : ""}
  description={openedUser?.username ? "@" + openedUser.username : ""}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={onClose}
  class="admin-dialog admin-user-dialog"
>
  {#if openedUser}
    {#if userDetailLoading || !openedUserDetail}
      <p class="admin-muted">{at("loading", {}, "Загрузка…")}</p>
    {:else}
      <div class="admin-user-dialog-body">
        <aside class="admin-user-aside">
          <div class="admin-user-summary">
            <button
              type="button"
              class="admin-avatar admin-avatar-lg admin-avatar-preview-trigger"
              class:is-clickable={Boolean(openedUserAvatarUrl)}
              disabled={!openedUserAvatarUrl}
              onclick={openAvatarPreview}
              aria-label={at("user_avatar_open", {}, "Открыть аватар")}
              title={openedUserAvatarUrl ? at("user_avatar_open", {}, "Открыть аватар") : ""}
            >
              {#if openedUserAvatarUrl}
                <img src={openedUserAvatarUrl} alt="" loading="lazy" referrerpolicy="no-referrer" />
              {:else}
                <span>{userInitials(openedUser)}</span>
              {/if}
            </button>
            <div class="admin-user-summary-meta">
              <strong>{userDisplayName(openedUser)}</strong>
              <small>{userSecondaryName(openedUser)}</small>
              <div class="admin-user-summary-tags">
                {#if openedUser.is_banned}
                  <AdminBadge variant="danger">{at("badge_banned", {}, "Бан")}</AdminBadge>
                {:else}
                  <AdminBadge variant="success">{at("badge_active", {}, "Активен")}</AdminBadge>
                {/if}
                {#if openedUserDetail.active_subscription}
                  <AdminBadge variant="success"
                    >{at("badge_subscription", {}, "Подписка")}</AdminBadge
                  >
                {:else}
                  <AdminBadge variant="muted"
                    >{at("badge_no_subscription", {}, "Без подписки")}</AdminBadge
                  >
                {/if}
              </div>
              <div class="admin-user-summary-actions">
                <AdminButton
                  size="sm"
                  variant="ghost"
                  onclick={openUserTelegramProfile}
                  disabled={!openedUserTelegramProfileLink}
                  title={openedUserTelegramProfileHint}
                  aria-label={at("user_open_tg_profile", {}, "Открыть профиль Telegram")}
                >
                  <ExternalLink size={14} />
                  {at("user_open_tg_profile", {}, "Открыть Telegram")}
                </AdminButton>
              </div>
            </div>
          </div>

          <div class="admin-user-stats">
            <div class="admin-user-stat">
              <span>{at("user_label_paid", {}, "Заплачено")}</span>
              <strong>{fmtMoney(openedUserDetail.total_paid)}</strong>
            </div>
            <div class="admin-user-stat">
              <span>{at("user_label_logs", {}, "Логов")}</span>
              <strong>{openedUserDetail.log_count}</strong>
            </div>
          </div>

          <div class="admin-subsection-title">{at("user_section_profile", {}, "Профиль")}</div>
          <ul class="admin-meta-list">
            <li><span>ID</span><strong>{openedUser.user_id}</strong></li>
            <li><span>Telegram ID</span><strong>{openedUser.telegram_id || "—"}</strong></li>
            <li>
              <span>Username</span><strong
                >{openedUser.username ? "@" + openedUser.username : "—"}</strong
              >
            </li>
            <li>
              <span>Email</span><strong class="admin-meta-truncate"
                >{openedUser.email || "—"}</strong
              >
            </li>
            <li>
              <span>{at("user_label_registration", {}, "Регистрация")}</span><strong
                >{fmtDate(openedUser.registration_date)}</strong
              >
            </li>
            <li>
              <span>{at("user_label_vpn_last_connected", {}, "Последнее VPN-подключение")}</span
              ><strong>{vpnLastConnectionLabel(openedUserDetail)}</strong>
            </li>
            <li>
              <span>{at("user_label_ref_code", {}, "Реф. код")}</span><strong
                >{openedUserDetail.referral?.code ||
                  openedUserDetail.user?.referral_code ||
                  "—"}</strong
              >
            </li>
            <li class="admin-user-ref-row">
              <span>{at("user_label_invited_by", {}, "Пригласил")}</span>
              <strong class="admin-user-ref-value">
                {#if referralInviter}
                  <span>{userDisplayName(referralInviter)}</span>
                  <small>ID {referralInviter.user_id}</small>
                {:else}
                  <span>{at("user_invited_by_none", {}, "—")}</span>
                {/if}
              </strong>
              {#if referralInviter}
                <AdminButton
                  size="icon"
                  variant="icon"
                  title={at("user_open_related", {}, "Открыть карточку")}
                  aria-label={at("user_open_related", {}, "Открыть карточку")}
                  onclick={() => openRelatedUser(referralInviter)}
                >
                  <ExternalLink size={14} />
                </AdminButton>
              {/if}
            </li>
            <li class="admin-user-ref-row">
              <span>{at("user_label_invited_users", {}, "Приглашённые")}</span>
              <strong>{referralInviteesTotal}</strong>
              <AdminButton
                data-admin-action="open-user-referrals"
                size="sm"
                variant="ghost"
                disabled={referralInviteesTotal <= 0}
                onclick={() => usersStore.openUserReferrals(0)}
              >
                <UsersRound size={14} />
                {at("user_invitees_open", {}, "Показать")}
              </AdminButton>
            </li>
          </ul>

          {#if openedUserDetail.subscription_url || openedUserDetail.install_share_url || openedUserDetail.referral?.bot_link || openedUserDetail.referral?.webapp_link}
            <div class="admin-subsection-title">{at("user_section_links", {}, "Ссылки")}</div>
            <div class="admin-link-list">
              {#if openedUserDetail.subscription_url}
                <div class="admin-link-row">
                  <div class="admin-link-row-meta">
                    <span class="admin-link-row-label"
                      >{at("status_subscription", {}, "Подписка")}</span
                    >
                    <a
                      class="admin-link-row-url"
                      href={openedUserDetail.subscription_url}
                      target="_blank"
                      rel="noopener"
                    >
                      {openedUserDetail.subscription_url}
                    </a>
                  </div>
                  <AdminButton
                    size="icon"
                    variant="icon"
                    title={at("user_copy_tooltip", {}, "Скопировать")}
                    onclick={() =>
                      usersStore.copyToClipboard(
                        openedUserDetail.subscription_url,
                        at("user_sub_link_copied", {}, "Ссылка на подписку скопирована")
                      )}
                  >
                    <Copy size={14} />
                  </AdminButton>
                </div>
              {/if}
              {#if openedUserDetail.install_share_url}
                <div class="admin-link-row">
                  <div class="admin-link-row-meta">
                    <span class="admin-link-row-label"
                      >{at("user_label_install_share", {}, "Install guide")}</span
                    >
                    <a
                      class="admin-link-row-url"
                      href={openedUserDetail.install_share_url}
                      target="_blank"
                      rel="noopener"
                    >
                      {openedUserDetail.install_share_url}
                    </a>
                  </div>
                  <AdminButton
                    size="icon"
                    variant="icon"
                    title={at("user_copy_tooltip", {}, "Copy")}
                    onclick={() =>
                      usersStore.copyToClipboard(
                        openedUserDetail.install_share_url,
                        at("user_install_share_link_copied", {}, "Install guide link copied")
                      )}
                  >
                    <Copy size={14} />
                  </AdminButton>
                </div>
              {/if}
              {#if openedUserDetail.referral?.bot_link}
                <div class="admin-link-row">
                  <div class="admin-link-row-meta">
                    <span class="admin-link-row-label"
                      >{at("user_label_ref_bot", {}, "Реф. ссылка (бот)")}</span
                    >
                    <a
                      class="admin-link-row-url"
                      href={openedUserDetail.referral.bot_link}
                      target="_blank"
                      rel="noopener"
                    >
                      {openedUserDetail.referral.bot_link}
                    </a>
                  </div>
                  <AdminButton
                    size="icon"
                    variant="icon"
                    title={at("user_copy_tooltip", {}, "Скопировать")}
                    onclick={() =>
                      usersStore.copyToClipboard(
                        openedUserDetail.referral.bot_link,
                        at("user_ref_link_copied", {}, "Реф. ссылка скопирована")
                      )}
                  >
                    <Copy size={14} />
                  </AdminButton>
                </div>
              {/if}
              {#if openedUserDetail.referral?.webapp_link}
                <div class="admin-link-row">
                  <div class="admin-link-row-meta">
                    <span class="admin-link-row-label"
                      >{at("user_label_ref_web", {}, "Реф. ссылка (веб)")}</span
                    >
                    <a
                      class="admin-link-row-url"
                      href={openedUserDetail.referral.webapp_link}
                      target="_blank"
                      rel="noopener"
                    >
                      {openedUserDetail.referral.webapp_link}
                    </a>
                  </div>
                  <AdminButton
                    size="icon"
                    variant="icon"
                    title={at("user_copy_tooltip", {}, "Скопировать")}
                    onclick={() =>
                      usersStore.copyToClipboard(
                        openedUserDetail.referral.webapp_link,
                        at("user_ref_link_copied", {}, "Реф. ссылка скопирована")
                      )}
                  >
                    <Copy size={14} />
                  </AdminButton>
                </div>
              {/if}
            </div>
          {/if}
        </aside>

        <main class="admin-user-main">
          <Tabs.Root
            bind:value={usersStore.userDetailTab}
            class="admin-tabs-root admin-user-tabs-root"
          >
            <Tabs.List class="admin-tabs-list">
              <Tabs.Trigger value="subscription" class="admin-tabs-trigger"
                >{at("user_tab_subscription", {}, "Подписка")}</Tabs.Trigger
              >
              <Tabs.Trigger value="activity" class="admin-tabs-trigger"
                >{at("user_tab_activity", {}, "Активность")}</Tabs.Trigger
              >
              <Tabs.Trigger value="logs" class="admin-tabs-trigger"
                >{at("user_tab_logs", {}, "Логи")}</Tabs.Trigger
              >
              <Tabs.Trigger value="actions" class="admin-tabs-trigger"
                >{at("user_tab_actions", {}, "Действия")}</Tabs.Trigger
              >
            </Tabs.List>

            <Tabs.Content value="subscription" class="admin-tabs-content">
              {#if openedUserDetail.active_subscription}
                <ul class="admin-meta-list">
                  <li>
                    <span>{at("user_label_active_until", {}, "Активна до")}</span><strong
                      >{fmtDate(openedUserDetail.active_subscription.end_date)}</strong
                    >
                  </li>
                  <li>
                    <span>{at("user_label_tariff", {}, "Тариф")}</span><strong
                      >{subscriptionDisplayLabel(openedUserDetail.active_subscription)}</strong
                    >
                  </li>
                  <li>
                    <span>{at("user_label_auto_renew", {}, "Авто-продление")}</span><strong
                      >{pretty(openedUserDetail.active_subscription.auto_renew_enabled)}</strong
                    >
                  </li>
                  <li>
                    <span>{at("user_label_provider", {}, "Провайдер")}</span><strong
                      >{openedUserDetail.active_subscription.provider || "—"}</strong
                    >
                  </li>
                  <li>
                    <span>{at("user_label_hwid_devices", {}, "HWID-устройства")}</span><strong
                      >{hwidLimitLabel(openedUserDetail.active_subscription)}</strong
                    >
                  </li>
                </ul>
                <div class="admin-traffic-summary">
                  <AdminTrafficCard
                    title={at("user_label_main_traffic", {}, "Основной трафик")}
                    value={trafficOfLabel(
                      openedUserDetail.active_subscription.traffic_used_bytes,
                      openedUserDetail.active_subscription.traffic_limit_bytes
                    )}
                    left={at(
                      "user_traffic_left",
                      {
                        left: trafficLeftLabel(
                          openedUserDetail.active_subscription.traffic_used_bytes,
                          openedUserDetail.active_subscription.traffic_limit_bytes
                        ),
                      },
                      "Осталось: " +
                        trafficLeftLabel(
                          openedUserDetail.active_subscription.traffic_used_bytes,
                          openedUserDetail.active_subscription.traffic_limit_bytes
                        )
                    )}
                    percent={trafficPercentValue(
                      openedUserDetail.active_subscription.traffic_used_bytes,
                      openedUserDetail.active_subscription.traffic_limit_bytes
                    )}
                    warning={openedUserDetail.active_subscription.is_throttled}
                    label={at("aria_label_main_traffic", {}, "Использование основного трафика")}
                  />
                  {#if openedUserDetail.active_subscription.premium_unlimited_override}
                    <AdminTrafficCard
                      premium
                      title={at("user_label_premium_squads", {}, "Premium-сквады")}
                      value={at(
                        "user_premium_unlimited_value",
                        {
                          used: trafficLeftLabel(
                            0,
                            openedUserDetail.active_subscription.premium_used_bytes
                          ),
                        },
                        "∞ (использовано " +
                          trafficLeftLabel(
                            0,
                            openedUserDetail.active_subscription.premium_used_bytes
                          ) +
                          ")"
                      )}
                      left={at("user_premium_unlimited_hint", {}, "Безлимит (админ-оверрайд)")}
                      percent={0}
                      warning={false}
                      label={at("aria_label_premium_traffic", {}, "Использование premium-трафика")}
                    />
                  {:else if Number(openedUserDetail.active_subscription.premium_limit_bytes || 0) > 0}
                    <AdminTrafficCard
                      premium
                      title={at("user_label_premium_squads", {}, "Premium-сквады")}
                      value={trafficOfLabel(
                        openedUserDetail.active_subscription.premium_used_bytes,
                        openedUserDetail.active_subscription.premium_limit_bytes
                      )}
                      left={at(
                        "user_traffic_left",
                        {
                          left: trafficLeftLabel(
                            openedUserDetail.active_subscription.premium_used_bytes,
                            openedUserDetail.active_subscription.premium_limit_bytes
                          ),
                        },
                        "Осталось: " +
                          trafficLeftLabel(
                            openedUserDetail.active_subscription.premium_used_bytes,
                            openedUserDetail.active_subscription.premium_limit_bytes
                          )
                      )}
                      percent={trafficPercentValue(
                        openedUserDetail.active_subscription.premium_used_bytes,
                        openedUserDetail.active_subscription.premium_limit_bytes
                      )}
                      warning={openedUserDetail.active_subscription.premium_is_limited}
                      label={at("aria_label_premium_traffic", {}, "Использование premium-трафика")}
                    />
                  {/if}
                </div>
              {:else}
                <p class="admin-muted">
                  {at("user_no_active_subscription", {}, "Активной подписки нет")}
                </p>
              {/if}

              {#if openedUserDetail?.trial}
                <ul class="admin-meta-list">
                  <li>
                    <span>{at("user_label_trial", {}, "Пробник / триал")}</span><strong
                      >{trialSummaryText(openedUserDetail.trial)}</strong
                    >
                  </li>
                  {#if openedUserDetail.trial.used && openedUserDetail.trial.latest_end_date}
                    <li>
                      <span>{at("user_label_trial_until", {}, "Триал до")}</span><strong
                        >{fmtDate(openedUserDetail.trial.latest_end_date)}</strong
                      >
                    </li>
                  {/if}
                  {#if Number(openedUserDetail.trial.count || 0) > 1}
                    <li>
                      <span>{at("user_label_trial_count", {}, "Триалов")}</span><strong
                        >{openedUserDetail.trial.count}</strong
                      >
                    </li>
                  {/if}
                  {#if openedUserDetail.trial.last_reset_at}
                    <li>
                      <span>{at("user_label_trial_reset_at", {}, "Сброс триала")}</span><strong
                        >{fmtDate(openedUserDetail.trial.last_reset_at)}</strong
                      >
                    </li>
                  {/if}
                </ul>
              {/if}

              {#if (openedUserDetail.subscriptions || []).length}
                <Separator.Root class="admin-separator" />
                <div class="admin-subsection-title">
                  {at(
                    "user_history_title",
                    { count: openedUserDetail.subscriptions.length },
                    `История подписок · ${openedUserDetail.subscriptions.length}`
                  )}
                </div>
                <div class="admin-mini-list">
                  {#each openedUserDetail.subscriptions.slice(0, 8) as sub}
                    <div class="admin-mini-list-row">
                      <div>
                        <strong>{subscriptionDisplayLabel(sub)}</strong>
                        <small
                          >{at(
                            "user_history_until",
                            { date: fmtDate(sub.end_date) },
                            `до ${fmtDate(sub.end_date)}`
                          )}</small
                        >
                      </div>
                      {#if sub.is_active}
                        <AdminBadge variant="success"
                          >{at("user_history_active", {}, "Активна")}</AdminBadge
                        >
                      {:else}
                        <AdminBadge variant="muted"
                          >{sub.status_from_panel ||
                            at("user_history_status_panel", {}, "История")}</AdminBadge
                        >
                      {/if}
                    </div>
                  {/each}
                </div>
              {/if}
            </Tabs.Content>

            <Tabs.Content value="activity" class="admin-tabs-content">
              <div class="admin-subsection-title">
                {at(
                  "user_recent_payments_title",
                  { count: (openedUserDetail.recent_payments || []).length },
                  `Последние платежи · ${(openedUserDetail.recent_payments || []).length}`
                )}
              </div>
              {#if (openedUserDetail.recent_payments || []).length}
                <div class="admin-mini-list">
                  {#each openedUserDetail.recent_payments.slice(0, 8) as payment}
                    <div class="admin-mini-list-row">
                      <div>
                        <strong>{fmtMoney(payment.amount, payment.currency)}</strong>
                        <small>{payment.provider} · {fmtDateShort(payment.created_at)}</small>
                      </div>
                      <AdminBadge variant={paymentStatusVariant(payment.status)}
                        >{payment.status}</AdminBadge
                      >
                    </div>
                  {/each}
                </div>
              {:else}
                <p class="admin-muted">{at("user_no_payments", {}, "Платежей нет")}</p>
              {/if}
            </Tabs.Content>

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
          </Tabs.Root>
        </main>
      </div>
    {/if}
  {/if}
</Dialog>
