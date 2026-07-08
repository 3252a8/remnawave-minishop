<script lang="ts">
  import { getTariffsStore, getUsersStore } from "$lib/admin/context";
  import UserDetailDialogs from "./user-detail/UserDetailDialogs.svelte";
  import UserDetailView from "./user-detail/UserDetailView.svelte";
  import { TableHandler } from "@vincjo/datatables";

  import type { Tariff } from "$lib/admin/stores/tariffsStore";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import "./UserDetailModal.css";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type MoneyFormatter = (value: unknown, currency?: string | null) => string;
  type DateFormatter = (value: unknown) => string;
  type BadgeVariant = "success" | "danger" | "warning" | "muted";
  type SelectOption = { value: string; label: string };
  type HwidDraftState = { key: string; valid: boolean };
  type UserLogRow = Record<string, unknown> & { log_id?: number | string };

  const usersStore = getUsersStore();
  const tariffsStore = getTariffsStore();
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

  function hwidBaseLimitLabel(value: unknown): string {
    if (value === null || value === undefined || value === "") {
      return at("user_hwid_limit_default", {}, "Тарифный / default");
    }
    const limit = Number(value);
    if (limit === 0) return at("user_hwid_limit_unlimited", {}, "Безлимит");
    if (Number.isFinite(limit)) return at("user_hwid_limit_count", { count: limit }, `${limit}`);
    return at("user_hwid_limit_default", {}, "Тарифный / default");
  }

  function hwidBaseLimitKey(value: unknown): string {
    if (value === null || value === undefined || value === "") return "default";
    const limit = Number(value);
    return Number.isFinite(limit) ? String(limit) : "default";
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

  const selectExtendTariff = (value: string) =>
    usersStore.updateState({ userExtendTariffKey: value });
  const selectTariffAction = (value: string) =>
    usersStore.updateState({ userTariffActionKey: value });
  const selectTrafficStrategy = (value: string) =>
    usersStore.updateState({ trafficStrategyDraft: value });
  const selectGrantTrafficKind = (value: string) =>
    usersStore.updateState({
      grantTrafficKindDraft: value === "premium" ? "premium" : "regular",
    });
  const selectUserSquadOverride = (value: string) =>
    usersStore.updateState({ userSquadOverrideDraft: value });
  const selectUserExternalSquadMode = (value: string) =>
    usersStore.updateState({
      userExternalSquadModeDraft: value === "set" || value === "cleared" ? value : "inherit",
    });
  const updateUserExternalSquadUuid = (value: string) =>
    usersStore.updateState({ userExternalSquadUuidDraft: value });

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

  function trafficStrategyLockHint(reason: unknown): string {
    const lockReason = String(reason || "");
    if (lockReason === "traffic_tariff") {
      return at(
        "user_traffic_strategy_locked_traffic",
        {},
        "Для traffic-тарифов стратегия всегда NO_RESET. Сначала смените тариф на периодический."
      );
    }
    if (lockReason === "trial") {
      return at(
        "user_traffic_strategy_locked_trial",
        {},
        "Для триала стратегия задаётся общей настройкой TRIAL_TRAFFIC_STRATEGY."
      );
    }
    if (lockReason === "panel_unavailable") {
      return at(
        "user_traffic_strategy_locked_panel",
        {},
        "Текущее значение панели недоступно. Повторите после восстановления связи с Remnawave."
      );
    }
    return "";
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
  const userTariffHwidConfirmOpen = $derived(usersState.userTariffHwidConfirmOpen);
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
  const trafficStrategyDraft = $derived(usersState.trafficStrategyDraft);
  const trafficStrategyBaseline = $derived(usersState.trafficStrategyBaseline);
  const grantTrafficGbDraft = $derived(usersState.grantTrafficGbDraft);
  const userSquadOverrideDraft = $derived(usersState.userSquadOverrideDraft);
  const userExternalSquadModeDraft = $derived(usersState.userExternalSquadModeDraft);
  const userExternalSquadUuidDraft = $derived(usersState.userExternalSquadUuidDraft);
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
  const selectedTariffAction = $derived(
    tariffCatalogItems.find((tariff) => String(tariff?.key || "") === userTariffActionKey) || null
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
  const panelSquadItems = $derived(
    (tariffsState.panelSquads || []).map((squad) => ({
      value: squad.uuid,
      label: tariffsStore.squadLabel(squad.uuid),
    }))
  );
  const tariffActionDirty = $derived(
    Boolean(userTariffActionKey) && userTariffActionKey !== userTariffActionBaselineKey
  );
  const currentHwidBaseKey = $derived(
    hwidBaseLimitKey(openedUserDetail?.active_subscription?.hwid_device_limit)
  );
  const selectedTariffHwidBaseKey = $derived(
    hwidBaseLimitKey(selectedTariffAction?.hwid_device_limit)
  );
  const tariffHwidLimitChangeAvailable = $derived(
    Boolean(
      tariffActionDirty &&
      openedUserDetail?.active_subscription?.hwid_device_limit !== null &&
      openedUserDetail?.active_subscription?.hwid_device_limit !== undefined &&
      selectedTariffAction &&
      currentHwidBaseKey !== selectedTariffHwidBaseKey
    )
  );
  const tariffHwidCurrentLabel = $derived(
    hwidBaseLimitLabel(openedUserDetail?.active_subscription?.hwid_device_limit)
  );
  const tariffHwidTargetLabel = $derived(
    hwidBaseLimitLabel(selectedTariffAction?.hwid_device_limit)
  );
  const trafficStrategyItems = $derived([
    {
      value: "NO_RESET",
      label: at(
        "settings_field_user_traffic_strategy_choice_no_reset",
        {},
        "Без автоматического сброса"
      ),
    },
    {
      value: "DAY",
      label: at("settings_field_user_traffic_strategy_choice_day", {}, "Каждый день"),
    },
    {
      value: "WEEK",
      label: at("settings_field_user_traffic_strategy_choice_week", {}, "Каждую неделю"),
    },
    {
      value: "MONTH",
      label: at("settings_field_user_traffic_strategy_choice_month", {}, "Каждый месяц"),
    },
    {
      value: "MONTH_ROLLING",
      label: at(
        "settings_field_user_traffic_strategy_choice_month_rolling",
        {},
        "Месяц от даты сброса"
      ),
    },
  ]);
  const trafficStrategyDraftValid = $derived(
    trafficStrategyItems.some((item) => item.value === trafficStrategyDraft)
  );
  const trafficStrategyDirty = $derived(
    Boolean(trafficStrategyDraft) && trafficStrategyDraft !== trafficStrategyBaseline
  );
  const trafficStrategyEditable = $derived(
    Boolean(openedUserDetail?.active_subscription?.traffic_strategy_editable)
  );
  const trafficStrategyCurrentLabel = $derived(
    trafficStrategyItems.find((item) => item.value === trafficStrategyBaseline)?.label ||
      trafficStrategyBaseline ||
      "—"
  );
  const trafficStrategyLockMessage = $derived(
    trafficStrategyLockHint(openedUserDetail?.active_subscription?.traffic_strategy_lock_reason)
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
    if (openedUser && !tariffsState.panelSquadsLoading && !tariffsState.panelSquads.length) {
      void tariffsStore.loadPanelSquads();
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

<UserDetailView
  {at}
  {usersStore}
  {openedUser}
  {openedUserDetail}
  {userDetailLoading}
  {onClose}
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
  {subscriptionDisplayLabel}
  {pretty}
  {hwidLimitLabel}
  {trafficOfLabel}
  {trafficLeftLabel}
  {trafficPercentValue}
  {trialSummaryText}
  {fmtDateShort}
  {paymentStatusVariant}
  userLogsRows={userLogsTable.rows}
  {userLogsTotal}
  {userLogsPage}
  {userLogsPageCount}
  {userLogsPageSize}
  {userLogsLoading}
  {userLogsLoaded}
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
  {selectGrantTrafficKind}
  {grantTrafficGbValid}
  {panelSquadItems}
  squadLabel={tariffsStore.squadLabel}
  {userSquadOverrideDraft}
  {selectUserSquadOverride}
  {userExternalSquadModeDraft}
  {selectUserExternalSquadMode}
  {userExternalSquadUuidDraft}
  {updateUserExternalSquadUuid}
/>
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
  {userTariffHwidConfirmOpen}
  {tariffHwidCurrentLabel}
  {tariffHwidTargetLabel}
  {userDeleteOpen}
  {userActionBusy}
/>
