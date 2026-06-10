<script>
  import { Label, Separator, Tabs } from "$components/ui/primitives.js";
  import { Checkbox, Input, ScrollArea, Textarea } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminPagination,
    AdminSectionHeader,
    AdminSelect,
    AdminTable,
    AdminTableSkeleton,
    AdminTrafficCard,
  } from "$components/patterns/admin/index.js";
  import {
    Copy,
    Eye,
    ExternalLink,
    RefreshCw,
    Send,
    Plus,
    Trash2,
    UserMinus,
    UserPlus,
    UsersRound,
  } from "$components/ui/icons.js";
  import { getContext } from "svelte";

  export let at;
  export let fmtDate;
  export let fmtMoney;
  export let resolvedAvatarUrl;
  export let userDisplayName;
  export let userSecondaryName;
  export let paymentStatusVariant;
  export let trafficPercentValue;
  export let trafficLeftLabel;
  export let trafficOfLabel;
  export let userInitials = () => "";
  export let fmtDateShort = (v) => v;
  export let userTelegramProfileLink = () => "";
  export let userTelegramProfileLinkKind = () => "";
  export let openTelegramProfileLink = () => false;
  export let onClose = () => usersStore.closeUser();

  let avatarPreviewOpen = false;
  let avatarPreviewUrl = "";
  let avatarPreviewName = "";

  function pretty(val) {
    if (val === true) return at("yes", {}, "Да");
    if (val === false) return at("no", {}, "Нет");
    return String(val ?? "—");
  }

  function isTrialSubscription(sub) {
    return Boolean(sub?.is_trial || String(sub?.provider || "").toLowerCase() === "trial");
  }

  function subscriptionDisplayLabel(sub) {
    if (!sub) return "—";
    if (isTrialSubscription(sub)) return at("user_subscription_trial", {}, "Триал");
    if (sub.display_label) return sub.display_label;
    return sub.tariff_name || sub.tariff_key || at("user_history_no_tariff", {}, "Без тарифа");
  }

  function trialSummaryText(trial) {
    if (!trial?.used) return at("user_trial_not_used", {}, "Не брал");
    const date = trial.latest_activated_at || trial.first_activated_at;
    const base = date
      ? at("user_trial_used_at", { date: fmtDate(date) }, `Брал ${fmtDate(date)}`)
      : at("user_trial_used", {}, "Брал");
    return trial.active ? `${base} · ${at("user_trial_active", {}, "активен")}` : base;
  }

  function hwidLimitLabel(sub) {
    const rawBase = sub?.hwid_device_limit;
    const hasBase = rawBase !== null && rawBase !== undefined;
    const extra = Math.max(0, Number(sub?.extra_hwid_devices || 0));
    if (!hasBase) return at("user_hwid_limit_default", {}, "Тарифный / default");
    const base = Number(rawBase);
    if (base === 0) return at("user_hwid_limit_unlimited", {}, "Безлимит");
    if (extra > 0) {
      return at(
        "user_hwid_limit_with_extra",
        { base, extra, total: base + extra },
        `${base + extra} (${base} + ${extra})`
      );
    }
    return at("user_hwid_limit_count", { count: base }, `${base}`);
  }

  function vpnLastConnectionLabel(detail) {
    const connectedAt = detail?.last_vpn_connected_at;
    const status = detail?.vpn_connection_status;
    if (connectedAt) return fmtDate(connectedAt);
    if (status === "never") return at("user_vpn_never_connected", {}, "Никогда");
    if (status === "connected") {
      return at("user_vpn_connected_no_time", {}, "Подключался, время неизвестно");
    }
    return "—";
  }

  const usersStore = getContext("usersStore");

  $: ({
    openedUser,
    openedUserDetail,
    userDetailLoading,
    userMessageDraft,
    userActionBusy,
    userDeleteOpen,
    userBanConfirmOpen,
    userMessageConfirmOpen,
    userReferralsOpen,
    userReferralsLoading,
    userReferrals,
    userReferralsTotal,
    userReferralsPage,
    userReferralsPageSize,
    premiumUnlimitedDraft,
    hwidUnlimitedDraft,
    userDetailTab,
    userLogs,
    userLogsTotal,
    userLogsPage,
    userLogsLoading,
    userLogsLoaded,
    userLogsPageSize,
  } = $usersStore);

  $: userLogsPageCount = Math.max(
    1,
    Math.ceil(Number(userLogsTotal || 0) / Number(userLogsPageSize || 20))
  );
  $: userReferralsPageCount = Math.max(
    1,
    Math.ceil(Number(userReferralsTotal || 0) / Number(userReferralsPageSize || 25))
  );

  $: openedUserAvatarUrl = openedUser ? resolvedAvatarUrl(openedUser) : "";
  $: referralInviter = openedUserDetail?.referral?.inviter || null;
  $: referralInviteesTotal = Number(openedUserDetail?.referral?.invitees_total || 0);
  $: openedUserTelegramProfileLink = openedUser ? userTelegramProfileLink(openedUser) : "";
  $: openedUserTelegramProfileLinkKind = openedUser ? userTelegramProfileLinkKind(openedUser) : "";
  $: openedUserTelegramProfileHint =
    openedUserTelegramProfileLinkKind === "id"
      ? at("user_open_tg_profile_id_hint", {}, "Бот отправит кнопку профиля в Telegram")
      : at("user_open_tg_profile_hint", {}, "Открыть профиль Telegram");

  $: if (openedUser && userDetailTab === "logs" && !userLogsLoading && !userLogsLoaded) {
    usersStore.loadUserLogs(0);
  }

  $: if (!openedUser) {
    avatarPreviewOpen = false;
    avatarPreviewUrl = "";
    avatarPreviewName = "";
  }

  function openAvatarPreview() {
    if (!openedUserAvatarUrl || !openedUser) return;
    avatarPreviewUrl = openedUserAvatarUrl;
    avatarPreviewName = userDisplayName(openedUser);
    avatarPreviewOpen = true;
  }

  function closeAvatarPreview() {
    avatarPreviewOpen = false;
  }

  function openUserTelegramProfile() {
    if (!openedUserTelegramProfileLink) {
      usersStore.copyToClipboard(
        String(openedUser?.telegram_id || ""),
        at("user_tg_profile_unavailable", {}, "Ссылка на профиль Telegram недоступна")
      );
      return;
    }
    if (openedUserTelegramProfileLinkKind === "id") {
      usersStore.sendTelegramProfileLink();
      return;
    }
    openTelegramProfileLink(openedUserTelegramProfileLink);
  }

  function openRelatedUser(user) {
    if (!user?.user_id) return;
    usersStore.closeUserReferrals();
    usersStore.openUser(user);
  }
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

          {#if openedUserDetail.subscription_url || openedUserDetail.referral?.bot_link || openedUserDetail.referral?.webapp_link}
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
            bind:value={$usersStore.userDetailTab}
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

            <Tabs.Content value="logs" class="admin-tabs-content admin-user-logs-tab">
              <div class="admin-user-logs-head">
                <div class="admin-subsection-title">
                  {at("user_logs_section_title", {}, "Логи пользователя")}
                </div>
                <div class="admin-user-logs-meta">
                  <span class="admin-muted">{at("total", {}, "Всего")}</span>
                  <strong>{userLogsTotal}</strong>
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    disabled={userLogsLoading}
                    onclick={() => usersStore.loadUserLogs(userLogsPage)}
                    title={at("refresh", {}, "Обновить")}
                  >
                    <RefreshCw size={14} />
                    {at("refresh", {}, "Обновить")}
                  </AdminButton>
                </div>
              </div>

              <ScrollArea class="admin-user-logs-wrap" maxHeight="min(52vh, 460px)">
                {#if userLogsLoading}
                  <AdminTableSkeleton
                    headers={[
                      at("date", {}, "Дата"),
                      at("event", {}, "Событие"),
                      at("content", {}, "Контент"),
                    ]}
                    rows={6}
                    widths={["140px", "140px", "60%"]}
                  />
                {:else if !userLogs.length}
                  <AdminEmptyState tone="card">
                    <span class="admin-muted">{at("logs_empty", {}, "Записей нет")}</span>
                  </AdminEmptyState>
                {:else}
                  <AdminTable>
                    <thead>
                      <tr>
                        <th>{at("date", {}, "Дата")}</th>
                        <th>{at("event", {}, "Событие")}</th>
                        <th>{at("content", {}, "Контент")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {#each userLogs as entry (entry.log_id)}
                        <tr>
                          <td data-label={at("date", {}, "Дата")}>{fmtDate(entry.timestamp)}</td>
                          <td class="admin-cell-mono" data-label={at("event", {}, "Событие")}>
                            <span class="admin-user-log-event">
                              <span>{entry.event_type || "—"}</span>
                              {#if entry.is_admin_event}
                                <AdminBadge variant="warning"
                                  >{at("user_logs_admin_event", {}, "Админ")}</AdminBadge
                                >
                              {/if}
                              {#if entry.target_user_id && entry.target_user_id !== openedUser?.user_id}
                                <small class="admin-muted">→ {entry.target_user_id}</small>
                              {/if}
                            </span>
                          </td>
                          <td
                            class="admin-cell-wrap admin-user-log-content"
                            data-label={at("content", {}, "Контент")}
                          >
                            {entry.content || ""}
                          </td>
                        </tr>
                      {/each}
                    </tbody>
                  </AdminTable>
                {/if}
              </ScrollArea>

              {#if userLogsLoaded && userLogsTotal > userLogsPageSize}
                <AdminPagination
                  page={userLogsPage}
                  pageCount={userLogsPageCount}
                  total={userLogsTotal}
                  pageLabel={at("page_short", {}, "Стр.")}
                  ofLabel={at("pagination_of", {}, "из")}
                  totalLabel={at("total", {}, "Всего")}
                  jumpLabel={at("page_short", {}, "Стр.")}
                  jumpAriaLabel={at("pagination_jump_aria", {}, "Перейти к странице")}
                  goLabel={at("pagination_go", {}, "Перейти")}
                  prevLabel={at("back", {}, "Назад")}
                  nextLabel={at("next", {}, "Далее")}
                  disabled={userLogsLoading}
                  onPageChange={(page) => usersStore.setUserLogsPage(page)}
                />
              {/if}
            </Tabs.Content>

            <Tabs.Content value="actions" class="admin-tabs-content admin-actions-tab">
              <div class="admin-user-quick-actions">
                <AdminButton
                  class="admin-reset-trial-btn"
                  onclick={usersStore.resetTrialUser}
                  disabled={userActionBusy}
                >
                  <RefreshCw size={14} />
                  {at("user_btn_reset_trial", {}, "Сбросить триал")}
                </AdminButton>
                <Label.Root class="admin-field-label admin-extend-field">
                  <span>{at("user_label_extend", {}, "Продлить подписку")}</span>
                  <div class="admin-extend-control">
                    <Input
                      class="input"
                      type="number"
                      min="1"
                      bind:value={$usersStore.userExtendDays}
                      aria-label={at("user_label_extend_days", {}, "Дней")}
                    />
                    <AdminButton onclick={usersStore.extendUser} disabled={userActionBusy}>
                      <Plus size={14} />
                      {at("user_btn_extend", {}, "Продлить")}
                    </AdminButton>
                  </div>
                  {#if Number(openedUserDetail?.active_subscription?.extra_hwid_devices || 0) > 0}
                    <label class="admin-extend-hwid-option">
                      <Checkbox
                        bind:checked={$usersStore.userExtendHwidDevices}
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
                              count: Number(
                                openedUserDetail.active_subscription.extra_hwid_devices || 0
                              ),
                            },
                            `Продлить также +${Number(
                              openedUserDetail.active_subscription.extra_hwid_devices || 0
                            )} HWID-устройств`
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
                </Label.Root>
              </div>

              {#if openedUserDetail?.active_subscription}
                <section class="admin-user-action-sheet admin-user-action-sheet--premium-override">
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
                      <span>{at("user_premium_override_bonus", {}, "Доп. премиум-трафик, GB")}</span
                      >
                      <small>{at("user_premium_override_bonus_hint", {}, "")}</small>
                      <Input
                        class="input"
                        type="number"
                        min="0"
                        step="1"
                        placeholder="0"
                        disabled={premiumUnlimitedDraft}
                        aria-label={at(
                          "user_premium_override_bonus",
                          {},
                          "Доп. премиум-трафик, GB"
                        )}
                        bind:value={$usersStore.premiumBonusGbDraft}
                      />
                    </Label.Root>
                  </div>
                  <div class="admin-user-action-sheet-footer admin-override-card-footer">
                    <div class="admin-override-card-toolbar">
                      <label class="admin-override-unlimited-label">
                        <Checkbox
                          bind:checked={$usersStore.premiumUnlimitedDraft}
                          aria-label={at("user_override_unlimited_short", {}, "Безлимит")}
                        />
                        <span>{at("user_override_unlimited_short", {}, "Безлимит")}</span>
                      </label>
                      <AdminButton
                        variant="primary"
                        onclick={usersStore.savePremiumTrafficOverride}
                        disabled={userActionBusy}
                      >
                        {at("user_premium_override_save", {}, "Сохранить")}
                      </AdminButton>
                    </div>
                    <div class="admin-override-status-lines">
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
                          >{at(
                            "user_premium_override_status_none",
                            {},
                            "Премиум-оверрайд не задан"
                          )}</span
                        >
                      {/if}
                    </div>
                  </div>
                </section>

                <section class="admin-user-action-sheet admin-user-action-sheet--regular-override">
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
                      <span
                        >{at("user_regular_override_bonus", {}, "Доп. основной трафик, GB")}</span
                      >
                      <small>{at("user_regular_override_bonus_hint", {}, "")}</small>
                      <Input
                        class="input"
                        type="number"
                        min="0"
                        step="1"
                        placeholder="0"
                        disabled={$usersStore.regularUnlimitedDraft}
                        aria-label={at(
                          "user_regular_override_bonus",
                          {},
                          "Доп. основной трафик, GB"
                        )}
                        bind:value={$usersStore.regularBonusGbDraft}
                      />
                    </Label.Root>
                  </div>
                  <div class="admin-user-action-sheet-footer admin-override-card-footer">
                    <div class="admin-override-card-toolbar">
                      <label class="admin-override-unlimited-label">
                        <Checkbox
                          bind:checked={$usersStore.regularUnlimitedDraft}
                          aria-label={at("user_override_unlimited_short", {}, "Безлимит")}
                        />
                        <span>{at("user_override_unlimited_short", {}, "Безлимит")}</span>
                      </label>
                      <AdminButton
                        variant="primary"
                        onclick={usersStore.saveRegularTrafficOverride}
                        disabled={userActionBusy}
                      >
                        {at("user_regular_override_save", {}, "Сохранить")}
                      </AdminButton>
                    </div>
                    <div class="admin-override-status-lines">
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

                <section class="admin-user-action-sheet admin-user-action-sheet--hwid-limit">
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
                        bind:value={$usersStore.hwidDeviceLimitDraft}
                      />
                    </Label.Root>
                  </div>
                  <div class="admin-user-action-sheet-footer admin-override-card-footer">
                    <div class="admin-override-card-toolbar">
                      <label class="admin-override-unlimited-label">
                        <Checkbox
                          bind:checked={$usersStore.hwidUnlimitedDraft}
                          aria-label={at("user_override_unlimited_short", {}, "Безлимит")}
                        />
                        <span>{at("user_override_unlimited_short", {}, "Безлимит")}</span>
                      </label>
                      <AdminButton
                        variant="primary"
                        onclick={usersStore.saveHwidDeviceLimit}
                        disabled={userActionBusy}
                      >
                        {at("user_hwid_limit_save", {}, "Сохранить")}
                      </AdminButton>
                    </div>
                    <div class="admin-override-status-lines">
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
                        value={$usersStore.grantTrafficKindDraft}
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
                        onValueChange={(v) => usersStore.updateState({ grantTrafficKindDraft: v })}
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
                          bind:value={$usersStore.grantTrafficGbDraft}
                        />
                        <AdminButton
                          variant="primary"
                          onclick={usersStore.grantTraffic}
                          disabled={userActionBusy}
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
                <small
                  >{at(
                    "user_hint_telegram_msg",
                    {},
                    "Поддерживается HTML-разметка Telegram"
                  )}</small
                >
                <Textarea
                  class="admin-textarea"
                  rows="3"
                  placeholder={at("user_placeholder_msg", {}, "Текст сообщения")}
                  bind:value={$usersStore.userMessageDraft}
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
                  {#if openedUser.is_banned}
                    <AdminButton
                      variant="dangerSoft"
                      onclick={usersStore.requestBanToggle}
                      disabled={userActionBusy}
                    >
                      <UserPlus size={14} />
                      {at("btn_unban", {}, "Разбанить пользователя")}
                    </AdminButton>
                  {:else}
                    <AdminButton
                      variant="danger"
                      onclick={usersStore.requestBanToggle}
                      disabled={userActionBusy}
                    >
                      <UserMinus size={14} />
                      {at("btn_ban", {}, "Заблокировать")}
                    </AdminButton>
                  {/if}
                  <AdminButton
                    variant="danger"
                    onclick={() => usersStore.updateState({ userDeleteOpen: true })}
                    disabled={userActionBusy}
                  >
                    <Trash2 size={14} />
                    {at("btn_delete_account", {}, "Удалить аккаунт")}
                  </AdminButton>
                </div>
              </section>
            </Tabs.Content>
          </Tabs.Root>
        </main>
      </div>
    {/if}
  {/if}
</Dialog>

<Dialog
  open={userReferralsOpen}
  title={at("user_invitees_title", {}, "Приглашённые пользователи")}
  description={openedUser
    ? at(
        "user_invitees_description",
        { name: userDisplayName(openedUser), count: userReferralsTotal },
        `${userDisplayName(openedUser)} · ${userReferralsTotal}`
      )
    : ""}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={usersStore.closeUserReferrals}
  class="admin-dialog admin-user-referrals-dialog"
>
  <div class="admin-user-referrals-body">
    {#if userReferralsLoading}
      <AdminTableSkeleton
        headers={[
          at("user_col_user", {}, "Пользователь"),
          "ID",
          at("user_label_registration", {}, "Регистрация"),
          "",
        ]}
        rows={5}
        widths={["42%", "18%", "26%", "14%"]}
      />
    {:else if !userReferrals.length}
      <AdminEmptyState tone="card">
        <span class="admin-muted"
          >{at("user_invitees_empty", {}, "Пользователь пока никого не пригласил")}</span
        >
      </AdminEmptyState>
    {:else}
      <ScrollArea class="admin-user-referrals-table-wrap" maxHeight="min(55vh, 460px)">
        <AdminTable class="admin-user-referrals-table">
          <thead>
            <tr>
              <th>{at("user_col_user", {}, "Пользователь")}</th>
              <th>ID</th>
              <th>{at("user_label_registration", {}, "Регистрация")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each userReferrals as invitee (invitee.user_id)}
              <tr>
                <td data-label={at("user_col_user", {}, "Пользователь")}>
                  <span class="admin-referral-user-cell">
                    <strong>{userDisplayName(invitee)}</strong>
                    <small>{userSecondaryName(invitee)}</small>
                  </span>
                </td>
                <td class="admin-cell-mono" data-label="ID">{invitee.user_id}</td>
                <td data-label={at("user_label_registration", {}, "Регистрация")}>
                  {fmtDateShort(invitee.registration_date)}
                </td>
                <td class="admin-referral-user-actions">
                  <AdminButton
                    size="icon"
                    variant="icon"
                    title={at("user_open_related", {}, "Открыть карточку")}
                    aria-label={at("user_open_related", {}, "Открыть карточку")}
                    onclick={() => openRelatedUser(invitee)}
                  >
                    <ExternalLink size={14} />
                  </AdminButton>
                </td>
              </tr>
            {/each}
          </tbody>
        </AdminTable>
      </ScrollArea>
    {/if}

    {#if userReferralsTotal > userReferralsPageSize}
      <AdminPagination
        page={userReferralsPage}
        pageCount={userReferralsPageCount}
        total={userReferralsTotal}
        pageLabel={at("page_short", {}, "Стр.")}
        ofLabel={at("pagination_of", {}, "из")}
        totalLabel={at("total", {}, "Всего")}
        jumpLabel={at("page_short", {}, "Стр.")}
        jumpAriaLabel={at("pagination_jump_aria", {}, "Перейти к странице")}
        goLabel={at("pagination_go", {}, "Перейти")}
        prevLabel={at("prev_page", {}, "Назад")}
        nextLabel={at("next_page", {}, "Вперёд")}
        disabled={userReferralsLoading}
        onPageChange={(page) => usersStore.setUserReferralsPage(page)}
      />
    {/if}
  </div>
</Dialog>

<Dialog
  open={avatarPreviewOpen}
  title={avatarPreviewName || at("user_avatar_title", {}, "Аватар")}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={closeAvatarPreview}
  class="admin-dialog admin-avatar-dialog"
>
  {#if avatarPreviewUrl}
    <div class="admin-avatar-preview">
      <img
        src={avatarPreviewUrl}
        alt={avatarPreviewName}
        loading="eager"
        referrerpolicy="no-referrer"
      />
    </div>
  {/if}
</Dialog>

<Dialog
  open={userMessageConfirmOpen}
  title={at("user_msg_confirm_title", {}, "Отправить сообщение пользователю?")}
  description={openedUser
    ? at(
        "user_msg_confirm_recipient",
        { name: userDisplayName(openedUser) },
        `Получатель: ${userDisplayName(openedUser)}`
      )
    : ""}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={() => usersStore.updateState({ userMessageConfirmOpen: false })}
  class="admin-dialog"
>
  <ScrollArea class="admin-confirm-message-preview" maxHeight="min(280px, 45vh)">
    {userMessageDraft}
  </ScrollArea>
  <div class="admin-dialog-actions">
    <AdminButton onclick={() => usersStore.updateState({ userMessageConfirmOpen: false })}
      >{at("btn_cancel", {}, "Отмена")}</AdminButton
    >
    <AdminButton
      variant="primary"
      onclick={usersStore.sendUserMessage}
      disabled={userActionBusy || !userMessageDraft.trim()}
    >
      <Send size={14} />
      {at("btn_confirm_send", {}, "Подтвердить отправку")}
    </AdminButton>
  </div>
</Dialog>

<Dialog
  open={userBanConfirmOpen}
  title={at("user_ban_confirm_title", {}, "Заблокировать пользователя?")}
  description={openedUser
    ? at(
        "user_ban_confirm_subtitle",
        { name: userDisplayName(openedUser) },
        `${userDisplayName(openedUser)} больше не сможет взаимодействовать с ботом. Действие можно отменить позже.`
      )
    : ""}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={() => usersStore.updateState({ userBanConfirmOpen: false })}
  class="admin-dialog"
>
  <div class="admin-dialog-actions">
    <AdminButton onclick={() => usersStore.updateState({ userBanConfirmOpen: false })}
      >{at("btn_cancel", {}, "Отмена")}</AdminButton
    >
    <AdminButton
      variant="danger"
      onclick={() => usersStore.applyBanToggle(true)}
      disabled={userActionBusy}
    >
      <UserMinus size={14} />
      {at("btn_ban", {}, "Заблокировать")}
    </AdminButton>
  </div>
</Dialog>

<Dialog
  open={userDeleteOpen}
  title={at("user_delete_confirm_title", {}, "Удалить пользователя?")}
  description={at(
    "user_delete_confirm_subtitle",
    {},
    "Действие необратимо. Удалятся записи в БД бота и пользователь в Remnawave Panel."
  )}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={() => usersStore.updateState({ userDeleteOpen: false })}
  class="admin-dialog"
>
  <div class="admin-form-row">
    <AdminButton onclick={() => usersStore.updateState({ userDeleteOpen: false })}
      >{at("btn_cancel", {}, "Отмена")}</AdminButton
    >
    <AdminButton variant="danger" onclick={usersStore.deleteUser} disabled={userActionBusy}>
      <Trash2 size={14} />
      {at("btn_confirm_delete", {}, "Подтвердить удаление")}
    </AdminButton>
  </div>
</Dialog>

<style>
  .admin-user-action-sheet {
    border: 1px solid var(--admin-border-muted, rgba(255, 255, 255, 0.08));
    border-radius: 12px;
    margin-bottom: 14px;
    overflow: hidden;
    background: var(--admin-surface-1, rgba(255, 255, 255, 0.02));
  }
  .admin-user-action-sheet :global(.admin-dashboard-section-head) {
    padding: 12px 14px 10px;
    margin: 0;
    border-bottom: 1px solid var(--admin-border-muted, rgba(255, 255, 255, 0.06));
  }
  .admin-user-action-sheet-body {
    padding: 12px 14px 12px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .admin-user-override-stack {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .admin-user-grant-stack {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .admin-user-action-sheet-footer {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: 12px;
    padding: 4px 14px 12px;
  }
  .admin-override-card-footer {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }
  .admin-override-card-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 10px 14px;
    width: 100%;
  }
  .admin-override-card-toolbar :global(.admin-btn) {
    flex: 0 0 auto;
    min-height: 36px;
    padding-left: 16px;
    padding-right: 16px;
  }
  .admin-override-unlimited-label {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--admin-text, inherit);
    cursor: pointer;
    user-select: none;
    min-height: 36px;
  }
  @media (max-width: 520px) {
    .admin-override-card-toolbar {
      flex-direction: column;
      align-items: stretch;
    }
    .admin-override-card-toolbar :global(.admin-btn) {
      width: 100%;
    }
  }
  .admin-override-status-lines {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex: 1;
    min-width: 0;
    font-size: 12px;
    line-height: 1.35;
  }
  :global(.admin-user-dialog .admin-actions-tab) {
    padding-bottom: 14px;
  }
  .admin-user-action-sheet--regular-override {
    margin-top: 10px;
  }
  .admin-user-action-sheet--traffic-grant {
    margin-top: 10px;
  }
  .admin-user-action-sheet :global(.admin-grant-kind-select) {
    width: 100%;
    max-width: 100%;
  }
  .admin-avatar-preview-trigger {
    padding: 0;
    appearance: none;
  }
  .admin-avatar-preview-trigger img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .admin-avatar-preview-trigger:disabled {
    cursor: default;
  }
  .admin-avatar-preview-trigger.is-clickable {
    cursor: zoom-in;
  }
  .admin-avatar-preview-trigger.is-clickable:hover,
  .admin-avatar-preview-trigger.is-clickable:focus-visible {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);
  }
  .admin-user-summary-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 6px;
  }
  .admin-user-ref-row {
    grid-template-columns: 130px minmax(0, 1fr) auto;
    align-items: center;
  }
  .admin-user-ref-row :global(.admin-btn) {
    flex: 0 0 auto;
  }
  .admin-user-ref-value {
    display: grid;
    gap: 2px;
    min-width: 0;
  }
  .admin-user-ref-value small {
    color: var(--admin-muted);
    font-size: 11px;
    font-weight: 500;
  }
  :global(.admin-user-referrals-dialog) {
    width: min(760px, calc(100vw - 28px));
    max-height: min(760px, calc(100dvh - 28px));
  }
  .admin-user-referrals-body {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  :global(.admin-user-referrals-table-wrap) {
    min-height: 120px;
  }
  .admin-referral-user-cell {
    display: grid;
    gap: 2px;
    min-width: 0;
  }
  .admin-referral-user-cell strong {
    color: var(--admin-text);
    font-weight: 650;
    word-break: break-word;
  }
  .admin-referral-user-cell small {
    color: var(--admin-muted);
    font-size: 12px;
    word-break: break-word;
  }
  .admin-referral-user-actions {
    text-align: right;
  }
  @media (max-width: 560px) {
    .admin-user-ref-row {
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 4px 8px;
    }
    .admin-user-ref-row > span {
      grid-column: 1 / -1;
    }
  }
  :global(.admin-avatar-dialog) {
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    width: min(920px, calc(100vw - 28px));
    height: min(820px, calc(100dvh - 28px));
    max-height: calc(100dvh - 28px);
    gap: 10px;
    padding: 12px;
    overflow: hidden;
  }
  .admin-avatar-preview {
    display: grid;
    place-items: center;
    min-height: 0;
    width: 100%;
    height: 100%;
    padding: 4px;
    overflow: hidden;
  }
  .admin-avatar-preview img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    border-radius: 14px;
    border: 1px solid var(--admin-border);
    background: var(--admin-surface-2);
  }
  @media (max-width: 640px) {
    :global(.dialog:has(.admin-avatar-dialog)) {
      padding: max(8px, env(safe-area-inset-top)) max(8px, env(safe-area-inset-right))
        max(8px, env(safe-area-inset-bottom)) max(8px, env(safe-area-inset-left));
    }
    :global(.admin-avatar-dialog) {
      width: calc(100vw - 16px);
      height: min(88dvh, calc(100dvh - 16px));
      max-height: calc(100dvh - 16px);
      border-radius: 18px;
      padding: 10px;
    }
  }
  :global(.admin-user-dialog .admin-user-logs-tab) {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .admin-user-logs-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }
  .admin-user-logs-meta {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
  }
  :global(.admin-user-logs-wrap) {
    min-height: 120px;
  }
  .admin-user-log-event {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  :global(.admin-user-log-content) {
    white-space: pre-wrap;
    word-break: break-word;
    max-width: 520px;
  }
  @media (max-width: 640px) {
    :global(.admin-user-log-content) {
      max-width: 100%;
    }
  }
</style>
