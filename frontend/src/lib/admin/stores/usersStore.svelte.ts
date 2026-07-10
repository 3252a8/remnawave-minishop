import { adminErrorMessage } from "../errors.js";
import { createAdminPerfSpan } from "../adminPerfMarks";
import { userDisplayName } from "../users.js";
import { withRoutePrefix } from "../../webapp/routes.js";
import { snapshotForPayload } from "./snapshotForPayload.svelte";
import { defineRawStateProperty } from "./rawStateProperty";
import { AdminUsersError, createUsersStoreQueries } from "./usersStoreQueries";
import { createUsersStoreSquadOverrideActions } from "./usersStoreSquadOverrides";
import {
  buildAdminUserActionPath,
  buildAdminUserPath,
  buildAdminPaymentsPath,
  buildAdminPaymentsUserPath,
  buildAdminUsersPath,
} from "../../webapp/publicApi";
import {
  USERS_PAGE_SIZE,
  closedUserModalState,
  createInitialUsersState,
  type AdminStoreState,
  type AdminSubscription,
  type AdminUser,
  type AdminUserDetail,
  type OpenUserOptions,
  type PathContext,
  type SnapshotOptions,
  type UserLogRow,
  type UsersStoreOptions,
} from "./usersStoreState";

export type { AdminUser } from "./usersStoreState";

type RawUsersState = Pick<AdminStoreState, "users" | "userReferrals" | "userLogs">;
type ProxiedUsersState = Omit<AdminStoreState, keyof RawUsersState>;

export function createUsersStore({
  api,
  onToast,
  at,
  routePrefix = "",
  queryClient = null,
}: UsersStoreOptions) {
  const {
    users: initialUsers,
    userReferrals: initialUserReferrals,
    userLogs: initialUserLogs,
    ...initialProxiedState
  } = createInitialUsersState();
  let users = $state.raw<AdminUser[]>(initialUsers);
  let userReferrals = $state.raw<AdminUser[]>(initialUserReferrals);
  let userLogs = $state.raw<UserLogRow[]>(initialUserLogs);
  const state = $state<ProxiedUsersState>({ ...initialProxiedState });
  const stateKeys = Object.keys(initialProxiedState) as Array<keyof ProxiedUsersState>;
  const store = Object.create(state) as AdminStoreState;
  defineRawStateProperty(store, "users", {
    get: () => users,
    set: (value) => {
      users = value;
    },
  });
  defineRawStateProperty(store, "userReferrals", {
    get: () => userReferrals,
    set: (value) => {
      userReferrals = value;
    },
  });
  defineRawStateProperty(store, "userLogs", {
    get: () => userLogs,
    set: (value) => {
      userLogs = value;
    },
  });

  let _activeRef = "stats"; // fallback if active isn't tracked
  let _pathContext: PathContext = null;
  let _openUserRequestId = 0;
  let _loadUsersRequestId = 0;
  const {
    invalidateUsersQueries,
    loadUserErrorMessage,
    queryUserDetail,
    queryUserLogs,
    queryUserReferrals,
    queryUsers,
  } = createUsersStoreQueries({ api, at, queryClient });

  function applyState(updater: (snapshot: AdminStoreState) => AdminStoreState): void {
    const current = readCurrentState();
    const next = updater(current);
    if (next === current) return;
    assignState(next);
  }

  function assignState(next: Partial<AdminStoreState>): void {
    const {
      users: nextUsers,
      userReferrals: nextUserReferrals,
      userLogs: nextUserLogs,
      ...nextState
    } = next;
    if (nextUsers !== undefined && nextUsers !== users) users = nextUsers;
    if (nextUserReferrals !== undefined && nextUserReferrals !== userReferrals) {
      userReferrals = nextUserReferrals;
    }
    if (nextUserLogs !== undefined && nextUserLogs !== userLogs) userLogs = nextUserLogs;
    Object.assign(state, nextState);
  }

  function readCurrentState(): AdminStoreState {
    return {
      ...(Object.fromEntries(stateKeys.map((key) => [key, state[key]])) as ProxiedUsersState),
      users,
      userReferrals,
      userLogs,
    } satisfies AdminStoreState;
  }

  function readStateSnapshot(): AdminStoreState {
    return snapshotForPayload(readCurrentState());
  }

  function _openingUserModalState(
    user: AdminUser | null,
    userId: number
  ): Partial<AdminStoreState> {
    return {
      ...closedUserModalState(),
      openedUser: user,
      userDetailLoading: true,
      userDetailTab: "subscription",
      userLogsUserId: userId,
    };
  }

  function _isCurrentUserRequest(s: AdminStoreState, requestId: number, userId: number) {
    const openedUser = s.openedUser;
    return (
      requestId === _openUserRequestId && Boolean(openedUser) && openedUser?.user_id === userId
    );
  }

  function _gbDraftFromBytes(bytes: unknown) {
    const value = Number(bytes || 0);
    return value > 0 ? +(value / 1024 ** 3).toFixed(2) : "";
  }

  function _draftStateFromSubscription(sub: AdminSubscription | null | undefined) {
    const bonusGb = _gbDraftFromBytes(sub?.premium_bonus_bytes);
    const regularBonusGb = _gbDraftFromBytes(sub?.regular_bonus_bytes);
    const hasHwidLimit = sub?.hwid_device_limit !== null && sub?.hwid_device_limit !== undefined;
    const hwidLimit = hasHwidLimit ? Number(sub?.hwid_device_limit) : null;
    const hwidUnlimited = hasHwidLimit && hwidLimit === 0;
    const hwidLimitDraft =
      hasHwidLimit && hwidLimit !== null && hwidLimit > 0 ? String(hwidLimit) : "";
    const tariffKey = String(sub?.tariff_key || "");
    const trafficStrategy = String(sub?.traffic_limit_strategy || "NO_RESET").trim() || "NO_RESET";

    return {
      tariffKey,
      trafficStrategy,
      premiumUnlimited: Boolean(sub?.premium_unlimited_override),
      premiumBonusGb: bonusGb,
      regularUnlimited: Boolean(sub?.regular_unlimited_override),
      regularBonusGb,
      hwidUnlimited,
      hwidDeviceLimit: hwidLimitDraft,
    };
  }

  function _applyUserDetailSnapshot(
    s: AdminStoreState,
    res: AdminUserDetail,
    options: SnapshotOptions = {}
  ) {
    const {
      resetExtendTariff = true,
      resetTariffAction = true,
      resetTrafficStrategy = true,
      resetPremium = true,
      resetRegular = true,
      resetHwid = true,
      resetGrant = true,
      resetSquadOverrides = true,
    } = options;
    const sub = res.active_subscription || null;
    const draft = _draftStateFromSubscription(sub);
    const next: AdminStoreState = {
      ...s,
      openedUserDetail: res,
      openedUser: res.user ? { ...res.user, ...s.openedUser, ...res.user } : s.openedUser,
    };

    if (resetExtendTariff) {
      next.userExtendTariffKey = draft.tariffKey || s.userExtendTariffKey || "";
    }
    if (resetTariffAction) {
      next.userTariffActionKey = draft.tariffKey;
      next.userTariffActionBaselineKey = draft.tariffKey;
    }
    if (resetTrafficStrategy) {
      next.trafficStrategyDraft = draft.trafficStrategy;
      next.trafficStrategyBaseline = draft.trafficStrategy;
    }
    if (resetPremium) {
      next.premiumUnlimitedDraft = draft.premiumUnlimited;
      next.premiumBonusGbDraft = draft.premiumBonusGb;
      next.premiumUnlimitedBaseline = draft.premiumUnlimited;
      next.premiumBonusGbBaseline = draft.premiumBonusGb;
    }
    if (resetRegular) {
      next.regularUnlimitedDraft = draft.regularUnlimited;
      next.regularBonusGbDraft = draft.regularBonusGb;
      next.regularUnlimitedBaseline = draft.regularUnlimited;
      next.regularBonusGbBaseline = draft.regularBonusGb;
    }
    if (resetHwid) {
      next.hwidUnlimitedDraft = draft.hwidUnlimited;
      next.hwidDeviceLimitDraft = draft.hwidDeviceLimit;
      next.hwidUnlimitedBaseline = draft.hwidUnlimited;
      next.hwidDeviceLimitBaseline = draft.hwidDeviceLimit;
    }
    if (resetGrant) {
      next.grantTrafficGbDraft = "";
      next.grantTrafficKindDraft = "regular";
    }
    if (resetSquadOverrides) {
      const panelOverrides = res.panel_squad_overrides || null;
      const external = panelOverrides?.external || null;
      const mode = String(external?.mode || "inherit");
      next.userSquadOverrideDraft = "";
      next.userExternalSquadModeDraft = mode === "set" || mode === "cleared" ? mode : "inherit";
      next.userExternalSquadUuidDraft = String(
        external?.manual_uuid || (mode === "set" ? external?.effective_uuid || "" : "") || ""
      );
    }

    return next;
  }

  function setActive(active: string) {
    _activeRef = active;
  }

  function _setPathContext(context: PathContext | undefined) {
    if (context === "payments") {
      _pathContext = "payments";
      return;
    }
    if (_activeRef === "users") {
      _pathContext = "users";
      return;
    }
    _pathContext = null;
  }

  function _pushUserPath(userId: number | string | null) {
    if (typeof window === "undefined") return;
    if (window.location.protocol === "file:") return;
    let target = "";
    if (_activeRef === "users") {
      target = userId ? buildAdminUserPath(userId) : buildAdminUsersPath();
    } else if (_activeRef === "payments" && _pathContext === "payments") {
      target = userId ? buildAdminPaymentsUserPath(userId) : buildAdminPaymentsPath();
    }
    if (!target) return;
    target = withRoutePrefix(target, routePrefix);
    if (window.location.pathname === target) return;
    window.history.pushState(null, "", `${target}${window.location.search}${window.location.hash}`);
  }

  async function loadUsers({ refresh = false }: { refresh?: boolean } = {}) {
    const requestId = ++_loadUsersRequestId;
    const perf = createAdminPerfSpan("users");
    applyState((s) => ({ ...s, usersLoading: true }));
    const s = readStateSnapshot();

    try {
      const data = await queryUsers(s, refresh);
      perf.apiResponse();
      if (requestId === _loadUsersRequestId) {
        applyState((st) => ({
          ...st,
          users: data.users || [],
          usersTotal: data.total || (data.users || []).length,
        }));
        perf.stateAssign();
        void perf.renderSettled();
      }
    } catch (error) {
      const message = loadUserErrorMessage(error);
      if (message) onToast(message);
    } finally {
      if (requestId === _loadUsersRequestId) {
        applyState((st) => ({ ...st, usersLoading: false }));
      }
    }
  }

  async function openUser(userOrId: AdminUser | number | string, opts: OpenUserOptions = {}) {
    const userId: number =
      typeof userOrId === "object" && userOrId !== null
        ? Number(userOrId.user_id)
        : Number(userOrId);
    if (!userId) return;
    const requestId = ++_openUserRequestId;
    _setPathContext(opts.pathContext);
    const openedUser =
      typeof userOrId === "object" && userOrId !== null ? userOrId : { user_id: userId };

    applyState((s) => ({
      ...s,
      ..._openingUserModalState(openedUser, userId),
      userActionBusy: s.userActionBusy,
    }));

    if (!opts.skipPush) _pushUserPath(userId);
    try {
      const res = await queryUserDetail(userId);
      applyState((s) => {
        if (!_isCurrentUserRequest(s, requestId, userId)) return s;
        return _applyUserDetailSnapshot(s, res);
      });
    } catch (error) {
      if (error instanceof AdminUsersError) {
        let shouldClearPath = false;
        let shouldShowError = false;
        applyState((s) => {
          if (!_isCurrentUserRequest(s, requestId, userId)) return s;
          shouldShowError = true;
          shouldClearPath = true;
          _pathContext = null;
          return { ...s, ...closedUserModalState() };
        });
        if (shouldShowError) onToast(adminErrorMessage(error.payload, at, "load_failed"));
        if (shouldClearPath && !opts.skipPush) _pushUserPath(null);
      } else {
        onToast(loadUserErrorMessage(error));
      }
    } finally {
      applyState((s) => {
        if (!_isCurrentUserRequest(s, requestId, userId)) return s;
        return { ...s, userDetailLoading: false };
      });
    }
  }

  async function refreshOpenedUserDetail(options: SnapshotOptions = {}) {
    const snapshot = readStateSnapshot();
    const userId = Number(snapshot?.openedUser?.user_id || 0);
    if (!userId) return null;
    const requestId = _openUserRequestId;
    try {
      const res = await queryUserDetail(userId, true);
      applyState((s) => {
        if (!_isCurrentUserRequest(s, requestId, userId)) return s;
        return _applyUserDetailSnapshot(s, res, options);
      });
      return res;
    } catch (error) {
      if (error instanceof AdminUsersError) {
        onToast(adminErrorMessage(error.payload, at, "load_failed"));
        return error.payload;
      }
      onToast(loadUserErrorMessage(error));
      return null;
    }
  }

  function closeUser(opts: OpenUserOptions = {}) {
    let wasOpen = false;
    _openUserRequestId += 1;
    applyState((s) => {
      wasOpen = Boolean(s.openedUser);
      return {
        ...s,
        ...closedUserModalState(),
      };
    });
    if (wasOpen && !opts.skipPush) _pushUserPath(null);
    _pathContext = null;
  }

  async function loadUserLogs(page: number) {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    const userId = s.openedUser.user_id;
    const targetPage = Number.isFinite(page) ? Math.max(0, Math.floor(page)) : s.userLogsPage || 0;
    applyState((st) => ({
      ...st,
      userLogsLoading: true,
      userLogsPage: targetPage,
      userLogsUserId: userId,
    }));
    try {
      const data = await queryUserLogs(userId, targetPage);
      applyState((st) => {
        if (!st.openedUser || st.openedUser.user_id !== userId) return st;
        return {
          ...st,
          userLogs: data.logs || [],
          userLogsTotal: Number(data.total || 0),
          userLogsLoaded: true,
        };
      });
    } catch (error) {
      if (error instanceof AdminUsersError) {
        onToast(adminErrorMessage(error.payload, at));
      } else {
        onToast(loadUserErrorMessage(error));
      }
    } finally {
      applyState((st) => ({ ...st, userLogsLoading: false }));
    }
  }

  function setUserLogsPage(page: number) {
    loadUserLogs(page);
  }

  async function openUserReferrals(page = 0) {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    const userId = s.openedUser.user_id;
    const targetPage = Number.isFinite(page) ? Math.max(0, Math.floor(page)) : 0;
    applyState((st) => ({
      ...st,
      userReferralsOpen: true,
      userReferralsLoading: true,
      userReferralsPage: targetPage,
    }));
    try {
      const pageSize = s.userReferralsPageSize || USERS_PAGE_SIZE;
      const data = await queryUserReferrals(userId, targetPage, pageSize);
      applyState((st) => {
        if (!st.openedUser || st.openedUser.user_id !== userId) return st;
        return {
          ...st,
          userReferrals: data.invitees || [],
          userReferralsTotal: Number(data.total || 0),
          userReferralsPage: Number(data.page || 0),
          userReferralsPageSize: Number(data.page_size || st.userReferralsPageSize),
          userReferralsInviter: data.inviter || null,
        };
      });
    } catch (error) {
      if (error instanceof AdminUsersError) {
        onToast(adminErrorMessage(error.payload, at));
      } else {
        onToast(loadUserErrorMessage(error));
      }
    } finally {
      applyState((st) => ({ ...st, userReferralsLoading: false }));
    }
  }

  function closeUserReferrals() {
    applyState((s) => ({
      ...s,
      userReferralsOpen: false,
    }));
  }

  function setUserReferralsPage(page: number) {
    openUserReferrals(page);
  }

  function copyToClipboard(
    text: string | null | undefined,
    successMessage = at("link_copied", {}, "Скопировано")
  ) {
    if (!text) return;
    if (typeof navigator !== "undefined" && navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(
        () => onToast(successMessage),
        () => onToast(text)
      );
    } else {
      onToast(text);
    }
  }

  function requestBanToggle() {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    if (s.openedUser.is_banned) {
      applyBanToggle(false);
    } else {
      applyState((st) => ({ ...st, userBanConfirmOpen: true }));
    }
  }

  async function applyBanToggle(banned: boolean) {
    const s = readStateSnapshot();
    const openedUser = s.openedUser;
    if (!openedUser) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(buildAdminUserActionPath(openedUser.user_id, "ban"), {
        method: "POST",
        body: JSON.stringify({ banned }),
      });
      if (res?.ok) {
        invalidateUsersQueries(openedUser.user_id);
        applyState((st) => {
          const updatedUser: AdminUser = { ...openedUser, is_banned: banned };
          return {
            ...st,
            openedUser: updatedUser,
            users: st.users.map((u: AdminUser) =>
              u.user_id === updatedUser.user_id ? updatedUser : u
            ),
            userBanConfirmOpen: false,
          };
        });
        onToast(
          banned ? at("user_banned", {}, "Заблокирован") : at("user_unbanned", {}, "Разблокирован")
        );
      } else onToast(adminErrorMessage(res, at));
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function sendUserMessage() {
    const s = readStateSnapshot();
    if (!s.openedUser || !s.userMessageDraft.trim()) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(buildAdminUserActionPath(s.openedUser.user_id, "message"), {
        method: "POST",
        body: JSON.stringify({ text: s.userMessageDraft }),
      });
      if (res?.ok) {
        invalidateUsersQueries(s.openedUser.user_id);
        onToast(at("message_sent", {}, "Отправлено"));
        applyState((st) => ({
          ...st,
          userMessageDraft: "",
          userMessageConfirmOpen: false,
        }));
      } else onToast(adminErrorMessage(res, at, at("message_send_failed", {}, "Ошибка отправки")));
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  function requestSendUserMessage() {
    applyState((s) => {
      if (!s.openedUser || !s.userMessageDraft.trim()) return s;
      return { ...s, userMessageConfirmOpen: true };
    });
  }

  async function previewUserMessage() {
    const s = readStateSnapshot();
    if (!s.openedUser || !s.userMessageDraft.trim()) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(buildAdminUserActionPath(s.openedUser.user_id, "message/preview"), {
        method: "POST",
        body: JSON.stringify({ text: s.userMessageDraft }),
      });
      if (res?.ok) onToast(at("message_preview_sent", {}, "Превью отправлено в Telegram"));
      else
        onToast(
          adminErrorMessage(res, at, at("message_preview_failed", {}, "Ошибка отправки превью"))
        );
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function sendTelegramProfileLink() {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(
        buildAdminUserActionPath(s.openedUser.user_id, "telegram-profile-link"),
        {
          method: "POST",
        }
      );
      if (res?.ok) {
        invalidateUsersQueries(s.openedUser.user_id);
        onToast(at("user_tg_profile_link_sent", {}, "Ссылка отправлена в Telegram"));
      } else {
        onToast(
          adminErrorMessage(
            res,
            at,
            at("user_tg_profile_link_failed", {}, "Не удалось отправить ссылку")
          )
        );
      }
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function extendUser() {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    const days = Number(s.userExtendDays);
    if (!days || days <= 0) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const body: Record<string, unknown> = {
        days,
        extend_hwid_devices: Boolean(s.userExtendHwidDevices),
      };
      if (s.userExtendTariffKey) body.tariff_key = s.userExtendTariffKey;
      if (s.userApplyTariffHwidLimit) body.apply_tariff_hwid_limit = true;
      const res = await api(buildAdminUserActionPath(s.openedUser.user_id, "extend"), {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (res?.ok) {
        invalidateUsersQueries(s.openedUser.user_id);
        onToast(at("subscription_extended", { days }, `Продлено на ${days} д.`));
        await refreshOpenedUserDetail({
          resetTrafficStrategy: false,
          resetPremium: false,
          resetRegular: false,
          resetHwid: false,
          resetGrant: false,
        });
      } else onToast(adminErrorMessage(res, at));
    } finally {
      applyState((st) => ({
        ...st,
        userActionBusy: false,
        userApplyTariffHwidLimit: false,
      }));
    }
  }

  async function changeUserTariff() {
    const s = readStateSnapshot();
    if (!s.openedUser || !s.userTariffActionKey) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(buildAdminUserActionPath(s.openedUser.user_id, "tariff"), {
        method: "POST",
        body: JSON.stringify({
          tariff_key: s.userTariffActionKey,
          apply_tariff_hwid_limit: Boolean(s.userApplyTariffHwidLimit),
        }),
      });
      if (res?.ok) {
        invalidateUsersQueries(s.openedUser.user_id);
        onToast(at("user_tariff_saved", {}, "Tariff saved"));
        await refreshOpenedUserDetail({
          resetPremium: false,
          resetRegular: false,
          resetHwid: false,
          resetGrant: false,
        });
        if (_activeRef === "users") await loadUsers({ refresh: true });
      } else {
        onToast(adminErrorMessage(res, at));
      }
    } finally {
      applyState((st) => ({
        ...st,
        userActionBusy: false,
        userApplyTariffHwidLimit: false,
        userTariffHwidConfirmOpen: false,
      }));
    }
  }

  async function resetTrialUser() {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(buildAdminUserActionPath(s.openedUser.user_id, "reset-trial"), {
        method: "POST",
      });
      if (res?.ok) {
        invalidateUsersQueries(s.openedUser.user_id);
        onToast(at("trial_reset", {}, "Триал сброшен"));
        await refreshOpenedUserDetail({
          resetExtendTariff: false,
          resetTariffAction: false,
          resetTrafficStrategy: false,
          resetPremium: false,
          resetRegular: false,
          resetHwid: false,
          resetGrant: false,
        });
        if (_activeRef === "users") await loadUsers({ refresh: true });
      } else onToast(adminErrorMessage(res, at));
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function savePremiumTrafficOverride() {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const bonusGbRaw = s.premiumBonusGbDraft;
      const bonusGb =
        bonusGbRaw === "" || bonusGbRaw === null || bonusGbRaw === undefined
          ? 0
          : Number(bonusGbRaw);
      if (Number.isNaN(bonusGb) || bonusGb < 0) {
        onToast(at("premium_override_invalid_bonus", {}, "Некорректное значение GB"));
        return;
      }
      const res = await api(buildAdminUserActionPath(s.openedUser.user_id, "premium-override"), {
        method: "POST",
        body: JSON.stringify({
          unlimited: Boolean(s.premiumUnlimitedDraft),
          bonus_gb: bonusGb,
        }),
      });
      if (res?.ok) {
        invalidateUsersQueries(s.openedUser.user_id);
        onToast(at("premium_override_saved", {}, "Премиум-оверрайд сохранён"));
        await refreshOpenedUserDetail({
          resetExtendTariff: false,
          resetTariffAction: false,
          resetTrafficStrategy: false,
          resetRegular: false,
          resetHwid: false,
          resetGrant: false,
        });
      } else {
        onToast(adminErrorMessage(res, at));
      }
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function saveRegularTrafficOverride() {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const regGbRaw = s.regularBonusGbDraft;
      const regularGb =
        regGbRaw === "" || regGbRaw === null || regGbRaw === undefined ? 0 : Number(regGbRaw);
      if (Number.isNaN(regularGb) || regularGb < 0) {
        onToast(
          at("regular_override_invalid_bonus", {}, "Некорректное значение GB для основного трафика")
        );
        return;
      }
      const res = await api(
        buildAdminUserActionPath(s.openedUser.user_id, "regular-traffic-override"),
        {
          method: "POST",
          body: JSON.stringify({
            unlimited: Boolean(s.regularUnlimitedDraft),
            regular_bonus_gb: regularGb,
          }),
        }
      );
      if (res?.ok) {
        invalidateUsersQueries(s.openedUser.user_id);
        onToast(at("regular_override_saved", {}, "Оверрайд основного трафика сохранён"));
        await refreshOpenedUserDetail({
          resetExtendTariff: false,
          resetTariffAction: false,
          resetTrafficStrategy: false,
          resetPremium: false,
          resetHwid: false,
          resetGrant: false,
        });
      } else {
        onToast(adminErrorMessage(res, at));
      }
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function saveTrafficStrategy() {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    const trafficLimitStrategy = String(s.trafficStrategyDraft || "")
      .trim()
      .toUpperCase();
    if (!trafficLimitStrategy) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(buildAdminUserActionPath(s.openedUser.user_id, "traffic-strategy"), {
        method: "POST",
        body: JSON.stringify({ traffic_limit_strategy: trafficLimitStrategy }),
      });
      if (res?.ok) {
        invalidateUsersQueries(s.openedUser.user_id);
        onToast(at("user_traffic_strategy_saved", {}, "Стратегия сброса сохранена"));
        await refreshOpenedUserDetail({
          resetExtendTariff: false,
          resetTariffAction: false,
          resetPremium: false,
          resetRegular: false,
          resetHwid: false,
          resetGrant: false,
        });
      } else {
        onToast(adminErrorMessage(res, at));
      }
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function saveHwidDeviceLimit() {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const unlimited = Boolean(s.hwidUnlimitedDraft);
      const raw = s.hwidDeviceLimitDraft;
      const useDefault = !unlimited && (raw === "" || raw === null || raw === undefined);
      let limit = null;
      if (!unlimited && !useDefault) {
        limit = Number(raw);
        if (!Number.isInteger(limit) || limit < 0 || limit > 1_000_000) {
          onToast(
            at(
              "hwid_limit_invalid",
              {},
              "Введите целое число устройств от 0 до 1 000 000 или включите безлимит"
            )
          );
          return;
        }
      }
      const res = await api(buildAdminUserActionPath(s.openedUser.user_id, "hwid-device-limit"), {
        method: "POST",
        body: JSON.stringify({
          unlimited,
          use_default: useDefault,
          hwid_device_limit: unlimited ? 0 : limit,
        }),
      });
      if (res?.ok) {
        invalidateUsersQueries(s.openedUser.user_id);
        onToast(at("hwid_limit_saved", {}, "Лимит устройств сохранён"));
        await refreshOpenedUserDetail({
          resetExtendTariff: false,
          resetTariffAction: false,
          resetTrafficStrategy: false,
          resetPremium: false,
          resetRegular: false,
          resetGrant: false,
        });
      } else {
        onToast(adminErrorMessage(res, at));
      }
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function grantTraffic() {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    const gbRaw = s.grantTrafficGbDraft;
    const gb = Number(gbRaw);
    if (!gbRaw || Number.isNaN(gb) || gb <= 0) {
      onToast(at("traffic_grant_invalid_gb", {}, "Введите положительное число GB"));
      return;
    }
    const kind = s.grantTrafficKindDraft === "premium" ? "premium" : "regular";
    const userId = String(s.openedUser.user_id ?? "");
    const user = userDisplayName(s.openedUser);
    const toastParams = { gb, user_id: userId, user };
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(buildAdminUserActionPath(s.openedUser.user_id, "traffic-grant"), {
        method: "POST",
        body: JSON.stringify({ kind, gb }),
      });
      if (res?.ok) {
        invalidateUsersQueries(s.openedUser.user_id);
        onToast(
          kind === "premium"
            ? at(
                "traffic_grant_premium_done",
                toastParams,
                `+${gb} ГБ премиум-трафика для ${user} (ID: ${userId})`
              )
            : at(
                "traffic_grant_regular_done",
                toastParams,
                `+${gb} ГБ трафика для ${user} (ID: ${userId})`
              )
        );
        await refreshOpenedUserDetail({
          resetExtendTariff: false,
          resetTariffAction: false,
          resetTrafficStrategy: false,
          resetPremium: false,
          resetRegular: false,
          resetHwid: false,
        });
      } else {
        onToast(adminErrorMessage(res, at));
      }
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function deleteUser() {
    const s = readStateSnapshot();
    const openedUser = s.openedUser;
    if (!openedUser) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(buildAdminUserPath(openedUser.user_id), { method: "DELETE" });
      if (res?.ok) {
        invalidateUsersQueries(openedUser.user_id);
        onToast(at("user_deleted", {}, "Удален"));
        applyState((st) => ({
          ...st,
          users: st.users.filter((u: AdminUser) => u.user_id !== openedUser.user_id),
        }));
        closeUser();
      } else onToast(adminErrorMessage(res, at));
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  function updateState(updates: Partial<AdminStoreState>) {
    if (!Object.keys(updates).length) return;
    assignState(updates);
  }

  const squadOverrideActions = createUsersStoreSquadOverrideActions({
    api,
    onToast,
    at,
    readStateSnapshot,
    applyState,
    invalidateUsersQueries,
  });

  return Object.assign(store, {
    updateState,
    setActive,
    loadUsers,
    openUser,
    closeUser,
    copyToClipboard,
    requestBanToggle,
    applyBanToggle,
    sendUserMessage,
    requestSendUserMessage,
    previewUserMessage,
    sendTelegramProfileLink,
    extendUser,
    changeUserTariff,
    resetTrialUser,
    deleteUser,
    savePremiumTrafficOverride,
    saveRegularTrafficOverride,
    saveTrafficStrategy,
    saveHwidDeviceLimit,
    grantTraffic,
    ...squadOverrideActions,
    loadUserLogs,
    setUserLogsPage,
    openUserReferrals,
    closeUserReferrals,
    setUserReferralsPage,
  });
}

export type UsersStore = ReturnType<typeof createUsersStore>;
