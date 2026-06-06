import { writable } from "svelte/store";
import { withRoutePrefix } from "../../webapp/routes.js";

export function createUsersStore({ api, onToast, at, routePrefix = "" }) {
  const USERS_PAGE_SIZE = 25;
  const USER_LOGS_PAGE_SIZE = 20;

  const state = writable({
    users: [],
    usersTotal: 0,
    usersPage: 0,
    usersQuery: "",
    usersFilter: "all",
    usersPanelStatus: "all",
    usersPremiumTraffic: "all",
    usersSort: "",
    usersLoading: false,

    ..._closedUserModalState(),
    userReferralsPageSize: USERS_PAGE_SIZE,
    userLogsPageSize: USER_LOGS_PAGE_SIZE,
  });

  let _activeRef = "stats"; // fallback if active isn't tracked
  let _pathContext = null;
  let _openUserRequestId = 0;

  function _closedUserModalState() {
    return {
      openedUser: null,
      openedUserDetail: null,
      userDetailLoading: false,
      userMessageDraft: "",
      userExtendDays: 30,
      userExtendHwidDevices: true,
      userActionBusy: false,
      userDeleteOpen: false,
      userBanConfirmOpen: false,
      userMessageConfirmOpen: false,
      userReferralsOpen: false,
      userReferralsLoading: false,
      userReferrals: [],
      userReferralsTotal: 0,
      userReferralsPage: 0,
      userReferralsInviter: null,
      userDetailTab: "profile",
      premiumUnlimitedDraft: false,
      premiumBonusGbDraft: "",
      regularUnlimitedDraft: false,
      regularBonusGbDraft: "",
      hwidUnlimitedDraft: false,
      hwidDeviceLimitDraft: "",
      grantTrafficGbDraft: "",
      grantTrafficKindDraft: "regular",
      userLogs: [],
      userLogsTotal: 0,
      userLogsPage: 0,
      userLogsLoading: false,
      userLogsLoaded: false,
      userLogsUserId: null,
    };
  }

  function _openingUserModalState(user, userId) {
    return {
      ..._closedUserModalState(),
      openedUser: user,
      userDetailLoading: true,
      userDetailTab: "subscription",
      userLogsUserId: userId,
    };
  }

  function _isCurrentUserRequest(s, requestId, userId) {
    return (
      requestId === _openUserRequestId &&
      Boolean(s.openedUser) &&
      s.openedUser.user_id === userId
    );
  }

  function setActive(active) {
    _activeRef = active;
  }

  function _setPathContext(context) {
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

  function _pushUserPath(userId) {
    if (typeof window === "undefined") return;
    if (window.location.protocol === "file:") return;
    let target = "";
    if (_activeRef === "users") {
      target = userId ? `/admin/users/${userId}` : `/admin/users`;
    } else if (_activeRef === "payments" && _pathContext === "payments") {
      target = userId ? `/admin/payments/users/${userId}` : `/admin/payments`;
    }
    if (!target) return;
    target = withRoutePrefix(target, routePrefix);
    if (window.location.pathname === target) return;
    window.history.pushState(null, "", `${target}${window.location.search}${window.location.hash}`);
  }

  async function loadUsers() {
    state.update((s) => ({ ...s, usersLoading: true }));
    let s;
    state.update((st) => {
      s = st;
      return st;
    });

    try {
      const params = new URLSearchParams({
        page: String(s.usersPage),
        page_size: String(USERS_PAGE_SIZE),
      });
      if (s.usersQuery.trim()) params.set("q", s.usersQuery.trim());
      if (s.usersFilter && s.usersFilter !== "all") params.set("filter", s.usersFilter);
      if (s.usersPanelStatus && s.usersPanelStatus !== "all")
        params.set("panel_status", s.usersPanelStatus);
      if (s.usersPremiumTraffic && s.usersPremiumTraffic !== "all") {
        params.set("premium_traffic", s.usersPremiumTraffic);
      }
      if (s.usersSort) params.set("sort", s.usersSort);
      const data = await api(`/admin/users?${params.toString()}`);
      if (data?.ok) {
        state.update((st) => ({
          ...st,
          users: data.users || [],
          usersTotal: data.total || (data.users || []).length,
        }));
      }
    } finally {
      state.update((st) => ({ ...st, usersLoading: false }));
    }
  }

  async function openUser(userOrId, opts = {}) {
    const userId =
      typeof userOrId === "object" && userOrId !== null ? userOrId.user_id : Number(userOrId);
    if (!userId) return;
    const requestId = ++_openUserRequestId;
    _setPathContext(opts.pathContext);
    const openedUser =
      typeof userOrId === "object" && userOrId !== null ? userOrId : { user_id: userId };

    state.update((s) => ({
      ...s,
      ..._openingUserModalState(openedUser, userId),
      userActionBusy: s.userActionBusy,
    }));

    if (!opts.skipPush) _pushUserPath(userId);
    try {
      const res = await api(`/admin/users/${userId}`);
      if (res?.ok) {
        const sub = res.active_subscription || null;
        const bonusBytes = Number(sub?.premium_bonus_bytes || 0);
        const regularBonusBytes = Number(sub?.regular_bonus_bytes || 0);
        const hasHwidLimit =
          sub?.hwid_device_limit !== null && sub?.hwid_device_limit !== undefined;
        const hwidLimit = hasHwidLimit ? Number(sub?.hwid_device_limit) : null;
        state.update((s) => {
          if (!_isCurrentUserRequest(s, requestId, userId)) return s;
          return {
            ...s,
            openedUserDetail: res,
            openedUser: res.user ? { ...res.user, ...s.openedUser, ...res.user } : s.openedUser,
            premiumUnlimitedDraft: Boolean(sub?.premium_unlimited_override),
            premiumBonusGbDraft: bonusBytes > 0 ? +(bonusBytes / 1024 ** 3).toFixed(2) : "",
            regularUnlimitedDraft: Boolean(sub?.regular_unlimited_override),
            regularBonusGbDraft:
              regularBonusBytes > 0 ? +(regularBonusBytes / 1024 ** 3).toFixed(2) : "",
            hwidUnlimitedDraft: hasHwidLimit && hwidLimit === 0,
            hwidDeviceLimitDraft: hasHwidLimit && hwidLimit > 0 ? String(hwidLimit) : "",
            grantTrafficGbDraft: "",
            grantTrafficKindDraft: "regular",
          };
        });
      } else {
        let shouldClearPath = false;
        let shouldShowError = false;
        state.update((s) => {
          if (!_isCurrentUserRequest(s, requestId, userId)) return s;
          shouldShowError = true;
          shouldClearPath = true;
          _pathContext = null;
          return { ...s, ..._closedUserModalState() };
        });
        if (shouldShowError) onToast(res?.error || "load_failed");
        if (shouldClearPath && !opts.skipPush) _pushUserPath(null);
      }
    } finally {
      state.update((s) => {
        if (!_isCurrentUserRequest(s, requestId, userId)) return s;
        return { ...s, userDetailLoading: false };
      });
    }
  }

  function closeUser(opts = {}) {
    let wasOpen = false;
    _openUserRequestId += 1;
    state.update((s) => {
      wasOpen = Boolean(s.openedUser);
      return {
        ...s,
        ..._closedUserModalState(),
      };
    });
    if (wasOpen && !opts.skipPush) _pushUserPath(null);
    _pathContext = null;
  }

  async function loadUserLogs(page) {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!s.openedUser) return;
    const userId = s.openedUser.user_id;
    const targetPage = Number.isFinite(page) ? Math.max(0, Math.floor(page)) : s.userLogsPage || 0;
    state.update((st) => ({
      ...st,
      userLogsLoading: true,
      userLogsPage: targetPage,
      userLogsUserId: userId,
    }));
    try {
      const params = new URLSearchParams({
        page: String(targetPage),
        page_size: String(USER_LOGS_PAGE_SIZE),
        user_id: String(userId),
      });
      const data = await api(`/admin/logs?${params.toString()}`);
      if (data?.ok) {
        state.update((st) => {
          if (!st.openedUser || st.openedUser.user_id !== userId) return st;
          return {
            ...st,
            userLogs: data.logs || [],
            userLogsTotal: Number(data.total || 0),
            userLogsLoaded: true,
          };
        });
      } else if (data?.error) {
        onToast(data.error);
      }
    } finally {
      state.update((st) => ({ ...st, userLogsLoading: false }));
    }
  }

  function setUserLogsPage(page) {
    loadUserLogs(page);
  }

  async function openUserReferrals(page = 0) {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!s.openedUser) return;
    const userId = s.openedUser.user_id;
    const targetPage = Number.isFinite(page) ? Math.max(0, Math.floor(page)) : 0;
    state.update((st) => ({
      ...st,
      userReferralsOpen: true,
      userReferralsLoading: true,
      userReferralsPage: targetPage,
    }));
    try {
      const params = new URLSearchParams({
        page: String(targetPage),
        page_size: String(s.userReferralsPageSize || USERS_PAGE_SIZE),
      });
      const data = await api(`/admin/users/${userId}/referrals?${params.toString()}`);
      if (data?.ok) {
        state.update((st) => {
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
      } else if (data?.error) {
        onToast(data.error);
      }
    } finally {
      state.update((st) => ({ ...st, userReferralsLoading: false }));
    }
  }

  function closeUserReferrals() {
    state.update((s) => ({
      ...s,
      userReferralsOpen: false,
    }));
  }

  function setUserReferralsPage(page) {
    openUserReferrals(page);
  }

  function copyToClipboard(text, successMessage = at("link_copied", {}, "Скопировано")) {
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
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!s.openedUser) return;
    if (s.openedUser.is_banned) {
      applyBanToggle(false);
    } else {
      state.update((st) => ({ ...st, userBanConfirmOpen: true }));
    }
  }

  async function applyBanToggle(banned) {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!s.openedUser) return;
    state.update((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(`/admin/users/${s.openedUser.user_id}/ban`, {
        method: "POST",
        body: JSON.stringify({ banned }),
      });
      if (res?.ok) {
        state.update((st) => {
          const updatedUser = { ...st.openedUser, is_banned: banned };
          return {
            ...st,
            openedUser: updatedUser,
            users: st.users.map((u) => (u.user_id === updatedUser.user_id ? updatedUser : u)),
            userBanConfirmOpen: false,
          };
        });
        onToast(
          banned ? at("user_banned", {}, "Заблокирован") : at("user_unbanned", {}, "Разблокирован")
        );
      } else onToast(res?.error || at("error", {}, "Ошибка"));
    } finally {
      state.update((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function sendUserMessage() {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!s.openedUser || !s.userMessageDraft.trim()) return;
    state.update((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(`/admin/users/${s.openedUser.user_id}/message`, {
        method: "POST",
        body: JSON.stringify({ text: s.userMessageDraft }),
      });
      if (res?.ok) {
        onToast(at("message_sent", {}, "Отправлено"));
        state.update((st) => ({
          ...st,
          userMessageDraft: "",
          userMessageConfirmOpen: false,
        }));
      } else onToast(res?.error || at("message_send_failed", {}, "Ошибка отправки"));
    } finally {
      state.update((st) => ({ ...st, userActionBusy: false }));
    }
  }

  function requestSendUserMessage() {
    state.update((s) => {
      if (!s.openedUser || !s.userMessageDraft.trim()) return s;
      return { ...s, userMessageConfirmOpen: true };
    });
  }

  async function previewUserMessage() {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!s.openedUser || !s.userMessageDraft.trim()) return;
    state.update((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(`/admin/users/${s.openedUser.user_id}/message/preview`, {
        method: "POST",
        body: JSON.stringify({ text: s.userMessageDraft }),
      });
      if (res?.ok) onToast(at("message_preview_sent", {}, "Превью отправлено в Telegram"));
      else onToast(res?.error || at("message_preview_failed", {}, "Ошибка отправки превью"));
    } finally {
      state.update((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function sendTelegramProfileLink() {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!s.openedUser) return;
    state.update((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(`/admin/users/${s.openedUser.user_id}/telegram-profile-link`, {
        method: "POST",
      });
      if (res?.ok) {
        onToast(at("user_tg_profile_link_sent", {}, "Ссылка отправлена в Telegram"));
      } else {
        onToast(res?.error || at("user_tg_profile_link_failed", {}, "Не удалось отправить ссылку"));
      }
    } finally {
      state.update((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function extendUser() {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!s.openedUser) return;
    const days = Number(s.userExtendDays);
    if (!days || days <= 0) return;
    state.update((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(`/admin/users/${s.openedUser.user_id}/extend`, {
        method: "POST",
        body: JSON.stringify({ days, extend_hwid_devices: Boolean(s.userExtendHwidDevices) }),
      });
      if (res?.ok) {
        onToast(at("subscription_extended", { days }, `Продлено на ${days} д.`));
        await openUser(s.openedUser, { skipPush: true });
      } else onToast(res?.error || at("error", {}, "Ошибка"));
    } finally {
      state.update((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function resetTrialUser() {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!s.openedUser) return;
    state.update((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(`/admin/users/${s.openedUser.user_id}/reset-trial`, { method: "POST" });
      if (res?.ok) {
        onToast(at("trial_reset", {}, "Триал сброшен"));
        await openUser(s.openedUser.user_id, { skipPush: true, pathContext: _pathContext });
        if (_activeRef === "users") await loadUsers();
      } else onToast(res?.error || at("error", {}, "Ошибка"));
    } finally {
      state.update((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function savePremiumTrafficOverride() {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!s.openedUser) return;
    state.update((st) => ({ ...st, userActionBusy: true }));
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
      const res = await api(`/admin/users/${s.openedUser.user_id}/premium-override`, {
        method: "POST",
        body: JSON.stringify({
          unlimited: Boolean(s.premiumUnlimitedDraft),
          bonus_gb: bonusGb,
        }),
      });
      if (res?.ok) {
        onToast(at("premium_override_saved", {}, "Премиум-оверрайд сохранён"));
        await openUser(s.openedUser, { skipPush: true });
      } else {
        onToast(res?.error || at("error", {}, "Ошибка"));
      }
    } finally {
      state.update((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function saveRegularTrafficOverride() {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!s.openedUser) return;
    state.update((st) => ({ ...st, userActionBusy: true }));
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
      const res = await api(`/admin/users/${s.openedUser.user_id}/regular-traffic-override`, {
        method: "POST",
        body: JSON.stringify({
          unlimited: Boolean(s.regularUnlimitedDraft),
          regular_bonus_gb: regularGb,
        }),
      });
      if (res?.ok) {
        onToast(at("regular_override_saved", {}, "Оверрайд основного трафика сохранён"));
        await openUser(s.openedUser, { skipPush: true });
      } else {
        onToast(res?.error || at("error", {}, "Ошибка"));
      }
    } finally {
      state.update((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function saveHwidDeviceLimit() {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!s.openedUser) return;
    state.update((st) => ({ ...st, userActionBusy: true }));
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
      const res = await api(`/admin/users/${s.openedUser.user_id}/hwid-device-limit`, {
        method: "POST",
        body: JSON.stringify({
          unlimited,
          use_default: useDefault,
          hwid_device_limit: unlimited ? 0 : limit,
        }),
      });
      if (res?.ok) {
        onToast(at("hwid_limit_saved", {}, "Лимит устройств сохранён"));
        await openUser(s.openedUser, { skipPush: true });
      } else {
        onToast(res?.error || at("error", {}, "Ошибка"));
      }
    } finally {
      state.update((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function grantTraffic() {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!s.openedUser) return;
    const gbRaw = s.grantTrafficGbDraft;
    const gb = Number(gbRaw);
    if (!gbRaw || Number.isNaN(gb) || gb <= 0) {
      onToast(at("traffic_grant_invalid_gb", {}, "Введите положительное число GB"));
      return;
    }
    const kind = s.grantTrafficKindDraft === "premium" ? "premium" : "regular";
    state.update((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(`/admin/users/${s.openedUser.user_id}/traffic-grant`, {
        method: "POST",
        body: JSON.stringify({ kind, gb }),
      });
      if (res?.ok) {
        onToast(
          kind === "premium"
            ? at("traffic_grant_premium_done", { gb }, `+${gb} ГБ премиум-трафика`)
            : at("traffic_grant_regular_done", { gb }, `+${gb} ГБ трафика`)
        );
        state.update((st) => ({ ...st, grantTrafficGbDraft: "" }));
        await openUser(s.openedUser, { skipPush: true });
      } else {
        onToast(res?.error || at("error", {}, "Ошибка"));
      }
    } finally {
      state.update((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function deleteUser() {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!s.openedUser) return;
    state.update((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(`/admin/users/${s.openedUser.user_id}`, { method: "DELETE" });
      if (res?.ok) {
        onToast(at("user_deleted", {}, "Удален"));
        state.update((st) => ({
          ...st,
          users: st.users.filter((u) => u.user_id !== st.openedUser.user_id),
        }));
        closeUser();
      } else onToast(res?.error || at("error", {}, "Ошибка"));
    } finally {
      state.update((st) => ({ ...st, userActionBusy: false }));
    }
  }

  function updateState(updates) {
    state.update((s) => ({ ...s, ...updates }));
  }

  return {
    subscribe: state.subscribe,
    set: state.set,
    update: state.update,
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
    resetTrialUser,
    deleteUser,
    savePremiumTrafficOverride,
    saveRegularTrafficOverride,
    saveHwidDeviceLimit,
    grantTraffic,
    loadUserLogs,
    setUserLogsPage,
    openUserReferrals,
    closeUserReferrals,
    setUserReferralsPage,
  };
}
