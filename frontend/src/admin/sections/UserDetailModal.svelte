<script lang="ts">
  import { Separator, Tabs } from "$components/ui/primitives.js";
  import Dialog from "$components/ui/dialog.svelte";
  import UserActionsTab from "./user-detail/UserActionsTab.svelte";
  import UserDetailDialogs from "./user-detail/UserDetailDialogs.svelte";
  import UserLogsTab from "./user-detail/UserLogsTab.svelte";
  import { AdminBadge, AdminButton, AdminTrafficCard } from "$components/patterns/admin/index.js";
  import { Copy, ExternalLink, UsersRound } from "$components/ui/icons.js";
  import { getContext } from "svelte";
  import { TableHandler } from "@vincjo/datatables";

  import type { Tariff, TariffsStore } from "$lib/admin/stores/tariffsStore";
  import type { AdminUser, UsersStore } from "$lib/admin/stores/usersStore";
  import "./UserDetailModal.css";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type MoneyFormatter = (value: unknown, currency?: string | null) => string;
  type DateFormatter = (value: unknown) => string;
  type BadgeVariant = "success" | "danger" | "warning" | "muted";
  type ComponentCallback = (...args: never[]) => void;
  type SelectOption = { value: string; label: string };
  type HwidDraftState = { key: string; valid: boolean };
  type UserLogRow = Record<string, unknown> & { log_id?: number | string };

  const usersStore = getContext<UsersStore>("usersStore");
  const tariffsStore = getContext<TariffsStore>("tariffsStore");
  const userLogsTable = new TableHandler<UserLogRow>();
  const userReferralsTable = new TableHandler<AdminUser>();

  let {
    at,
    fmtDate,
    fmtMoney,
    resolvedAvatarUrl,
    userDisplayName,
    userSecondaryName,
    paymentStatusVariant,
    trafficPercentValue,
    trafficLeftLabel,
    trafficOfLabel,
    userInitials = () => "",
    fmtDateShort = (value) => String(value ?? ""),
    userTelegramProfileLink = () => "",
    userTelegramProfileLinkKind = () => "",
    openTelegramProfileLink = () => false,
    onClose = () => usersStore.closeUser(),
  }: {
    at: TranslateFn;
    fmtDate: DateFormatter;
    fmtMoney: MoneyFormatter;
    resolvedAvatarUrl: (user: AdminUser) => string;
    userDisplayName: (user: AdminUser) => string;
    userSecondaryName: (user: AdminUser) => string;
    paymentStatusVariant: (status: unknown) => BadgeVariant;
    trafficPercentValue: (left: unknown, total: unknown) => number;
    trafficLeftLabel: (used: unknown, limit: unknown) => string;
    trafficOfLabel: (used: unknown, limit: unknown) => string;
    userInitials?: (user: AdminUser) => string;
    fmtDateShort?: DateFormatter;
    userTelegramProfileLink?: (user: AdminUser) => string;
    userTelegramProfileLinkKind?: (user: AdminUser) => string;
    openTelegramProfileLink?: (url: string) => boolean;
    onClose?: () => void;
  } = $props();

  let avatarPreviewOpen = $state(false);
  let avatarPreviewUrl = $state("");
  let avatarPreviewName = $state("");
  let tariffsLoadRequested = $state(false);

  function pretty(val: unknown): string {
    if (val === true) return at("yes", {}, "Да");
    if (val === false) return at("no", {}, "Нет");
    return String(val ?? "—");
  }

  function isTrialSubscription(sub: Record<string, unknown> | null | undefined): boolean {
    return Boolean(sub?.is_trial || String(sub?.provider || "").toLowerCase() === "trial");
  }

  function subscriptionDisplayLabel(sub: Record<string, unknown> | null | undefined): string {
    if (!sub) return "—";
    if (isTrialSubscription(sub)) return at("user_subscription_trial", {}, "Триал");
    if (sub.display_label) return String(sub.display_label);
    return sub.tariff_name || sub.tariff_key
      ? String(sub.tariff_name || sub.tariff_key)
      : at("user_history_no_tariff", {}, "Без тарифа");
  }

  function trialSummaryText(trial: Record<string, unknown> | null | undefined): string {
    if (!trial?.used) return at("user_trial_not_used", {}, "Не брал");
    const date = trial.latest_activated_at || trial.first_activated_at;
    const base = date
      ? at("user_trial_used_at", { date: fmtDate(date) }, `Брал ${fmtDate(date)}`)
      : at("user_trial_used", {}, "Брал");
    return trial.active ? `${base} · ${at("user_trial_active", {}, "активен")}` : base;
  }

  function hwidLimitLabel(sub: Record<string, unknown> | null | undefined): string {
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

  function vpnLastConnectionLabel(detail: Record<string, unknown> | null | undefined): string {
    const connectedAt = detail?.last_vpn_connected_at;
    const status = detail?.vpn_connection_status;
    if (connectedAt) return fmtDate(connectedAt);
    if (status === "never") return at("user_vpn_never_connected", {}, "Никогда");
    if (status === "connected") {
      return at("user_vpn_connected_no_time", {}, "Подключался, время неизвестно");
    }
    return "—";
  }

  const selectExtendTariff = ((value: string) =>
    usersStore.updateState({ userExtendTariffKey: value })) as ComponentCallback;
  const selectTariffAction = ((value: string) =>
    usersStore.updateState({ userTariffActionKey: value })) as ComponentCallback;
  const selectGrantTrafficKind = ((value: string) =>
    usersStore.updateState({
      grantTrafficKindDraft: value === "premium" ? "premium" : "regular",
    })) as ComponentCallback;

  function tariffLabel(tariff: Tariff | Record<string, unknown> | null | undefined): string {
    const raw = (tariff || {}) as Record<string, unknown>;
    const names =
      raw.names && typeof raw.names === "object" ? (raw.names as Record<string, unknown>) : {};
    return (
      String(names.ru || "") ||
      String(names.en || "") ||
      String(raw.name || "") ||
      String(raw.key || "") ||
      at("user_history_no_tariff", {}, "No tariff")
    );
  }

  function uniqueTariffsByKey(tariffs: Tariff[]): Tariff[] {
    const seen = new Set<string>();
    return tariffs.filter((tariff) => {
      const key = String(tariff?.key || "");
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function tariffSelectItem(
    tariff: Tariff,
    { currentKey = "", markCurrent = false }: { currentKey?: string; markCurrent?: boolean } = {}
  ): SelectOption {
    const value = String(tariff?.key || "");
    const label = tariffLabel(tariff);
    return {
      value,
      label:
        markCurrent && value && value === currentKey
          ? `${label} (${at("user_tariff_current_badge", {}, "current")})`
          : label,
    };
  }

  function gbDraftNumber(value: unknown): number {
    if (value === "" || value === null || value === undefined) return 0;
    const num = Number(value);
    return Number.isFinite(num) ? num : NaN;
  }

  function sameGbDraft(left: unknown, right: unknown): boolean {
    const leftNum = gbDraftNumber(left);
    const rightNum = gbDraftNumber(right);
    if (!Number.isFinite(leftNum) || !Number.isFinite(rightNum)) return false;
    return Math.abs(leftNum - rightNum) < 0.000001;
  }

  function hwidDraftState(unlimited: unknown, value: unknown): HwidDraftState {
    if (unlimited) return { key: "unlimited", valid: true };
    if (value === "" || value === null || value === undefined) {
      return { key: "default", valid: true };
    }
    const limit = Number(value);
    if (!Number.isInteger(limit) || limit < 0 || limit > 1_000_000) {
      return { key: "invalid", valid: false };
    }
    if (limit === 0) return { key: "unlimited", valid: true };
    return { key: `limit:${limit}`, valid: true };
  }

  const usersState = $derived(usersStore);
  const tariffsState = $derived(tariffsStore);
  const openedUser = $derived(usersState.openedUser);
  const openedUserDetail = $derived(usersState.openedUserDetail);
  const userDetailLoading = $derived(usersState.userDetailLoading);
  const userMessageDraft = $derived(usersState.userMessageDraft);
  const userActionBusy = $derived(usersState.userActionBusy);
  const userDeleteOpen = $derived(usersState.userDeleteOpen);
  const userBanConfirmOpen = $derived(usersState.userBanConfirmOpen);
  const userMessageConfirmOpen = $derived(usersState.userMessageConfirmOpen);
  const userReferralsOpen = $derived(usersState.userReferralsOpen);
  const userReferralsLoading = $derived(usersState.userReferralsLoading);
  const userReferrals = $derived(usersState.userReferrals);
  const userReferralsTotal = $derived(usersState.userReferralsTotal);
  const userReferralsPage = $derived(usersState.userReferralsPage);
  const userReferralsPageSize = $derived(usersState.userReferralsPageSize);
  const premiumUnlimitedDraft = $derived(usersState.premiumUnlimitedDraft);
  const premiumUnlimitedBaseline = $derived(usersState.premiumUnlimitedBaseline);
  const premiumBonusGbDraft = $derived(usersState.premiumBonusGbDraft);
  const premiumBonusGbBaseline = $derived(usersState.premiumBonusGbBaseline);
  const regularUnlimitedDraft = $derived(usersState.regularUnlimitedDraft);
  const regularUnlimitedBaseline = $derived(usersState.regularUnlimitedBaseline);
  const regularBonusGbDraft = $derived(usersState.regularBonusGbDraft);
  const regularBonusGbBaseline = $derived(usersState.regularBonusGbBaseline);
  const hwidUnlimitedDraft = $derived(usersState.hwidUnlimitedDraft);
  const hwidUnlimitedBaseline = $derived(usersState.hwidUnlimitedBaseline);
  const hwidDeviceLimitDraft = $derived(usersState.hwidDeviceLimitDraft);
  const hwidDeviceLimitBaseline = $derived(usersState.hwidDeviceLimitBaseline);
  const userDetailTab = $derived(usersState.userDetailTab);
  const userTariffActionKey = $derived(usersState.userTariffActionKey);
  const userTariffActionBaselineKey = $derived(usersState.userTariffActionBaselineKey);
  const grantTrafficGbDraft = $derived(usersState.grantTrafficGbDraft);
  const userLogs = $derived(usersState.userLogs);
  const userLogsTotal = $derived(usersState.userLogsTotal);
  const userLogsPage = $derived(usersState.userLogsPage);
  const userLogsLoading = $derived(usersState.userLogsLoading);
  const userLogsLoaded = $derived(usersState.userLogsLoaded);
  const userLogsPageSize = $derived(usersState.userLogsPageSize);

  $effect(() => userLogsTable.setRows(userLogs as UserLogRow[]));
  $effect(() => userReferralsTable.setRows(userReferrals));

  const userLogsPageCount = $derived(
    Math.max(1, Math.ceil(Number(userLogsTotal || 0) / Number(userLogsPageSize || 20)))
  );
  const userReferralsPageCount = $derived(
    Math.max(1, Math.ceil(Number(userReferralsTotal || 0) / Number(userReferralsPageSize || 25)))
  );

  const openedUserAvatarUrl = $derived(openedUser ? resolvedAvatarUrl(openedUser) : "");
  const referralInviter = $derived(openedUserDetail?.referral?.inviter || null);
  const referralInviteesTotal = $derived(Number(openedUserDetail?.referral?.invitees_total || 0));
  const openedUserTelegramProfileLink = $derived(
    openedUser ? userTelegramProfileLink(openedUser) : ""
  );
  const openedUserTelegramProfileLinkKind = $derived(
    openedUser ? userTelegramProfileLinkKind(openedUser) : ""
  );
  const openedUserTelegramProfileHint = $derived(
    openedUserTelegramProfileLinkKind === "id"
      ? at("user_open_tg_profile_id_hint", {}, "Бот отправит кнопку профиля в Telegram")
      : at("user_open_tg_profile_hint", {}, "Открыть профиль Telegram")
  );

  const tariffCatalogItems = $derived((tariffsState.tariffsCatalog?.tariffs || []) as Tariff[]);
  const enabledTariffs = $derived(tariffCatalogItems.filter((tariff) => tariff?.enabled !== false));
  const currentSubscriptionTariffKey = $derived(
    String(openedUserDetail?.active_subscription?.tariff_key || "")
  );
  const currentSubscriptionTariff = $derived(
    tariffCatalogItems.find(
      (tariff) => String(tariff?.key || "") === currentSubscriptionTariffKey
    ) || null
  );
  const periodTariffs = $derived(
    enabledTariffs.filter((tariff) => tariff?.billing_model === "period")
  );
  const periodTariffItems = $derived(periodTariffs.map((tariff) => tariffSelectItem(tariff)));
  const extendPeriodTariffs = $derived(
    uniqueTariffsByKey([
      ...periodTariffs,
      ...(currentSubscriptionTariff?.billing_model === "period" ? [currentSubscriptionTariff] : []),
    ])
  );
  const extendTariffItems = $derived(
    extendPeriodTariffs.map((tariff) =>
      tariffSelectItem(tariff, { currentKey: currentSubscriptionTariffKey, markCurrent: true })
    )
  );
  const extendTariffRequired = $derived(extendTariffItems.length > 1);
  const userExtendTariffValid = $derived(
    !usersState.userExtendTariffKey ||
      !extendTariffItems.length ||
      extendTariffItems.some((item) => item.value === usersState.userExtendTariffKey)
  );
  const userExtendDaysValid = $derived(Number(usersState.userExtendDays) > 0);
  const extendTariffsLoading = $derived(
    Boolean(openedUser && tariffsState.tariffsLoading && !extendTariffItems.length)
  );
  const tariffActionDirty = $derived(
    Boolean(userTariffActionKey) && userTariffActionKey !== userTariffActionBaselineKey
  );
  const premiumOverrideDraftValid = $derived(gbDraftNumber(premiumBonusGbDraft) >= 0);
  const premiumOverrideDirty = $derived(
    Boolean(premiumUnlimitedDraft) !== Boolean(premiumUnlimitedBaseline) ||
      !sameGbDraft(premiumBonusGbDraft, premiumBonusGbBaseline)
  );
  const regularOverrideDraftValid = $derived(gbDraftNumber(regularBonusGbDraft) >= 0);
  const regularOverrideDirty = $derived(
    Boolean(regularUnlimitedDraft) !== Boolean(regularUnlimitedBaseline) ||
      !sameGbDraft(regularBonusGbDraft, regularBonusGbBaseline)
  );
  const hwidDraft = $derived(hwidDraftState(hwidUnlimitedDraft, hwidDeviceLimitDraft));
  const hwidBaseline = $derived(hwidDraftState(hwidUnlimitedBaseline, hwidDeviceLimitBaseline));
  const hwidLimitDraftValid = $derived(hwidDraft.valid);
  const hwidLimitDirty = $derived(hwidDraft.key !== hwidBaseline.key);
  const grantTrafficGbValid = $derived(
    grantTrafficGbDraft !== "" &&
      grantTrafficGbDraft !== null &&
      grantTrafficGbDraft !== undefined &&
      gbDraftNumber(grantTrafficGbDraft) > 0
  );
  const currentSubscriptionTariffLabel = $derived(
    (currentSubscriptionTariff ? tariffLabel(currentSubscriptionTariff) : "") ||
      periodTariffItems.find((item) => item.value === currentSubscriptionTariffKey)?.label ||
      currentSubscriptionTariffKey ||
      at("user_tariff_none", {}, "No tariff")
  );

  $effect(() => {
    if (
      openedUser &&
      !tariffsLoadRequested &&
      !tariffsState.tariffsLoading &&
      enabledTariffs.length === 0
    ) {
      tariffsLoadRequested = true;
      tariffsStore.loadTariffs();
    }
  });

  $effect(() => {
    if (openedUser && extendTariffItems.length === 1 && !usersState.userExtendTariffKey) {
      usersStore.updateState({ userExtendTariffKey: extendTariffItems[0].value });
    }
  });

  $effect(() => {
    if (
      openedUser &&
      extendTariffItems.length > 0 &&
      usersState.userExtendTariffKey &&
      !userExtendTariffValid
    ) {
      usersStore.updateState({ userExtendTariffKey: "" });
    }
  });

  $effect(() => {
    if (openedUser && currentSubscriptionTariffKey && !usersState.userTariffActionKey) {
      usersStore.updateState({ userTariffActionKey: currentSubscriptionTariffKey });
    }
  });

  $effect(() => {
    if (openedUser && userDetailTab === "logs" && !userLogsLoading && !userLogsLoaded) {
      usersStore.loadUserLogs(0);
    }
  });

  $effect(() => {
    if (!openedUser) {
      avatarPreviewOpen = false;
      avatarPreviewUrl = "";
      avatarPreviewName = "";
      tariffsLoadRequested = false;
    }
  });

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

  function openRelatedUser(user: AdminUser | null | undefined): void {
    if (!user?.user_id) return;
    usersStore.closeUserReferrals();
    void usersStore.openUser(user);
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
              userLogsRows={userLogsTable.rows}
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
              {currentSubscriptionTariffLabel}
              {userTariffActionKey}
              {selectTariffAction}
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
            />
          </Tabs.Root>
        </main>
      </div>
    {/if}
  {/if}
</Dialog>

<UserDetailDialogs
  {at}
  {fmtDateShort}
  {userDisplayName}
  {userSecondaryName}
  {openRelatedUser}
  {closeAvatarPreview}
  {openedUser}
  {userReferralsOpen}
  {userReferralsLoading}
  userReferralsRows={userReferralsTable.rows}
  {userReferralsTotal}
  {userReferralsPage}
  {userReferralsPageCount}
  {userReferralsPageSize}
  {avatarPreviewOpen}
  {avatarPreviewUrl}
  {avatarPreviewName}
  {userMessageConfirmOpen}
  {userMessageDraft}
  {userBanConfirmOpen}
  {userDeleteOpen}
  {userActionBusy}
/>
