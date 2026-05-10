<script>
  import {
    ArrowLeft,
    BarChart3,
    Check,
    ChevronsUpDown,
    ChevronDown,
    ChevronLeft,
    ChevronRight,
    Coins,
    Copy,
    ExternalLink,
    CreditCard,
    Database,
    Download,
    Eye,
    EyeOff,
    FileText,
    Globe2,
    LayoutDashboard,
    Megaphone,
    Menu,
    Plus,
    RefreshCw,
    Save,
    Send,
    Settings as SettingsIcon,
    Shield,
    Sliders,
    Sparkles,
    Tag,
    Trash2,
    UserMinus,
    UserPlus,
    UserRound,
    UsersRound,
    X,
  } from "lucide-svelte";
  import { onMount } from "svelte";
  import { Accordion, Label, Select, Separator, Switch, Tabs } from "bits-ui";

  import BrandMark from "../BrandMark.svelte";
  import Dialog from "../lib/components/ui/dialog.svelte";

  export let api;
  export let onClose = () => {};
  export let onToast = () => {};
  export let initialSection = "stats";
  export let initialUserId = null;
  export let onSectionChange = () => {};
  export let onSettingsSaved = () => {};
  export let onTariffsSaved = () => {};
  export let brandTitle = "/minishop";
  export let logoUrl = "";
  export let logoEmoji = "рџ«Ґ";
  export let appVersion = "dev+local";
  export let appRepositoryUrl = "https://github.com/3252a8/remnawave-minishop";
  export let currentLang = "ru";
  export let languageOptions = [];
  export let languageBusy = false;
  export let onLanguageChange = () => {};
  export let t = (key, params = {}, fallback = "") => fallback || key;

  const at = (key, params = {}, fallback = "") => t(`admin_${key}`, params, fallback || key);

  const NAV_GROUPS = [
    {
      id: "overview",
      label: at("nav_overview", {}, "Overview"),
      items: [
        { id: "stats", label: at("nav_dashboard", {}, "Дашборд"), icon: LayoutDashboard },
      ],
    },
    {
      id: "operations",
      label: at("nav_operations", {}, "Управление"),
      items: [
        { id: "users", label: at("nav_users", {}, "Пользователи"), icon: UsersRound },
        { id: "payments", label: at("nav_payments", {}, "Платежи"), icon: CreditCard },
        { id: "promos", label: at("nav_promos", {}, "Промокоды"), icon: Tag },
        { id: "ads", label: at("nav_ads", {}, "Реклама"), icon: Sparkles },
      ],
    },
    {
      id: "communication",
      label: at("nav_communication", {}, "Коммуникации"),
      items: [
        { id: "broadcast", label: at("nav_broadcast", {}, "Рассылка"), icon: Megaphone },
        { id: "logs", label: at("nav_logs", {}, "Логи"), icon: FileText },
      ],
    },
    {
      id: "system",
      label: at("nav_system", {}, "Система"),
      items: [
        { id: "tariffs", label: at("nav_tariffs", {}, "Тарифы"), icon: Coins },
        { id: "settings", label: at("nav_settings", {}, "Настройки"), icon: Sliders },
      ],
    },
  ];

  const SECTION_META = {
    stats: { title: at("section_stats_title", {}, "Дашборд"), subtitle: at("section_stats_subtitle", {}, "Сводка по магазину и панели") },
    users: { title: at("section_users_title", {}, "Пользователи"), subtitle: at("section_users_subtitle", {}, "Поиск, баны, действия над аккаунтами") },
    payments: { title: at("section_payments_title", {}, "Платежи"), subtitle: at("section_payments_subtitle", {}, "История транзакций и экспорт") },
    promos: { title: at("section_promos_title", {}, "Промокоды"), subtitle: at("section_promos_subtitle", {}, "Создание и управление кодами") },
    ads: { title: at("section_ads_title", {}, "Рекламные кампании"), subtitle: at("section_ads_subtitle", {}, "UTM-источники и атрибуция") },
    broadcast: { title: at("section_broadcast_title", {}, "Рассылка"), subtitle: at("section_broadcast_subtitle", {}, "Массовая отправка сообщений в Telegram") },
    logs: { title: at("section_logs_title", {}, "Логи активности"), subtitle: at("section_logs_subtitle", {}, "События пользователей и админ-действия") },
    tariffs: { title: at("section_tariffs_title", {}, "Тарифы"), subtitle: at("section_tariffs_subtitle", {}, "Каталог продаж, периоды, пакеты и лимиты") },
    settings: { title: at("section_settings_title", {}, "Настройки приложения"), subtitle: at("section_settings_subtitle", {}, "Оверрайды над .env, применяются мгновенно") },
  };

  const VALID_SECTIONS = NAV_GROUPS.flatMap((g) => g.items.map((i) => i.id));
  function _normalizeSection(value) {
    return VALID_SECTIONS.includes(value) ? value : "stats";
  }
  let active = _normalizeSection(initialSection);
  let sidebarOpen = false;

  // Stats
  let stats = null;
  let statsLoading = false;
  let statsError = "";
  let syncBusy = false;

  // Users
  let users = [];
  let usersTotal = 0;
  let usersPage = 0;
  const USERS_PAGE_SIZE = 25;
  let usersQuery = "";
  let usersFilter = "all";
  let usersPanelStatus = "all";
  let usersSort = "registered_desc";
  let usersLoading = false;

  const USERS_FILTER_OPTIONS = [
    { value: "all", label: at("filter_all", {}, "Все") },
    { value: "active", label: at("filter_not_banned", {}, "Не забанены") },
    { value: "banned", label: at("filter_banned", {}, "Забанены") },
    { value: "tg_linked", label: at("filter_tg_linked", {}, "С Telegram") },
    { value: "no_tg", label: at("filter_no_tg", {}, "Без Telegram") },
    { value: "email_linked", label: at("filter_email_linked", {}, "С email") },
    { value: "no_email", label: at("filter_no_email", {}, "Без email") },
    { value: "panel_linked", label: at("filter_panel_linked", {}, "С панелью") },
  ];

  const USERS_SORT_OPTIONS = [
    { value: "registered_desc", label: at("sort_registered_desc", {}, "Сначала новые") },
    { value: "registered_asc", label: at("sort_registered_asc", {}, "Сначала старые") },
    { value: "name_asc", label: at("sort_name_asc", {}, "Имя ↑") },
    { value: "name_desc", label: at("sort_name_desc", {}, "Имя ↓") },
    { value: "id_asc", label: at("sort_id_asc", {}, "ID ↑") },
    { value: "id_desc", label: at("sort_id_desc", {}, "ID ↓") },
  ];

  const USERS_PANEL_STATUS_OPTIONS = [
    { value: "all", label: at("panel_status_all", {}, "Все статусы") },
    { value: "active", label: "active" },
    { value: "expired", label: "expired" },
    { value: "limited", label: "limited" },
  ];

  const BROADCAST_TARGET_OPTIONS = [
    { value: "all", label: at("broadcast_target_all", {}, "Все активные") },
    { value: "active", label: at("broadcast_target_active", {}, "С подпиской") },
    { value: "inactive", label: at("broadcast_target_inactive", {}, "Без подписки") },
  ];
  let openedUser = null;
  let openedUserDetail = null;
  let userDetailLoading = false;
  let userMessageDraft = "";
  let userExtendDays = 30;
  let userActionBusy = false;
  let userDeleteOpen = false;
  let userBanConfirmOpen = false;
  let userMessageConfirmOpen = false;
  let userDetailTab = "profile";
  let tariffEditorTab = "general";

  // Payments
  let payments = [];
  let paymentsTotal = 0;
  let paymentsPage = 0;
  const PAYMENTS_PAGE_SIZE = 25;
  let paymentsLoading = false;

  // Promos
  let promos = [];
  let promosTotal = 0;
  let promosPage = 0;
  const PROMOS_PAGE_SIZE = 25;
  let promosLoading = false;
  let promoCreateOpen = false;
  let promoDraft = { code: "", bonus_days: 7, max_activations: 1, valid_days: 30 };

  // Broadcast
  let broadcastTarget = "all";
  let broadcastText = "";
  let broadcastBusy = false;
  let broadcastResult = null;

  // Logs
  let logs = [];
  let logsTotal = 0;
  let logsPage = 0;
  const LOGS_PAGE_SIZE = 50;
  let logsUserFilter = "";
  let logsLoading = false;

  // Ads
  let ads = [];
  let adsTotals = null;
  let adsLoading = false;
  let adCreateOpen = false;
  let adDraft = { source: "", start_param: "", cost: 0 };

  // Tariffs
  let tariffsCatalog = {
    default_tariff: "",
    topup_packages_default: { rub: [], stars: [] },
    tariffs: [],
  };
  let tariffsPath = "";
  let tariffsLoading = false;
  let tariffsSaving = false;
  let tariffEditorOpen = false;
  let tariffEditingKey = "";
  let tariffDeleteOpen = false;
  let tariffDeleteTarget = null;
  let tariffDraft = emptyTariffDraft();
  let panelSquads = [];
  let panelSquadsLoading = false;
  let selectedBaseSquad = "";
  let selectedPremiumSquad = "";

  // Settings
  let settingsSections = [];
  let settingsLoading = false;
  let settingsDirty = {};
  let settingsSaving = false;
  let settingsOpenSections = []; // bits-ui Accordion value (multiple)
  let settingsOpenSubsections = {}; // sectionId -> array of open subsection labels
  let isCompact = false;

  function flash(text) {
    onToast(text);
  }

  function setActive(id) {
    const next = _normalizeSection(id);
    if (active === next) {
      sidebarOpen = false;
      return;
    }
    active = next;
    sidebarOpen = false;
    if (openedUser) {
      openedUser = null;
      openedUserDetail = null;
      userDeleteOpen = false;
      userBanConfirmOpen = false;
    }
    onSectionChange(next);
    loadActive();
  }

  function _readSectionFromPath() {
    if (typeof window === "undefined") return "stats";
    const m = window.location.pathname.match(/^\/admin\/([a-z0-9_-]+)(?:\/[^/]+)?$/i);
    return _normalizeSection(m ? m[1].toLowerCase() : "stats");
  }

  function _readUserIdFromPath() {
    if (typeof window === "undefined") return null;
    const m = window.location.pathname.match(/^\/admin\/users\/(-?\d+)$/);
    return m ? Number(m[1]) : null;
  }

  function _onPopState() {
    const next = _readSectionFromPath();
    if (active !== next) {
      active = next;
      sidebarOpen = false;
      loadActive();
    }
    const uid = _readUserIdFromPath();
    if (uid) {
      if (!openedUser || openedUser.user_id !== uid) openUser(uid, { skipPush: true });
    } else if (openedUser) {
      closeUser({ skipPush: true });
    }
  }

  async function loadActive() {
    if (active === "stats") return loadStats();
    if (active === "users") return loadUsers();
    if (active === "payments") return loadPayments();
    if (active === "promos") return loadPromos();
    if (active === "logs") return loadLogs();
    if (active === "ads") return loadAds();
    if (active === "tariffs") return loadTariffs();
    if (active === "settings") return loadSettings();
  }

  // ─── Stats ────────────────────────────────────────────────────
  async function loadStats() {
    statsLoading = true;
    statsError = "";
    try {
      const data = await api("/admin/stats");
      if (!data?.ok) statsError = data?.error || "load_failed";
      else stats = data;
    } catch (e) {
      statsError = e?.message || String(e);
    } finally {
      statsLoading = false;
    }
  }

  async function triggerSync() {
    if (syncBusy) return;
    syncBusy = true;
    try {
      const res = await api("/admin/sync", { method: "POST" });
      if (res?.ok) {
        flash(at("sync_started", {}, "Синхронизация запущена"));
        await loadStats();
      } else {
        flash(res?.error || at("sync_error", {}, "Ошибка синхронизации"));
      }
    } finally {
      syncBusy = false;
    }
  }

  // ─── Users ────────────────────────────────────────────────────
  async function loadUsers() {
    usersLoading = true;
    try {
      const params = new URLSearchParams({
        page: String(usersPage),
        page_size: String(USERS_PAGE_SIZE),
      });
      if (usersQuery.trim()) params.set("q", usersQuery.trim());
      if (usersFilter && usersFilter !== "all") params.set("filter", usersFilter);
      if (usersPanelStatus && usersPanelStatus !== "all") params.set("panel_status", usersPanelStatus);
      if (usersSort && usersSort !== "registered_desc") params.set("sort", usersSort);
      const data = await api(`/admin/users?${params.toString()}`);
      if (data?.ok) {
        users = data.users || [];
        usersTotal = data.total || users.length;
      }
    } finally {
      usersLoading = false;
    }
  }

  async function openUser(userOrId, opts = {}) {
    const userId = typeof userOrId === "object" && userOrId !== null ? userOrId.user_id : Number(userOrId);
    if (!userId) return;
    openedUser = typeof userOrId === "object" && userOrId !== null ? userOrId : { user_id: userId };
    openedUserDetail = null;
    userMessageDraft = "";
    userMessageConfirmOpen = false;
    userExtendDays = 30;
    userDetailLoading = true;
    userDetailTab = "subscription";
    if (!opts.skipPush) _pushUserPath(userId);
    try {
      const res = await api(`/admin/users/${userId}`);
      if (res?.ok) {
        openedUserDetail = res;
        if (res.user) openedUser = { ...res.user, ...openedUser, ...res.user };
      } else {
        flash(res?.error || "load_failed");
        openedUser = null;
        if (!opts.skipPush) _pushUserPath(null);
      }
    } finally {
      userDetailLoading = false;
    }
  }

  function closeUser(opts = {}) {
    const wasOpen = Boolean(openedUser);
    openedUser = null;
    openedUserDetail = null;
    userDeleteOpen = false;
    userBanConfirmOpen = false;
    userMessageConfirmOpen = false;
    if (wasOpen && !opts.skipPush) _pushUserPath(null);
  }

  function _pushUserPath(userId) {
    if (typeof window === "undefined") return;
    if (window.location.protocol === "file:") return;
    if (active !== "users") return;
    const target = userId ? `/admin/users/${userId}` : `/admin/users`;
    if (window.location.pathname === target) return;
    window.history.pushState(null, "", `${target}${window.location.search}${window.location.hash}`);
  }

  function copyToClipboard(text, successMessage = at("link_copied", {}, "Ссылка скопирована")) {
    if (!text) return;
    if (typeof navigator !== "undefined" && navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(
        () => flash(successMessage),
        () => flash(text),
      );
    } else {
      flash(text);
    }
  }

  function requestBanToggle() {
    if (!openedUser) return;
    if (openedUser.is_banned) {
      // Unbanning is reversible — apply directly without confirmation.
      applyBanToggle(false);
    } else {
      userBanConfirmOpen = true;
    }
  }

  async function applyBanToggle(banned) {
    if (!openedUser) return;
    userActionBusy = true;
    try {
      const res = await api(`/admin/users/${openedUser.user_id}/ban`, {
        method: "POST",
        body: JSON.stringify({ banned }),
      });
      if (res?.ok) {
        openedUser.is_banned = banned;
        users = users.map((u) =>
          u.user_id === openedUser.user_id ? { ...u, is_banned: banned } : u,
        );
        userBanConfirmOpen = false;
        flash(banned ? at("user_banned", {}, "Пользователь забанен") : at("user_unbanned", {}, "Пользователь разбанен"));
      } else flash(res?.error || at("error", {}, "Ошибка"));
    } finally {
      userActionBusy = false;
    }
  }

  async function sendUserMessage() {
    if (!openedUser || !userMessageDraft.trim()) return;
    userActionBusy = true;
    try {
      const res = await api(`/admin/users/${openedUser.user_id}/message`, {
        method: "POST",
        body: JSON.stringify({ text: userMessageDraft }),
      });
      if (res?.ok) {
        flash(at("message_sent", {}, "Сообщение отправлено"));
        userMessageDraft = "";
        userMessageConfirmOpen = false;
      } else flash(res?.error || at("message_send_failed", {}, "Не удалось отправить"));
    } finally {
      userActionBusy = false;
    }
  }

  function requestSendUserMessage() {
    if (!openedUser || !userMessageDraft.trim()) return;
    userMessageConfirmOpen = true;
  }

  async function previewUserMessage() {
    if (!openedUser || !userMessageDraft.trim()) return;
    userActionBusy = true;
    try {
      const res = await api(`/admin/users/${openedUser.user_id}/message/preview`, {
        method: "POST",
        body: JSON.stringify({ text: userMessageDraft }),
      });
      if (res?.ok) flash(at("message_preview_sent", {}, "Превью отправлено вам в Telegram"));
      else flash(res?.error || at("message_preview_failed", {}, "Не удалось отправить превью"));
    } finally {
      userActionBusy = false;
    }
  }

  async function extendUser() {
    if (!openedUser) return;
    const days = Number(userExtendDays);
    if (!days || days <= 0) return;
    userActionBusy = true;
    try {
      const res = await api(`/admin/users/${openedUser.user_id}/extend`, {
        method: "POST",
        body: JSON.stringify({ days }),
      });
      if (res?.ok) {
        flash(at("subscription_extended", { days }, `Подписка продлена на ${days} дн.`));
        await openUser(openedUser, { skipPush: true });
      } else flash(res?.error || at("error", {}, "Ошибка"));
    } finally {
      userActionBusy = false;
    }
  }

  async function resetTrialUser() {
    if (!openedUser) return;
    userActionBusy = true;
    try {
      const res = await api(`/admin/users/${openedUser.user_id}/reset-trial`, { method: "POST" });
      if (res?.ok) flash(at("trial_reset", {}, "Триал сброшен"));
      else flash(res?.error || at("error", {}, "Ошибка"));
    } finally {
      userActionBusy = false;
    }
  }

  async function deleteUser() {
    if (!openedUser) return;
    userActionBusy = true;
    try {
      const res = await api(`/admin/users/${openedUser.user_id}`, { method: "DELETE" });
      if (res?.ok) {
        flash(at("user_deleted", {}, "Пользователь удалён"));
        users = users.filter((u) => u.user_id !== openedUser.user_id);
        closeUser();
      } else flash(res?.error || at("error", {}, "Ошибка"));
    } finally {
      userActionBusy = false;
    }
  }

  // ─── Payments ─────────────────────────────────────────────────
  async function loadPayments() {
    paymentsLoading = true;
    try {
      const data = await api(`/admin/payments?page=${paymentsPage}&page_size=${PAYMENTS_PAGE_SIZE}`);
      if (data?.ok) {
        payments = data.payments || [];
        paymentsTotal = data.total || 0;
      }
    } finally {
      paymentsLoading = false;
    }
  }

  function exportPayments() {
    window.location.assign("/api/admin/payments/export.csv");
  }

  // ─── Promos ───────────────────────────────────────────────────
  async function loadPromos() {
    promosLoading = true;
    try {
      const data = await api(`/admin/promos?page=${promosPage}&page_size=${PROMOS_PAGE_SIZE}`);
      if (data?.ok) {
        promos = data.promos || [];
        promosTotal = data.total || 0;
      }
    } finally {
      promosLoading = false;
    }
  }

  async function createPromo() {
    if (!promoDraft.code.trim()) return;
    const res = await api("/admin/promos", {
      method: "POST",
      body: JSON.stringify(promoDraft),
    });
    if (res?.ok) {
      flash("Промокод создан");
      promoCreateOpen = false;
      promoDraft = { code: "", bonus_days: 7, max_activations: 1, valid_days: 30 };
      loadPromos();
    } else flash(res?.error || "Ошибка");
  }

  async function togglePromo(promo) {
    const res = await api(`/admin/promos/${promo.id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !promo.is_active }),
    });
    if (res?.ok) {
      promos = promos.map((p) => (p.id === promo.id ? res.promo : p));
    } else flash(res?.error || "Ошибка");
  }

  async function deletePromo(promo) {
    const res = await api(`/admin/promos/${promo.id}`, { method: "DELETE" });
    if (res?.ok) {
      promos = promos.filter((p) => p.id !== promo.id);
      flash("Промокод удалён");
    } else flash(res?.error || "Ошибка");
  }

  // ─── Broadcast ────────────────────────────────────────────────
  async function runBroadcast() {
    if (!broadcastText.trim()) return;
    broadcastBusy = true;
    broadcastResult = null;
    try {
      const res = await api("/admin/broadcast", {
        method: "POST",
        body: JSON.stringify({ target: broadcastTarget, text: broadcastText }),
      });
      if (res?.ok) {
        broadcastResult = res;
        broadcastText = "";
        flash(`В очереди: ${res.queued}`);
      } else flash(res?.error || "Ошибка");
    } finally {
      broadcastBusy = false;
    }
  }

  // ─── Logs ─────────────────────────────────────────────────────
  async function loadLogs() {
    logsLoading = true;
    try {
      const params = new URLSearchParams({ page: String(logsPage), page_size: String(LOGS_PAGE_SIZE) });
      if (logsUserFilter.trim()) params.set("user_id", logsUserFilter.trim());
      const data = await api(`/admin/logs?${params.toString()}`);
      if (data?.ok) {
        logs = data.logs || [];
        logsTotal = data.total || 0;
      }
    } finally {
      logsLoading = false;
    }
  }

  // ─── Ads ──────────────────────────────────────────────────────
  async function loadAds() {
    adsLoading = true;
    try {
      const data = await api("/admin/ads");
      if (data?.ok) {
        ads = data.campaigns || [];
        adsTotals = data.totals || {};
      }
    } finally {
      adsLoading = false;
    }
  }

  async function createAd() {
    if (!adDraft.source.trim() || !adDraft.start_param.trim()) return;
    const res = await api("/admin/ads", {
      method: "POST",
      body: JSON.stringify(adDraft),
    });
    if (res?.ok) {
      flash("Кампания создана");
      adCreateOpen = false;
      adDraft = { source: "", start_param: "", cost: 0 };
      loadAds();
    } else flash(res?.error || "Ошибка");
  }

  async function toggleAd(ad) {
    const res = await api(`/admin/ads/${ad.id}/toggle`, {
      method: "POST",
      body: JSON.stringify({ is_active: !ad.is_active }),
    });
    if (res?.ok) {
      ads = ads.map((c) => (c.id === ad.id ? { ...c, is_active: !ad.is_active } : c));
    } else flash(res?.error || "Ошибка");
  }

  async function deleteAd(ad) {
    const res = await api(`/admin/ads/${ad.id}`, { method: "DELETE" });
    if (res?.ok) {
      ads = ads.filter((c) => c.id !== ad.id);
      flash("Удалено");
    } else flash(res?.error || "Ошибка");
  }

  // ─── Tariffs ─────────────────────────────────────────────────
  function emptyTariffDraft() {
    return {
      key: "",
      nameRu: "",
      nameEn: "",
      descriptionRu: "",
      descriptionEn: "",
      premiumNameRu: "",
      premiumNameEn: "",
      squadUuids: [],
      premiumSquadUuids: [],
      billing_model: "period",
      enabled: true,
      monthly_gb: 500,
      premium_monthly_gb: "",
      hwid_device_limit: "",
      conversion_rate_rub_per_gb: "",
      periodRows: [
        { months: 1, rub: 150, stars: "" },
        { months: 3, rub: 400, stars: "" },
        { months: 6, rub: 750, stars: "" },
        { months: 12, rub: 1400, stars: "" },
      ],
      topupRubRows: [],
      topupStarsRows: [],
      premiumTopupRubRows: [],
      premiumTopupStarsRows: [],
      trafficRubRows: [
        { gb: 10, price: 199 },
        { gb: 50, price: 799 },
      ],
      trafficStarsRows: [],
      hwidRubRows: [],
      hwidStarsRows: [],
    };
  }

  function cloneCatalog(catalog) {
    return structuredCloneSafe({
      default_tariff: catalog?.default_tariff || "",
      topup_packages_default: catalog?.topup_packages_default || { rub: [], stars: [] },
      tariffs: catalog?.tariffs || [],
    });
  }

  function rowsFromPackages(packageSet, currency, valueKey) {
    return (packageSet?.[currency] || []).map((pkg) => ({
      [valueKey]: pkg[valueKey],
      price: pkg.price,
    }));
  }

  function draftFromTariff(tariff) {
    const months = new Set([
      ...(tariff.enabled_periods || []),
      ...Object.keys(tariff.prices_rub || {}).map(Number),
      ...Object.keys(tariff.prices_stars || {}).map(Number),
    ]);
    const periodRows = [...months]
      .filter((month) => Number.isFinite(month) && month > 0)
      .sort((a, b) => a - b)
      .map((month) => ({
        months: month,
        rub: tariff.prices_rub?.[String(month)] ?? "",
        stars: tariff.prices_stars?.[String(month)] ?? "",
      }));

    return {
      ...emptyTariffDraft(),
      key: tariff.key || "",
      nameRu: tariff.names?.ru || "",
      nameEn: tariff.names?.en || "",
      descriptionRu: tariff.descriptions?.ru || "",
      descriptionEn: tariff.descriptions?.en || "",
      premiumNameRu: tariff.premium_names?.ru || "",
      premiumNameEn: tariff.premium_names?.en || "",
      squadUuids: tariff.squad_uuids || [],
      premiumSquadUuids: tariff.premium_squad_uuids || [],
      billing_model: tariff.billing_model || "period",
      enabled: tariff.enabled !== false,
      monthly_gb: tariff.monthly_gb ?? "",
      premium_monthly_gb: tariff.premium_monthly_gb ?? "",
      hwid_device_limit: tariff.hwid_device_limit ?? "",
      conversion_rate_rub_per_gb: tariff.conversion_rate_rub_per_gb ?? "",
      periodRows: periodRows.length ? periodRows : emptyTariffDraft().periodRows,
      topupRubRows: rowsFromPackages(tariff.topup_packages, "rub", "gb"),
      topupStarsRows: rowsFromPackages(tariff.topup_packages, "stars", "gb"),
      premiumTopupRubRows: rowsFromPackages(tariff.premium_topup_packages, "rub", "gb"),
      premiumTopupStarsRows: rowsFromPackages(tariff.premium_topup_packages, "stars", "gb"),
      trafficRubRows: rowsFromPackages(tariff.traffic_packages, "rub", "gb"),
      trafficStarsRows: rowsFromPackages(tariff.traffic_packages, "stars", "gb"),
      hwidRubRows: rowsFromPackages(tariff.hwid_device_packages, "rub", "count"),
      hwidStarsRows: rowsFromPackages(tariff.hwid_device_packages, "stars", "count"),
    };
  }

  function parseNumber(value, fallback = null) {
    if (value === "" || value === null || value === undefined) return fallback;
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
  }

  function parseIntNumber(value, fallback = null) {
    const num = parseNumber(value, fallback);
    return num === null ? fallback : Math.trunc(num);
  }

  function compactMap(obj) {
    return Object.fromEntries(Object.entries(obj).filter(([, value]) => value !== "" && value !== null && value !== undefined));
  }

  function packagesFromRows(rows, valueKey) {
    return (rows || [])
      .map((row) => ({
        [valueKey]: parseNumber(row[valueKey]),
        price: parseNumber(row.price),
      }))
      .filter((row) => row[valueKey] > 0 && row.price !== null && row.price >= 0);
  }

  function packageSetFromRows(rubRows, starsRows, valueKey) {
    const rub = packagesFromRows(rubRows, valueKey);
    const stars = packagesFromRows(starsRows, valueKey);
    return rub.length || stars.length ? { rub, stars } : null;
  }

  function tariffFromDraft() {
    const key = tariffDraft.key.trim();
    const names = compactMap({
      ru: tariffDraft.nameRu.trim(),
      en: tariffDraft.nameEn.trim(),
    });
    const descriptions = compactMap({
      ru: tariffDraft.descriptionRu.trim(),
      en: tariffDraft.descriptionEn.trim(),
    });
    const premiumNames = compactMap({
      ru: tariffDraft.premiumNameRu.trim(),
      en: tariffDraft.premiumNameEn.trim(),
    });
    const tariff = {
      key,
      names,
      descriptions,
      premium_names: premiumNames,
      squad_uuids: normalizeUuidList(tariffDraft.squadUuids),
      premium_squad_uuids: normalizeUuidList(tariffDraft.premiumSquadUuids),
      billing_model: tariffDraft.billing_model,
      enabled: Boolean(tariffDraft.enabled),
    };

    const hwidLimit = parseIntNumber(tariffDraft.hwid_device_limit);
    if (hwidLimit !== null) tariff.hwid_device_limit = hwidLimit;
    const hwidPackages = packageSetFromRows(tariffDraft.hwidRubRows, tariffDraft.hwidStarsRows, "count");
    if (hwidPackages) tariff.hwid_device_packages = hwidPackages;
    const premiumMonthlyGb = parseNumber(tariffDraft.premium_monthly_gb);
    if (premiumMonthlyGb !== null) tariff.premium_monthly_gb = premiumMonthlyGb;
    const premiumTopupPackages = packageSetFromRows(
      tariffDraft.premiumTopupRubRows,
      tariffDraft.premiumTopupStarsRows,
      "gb",
    );
    if (premiumTopupPackages) tariff.premium_topup_packages = premiumTopupPackages;

    if (tariff.billing_model === "period") {
      const seenMonths = new Set();
      const rows = (tariffDraft.periodRows || [])
        .map((row) => ({
          months: parseIntNumber(row.months),
          rub: parseNumber(row.rub, 0),
          stars: parseNumber(row.stars, 0),
        }))
        .filter((row) => row.months > 0)
        .filter((row) => {
          if (seenMonths.has(row.months)) return false;
          seenMonths.add(row.months);
          return true;
        })
        .sort((a, b) => a.months - b.months);
      tariff.monthly_gb = parseNumber(tariffDraft.monthly_gb, 0);
      tariff.enabled_periods = rows.map((row) => row.months);
      tariff.prices_rub = Object.fromEntries(rows.map((row) => [String(row.months), row.rub || 0]));
      tariff.prices_stars = Object.fromEntries(rows.map((row) => [String(row.months), row.stars || 0]));
      const topupPackages = packageSetFromRows(tariffDraft.topupRubRows, tariffDraft.topupStarsRows, "gb");
      if (topupPackages) tariff.topup_packages = topupPackages;
    } else {
      const trafficPackages = packageSetFromRows(tariffDraft.trafficRubRows, tariffDraft.trafficStarsRows, "gb");
      if (trafficPackages) tariff.traffic_packages = trafficPackages;
      const conversion = parseNumber(tariffDraft.conversion_rate_rub_per_gb);
      if (conversion !== null) tariff.conversion_rate_rub_per_gb = conversion;
    }

    return tariff;
  }

  async function loadTariffs() {
    tariffsLoading = true;
    try {
      loadPanelSquads();
      const data = await api("/admin/tariffs");
      if (data?.ok) {
        tariffsCatalog = cloneCatalog(data.catalog);
        tariffsPath = data.path || "";
      } else {
        flash(data?.message || data?.error || "Не удалось загрузить тарифы");
      }
    } finally {
      tariffsLoading = false;
    }
  }

  async function loadPanelSquads() {
    if (panelSquadsLoading) return;
    panelSquadsLoading = true;
    try {
      const data = await api("/admin/panel/internal-squads");
      if (data?.ok) panelSquads = data.squads || [];
    } catch (e) {
      panelSquads = [];
    } finally {
      panelSquadsLoading = false;
    }
  }

  function normalizeUuidList(value) {
    if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
    return String(value || "")
      .split(/[\n,]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function squadLabel(uuid) {
    const squad = panelSquads.find((item) => item.uuid === uuid);
    return squad ? `${squad.name} · ${uuid.slice(0, 8)}…` : uuid;
  }

  function addSquadToDraft(field, uuid) {
    if (!uuid) return;
    const current = normalizeUuidList(tariffDraft[field]);
    if (current.includes(uuid)) return;
    tariffDraft = { ...tariffDraft, [field]: [...current, uuid] };
  }

  function removeSquadFromDraft(field, uuid) {
    tariffDraft = {
      ...tariffDraft,
      [field]: normalizeUuidList(tariffDraft[field]).filter((item) => item !== uuid),
    };
  }

  async function persistTariffs(nextCatalog, successText) {
    tariffsSaving = true;
    try {
      const res = await api("/admin/tariffs", {
        method: "PUT",
        body: JSON.stringify({ catalog: nextCatalog }),
      });
      if (res?.ok) {
        tariffsCatalog = cloneCatalog(res.catalog);
        tariffsPath = res.path || tariffsPath;
        await onTariffsSaved(res.catalog);
        flash(successText || "Тарифы сохранены");
        tariffEditorOpen = false;
        tariffDeleteOpen = false;
        tariffDeleteTarget = null;
      } else {
        flash(res?.message || res?.error || "Ошибка сохранения тарифов");
      }
    } finally {
      tariffsSaving = false;
    }
  }

  function openCreateTariff() {
    tariffEditingKey = "";
    tariffDraft = emptyTariffDraft();
    tariffEditorTab = "general";
    selectedBaseSquad = "";
    selectedPremiumSquad = "";
    tariffEditorOpen = true;
  }

  function openEditTariff(tariff) {
    tariffEditingKey = tariff.key;
    tariffDraft = draftFromTariff(tariff);
    tariffEditorTab = "general";
    selectedBaseSquad = "";
    selectedPremiumSquad = "";
    tariffEditorOpen = true;
  }

  async function saveTariffDraft() {
    const tariff = tariffFromDraft();
    if (!tariff.key) {
      flash("Укажите ключ тарифа");
      return;
    }
    const existing = (tariffsCatalog.tariffs || []).find((item) => item.key === tariff.key && item.key !== tariffEditingKey);
    if (existing) {
      flash("Тариф с таким ключом уже есть");
      return;
    }
    const current = tariffsCatalog.tariffs || [];
    const tariffs = tariffEditingKey
      ? current.map((item) => (item.key === tariffEditingKey ? tariff : item))
      : [...current, tariff];
    const enabledKeys = tariffs.filter((item) => item.enabled !== false).map((item) => item.key);
    if (!enabledKeys.length) {
      flash("Должен быть хотя бы один включённый тариф");
      return;
    }
    const currentDefault = tariffsCatalog.default_tariff === tariffEditingKey ? tariff.key : tariffsCatalog.default_tariff;
    const defaultTariff = enabledKeys.includes(currentDefault)
      ? currentDefault
      : enabledKeys[0];
    await persistTariffs({ ...cloneCatalog(tariffsCatalog), default_tariff: defaultTariff, tariffs }, "Тариф сохранён");
  }

  async function toggleTariffEnabled(tariff) {
    const tariffs = (tariffsCatalog.tariffs || []).map((item) =>
      item.key === tariff.key ? { ...item, enabled: item.enabled === false } : item,
    );
    const enabledKeys = tariffs.filter((item) => item.enabled !== false).map((item) => item.key);
    if (!enabledKeys.length) {
      flash("Должен остаться хотя бы один включённый тариф");
      return;
    }
    const defaultTariff = enabledKeys.includes(tariffsCatalog.default_tariff) ? tariffsCatalog.default_tariff : enabledKeys[0];
    await persistTariffs({ ...cloneCatalog(tariffsCatalog), default_tariff: defaultTariff, tariffs }, "Статус тарифа обновлён");
  }

  async function setDefaultTariff(key) {
    if (!key || key === tariffsCatalog.default_tariff) return;
    await persistTariffs({ ...cloneCatalog(tariffsCatalog), default_tariff: key }, "Тариф по умолчанию обновлён");
  }

  async function deleteTariff() {
    if (!tariffDeleteTarget) return;
    const tariffs = (tariffsCatalog.tariffs || []).filter((item) => item.key !== tariffDeleteTarget.key);
    const enabledKeys = tariffs.filter((item) => item.enabled !== false).map((item) => item.key);
    if (!enabledKeys.length) {
      flash("Нельзя удалить последний включённый тариф");
      return;
    }
    const defaultTariff = enabledKeys.includes(tariffsCatalog.default_tariff) ? tariffsCatalog.default_tariff : enabledKeys[0];
    await persistTariffs({ ...cloneCatalog(tariffsCatalog), default_tariff: defaultTariff, tariffs }, "Тариф удалён");
  }

  function addDraftRow(field, row) {
    tariffDraft = { ...tariffDraft, [field]: [...(tariffDraft[field] || []), row] };
  }

  function removeDraftRow(field, index) {
    tariffDraft = {
      ...tariffDraft,
      [field]: (tariffDraft[field] || []).filter((_, idx) => idx !== index),
    };
  }

  // ─── Settings ─────────────────────────────────────────────────
  async function loadSettings() {
    settingsLoading = true;
    settingsDirty = {};
    try {
      const data = await api("/admin/settings");
      if (data?.ok) {
        settingsSections = data.sections || [];
        // Expand the first section on phones; expand all on desktop.
        const ids = settingsSections.map((s) => s.id);
        settingsOpenSections = isCompact ? ids.slice(0, 1) : ids.slice();
      }
    } finally {
      settingsLoading = false;
    }
  }

  function toggleAllSections() {
    if (settingsOpenSections.length === settingsSections.length) {
      settingsOpenSections = [];
    } else {
      settingsOpenSections = settingsSections.map((s) => s.id);
    }
  }

  function markDirty(key, value, deleted = false) {
    settingsDirty = { ...settingsDirty, [key]: { value, deleted } };
  }

  function clearDirty(key) {
    const next = { ...settingsDirty };
    delete next[key];
    settingsDirty = next;
  }

  function valueFor(field) {
    if (settingsDirty[field.key]?.deleted) return "";
    if (Object.prototype.hasOwnProperty.call(settingsDirty, field.key)) {
      return settingsDirty[field.key].value;
    }
    return field.value ?? "";
  }

  function isOverridden(field) {
    return Boolean(field.overridden) && !settingsDirty[field.key]?.deleted;
  }

  let revealedSecrets = new Set();
  function isSecretRevealed(key) {
    return revealedSecrets.has(key);
  }
  function toggleSecretReveal(key) {
    const next = new Set(revealedSecrets);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    revealedSecrets = next;
  }

  function groupSectionFields(section) {
    const groups = new Map();
    for (const field of section.fields || []) {
      const key = field.subsection || "_root";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(field);
    }
    return Array.from(groups.entries()).map(([id, fields]) => ({
      id,
      label: id === "_root" ? null : id,
      fields,
    }));
  }

  function resetField(field) {
    if (field.overridden) {
      markDirty(field.key, "", true);
    } else {
      clearDirty(field.key);
    }
  }

  async function saveSettings() {
    if (!Object.keys(settingsDirty).length) return;
    settingsSaving = true;
    try {
      const updates = {};
      const deletes = [];
      for (const [key, change] of Object.entries(settingsDirty)) {
        if (change.deleted) deletes.push(key);
        else updates[key] = change.value;
      }
      const res = await api("/admin/settings", {
        method: "PATCH",
        body: JSON.stringify({ updates, deletes }),
      });
      if (res?.ok) {
        flash("Настройки сохранены");
        settingsDirty = {};
        await onSettingsSaved({ updates, deletes });
        await loadSettings();
      } else if (res?.errors) {
        const summary = Object.entries(res.errors).map(([k, v]) => `${k}: ${v}`).join("; ");
        flash(`Ошибка: ${summary}`);
      } else {
        flash(res?.error || "Ошибка");
      }
    } finally {
      settingsSaving = false;
    }
  }

  // ─── Helpers ──────────────────────────────────────────────────
  function structuredCloneSafe(value) {
    if (typeof structuredClone === "function") return structuredClone(value);
    return JSON.parse(JSON.stringify(value));
  }

  function pretty(value) {
    if (value === null || value === undefined) return "—";
    if (typeof value === "boolean") return value ? "Да" : "Нет";
    return String(value);
  }

  function fmtDate(value) {
    if (!value) return "—";
    try {
      return new Date(value).toLocaleString("ru-RU");
    } catch {
      return String(value);
    }
  }

  function fmtDateShort(value) {
    if (!value) return "—";
    try {
      return new Date(value).toLocaleDateString("ru-RU");
    } catch {
      return String(value);
    }
  }

  function fmtMoney(amount, currency) {
    const sym = currency === "RUB" ? "₽" : currency || "";
    const num = Number(amount || 0);
    return `${num.toFixed(2)} ${sym}`.trim();
  }

  function fmtTrafficBytes(value) {
    const bytes = Number(value || 0);
    if (!bytes || bytes <= 0) return "0 GB";
    const gb = bytes / 1073741824;
    const formatted = gb >= 10 ? gb.toFixed(1) : gb.toFixed(2);
    return `${formatted.replace(/\.0+$/, "").replace(/(\.\d*[1-9])0+$/, "$1")} GB`;
  }

  function trafficPercentValue(used, limit) {
    const usedBytes = Number(used || 0);
    const limitBytes = Number(limit || 0);
    if (!limitBytes || limitBytes <= 0) return 0;
    return Math.max(0, Math.min(100, Math.round((usedBytes / limitBytes) * 100)));
  }

  function trafficLeftLabel(used, limit) {
    const limitBytes = Number(limit || 0);
    if (!limitBytes || limitBytes <= 0) return "Без лимита";
    return fmtTrafficBytes(Math.max(0, limitBytes - Number(used || 0)));
  }

  function trafficOfLabel(used, limit) {
    const limitBytes = Number(limit || 0);
    if (!limitBytes || limitBytes <= 0) return `${fmtTrafficBytes(used)} / без лимита`;
    return `${fmtTrafficBytes(used)} / ${fmtTrafficBytes(limit)}`;
  }

  function tariffName(tariff) {
    return tariff?.names?.ru || tariff?.names?.en || tariff?.key || "—";
  }

  function tariffPriceSummary(tariff) {
    if (tariff.billing_model === "traffic") {
      const rub = tariff.traffic_packages?.rub || [];
      const first = rub[0];
      return first ? `${first.gb} GB за ${fmtMoney(first.price, "RUB")}` : "Пакеты трафика";
    }
    const months = [...(tariff.enabled_periods || [])].sort((a, b) => a - b);
    return months
      .map((month) => {
        const rub = tariff.prices_rub?.[String(month)];
        const stars = tariff.prices_stars?.[String(month)];
        if (rub) return `${month} мес. ${fmtMoney(rub, "RUB")}`;
        if (stars) return `${month} мес. ${stars} ⭐`;
        return `${month} мес.`;
      })
      .join(" · ");
  }

  function packageSummary(packages, valueKey, unit) {
    const rub = packages?.rub || [];
    const stars = packages?.stars || [];
    if (!rub.length && !stars.length) return "—";
    const first = [...rub, ...stars][0];
    const total = rub.length + stars.length;
    return `${first[valueKey]} ${unit}, всего ${total}`;
  }

  function userDisplayName(user) {
    const full = [user?.first_name, user?.last_name].filter(Boolean).join(" ").trim();
    return full || (user?.username ? `@${user.username}` : user?.email || `User #${user?.user_id || "—"}`);
  }

  function userSecondaryName(user) {
    if (user?.username && userDisplayName(user) !== `@${user.username}`) return `@${user.username}`;
    if (user?.email && userDisplayName(user) !== user.email) return user.email;
    return `ID ${user?.user_id || "—"}`;
  }

  function userInitials(user) {
    const source = userDisplayName(user).replace(/^@/, "").trim();
    const parts = source.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    return (source.slice(0, 2) || "U").toUpperCase();
  }

  function userAvatarUrl(user) {
    // Prefer the admin cached endpoint (cheap, ETag'd, served from DB cache);
    // fall back to the raw Telegram photo URL only if there's no cache yet.
    const cached = String(user?.avatar_url || "").trim();
    if (cached) return cached;
    const value = String(user?.telegram_photo_url || "").trim();
    return value && !value.startsWith("/api/account/avatar") ? value : "";
  }

  // Gravatar fallback for users with no Telegram avatar but a known email.
  // Gravatar accepts SHA-256 hashes since 2024 — convenient because the
  // browser SubtleCrypto can compute SHA-256 natively (no MD5 dep needed).
  const _gravatarCache = new Map();
  const _gravatarPending = new Map();

  async function _sha256Hex(value) {
    const buf = new TextEncoder().encode(value);
    const digest = await crypto.subtle.digest("SHA-256", buf);
    return Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }

  function userGravatarUrl(user) {
    const email = String(user?.email || "").trim().toLowerCase();
    if (!email) return "";
    if (_gravatarCache.has(email)) return _gravatarCache.get(email);
    if (_gravatarPending.has(email)) return "";
    _gravatarPending.set(
      email,
      _sha256Hex(email)
        .then((h) => {
          _gravatarCache.set(email, `https://gravatar.com/avatar/${h}?d=identicon&s=80`);
          users = users; // trigger reactivity
          openedUser = openedUser;
        })
        .catch(() => _gravatarPending.delete(email)),
    );
    return "";
  }

  function resolvedAvatarUrl(user) {
    return userAvatarUrl(user) || (!user?.telegram_id && user?.email ? userGravatarUrl(user) : "");
  }

  function panelStatusBadge(user) {
    const status = String(user?.panel_status || "").toLowerCase();
    if (user?.is_banned) return { label: "Бан", variant: "danger" };
    switch (status) {
      case "active":
        return { label: "Active", variant: "success" };
      case "expired":
        return {
          label: user?.panel_status_expired_at
            ? at("expired_badge", { date: fmtDateShort(user.panel_status_expired_at) }, `Expired ${fmtDateShort(user.panel_status_expired_at)}`)
            : "Expired",
          variant: "warning",
        };
      case "limited":
        return { label: "Limited", variant: "warning" };
      case "disabled":
        return { label: "Disabled", variant: "muted" };
      case "bot_only":
        return { label: "Только бот", variant: "muted" };
      default:
        return { label: status || "—", variant: "muted" };
    }
  }

  function paymentStatusVariant(status) {
    if (status === "succeeded") return "success";
    if (typeof status === "string" && status.startsWith("pending")) return "warning";
    return "danger";
  }

  function sectionTitle(id) {
    const map = {
      general: at("settings_section_general", {}, "Общие"),
      appearance: at("settings_section_appearance", {}, "Внешний вид"),
      pricing: at("settings_section_pricing", {}, "Тарифы и цены"),
      payments: at("settings_section_payments", {}, "Платёжные системы"),
      trial: at("settings_section_trial", {}, "Триал"),
      referral: at("settings_section_referral", {}, "Реферальная программа"),
      notifications: at("settings_section_notifications", {}, "Уведомления"),
      devices: at("settings_section_devices", {}, "Устройства"),
    };
    return map[id] || id;
  }

  function optionLabel(options, value) {
    return options.find((option) => option.value === value)?.label || value;
  }

  $: dirtyCount = Object.keys(settingsDirty).length;
  $: meta = SECTION_META[active] || { title: active, subtitle: "" };
  $: currentLanguageOption = languageOptions.find((option) => option.value === currentLang) || languageOptions[0];
  $: usersHasMore = users.length === USERS_PAGE_SIZE;
  $: paymentsHasMore = payments.length === PAYMENTS_PAGE_SIZE;
  $: logsHasMore = logs.length === LOGS_PAGE_SIZE;
  $: enabledTariffs = (tariffsCatalog.tariffs || []).filter((tariff) => tariff.enabled !== false);
  $: disabledTariffs = Math.max(0, (tariffsCatalog.tariffs || []).length - enabledTariffs.length);
  $: settingsAllOpen =
    settingsSections.length > 0 && settingsOpenSections.length === settingsSections.length;

  let _compactMql = null;
  function _onCompactChange(event) {
    const next = Boolean(event?.matches);
    if (next === isCompact) return;
    isCompact = next;
    if (settingsSections.length) {
      const ids = settingsSections.map((s) => s.id);
      settingsOpenSections = isCompact ? ids.slice(0, 1) : ids.slice();
    }
  }

  onMount(() => {
    if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
      _compactMql = window.matchMedia("(max-width: 720px)");
      isCompact = _compactMql.matches;
      if (_compactMql.addEventListener) _compactMql.addEventListener("change", _onCompactChange);
      else if (_compactMql.addListener) _compactMql.addListener(_onCompactChange);
    }
    if (typeof window !== "undefined") {
      window.addEventListener("popstate", _onPopState);
    }
    loadActive();
    if (active === "users" && initialUserId) {
      openUser(initialUserId, { skipPush: true });
    }
    return () => {
      if (_compactMql) {
        if (_compactMql.removeEventListener) _compactMql.removeEventListener("change", _onCompactChange);
        else if (_compactMql.removeListener) _compactMql.removeListener(_onCompactChange);
      }
      if (typeof window !== "undefined") {
        window.removeEventListener("popstate", _onPopState);
      }
    };
  });
</script>

{#snippet renderField(field)}
  {@const revealed = isSecretRevealed(field.key)}
  <div class="admin-setting" class:is-overridden={isOverridden(field)}>
    <div class="admin-setting-meta">
      <strong>
        {field.label}
        {#if field.secret}
          <span class="admin-badge admin-badge-warning">Secret</span>
        {/if}
        {#if isOverridden(field)}
          <span class="admin-badge admin-badge-success">Override</span>
        {/if}
      </strong>
      <code>{field.key}</code>
      {#if field.description}
        <small>{field.description}</small>
      {/if}
    </div>
    <div class="admin-setting-control">
      {#if field.type === "bool"}
        <div class="admin-setting-switch">
          <Switch.Root
            checked={Boolean(valueFor(field))}
            onCheckedChange={(checked) => markDirty(field.key, checked)}
            class="admin-switch-root"
          >
            <Switch.Thumb class="admin-switch-thumb" />
          </Switch.Root>
          <span>{Boolean(valueFor(field)) ? "Включено" : "Выключено"}</span>
        </div>
      {:else if field.type === "color"}
        <input
          class="admin-color"
          type="color"
          value={valueFor(field) || "#00fe7a"}
          on:input={(e) => markDirty(field.key, e.currentTarget.value)}
        />
        <input
          class="input"
          type="text"
          value={valueFor(field) || ""}
          on:input={(e) => markDirty(field.key, e.currentTarget.value)}
        />
      {:else if field.type === "int" || field.type === "float"}
        <input
          class="input"
          type="number"
          step={field.type === "float" ? "0.1" : "1"}
          placeholder={field.placeholder}
          value={valueFor(field) ?? ""}
          on:input={(e) => markDirty(field.key, e.currentTarget.value)}
        />
      {:else if field.secret}
        <input
          class="input"
          type={revealed ? "text" : "password"}
          placeholder={field.placeholder || "••••••••"}
          autocomplete="off"
          value={valueFor(field) ?? ""}
          on:input={(e) => markDirty(field.key, e.currentTarget.value)}
        />
        <button
          type="button"
          class="admin-btn admin-btn-sm admin-btn-ghost"
          aria-label={revealed ? "Скрыть" : "Показать"}
          on:click={() => toggleSecretReveal(field.key)}
        >
          {#if revealed}<EyeOff size={13} />{:else}<Eye size={13} />{/if}
        </button>
      {:else}
        <input
          class="input"
          type="text"
          placeholder={field.placeholder}
          value={valueFor(field) ?? ""}
          on:input={(e) => markDirty(field.key, e.currentTarget.value)}
        />
      {/if}
      {#if isOverridden(field) || settingsDirty[field.key]}
        <button type="button" class="admin-btn admin-btn-sm admin-btn-ghost" on:click={() => resetField(field)}>
          <X size={12} /> Сбросить
        </button>
      {/if}
    </div>
  </div>
{/snippet}

<div class="admin-screen-wrap" class:is-sidebar-open={sidebarOpen}>
  {#if sidebarOpen}
    <button
      type="button"
      class="admin-sidebar-backdrop"
      aria-label={at("close_menu", {}, "Закрыть меню")}
      on:click={() => (sidebarOpen = false)}
    ></button>
  {/if}

  <aside class="admin-sidebar" aria-label={at("sidebar_navigation", {}, "Навигация админки")}>
    <div class="admin-sidebar-brand">
      <BrandMark class="admin-brand-mark" logoUrl={logoUrl} emoji={logoEmoji} />
      <div>
        <strong class="admin-brand-title">{brandTitle}</strong>
        <small>{at("panel_title", {}, "Админ-панель")}</small>
      </div>
      <button type="button" class="admin-btn admin-btn-icon admin-btn-ghost" on:click={onClose} aria-label={at("exit", {}, "Выйти")}>
        <ArrowLeft size={16} />
      </button>
    </div>

    {#each NAV_GROUPS as group}
      <div class="admin-sidebar-section-label">{group.label}</div>
      <nav class="admin-nav" aria-label={group.label}>
        {#each group.items as item}
          <button
            type="button"
            class="admin-nav-item"
            class:active={active === item.id}
            on:click={() => setActive(item.id)}
          >
            <svelte:component this={item.icon} size={16} />
            <span>{item.label}</span>
            <span></span>
          </button>
        {/each}
      </nav>
    {/each}

    <div class="admin-sidebar-footer">
      {#if languageOptions.length}
        <div class="admin-language-switch">
          <Globe2 size={16} />
          <Select.Root
            type="single"
            value={currentLang}
            items={languageOptions}
            disabled={languageBusy}
            onValueChange={onLanguageChange}
          >
            <Select.Trigger class="admin-language-trigger" aria-label={t("wa_settings_language", {}, at("language", {}, "Язык"))}>
              <span>
                <strong>{t("wa_settings_language", {}, at("language", {}, "Язык"))}</strong>
                <small>
                  <span class="emoji-flag" aria-hidden="true">{currentLanguageOption?.flag || "🏳️"}</span>
                  {currentLanguageOption?.label || currentLang}
                </small>
              </span>
              <ChevronsUpDown size={14} />
            </Select.Trigger>
            <Select.Content class="language-select-content" side="top" align="start" sideOffset={8}>
              <Select.Viewport class="language-select-viewport">
                {#each languageOptions as option (option.value)}
                  <Select.Item value={option.value} label={option.label} class="language-select-item">
                    <span class="language-select-item-main">
                      <span class="emoji-flag" aria-hidden="true">{option.flag}</span>
                      <span>{option.label}</span>
                    </span>
                    <Check size={15} class="language-select-item-check" />
                  </Select.Item>
                {/each}
              </Select.Viewport>
            </Select.Content>
          </Select.Root>
        </div>
      {/if}
      <a
        class="admin-version-link"
        href={appRepositoryUrl}
        target="_blank"
        rel="noopener noreferrer"
        title="GitHub"
      >
        <span>remnawave-minishop</span>
        <span>{appVersion || "dev+local"}</span>
      </a>
    </div>
  </aside>

  <section class="admin-content">
    <header class="admin-header">
      <div style="display:flex; align-items:center; gap:12px; min-width:0;">
        <button
          type="button"
          class="admin-mobile-toggle"
          on:click={() => (sidebarOpen = !sidebarOpen)}
          aria-label={at("menu", {}, "Меню")}
        >
          <Menu size={18} />
        </button>
        <div class="admin-header-title">
          <h2>{meta.title}</h2>
          {#if meta.subtitle}<small>{meta.subtitle}</small>{/if}
        </div>
      </div>
      <div class="admin-header-actions">
        {#if active === "stats"}
          <button type="button" class="admin-btn" on:click={triggerSync} disabled={syncBusy}>
            <RefreshCw size={14} /> {syncBusy ? "Синхронизация..." : "Синхронизировать"}
          </button>
        {/if}
        {#if active === "payments"}
          <button type="button" class="admin-btn" on:click={exportPayments}>
            <Download size={14} /> CSV
          </button>
        {/if}
        {#if active === "promos"}
          <button type="button" class="admin-btn admin-btn-primary" on:click={() => (promoCreateOpen = true)}>
            <Plus size={14} /> Создать
          </button>
        {/if}
        {#if active === "ads"}
          <button type="button" class="admin-btn admin-btn-primary" on:click={() => (adCreateOpen = true)}>
            <Plus size={14} /> Кампания
          </button>
        {/if}
        {#if active === "tariffs"}
          <button type="button" class="admin-btn admin-btn-primary" on:click={openCreateTariff}>
            <Plus size={14} /> Тариф
          </button>
        {/if}
        {#if active === "settings"}
          {#if dirtyCount}
            <span class="admin-badge admin-badge-warning">Изменений: {dirtyCount}</span>
          {/if}
          <button type="button" class="admin-btn admin-btn-primary" on:click={saveSettings} disabled={!dirtyCount || settingsSaving}>
            <Save size={14} /> {settingsSaving ? "Сохранение..." : "Сохранить"}
          </button>
        {/if}
      </div>
    </header>

    <main class="admin-main">
      {#if active === "stats"}
        {#if statsError}
          <div class="admin-empty">Не удалось загрузить статистику: {statsError}</div>
        {:else if statsLoading || !stats}
          <div class="admin-empty">Загрузка…</div>
        {:else}
          <div class="admin-stat-grid">
            <article class="admin-stat-card">
              <span class="admin-stat-label"><UsersRound size={14} /> Пользователи</span>
              <span class="admin-stat-value">{stats.users?.total_users ?? 0}</span>
              <span class="admin-stat-trend">В бане: {stats.users?.banned_users ?? 0}</span>
            </article>
            <article class="admin-stat-card">
              <span class="admin-stat-label"><Shield size={14} /> Платные подписки</span>
              <span class="admin-stat-value">{stats.users?.paid_subscriptions ?? 0}</span>
              <span class="admin-stat-trend">Триалы: {stats.users?.trial_users ?? 0}</span>
            </article>
            <article class="admin-stat-card">
              <span class="admin-stat-label"><Coins size={14} /> Доход за день</span>
              <span class="admin-stat-value">{fmtMoney(stats.financial?.today_revenue, stats.currency_symbol)}</span>
              <span class="admin-stat-trend">{stats.financial?.today_payments_count ?? 0} платежей</span>
            </article>
            <article class="admin-stat-card">
              <span class="admin-stat-label"><BarChart3 size={14} /> За неделю</span>
              <span class="admin-stat-value">{fmtMoney(stats.financial?.week_revenue, stats.currency_symbol)}</span>
              <span class="admin-stat-trend">Месяц: {fmtMoney(stats.financial?.month_revenue, stats.currency_symbol)}</span>
            </article>
            <article class="admin-stat-card">
              <span class="admin-stat-label"><Database size={14} /> Всё время</span>
              <span class="admin-stat-value">{fmtMoney(stats.financial?.all_time_revenue, stats.currency_symbol)}</span>
              <span class="admin-stat-trend">Sync: {stats.panel_sync?.status ?? "—"}</span>
            </article>
            {#if stats.queue}
              <article class="admin-stat-card">
                <span class="admin-stat-label"><Send size={14} /> Очередь</span>
                <span class="admin-stat-value">{stats.queue.user_queue_size ?? 0}</span>
                <span class="admin-stat-trend">Группы: {stats.queue.group_queue_size ?? 0}</span>
              </article>
            {/if}
          </div>

          <div class="admin-table-wrap">
            <header class="admin-card-head">
              <h3>Последние платежи</h3>
              <small>{(stats.recent_payments || []).length} записей</small>
            </header>
            {#if (stats.recent_payments || []).length}
              <table class="admin-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Пользователь</th>
                    <th>Сумма</th>
                    <th>Провайдер</th>
                    <th>Статус</th>
                    <th>Дата</th>
                  </tr>
                </thead>
                <tbody>
                  {#each stats.recent_payments as p}
                    <tr>
                      <td class="admin-cell-id" data-label="ID">#{p.payment_id}</td>
                      <td data-label="Пользователь">{p.user_label || p.user_id}</td>
                      <td data-label="Сумма">{fmtMoney(p.amount, p.currency)}</td>
                      <td data-label="Провайдер">{p.provider}</td>
                      <td data-label="Статус">
                        <span class="admin-badge admin-badge-{paymentStatusVariant(p.status)}">{p.status}</span>
                      </td>
                      <td data-label="Дата">{fmtDate(p.created_at)}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            {:else}
              <div class="admin-card-body"><span class="admin-muted">Нет данных</span></div>
            {/if}
          </div>
        {/if}
      {/if}

      {#if active === "users"}
        <div class="admin-toolbar admin-toolbar-users">
          <div class="admin-toolbar-search">
            <input
              type="search"
              class="input"
              placeholder={at("users_search_placeholder", {}, "ID, @username или email")}
              bind:value={usersQuery}
              on:keydown={(e) => e.key === "Enter" && ((usersPage = 0), loadUsers())}
            />
            <button type="button" class="admin-btn admin-btn-primary" on:click={() => { usersPage = 0; loadUsers(); }}>{at("find", {}, "Найти")}</button>
          </div>

          <div class="admin-toolbar-controls">
            <Label.Root class="admin-toolbar-field">
              <span class="admin-toolbar-field-label">{at("filter", {}, "Фильтр")}</span>
              <Select.Root
                type="single"
                value={usersFilter}
                onValueChange={(value) => { usersFilter = value; usersPage = 0; loadUsers(); }}
              >
                <Select.Trigger class="admin-select-trigger admin-toolbar-select" aria-label={at("filter", {}, "Фильтр")}>
                  <span>{optionLabel(USERS_FILTER_OPTIONS, usersFilter)}</span>
                  <ChevronDown size={14} class="admin-select-icon" />
                </Select.Trigger>
                <Select.Portal>
                  <Select.Content class="admin-select-content" sideOffset={6}>
                    {#each USERS_FILTER_OPTIONS as opt}
                      <Select.Item value={opt.value} class="admin-select-item">
                        <span>{opt.label}</span>
                        <Check size={14} class="admin-select-item-check" />
                      </Select.Item>
                    {/each}
                  </Select.Content>
                </Select.Portal>
              </Select.Root>
            </Label.Root>

            <Label.Root class="admin-toolbar-field">
              <span class="admin-toolbar-field-label">{at("panel_status", {}, "Статус панели")}</span>
              <Select.Root
                type="single"
                value={usersPanelStatus}
                onValueChange={(value) => { usersPanelStatus = value; usersPage = 0; loadUsers(); }}
              >
                <Select.Trigger class="admin-select-trigger admin-toolbar-select" aria-label={at("panel_status", {}, "Статус панели")}>
                  <span>{optionLabel(USERS_PANEL_STATUS_OPTIONS, usersPanelStatus)}</span>
                  <ChevronDown size={14} class="admin-select-icon" />
                </Select.Trigger>
                <Select.Portal>
                  <Select.Content class="admin-select-content" sideOffset={6}>
                    {#each USERS_PANEL_STATUS_OPTIONS as opt}
                      <Select.Item value={opt.value} class="admin-select-item">
                        <span>{opt.label}</span>
                        <Check size={14} class="admin-select-item-check" />
                      </Select.Item>
                    {/each}
                  </Select.Content>
                </Select.Portal>
              </Select.Root>
            </Label.Root>

            <Label.Root class="admin-toolbar-field">
              <span class="admin-toolbar-field-label">{at("sort", {}, "Сортировка")}</span>
              <Select.Root
                type="single"
                value={usersSort}
                onValueChange={(value) => { usersSort = value; usersPage = 0; loadUsers(); }}
              >
                <Select.Trigger class="admin-select-trigger admin-toolbar-select" aria-label={at("sort", {}, "Сортировка")}>
                  <span>{optionLabel(USERS_SORT_OPTIONS, usersSort)}</span>
                  <ChevronDown size={14} class="admin-select-icon" />
                </Select.Trigger>
                <Select.Portal>
                  <Select.Content class="admin-select-content" sideOffset={6}>
                    {#each USERS_SORT_OPTIONS as opt}
                      <Select.Item value={opt.value} class="admin-select-item">
                        <span>{opt.label}</span>
                        <Check size={14} class="admin-select-item-check" />
                      </Select.Item>
                    {/each}
                  </Select.Content>
                </Select.Portal>
              </Select.Root>
            </Label.Root>

            <div class="admin-toolbar-summary">
              <span class="admin-toolbar-field-label">{at("total", {}, "Всего")}</span>
              <strong>{usersTotal}</strong>
            </div>
          </div>
        </div>

        <div class="admin-table-wrap">
          {#if usersLoading}
            <ul class="admin-user-list admin-user-list-skeleton" aria-hidden="true">
              {#each Array(USERS_PAGE_SIZE) as _, i (i)}
                <li>
                  <div class="admin-user-row admin-user-row-skeleton">
                    <span class="admin-skeleton admin-skeleton-avatar"></span>
                    <span class="admin-user-main">
                      <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"></span>
                      <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-soft"></span>
                    </span>
                    <span class="admin-user-side">
                      <span class="admin-skeleton admin-skeleton-badge"></span>
                      <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span>
                    </span>
                  </div>
                </li>
              {/each}
            </ul>
          {:else if !users.length}
            <div class="admin-card-body"><span class="admin-muted">{at("users_empty", {}, "Никого не найдено")}</span></div>
          {:else}
            <ul class="admin-user-list">
              {#each users as user}
                {@const avatar = resolvedAvatarUrl(user)}
                {@const badge = panelStatusBadge(user)}
                <li>
                  <button type="button" class="admin-user-row" on:click={() => openUser(user)}>
                    <span class="admin-avatar admin-avatar-sm">
                      {#if avatar}
                        <img src={avatar} alt="" loading="lazy" referrerpolicy="no-referrer" />
                      {:else}
                        <span>{userInitials(user)}</span>
                      {/if}
                    </span>
                    <span class="admin-user-main">
                      <strong>{userDisplayName(user)}</strong>
                      <small>{userSecondaryName(user)}</small>
                    </span>
                    <span class="admin-user-side">
                      <span class="admin-badge admin-badge-{badge.variant}">{badge.label}</span>
                      <span class="admin-user-tertiary">{fmtDateShort(user.registration_date)}</span>
                    </span>
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        </div>

        <div class="admin-pagination">
          <span class="admin-pagination-meta">{at("page", {}, "Страница")} {usersPage + 1}</span>
          <div class="admin-pagination-buttons">
            <button type="button" class="admin-btn admin-btn-sm" disabled={usersPage === 0} on:click={() => { usersPage = Math.max(0, usersPage - 1); loadUsers(); }}>
              <ChevronLeft size={14} /> {at("back", {}, "Назад")}
            </button>
            <button type="button" class="admin-btn admin-btn-sm" disabled={!usersHasMore} on:click={() => { usersPage += 1; loadUsers(); }}>
              {at("next", {}, "Далее")} <ChevronRight size={14} />
            </button>
          </div>
        </div>
      {/if}

      {#if active === "payments"}
        <div class="admin-table-wrap">
          {#if paymentsLoading}
            <table class="admin-table admin-table-skeleton" aria-hidden="true">
              <thead>
                <tr>
                  <th>ID</th><th>{at("user", {}, "Пользователь")}</th><th>{at("amount", {}, "Сумма")}</th><th>{at("provider", {}, "Провайдер")}</th><th>{at("description", {}, "Описание")}</th><th>{at("status", {}, "Статус")}</th><th>{at("date", {}, "Дата")}</th>
                </tr>
              </thead>
              <tbody>
                {#each Array(8) as _, i (i)}
                  <tr>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-badge"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span></td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {:else if !payments.length}
            <div class="admin-card-body"><span class="admin-muted">{at("payments_empty", {}, "Нет платежей")}</span></div>
          {:else}
            <table class="admin-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>{at("user", {}, "Пользователь")}</th>
                  <th>{at("amount", {}, "Сумма")}</th>
                  <th>{at("provider", {}, "Провайдер")}</th>
                  <th>{at("description", {}, "Описание")}</th>
                  <th>{at("status", {}, "Статус")}</th>
                  <th>{at("date", {}, "Дата")}</th>
                </tr>
              </thead>
              <tbody>
                {#each payments as p}
                  <tr>
                    <td class="admin-cell-id" data-label="ID">#{p.payment_id}</td>
                    <td data-label={at("user", {}, "Пользователь")}>{p.user_label || p.user_id}</td>
                    <td data-label={at("amount", {}, "Сумма")}>{fmtMoney(p.amount, p.currency)}</td>
                    <td data-label={at("provider", {}, "Провайдер")}>{p.provider}</td>
                    <td class="admin-cell-wrap" data-label={at("description", {}, "Описание")}>{p.description || "—"}</td>
                    <td data-label={at("status", {}, "Статус")}>
                      <span class="admin-badge admin-badge-{paymentStatusVariant(p.status)}">{p.status}</span>
                    </td>
                    <td data-label={at("date", {}, "Дата")}>{fmtDate(p.created_at)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        </div>

        <div class="admin-pagination">
          <span class="admin-pagination-meta">{at("page_short", {}, "Стр.")} {paymentsPage + 1} · {at("total", {}, "Всего")} {paymentsTotal}</span>
          <div class="admin-pagination-buttons">
            <button type="button" class="admin-btn admin-btn-sm" disabled={paymentsPage === 0} on:click={() => { paymentsPage = Math.max(0, paymentsPage - 1); loadPayments(); }}>
              <ChevronLeft size={14} /> {at("back", {}, "Назад")}
            </button>
            <button type="button" class="admin-btn admin-btn-sm" disabled={!paymentsHasMore} on:click={() => { paymentsPage += 1; loadPayments(); }}>
              {at("next", {}, "Далее")} <ChevronRight size={14} />
            </button>
          </div>
        </div>
      {/if}

      {#if active === "promos"}
        <div class="admin-table-wrap">
          {#if promosLoading}
            <table class="admin-table admin-table-skeleton" aria-hidden="true">
              <thead>
                <tr>
                  <th>Код</th><th>Бонус</th><th>Активаций</th><th>Действует до</th><th>Статус</th><th class="admin-cell-actions">Действия</th>
                </tr>
              </thead>
              <tbody>
                {#each Array(6) as _, i (i)}
                  <tr>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-badge"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line"></span></td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {:else if !promos.length}
            <div class="admin-card-body"><span class="admin-muted">Промокодов нет</span></div>
          {:else}
            <table class="admin-table">
              <thead>
                <tr>
                  <th>Код</th>
                  <th>Бонус</th>
                  <th>Активаций</th>
                  <th>Действует до</th>
                  <th>Статус</th>
                  <th class="admin-cell-actions">Действия</th>
                </tr>
              </thead>
              <tbody>
                {#each promos as p}
                  <tr>
                    <td class="admin-cell-mono" data-label="Код">{p.code}</td>
                    <td data-label="Бонус">+{p.bonus_days} дн.</td>
                    <td data-label="Активаций">{p.current_activations}/{p.max_activations}</td>
                    <td data-label="Действует до">{p.valid_until ? fmtDateShort(p.valid_until) : "∞"}</td>
                    <td data-label="Статус">
                      {#if p.is_active}
                        <span class="admin-badge admin-badge-success">Активен</span>
                      {:else}
                        <span class="admin-badge admin-badge-muted">Выключен</span>
                      {/if}
                    </td>
                    <td class="admin-cell-actions" data-label="Действия">
                      <button type="button" class="admin-btn admin-btn-sm" on:click={() => togglePromo(p)}>
                        {p.is_active ? "Выкл" : "Вкл"}
                      </button>
                      <button type="button" class="admin-btn admin-btn-sm admin-btn-danger" on:click={() => deletePromo(p)}>
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        </div>
      {/if}

      {#if active === "broadcast"}
        <div class="admin-card">
          <header class="admin-card-head">
            <h3>Рассылка</h3>
            <small>Доставка через очередь сообщений</small>
          </header>
          <div class="admin-card-body">
            <div class="admin-form">
              <Label.Root class="admin-field-label">
                <span>Аудитория</span>
                <Select.Root type="single" value={broadcastTarget} onValueChange={(value) => (broadcastTarget = value)}>
                  <Select.Trigger class="admin-select-trigger" aria-label="Аудитория">
                    <span>{optionLabel(BROADCAST_TARGET_OPTIONS, broadcastTarget)}</span>
                    <ChevronDown size={14} class="admin-select-icon" />
                  </Select.Trigger>
                  <Select.Portal>
                    <Select.Content class="admin-select-content" sideOffset={6}>
                      {#each BROADCAST_TARGET_OPTIONS as opt}
                        <Select.Item value={opt.value} class="admin-select-item">
                          <span>{opt.label}</span>
                          <Check size={14} class="admin-select-item-check" />
                        </Select.Item>
                      {/each}
                    </Select.Content>
                  </Select.Portal>
                </Select.Root>
              </Label.Root>
              <Label.Root class="admin-field-label">
                <span>Текст сообщения</span>
                <small>Поддерживается HTML-разметка Telegram</small>
                <textarea class="admin-textarea" rows="6" bind:value={broadcastText}></textarea>
              </Label.Root>
              <div style="display:flex; gap:8px; align-items:center;">
                <button type="button" class="admin-btn admin-btn-primary" on:click={runBroadcast} disabled={broadcastBusy || !broadcastText.trim()}>
                  <Send size={14} /> {broadcastBusy ? "Отправка..." : "Поставить в очередь"}
                </button>
                {#if broadcastResult}
                  <span class="admin-muted">В очереди: {broadcastResult.queued} · Неудач: {broadcastResult.failed}</span>
                {/if}
              </div>
            </div>
          </div>
        </div>
      {/if}

      {#if active === "logs"}
        <div class="admin-toolbar admin-toolbar-card">
          <div class="admin-toolbar-search admin-toolbar-search-actions">
            <input
              type="search"
              class="input"
              placeholder={at("logs_user_filter_placeholder", {}, "Фильтр по ID пользователя")}
              bind:value={logsUserFilter}
              on:keydown={(e) => e.key === "Enter" && ((logsPage = 0), loadLogs())}
            />
            <button type="button" class="admin-btn admin-btn-primary" on:click={() => { logsPage = 0; loadLogs(); }}>{at("apply", {}, "Применить")}</button>
            <button type="button" class="admin-btn admin-btn-ghost" on:click={() => { logsUserFilter = ""; logsPage = 0; loadLogs(); }}>{at("reset", {}, "Сбросить")}</button>
          </div>
          <div class="admin-toolbar-summary">
            <span class="admin-toolbar-field-label">{at("total", {}, "Всего")}</span>
            <strong>{logsTotal}</strong>
          </div>
        </div>

        <div class="admin-table-wrap">
          {#if logsLoading}
            <table class="admin-table admin-table-skeleton" aria-hidden="true">
              <thead>
                <tr>
                  <th>{at("date", {}, "Дата")}</th><th>{at("event", {}, "Событие")}</th><th>User</th><th>Target</th><th>{at("content", {}, "Контент")}</th>
                </tr>
              </thead>
              <tbody>
                {#each Array(10) as _, i (i)}
                  <tr>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line"></span></td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {:else if !logs.length}
            <div class="admin-card-body"><span class="admin-muted">{at("logs_empty", {}, "Записей нет")}</span></div>
          {:else}
            <table class="admin-table">
              <thead>
                <tr>
                  <th>{at("date", {}, "Дата")}</th>
                  <th>{at("event", {}, "Событие")}</th>
                  <th>User</th>
                  <th>Target</th>
                  <th>{at("content", {}, "Контент")}</th>
                </tr>
              </thead>
              <tbody>
                {#each logs as entry}
                  <tr>
                    <td data-label={at("date", {}, "Дата")}>{fmtDate(entry.timestamp)}</td>
                    <td class="admin-cell-mono" data-label={at("event", {}, "Событие")}>{entry.event_type}</td>
                    <td class="admin-cell-mono" data-label="User">{entry.user_id || "—"}</td>
                    <td class="admin-cell-mono" data-label="Target">{entry.target_user_id || "—"}</td>
                    <td class="admin-cell-wrap" data-label={at("content", {}, "Контент")}>{entry.content || ""}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        </div>

        <div class="admin-pagination">
          <span class="admin-pagination-meta">{at("page_short", {}, "Стр.")} {logsPage + 1}</span>
          <div class="admin-pagination-buttons">
            <button type="button" class="admin-btn admin-btn-sm" disabled={logsPage === 0} on:click={() => { logsPage = Math.max(0, logsPage - 1); loadLogs(); }}>
              <ChevronLeft size={14} /> {at("back", {}, "Назад")}
            </button>
            <button type="button" class="admin-btn admin-btn-sm" disabled={!logsHasMore} on:click={() => { logsPage += 1; loadLogs(); }}>
              {at("next", {}, "Далее")} <ChevronRight size={14} />
            </button>
          </div>
        </div>
      {/if}

      {#if active === "ads"}
        <div class="admin-table-wrap">
          {#if adsLoading}
            <table class="admin-table admin-table-skeleton" aria-hidden="true">
              <thead>
                <tr>
                  <th>ID</th><th>Источник</th><th>Параметр</th><th>Стоимость</th><th>Регистрации</th><th>Конверсии</th><th>Статус</th><th class="admin-cell-actions">Действия</th>
                </tr>
              </thead>
              <tbody>
                {#each Array(6) as _, i (i)}
                  <tr>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-badge"></span></td>
                    <td><span class="admin-skeleton admin-skeleton-line"></span></td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {:else if !ads.length}
            <div class="admin-card-body"><span class="admin-muted">Кампаний нет</span></div>
          {:else}
            <table class="admin-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Источник</th>
                  <th>Параметр</th>
                  <th>Стоимость</th>
                  <th>Регистрации</th>
                  <th>Конверсии</th>
                  <th>Статус</th>
                  <th class="admin-cell-actions">Действия</th>
                </tr>
              </thead>
              <tbody>
                {#each ads as ad}
                  <tr>
                    <td class="admin-cell-id" data-label="ID">#{ad.id}</td>
                    <td data-label="Источник">{ad.source}</td>
                    <td class="admin-cell-mono" data-label="Параметр">{ad.start_param}</td>
                    <td data-label="Стоимость">{fmtMoney(ad.cost)}</td>
                    <td data-label="Регистрации">{ad.stats?.registrations ?? 0}</td>
                    <td data-label="Конверсии">{ad.stats?.conversions ?? 0}</td>
                    <td data-label="Статус">
                      {#if ad.is_active}
                        <span class="admin-badge admin-badge-success">Активна</span>
                      {:else}
                        <span class="admin-badge admin-badge-muted">Выключена</span>
                      {/if}
                    </td>
                    <td class="admin-cell-actions" data-label="Действия">
                      <button type="button" class="admin-btn admin-btn-sm" on:click={() => toggleAd(ad)}>
                        {ad.is_active ? "Выкл" : "Вкл"}
                      </button>
                      <button type="button" class="admin-btn admin-btn-sm admin-btn-danger" on:click={() => deleteAd(ad)}>
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        </div>
      {/if}

      {#if active === "tariffs"}
        {#if tariffsLoading}
          <div class="admin-empty">Загрузка…</div>
        {:else}
          <div class="admin-stat-grid">
            <div class="admin-stat-card">
              <span class="admin-stat-label">Всего тарифов</span>
              <strong class="admin-stat-value">{tariffsCatalog.tariffs.length}</strong>
              <span class="admin-stat-trend">Включено: {enabledTariffs.length}</span>
            </div>
            <div class="admin-stat-card">
              <span class="admin-stat-label">По умолчанию</span>
              <strong class="admin-stat-value">{tariffsCatalog.default_tariff || "—"}</strong>
              <span class="admin-stat-trend">Используется для новых подписок</span>
            </div>
            <div class="admin-stat-card">
              <span class="admin-stat-label">Отключено</span>
              <strong class="admin-stat-value">{disabledTariffs}</strong>
              <span class="admin-stat-trend">Скрыто с витрины</span>
            </div>
          </div>

          <article class="admin-card">
            <header class="admin-card-head">
              <div>
                <h3>Каталог тарифов</h3>
                <small>{tariffsPath || "config/tariffs.json"}</small>
              </div>
              <button type="button" class="admin-btn admin-btn-sm" on:click={loadTariffs} disabled={tariffsLoading || tariffsSaving}>
                <RefreshCw size={13} /> Обновить
              </button>
            </header>
            <div class="admin-card-body">
              {#if !tariffsCatalog.tariffs.length}
                <div class="admin-empty">
                  Каталог пуст. Добавьте первый тариф, после сохранения будет создан JSON-файл каталога.
                </div>
              {:else}
                <div class="admin-tariff-grid">
                  {#each tariffsCatalog.tariffs as tariff}
                    <article class="admin-tariff-card" class:is-disabled={tariff.enabled === false}>
                      <div class="admin-tariff-top">
                        <div>
                          <div class="admin-tariff-title">
                            <strong>{tariffName(tariff)}</strong>
                            {#if tariff.key === tariffsCatalog.default_tariff}
                              <span class="admin-badge admin-badge-success">Default</span>
                            {/if}
                          </div>
                          <code>{tariff.key}</code>
                        </div>
                        {#if tariff.enabled === false}
                          <span class="admin-badge admin-badge-muted">Выключен</span>
                        {:else}
                          <span class="admin-badge admin-badge-success">Активен</span>
                        {/if}
                      </div>
                      <p>{tariff.descriptions?.ru || tariff.descriptions?.en || "Без описания"}</p>
                      <div class="admin-tariff-facts">
                        <span>{tariff.billing_model === "traffic" ? "Трафик" : "Периоды"}</span>
                        <span>{tariffPriceSummary(tariff)}</span>
                        <span>Squads: {(tariff.squad_uuids || []).length}</span>
                        <span>Premium: {(tariff.premium_squad_uuids || []).length ? `${tariff.premium_monthly_gb || 0} GB` : "—"}</span>
                        <span>Устройства: {tariff.hwid_device_limit ?? "env"}</span>
                      </div>
                      <div class="admin-tariff-actions">
                        <button type="button" class="admin-btn admin-btn-sm" on:click={() => openEditTariff(tariff)}>
                          Настроить
                        </button>
                        <button type="button" class="admin-btn admin-btn-sm" on:click={() => toggleTariffEnabled(tariff)} disabled={tariffsSaving}>
                          {tariff.enabled === false ? "Включить" : "Выключить"}
                        </button>
                        <button
                          type="button"
                          class="admin-btn admin-btn-sm"
                          on:click={() => setDefaultTariff(tariff.key)}
                          disabled={tariffsSaving || tariff.enabled === false || tariff.key === tariffsCatalog.default_tariff}
                        >
                          По умолчанию
                        </button>
                        <button
                          type="button"
                          class="admin-btn admin-btn-sm admin-btn-danger"
                          on:click={() => { tariffDeleteTarget = tariff; tariffDeleteOpen = true; }}
                          disabled={tariffsSaving}
                          aria-label="Удалить тариф"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </article>
                  {/each}
                </div>
              {/if}
            </div>
          </article>
        {/if}
      {/if}

      {#if active === "settings"}
        {#if settingsLoading || !settingsSections.length}
          <div class="admin-empty">{settingsLoading ? "Загрузка…" : "Нет данных"}</div>
        {:else}
          <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;">
            <p class="admin-muted" style="margin:0;">
              Изменения в админке имеют приоритет над <code>.env</code>. Кнопка «Восстановить» возвращает значение из переменных окружения.
            </p>
            <button type="button" class="admin-btn admin-btn-sm admin-btn-ghost" on:click={toggleAllSections}>
              {settingsAllOpen ? "Свернуть всё" : "Развернуть всё"}
            </button>
          </div>
          <Accordion.Root type="multiple" bind:value={settingsOpenSections} class="admin-accordion">
            {#each settingsSections as section}
              {@const dirtyInSection = section.fields.filter((f) => Boolean(settingsDirty[f.key])).length}
              {@const overriddenInSection = section.fields.filter((f) => isOverridden(f)).length}
              <Accordion.Item value={section.id} class="admin-accordion-item admin-card">
                <Accordion.Header class="admin-accordion-header">
                  <Accordion.Trigger class="admin-accordion-trigger">
                    <span class="admin-accordion-title">{sectionTitle(section.id)}</span>
                    <span class="admin-accordion-meta">
                      {section.fields.length} параметров{#if overriddenInSection} · {overriddenInSection} override{/if}{#if dirtyInSection} · {dirtyInSection} изм.{/if}
                    </span>
                    <ChevronRight size={16} class="admin-accordion-chev" />
                  </Accordion.Trigger>
                </Accordion.Header>
                <Accordion.Content class="admin-accordion-content">
                  {@const groups = groupSectionFields(section)}
                  {@const rootGroup = groups.find((g) => !g.label)}
                  {@const labelGroups = groups.filter((g) => g.label)}
                  <div class="admin-settings-fields">
                    {#if rootGroup}
                      {#each rootGroup.fields as field}
                        {@render renderField(field)}
                      {/each}
                    {/if}
                    {#if labelGroups.length}
                      <Accordion.Root
                        type="multiple"
                        value={settingsOpenSubsections[section.id] || []}
                        onValueChange={(v) => (settingsOpenSubsections = { ...settingsOpenSubsections, [section.id]: v })}
                        class="admin-subsection-accordion"
                      >
                        {#each labelGroups as group}
                          {@const subDirty = group.fields.filter((f) => Boolean(settingsDirty[f.key])).length}
                          {@const subOverridden = group.fields.filter((f) => isOverridden(f)).length}
                          <Accordion.Item value={group.id} class="admin-settings-subsection">
                            <Accordion.Header class="admin-accordion-header">
                              <Accordion.Trigger class="admin-settings-subsection-trigger">
                                <strong>{group.label}</strong>
                                <span class="admin-settings-subsection-meta">
                                  {group.fields.length} полей{#if subOverridden} · {subOverridden} override{/if}{#if subDirty} · {subDirty} изм.{/if}
                                </span>
                                <ChevronRight size={14} class="admin-accordion-chev" />
                              </Accordion.Trigger>
                            </Accordion.Header>
                            <Accordion.Content class="admin-accordion-content">
                              <div class="admin-settings-subsection-body">
                                {#each group.fields as field}
                                  {@render renderField(field)}
                                {/each}
                              </div>
                            </Accordion.Content>
                          </Accordion.Item>
                        {/each}
                      </Accordion.Root>
                    {/if}
                  </div>
                </Accordion.Content>
              </Accordion.Item>
            {/each}
          </Accordion.Root>
        {/if}
      {/if}
    </main>
  </section>
</div>

<Dialog
  open={tariffEditorOpen}
  title={tariffEditingKey ? "Настройка тарифа" : "Новый тариф"}
  description={tariffEditingKey || "Каталог будет сохранён в JSON после подтверждения"}
  closeLabel="Закрыть"
  onclose={() => (tariffEditorOpen = false)}
  class="admin-dialog admin-tariff-dialog"
>
  <Tabs.Root bind:value={tariffEditorTab} class="admin-tabs-root">
    <Tabs.List class="admin-tabs-list">
      <Tabs.Trigger value="general" class="admin-tabs-trigger">Основное</Tabs.Trigger>
      <Tabs.Trigger value="pricing" class="admin-tabs-trigger">Цены</Tabs.Trigger>
      <Tabs.Trigger value="topup" class="admin-tabs-trigger">Докупки</Tabs.Trigger>
      <Tabs.Trigger value="premium" class="admin-tabs-trigger">Premium</Tabs.Trigger>
      <Tabs.Trigger value="hwid" class="admin-tabs-trigger">Устройства</Tabs.Trigger>
    </Tabs.List>

    <Tabs.Content value="general" class="admin-tabs-content">
      <div class="admin-form-row admin-form-row-2">
        <Label.Root class="admin-field-label">
          <span>Ключ тарифа</span>
          <small>Латиницей, без пробелов. Используется в платежах и подписках, менять после публикации не рекомендуется</small>
          <input class="input" type="text" placeholder="standard" bind:value={tariffDraft.key} />
        </Label.Root>

        <div class="admin-field-label">
          <span>Модель тарификации</span>
          <small><b>Период</b> — пользователь покупает фиксированный срок (1/3/12 мес. и т.д.). <b>Трафик</b> — пользователь покупает пакеты гигабайт по фиксированной цене за GB</small>
          <Select.Root type="single" bind:value={tariffDraft.billing_model}>
            <Select.Trigger class="admin-select-trigger" aria-label="Модель">
              <span>{tariffDraft.billing_model === "traffic" ? "Трафик" : "Период"}</span>
              <ChevronDown size={14} class="admin-select-icon" />
            </Select.Trigger>
            <Select.Portal>
              <Select.Content class="admin-select-content" sideOffset={6}>
                <Select.Item value="period" class="admin-select-item">
                  <span>Период</span>
                  <Check size={14} class="admin-select-item-check" />
                </Select.Item>
                <Select.Item value="traffic" class="admin-select-item">
                  <span>Трафик</span>
                  <Check size={14} class="admin-select-item-check" />
                </Select.Item>
              </Select.Content>
            </Select.Portal>
          </Select.Root>
        </div>
      </div>

      <div class="admin-action-row admin-action-row-bordered">
        <Switch.Root
          checked={tariffDraft.enabled}
          onCheckedChange={(v) => (tariffDraft.enabled = v)}
          class="admin-switch-root"
        >
          <Switch.Thumb class="admin-switch-thumb" />
        </Switch.Root>
        <Label.Root class="admin-action-label">
          <strong>{tariffDraft.enabled ? "Тариф виден на витрине" : "Тариф скрыт от пользователей"}</strong>
          <small>Выключенный тариф не показывается в боте/мини-аппе, но активные подписки на нём продолжают работать</small>
        </Label.Root>
      </div>

      <div class="admin-form-row admin-form-row-2">
        <Label.Root class="admin-field-label">
          <span>Название · RU</span>
          <input class="input" type="text" placeholder="Стандарт" bind:value={tariffDraft.nameRu} />
        </Label.Root>
        <Label.Root class="admin-field-label">
          <span>Название · EN</span>
          <input class="input" type="text" placeholder="Standard" bind:value={tariffDraft.nameEn} />
        </Label.Root>
      </div>

      <div class="admin-form-row admin-form-row-2">
        <Label.Root class="admin-field-label">
          <span>Описание · RU</span>
          <input class="input" type="text" placeholder="Базовый набор серверов" bind:value={tariffDraft.descriptionRu} />
        </Label.Root>
        <Label.Root class="admin-field-label">
          <span>Описание · EN</span>
          <input class="input" type="text" placeholder="Base server pool" bind:value={tariffDraft.descriptionEn} />
        </Label.Root>
      </div>

      <div class="admin-field-label">
        <span>Базовые Internal Squads</span>
        <small>{panelSquadsLoading ? "Загружаю список из панели…" : "Сквады Remnawave, к которым подключается пользователь по этому тарифу. Выберите один или несколько"}</small>
        <Select.Root
          type="single"
          bind:value={selectedBaseSquad}
          onValueChange={(value) => {
            addSquadToDraft("squadUuids", value);
            selectedBaseSquad = "";
          }}
        >
          <Select.Trigger class="admin-select-trigger" aria-label="Добавить основной сквад">
            <span>Добавить сквад</span>
            <ChevronDown size={14} class="admin-select-icon" />
          </Select.Trigger>
          <Select.Portal>
            <Select.Content class="admin-select-content" sideOffset={6}>
              {#each panelSquads as squad}
                <Select.Item value={squad.uuid} class="admin-select-item">
                  <span>{squad.name}</span>
                  <Check size={14} class="admin-select-item-check" />
                </Select.Item>
              {/each}
            </Select.Content>
          </Select.Portal>
        </Select.Root>
        <div class="admin-chip-list">
          {#each normalizeUuidList(tariffDraft.squadUuids) as uuid}
            <button type="button" class="admin-chip" on:click={() => removeSquadFromDraft("squadUuids", uuid)}>
              {squadLabel(uuid)} <X size={12} />
            </button>
          {/each}
        </div>
      </div>

      <div class="admin-form-row admin-form-row-2">
        <Label.Root class="admin-field-label">
          <span>Лимит устройств (HWID)</span>
          <small>Сколько устройств может одновременно использовать подписку. Пусто — взять значение из .env, <code>0</code> — без ограничений</small>
          <input class="input" type="number" min="0" placeholder="5" bind:value={tariffDraft.hwid_device_limit} />
        </Label.Root>
        {#if tariffDraft.billing_model === "period"}
          <Label.Root class="admin-field-label">
            <span>Месячный лимит трафика, GB</span>
            <small>Сколько GB включено в тариф на каждый месяц. <code>0</code> — безлимитный трафик. Сверху можно докупать пакеты на вкладке «Докупки»</small>
            <input class="input" type="number" min="0" step="0.1" placeholder="100" bind:value={tariffDraft.monthly_gb} />
          </Label.Root>
        {:else}
          <Label.Root class="admin-field-label">
            <span>Курс конвертации, ₽ за 1 GB</span>
            <small>По этому курсу остаток подписки пересчитывается в гигабайты при переходе пользователя с тарифа «Период» на «Трафик»</small>
            <input class="input" type="number" min="0" step="0.01" placeholder="20" bind:value={tariffDraft.conversion_rate_rub_per_gb} />
          </Label.Root>
        {/if}
      </div>
    </Tabs.Content>

    <Tabs.Content value="premium" class="admin-tabs-content">
      <section class="admin-editor-section">
        <header class="admin-editor-section-head">
          <div class="admin-editor-section-title">
            <strong>Premium-доступ и отдельный счётчик трафика</strong>
            <small>Premium-сквады дают пользователю доступ к более быстрым/премиальным нодам; их трафик считается отдельно от основного, чтобы можно было ограничить или продавать дополнительно</small>
          </div>
        </header>
        <div class="admin-form-row admin-form-row-2">
          <Label.Root class="admin-field-label">
            <span>Название premium-раздела, RU</span>
            <small>Эта строка заменит «Premium-серверы» в кабинете, докупках и карточках лимитов.</small>
            <input class="input" type="text" placeholder="Premium-серверы" bind:value={tariffDraft.premiumNameRu} />
          </Label.Root>
          <Label.Root class="admin-field-label">
            <span>Название premium-раздела, EN</span>
            <small>Опционально для английского интерфейса.</small>
            <input class="input" type="text" placeholder="Premium servers" bind:value={tariffDraft.premiumNameEn} />
          </Label.Root>
        </div>
        <div class="admin-form-row admin-form-row-2">
          <div class="admin-field-label">
            <span>Premium Internal Squads</span>
            <small>Сквады из Remnawave, доступные только владельцам этого тарифа. Трафик считается по их accessible nodes</small>
            <Select.Root
              type="single"
              bind:value={selectedPremiumSquad}
              onValueChange={(value) => {
                addSquadToDraft("premiumSquadUuids", value);
                selectedPremiumSquad = "";
              }}
            >
              <Select.Trigger class="admin-select-trigger" aria-label="Добавить premium-сквад">
                <span>Добавить premium-сквад</span>
                <ChevronDown size={14} class="admin-select-icon" />
              </Select.Trigger>
              <Select.Portal>
                <Select.Content class="admin-select-content" sideOffset={6}>
                  {#each panelSquads as squad}
                    <Select.Item value={squad.uuid} class="admin-select-item">
                      <span>{squad.name}</span>
                      <Check size={14} class="admin-select-item-check" />
                    </Select.Item>
                  {/each}
                </Select.Content>
              </Select.Portal>
            </Select.Root>
            <div class="admin-chip-list">
              {#each normalizeUuidList(tariffDraft.premiumSquadUuids) as uuid}
                <button type="button" class="admin-chip" on:click={() => removeSquadFromDraft("premiumSquadUuids", uuid)}>
                  {squadLabel(uuid)} <X size={12} />
                </button>
              {/each}
            </div>
          </div>
          <Label.Root class="admin-field-label">
            <span>Месячный лимит premium-трафика, GB</span>
            <small>Сколько GB через premium-сквады включено в тариф каждый месяц. <code>0</code> или пусто — отдельного premium-лимита нет (premium-нодами можно пользоваться без ограничения)</small>
            <input class="input" type="number" min="0" step="0.1" placeholder="50" bind:value={tariffDraft.premium_monthly_gb} />
          </Label.Root>
        </div>
      </section>

      <section class="admin-editor-section">
        <header class="admin-editor-section-head">
          <div class="admin-editor-section-title">
            <strong>Докупка premium-трафика</strong>
            <small>Пакеты для расширения месячного premium-лимита, когда пользователь его исчерпал</small>
          </div>
          <div class="admin-editor-section-actions">
            <button type="button" class="admin-btn admin-btn-sm" on:click={() => addDraftRow("premiumTopupRubRows", { gb: 10, price: "" })}><Plus size={12} /> Пакет ₽</button>
            <button type="button" class="admin-btn admin-btn-sm" on:click={() => addDraftRow("premiumTopupStarsRows", { gb: 10, price: "" })}><Plus size={12} /> Пакет ⭐</button>
          </div>
        </header>
        <div class="admin-package-columns">
          <div class="admin-row-editor">
            <span class="admin-row-editor-caption">Оплата рублями</span>
            {#if tariffDraft.premiumTopupRubRows.length}
              <div class="admin-row-editor-line admin-row-editor-header">
                <span>Объём, GB</span>
                <span>Цена, ₽</span>
                <span></span>
              </div>
            {/if}
            {#each tariffDraft.premiumTopupRubRows as row, index}
              <div class="admin-row-editor-line">
                <input class="input" type="number" min="0.1" step="0.1" placeholder="10" bind:value={row.gb} aria-label="Объём premium-пакета в GB" />
                <input class="input" type="number" min="0" step="0.01" placeholder="199" bind:value={row.price} aria-label="Цена premium-пакета в рублях" />
                <button type="button" class="admin-btn admin-btn-sm admin-btn-danger" on:click={() => removeDraftRow("premiumTopupRubRows", index)} aria-label="Удалить"><Trash2 size={13} /></button>
              </div>
            {/each}
          </div>
          <div class="admin-row-editor">
            <span class="admin-row-editor-caption">Оплата Telegram Stars</span>
            {#if tariffDraft.premiumTopupStarsRows.length}
              <div class="admin-row-editor-line admin-row-editor-header">
                <span>Объём, GB</span>
                <span>Цена, ⭐</span>
                <span></span>
              </div>
            {/if}
            {#each tariffDraft.premiumTopupStarsRows as row, index}
              <div class="admin-row-editor-line">
                <input class="input" type="number" min="0.1" step="0.1" placeholder="10" bind:value={row.gb} aria-label="Объём premium-пакета в GB" />
                <input class="input" type="number" min="0" step="1" placeholder="100" bind:value={row.price} aria-label="Цена premium-пакета в Telegram Stars" />
                <button type="button" class="admin-btn admin-btn-sm admin-btn-danger" on:click={() => removeDraftRow("premiumTopupStarsRows", index)} aria-label="Удалить"><Trash2 size={13} /></button>
              </div>
            {/each}
          </div>
        </div>
      </section>
    </Tabs.Content>

    <Tabs.Content value="pricing" class="admin-tabs-content">
      {#if tariffDraft.billing_model === "period"}
        <section class="admin-editor-section">
          <header class="admin-editor-section-head">
            <div class="admin-editor-section-title">
              <strong>Периоды подписки и цены</strong>
              <small>Каждая строка — отдельный вариант на витрине: за сколько месяцев пользователь платит и сколько это стоит</small>
            </div>
            <button type="button" class="admin-btn admin-btn-sm" on:click={() => addDraftRow("periodRows", { months: 1, rub: "", stars: "" })}>
              <Plus size={13} /> Период
            </button>
          </header>
          {#if !tariffDraft.periodRows.length}
            <p class="admin-muted">Добавьте хотя бы один период — без него тариф не появится на витрине.</p>
          {:else}
            <div class="admin-row-editor">
              <div class="admin-row-editor-line admin-row-editor-4 admin-row-editor-header">
                <span>Срок, мес.</span>
                <span>Цена, ₽</span>
                <span>Цена, ⭐ Stars</span>
                <span></span>
              </div>
              {#each tariffDraft.periodRows as row, index}
                <div class="admin-row-editor-line admin-row-editor-4">
                  <input class="input" type="number" min="1" placeholder="1" bind:value={row.months} aria-label="Срок (месяцы)" />
                  <input class="input" type="number" min="0" step="0.01" placeholder="299" bind:value={row.rub} aria-label="Цена в рублях" />
                  <input class="input" type="number" min="0" step="1" placeholder="150" bind:value={row.stars} aria-label="Цена в Telegram Stars" />
                  <button type="button" class="admin-btn admin-btn-sm admin-btn-danger" on:click={() => removeDraftRow("periodRows", index)} aria-label="Удалить">
                    <Trash2 size={13} />
                  </button>
                </div>
              {/each}
            </div>
          {/if}
        </section>
      {:else}
        <section class="admin-editor-section">
          <header class="admin-editor-section-head">
            <div class="admin-editor-section-title">
              <strong>Пакеты трафика</strong>
              <small>Базовая витрина для трафиковой модели. Каждая строка — пакет «N гигабайт за N единиц валюты»</small>
            </div>
            <div class="admin-editor-section-actions">
              <button type="button" class="admin-btn admin-btn-sm" on:click={() => addDraftRow("trafficRubRows", { gb: 10, price: "" })}><Plus size={12} /> Пакет ₽</button>
              <button type="button" class="admin-btn admin-btn-sm" on:click={() => addDraftRow("trafficStarsRows", { gb: 10, price: "" })}><Plus size={12} /> Пакет ⭐</button>
            </div>
          </header>
          <div class="admin-package-columns">
            <div class="admin-row-editor">
              <span class="admin-row-editor-caption">Оплата рублями</span>
              {#if tariffDraft.trafficRubRows.length}
                <div class="admin-row-editor-line admin-row-editor-header">
                  <span>Объём, GB</span>
                  <span>Цена, ₽</span>
                  <span></span>
                </div>
              {/if}
              {#each tariffDraft.trafficRubRows as row, index}
                <div class="admin-row-editor-line">
                  <input class="input" type="number" min="0.1" step="0.1" placeholder="50" bind:value={row.gb} aria-label="Объём пакета в GB" />
                  <input class="input" type="number" min="0" step="0.01" placeholder="299" bind:value={row.price} aria-label="Цена пакета в рублях" />
                  <button type="button" class="admin-btn admin-btn-sm admin-btn-danger" on:click={() => removeDraftRow("trafficRubRows", index)} aria-label="Удалить"><Trash2 size={13} /></button>
                </div>
              {/each}
            </div>
            <div class="admin-row-editor">
              <span class="admin-row-editor-caption">Оплата Telegram Stars</span>
              {#if tariffDraft.trafficStarsRows.length}
                <div class="admin-row-editor-line admin-row-editor-header">
                  <span>Объём, GB</span>
                  <span>Цена, ⭐</span>
                  <span></span>
                </div>
              {/if}
              {#each tariffDraft.trafficStarsRows as row, index}
                <div class="admin-row-editor-line">
                  <input class="input" type="number" min="0.1" step="0.1" placeholder="50" bind:value={row.gb} aria-label="Объём пакета в GB" />
                  <input class="input" type="number" min="0" step="1" placeholder="150" bind:value={row.price} aria-label="Цена пакета в Telegram Stars" />
                  <button type="button" class="admin-btn admin-btn-sm admin-btn-danger" on:click={() => removeDraftRow("trafficStarsRows", index)} aria-label="Удалить"><Trash2 size={13} /></button>
                </div>
              {/each}
            </div>
          </div>
        </section>
      {/if}
    </Tabs.Content>

    <Tabs.Content value="topup" class="admin-tabs-content">
      {#if tariffDraft.billing_model === "period"}
        <section class="admin-editor-section">
          <header class="admin-editor-section-head">
            <div class="admin-editor-section-title">
              <strong>Докупка трафика поверх месячного лимита</strong>
              <small>Когда у пользователя кончился месячный лимит, ему предложат купить дополнительный пакет, не меняя срок подписки</small>
            </div>
            <div class="admin-editor-section-actions">
              <button type="button" class="admin-btn admin-btn-sm" on:click={() => addDraftRow("topupRubRows", { gb: 10, price: "" })}><Plus size={12} /> Пакет ₽</button>
              <button type="button" class="admin-btn admin-btn-sm" on:click={() => addDraftRow("topupStarsRows", { gb: 10, price: "" })}><Plus size={12} /> Пакет ⭐</button>
            </div>
          </header>
          <div class="admin-package-columns">
            <div class="admin-row-editor">
              <span class="admin-row-editor-caption">Оплата рублями</span>
              {#if tariffDraft.topupRubRows.length}
                <div class="admin-row-editor-line admin-row-editor-header">
                  <span>Объём, GB</span>
                  <span>Цена, ₽</span>
                  <span></span>
                </div>
              {/if}
              {#each tariffDraft.topupRubRows as row, index}
                <div class="admin-row-editor-line">
                  <input class="input" type="number" min="0.1" step="0.1" placeholder="20" bind:value={row.gb} aria-label="Объём пакета в GB" />
                  <input class="input" type="number" min="0" step="0.01" placeholder="149" bind:value={row.price} aria-label="Цена пакета в рублях" />
                  <button type="button" class="admin-btn admin-btn-sm admin-btn-danger" on:click={() => removeDraftRow("topupRubRows", index)} aria-label="Удалить"><Trash2 size={13} /></button>
                </div>
              {/each}
            </div>
            <div class="admin-row-editor">
              <span class="admin-row-editor-caption">Оплата Telegram Stars</span>
              {#if tariffDraft.topupStarsRows.length}
                <div class="admin-row-editor-line admin-row-editor-header">
                  <span>Объём, GB</span>
                  <span>Цена, ⭐</span>
                  <span></span>
                </div>
              {/if}
              {#each tariffDraft.topupStarsRows as row, index}
                <div class="admin-row-editor-line">
                  <input class="input" type="number" min="0.1" step="0.1" placeholder="20" bind:value={row.gb} aria-label="Объём пакета в GB" />
                  <input class="input" type="number" min="0" step="1" placeholder="75" bind:value={row.price} aria-label="Цена пакета в Telegram Stars" />
                  <button type="button" class="admin-btn admin-btn-sm admin-btn-danger" on:click={() => removeDraftRow("topupStarsRows", index)} aria-label="Удалить"><Trash2 size={13} /></button>
                </div>
              {/each}
            </div>
          </div>
        </section>
      {:else}
        <p class="admin-muted">Для трафиковой модели отдельные «докупки» не нужны — пакеты, которые вы настроили на вкладке «Цены», и являются докупками: пользователь покупает их повторно по мере исчерпания.</p>
      {/if}
    </Tabs.Content>

    <Tabs.Content value="hwid" class="admin-tabs-content">
      <section class="admin-editor-section">
        <header class="admin-editor-section-head">
          <div class="admin-editor-section-title">
            <strong>Пакеты дополнительных устройств (HWID)</strong>
            <small>Расширяет лимит, указанный во вкладке «Основное». Каждая строка — пакет «+N устройств за N единиц валюты»</small>
          </div>
          <div class="admin-editor-section-actions">
            <button type="button" class="admin-btn admin-btn-sm" on:click={() => addDraftRow("hwidRubRows", { count: 1, price: "" })}><Plus size={12} /> Пакет ₽</button>
            <button type="button" class="admin-btn admin-btn-sm" on:click={() => addDraftRow("hwidStarsRows", { count: 1, price: "" })}><Plus size={12} /> Пакет ⭐</button>
          </div>
        </header>
        <div class="admin-package-columns">
          <div class="admin-row-editor">
            <span class="admin-row-editor-caption">Оплата рублями</span>
            {#if tariffDraft.hwidRubRows.length}
              <div class="admin-row-editor-line admin-row-editor-header">
                <span>+ устройств</span>
                <span>Цена, ₽</span>
                <span></span>
              </div>
            {/if}
            {#each tariffDraft.hwidRubRows as row, index}
              <div class="admin-row-editor-line">
                <input class="input" type="number" min="1" step="1" placeholder="1" bind:value={row.count} aria-label="Сколько устройств добавляет пакет" />
                <input class="input" type="number" min="0" step="0.01" placeholder="99" bind:value={row.price} aria-label="Цена пакета в рублях" />
                <button type="button" class="admin-btn admin-btn-sm admin-btn-danger" on:click={() => removeDraftRow("hwidRubRows", index)} aria-label="Удалить"><Trash2 size={13} /></button>
              </div>
            {/each}
          </div>
          <div class="admin-row-editor">
            <span class="admin-row-editor-caption">Оплата Telegram Stars</span>
            {#if tariffDraft.hwidStarsRows.length}
              <div class="admin-row-editor-line admin-row-editor-header">
                <span>+ устройств</span>
                <span>Цена, ⭐</span>
                <span></span>
              </div>
            {/if}
            {#each tariffDraft.hwidStarsRows as row, index}
              <div class="admin-row-editor-line">
                <input class="input" type="number" min="1" step="1" placeholder="1" bind:value={row.count} aria-label="Сколько устройств добавляет пакет" />
                <input class="input" type="number" min="0" step="1" placeholder="50" bind:value={row.price} aria-label="Цена пакета в Telegram Stars" />
                <button type="button" class="admin-btn admin-btn-sm admin-btn-danger" on:click={() => removeDraftRow("hwidStarsRows", index)} aria-label="Удалить"><Trash2 size={13} /></button>
              </div>
            {/each}
          </div>
        </div>
      </section>
    </Tabs.Content>
  </Tabs.Root>

  <div class="admin-dialog-actions">
    <button type="button" class="admin-btn" on:click={() => (tariffEditorOpen = false)}>Отмена</button>
    <button type="button" class="admin-btn admin-btn-primary" on:click={saveTariffDraft} disabled={tariffsSaving || !tariffDraft.key.trim()}>
      <Save size={14} /> {tariffsSaving ? "Сохранение..." : "Сохранить тариф"}
    </button>
  </div>
</Dialog>

<Dialog
  open={tariffDeleteOpen}
  title="Удалить тариф?"
  description={tariffDeleteTarget ? `Тариф ${tariffDeleteTarget.key} исчезнет из каталога продаж.` : ""}
  closeLabel="Закрыть"
  onclose={() => (tariffDeleteOpen = false)}
  class="admin-dialog"
>
  <div class="admin-form-row">
    <button type="button" class="admin-btn" on:click={() => (tariffDeleteOpen = false)}>Отмена</button>
    <button type="button" class="admin-btn admin-btn-danger" on:click={deleteTariff} disabled={tariffsSaving}>
      <Trash2 size={14} /> Подтвердить удаление
    </button>
  </div>
</Dialog>

<Dialog
  open={Boolean(openedUser)}
  title={openedUser ? `Пользователь #${openedUser.user_id}` : ""}
  description={openedUser?.username ? "@" + openedUser.username : ""}
  closeLabel="Закрыть"
  onclose={closeUser}
  class="admin-dialog admin-user-dialog"
>
  {#if openedUser}
    {#if userDetailLoading || !openedUserDetail}
      <p class="admin-muted">Загрузка…</p>
    {:else}
      <div class="admin-user-dialog-body">
        <aside class="admin-user-aside">
          <div class="admin-user-summary">
            <span class="admin-avatar admin-avatar-lg">
              {#if resolvedAvatarUrl(openedUser)}
                <img src={resolvedAvatarUrl(openedUser)} alt="" loading="lazy" referrerpolicy="no-referrer" />
              {:else}
                <span>{userInitials(openedUser)}</span>
              {/if}
            </span>
            <div class="admin-user-summary-meta">
              <strong>{userDisplayName(openedUser)}</strong>
              <small>{userSecondaryName(openedUser)}</small>
              <div class="admin-user-summary-tags">
                {#if openedUser.is_banned}
                  <span class="admin-badge admin-badge-danger">Бан</span>
                {:else}
                  <span class="admin-badge admin-badge-success">Активен</span>
                {/if}
                {#if openedUserDetail.active_subscription}
                  <span class="admin-badge admin-badge-success">Подписка</span>
                {:else}
                  <span class="admin-badge admin-badge-muted">Без подписки</span>
                {/if}
              </div>
            </div>
          </div>

          <div class="admin-user-stats">
            <div class="admin-user-stat">
              <span>Заплачено</span>
              <strong>{fmtMoney(openedUserDetail.total_paid)}</strong>
            </div>
            <div class="admin-user-stat">
              <span>Логов</span>
              <strong>{openedUserDetail.log_count}</strong>
            </div>
          </div>

          <div class="admin-subsection-title">Профиль</div>
          <ul class="admin-meta-list">
            <li><span>ID</span><strong>{openedUser.user_id}</strong></li>
            <li><span>Telegram ID</span><strong>{openedUser.telegram_id || "—"}</strong></li>
            <li><span>Username</span><strong>{openedUser.username ? "@" + openedUser.username : "—"}</strong></li>
            <li><span>Email</span><strong class="admin-meta-truncate">{openedUser.email || "—"}</strong></li>
            <li><span>Регистрация</span><strong>{fmtDate(openedUser.registration_date)}</strong></li>
            <li><span>Реф. код</span><strong>{openedUserDetail.referral?.code || openedUserDetail.user?.referral_code || "—"}</strong></li>
          </ul>

          {#if openedUserDetail.subscription_url || openedUserDetail.referral?.bot_link || openedUserDetail.referral?.webapp_link}
            <div class="admin-subsection-title">Ссылки</div>
            <div class="admin-link-list">
              {#if openedUserDetail.subscription_url}
                <div class="admin-link-row">
                  <div class="admin-link-row-meta">
                    <span class="admin-link-row-label">Подписка</span>
                    <a class="admin-link-row-url" href={openedUserDetail.subscription_url} target="_blank" rel="noopener">
                      {openedUserDetail.subscription_url}
                    </a>
                  </div>
                  <button type="button" class="admin-btn admin-btn-icon" title="Скопировать" on:click={() => copyToClipboard(openedUserDetail.subscription_url, "Ссылка на подписку скопирована")}>
                    <Copy size={14} />
                  </button>
                </div>
              {/if}
              {#if openedUserDetail.referral?.bot_link}
                <div class="admin-link-row">
                  <div class="admin-link-row-meta">
                    <span class="admin-link-row-label">Реф. ссылка (бот)</span>
                    <a class="admin-link-row-url" href={openedUserDetail.referral.bot_link} target="_blank" rel="noopener">
                      {openedUserDetail.referral.bot_link}
                    </a>
                  </div>
                  <button type="button" class="admin-btn admin-btn-icon" title="Скопировать" on:click={() => copyToClipboard(openedUserDetail.referral.bot_link, "Реф. ссылка скопирована")}>
                    <Copy size={14} />
                  </button>
                </div>
              {/if}
              {#if openedUserDetail.referral?.webapp_link}
                <div class="admin-link-row">
                  <div class="admin-link-row-meta">
                    <span class="admin-link-row-label">Реф. ссылка (веб)</span>
                    <a class="admin-link-row-url" href={openedUserDetail.referral.webapp_link} target="_blank" rel="noopener">
                      {openedUserDetail.referral.webapp_link}
                    </a>
                  </div>
                  <button type="button" class="admin-btn admin-btn-icon" title="Скопировать" on:click={() => copyToClipboard(openedUserDetail.referral.webapp_link, "Реф. ссылка скопирована")}>
                    <Copy size={14} />
                  </button>
                </div>
              {/if}
            </div>
          {/if}
        </aside>

        <main class="admin-user-main">
          <Tabs.Root bind:value={userDetailTab} class="admin-tabs-root admin-user-tabs-root">
            <Tabs.List class="admin-tabs-list">
              <Tabs.Trigger value="subscription" class="admin-tabs-trigger">Подписка</Tabs.Trigger>
              <Tabs.Trigger value="activity" class="admin-tabs-trigger">Активность</Tabs.Trigger>
              <Tabs.Trigger value="actions" class="admin-tabs-trigger">Действия</Tabs.Trigger>
            </Tabs.List>

            <Tabs.Content value="subscription" class="admin-tabs-content">
          {#if openedUserDetail.active_subscription}
            <ul class="admin-meta-list">
              <li><span>Активна до</span><strong>{fmtDate(openedUserDetail.active_subscription.end_date)}</strong></li>
              <li><span>Тариф</span><strong>{openedUserDetail.active_subscription.tariff_key || "—"}</strong></li>
              <li><span>Авто-продление</span><strong>{pretty(openedUserDetail.active_subscription.auto_renew_enabled)}</strong></li>
              <li><span>Провайдер</span><strong>{openedUserDetail.active_subscription.provider || "—"}</strong></li>
            </ul>
            <div class="admin-traffic-summary">
              <div class={`admin-traffic-card${openedUserDetail.active_subscription.is_throttled ? " admin-traffic-card-warning" : ""}`}>
                <div class="admin-traffic-head">
                  <span>Основной трафик</span>
                  <strong>{trafficOfLabel(openedUserDetail.active_subscription.traffic_used_bytes, openedUserDetail.active_subscription.traffic_limit_bytes)}</strong>
                </div>
                <div class="admin-traffic-bar" aria-label="Использование основного трафика">
                  <span style={`width: ${trafficPercentValue(openedUserDetail.active_subscription.traffic_used_bytes, openedUserDetail.active_subscription.traffic_limit_bytes)}%`}></span>
                </div>
                <div class="admin-traffic-meta">
                  <span>Осталось: {trafficLeftLabel(openedUserDetail.active_subscription.traffic_used_bytes, openedUserDetail.active_subscription.traffic_limit_bytes)}</span>
                  <span>{trafficPercentValue(openedUserDetail.active_subscription.traffic_used_bytes, openedUserDetail.active_subscription.traffic_limit_bytes)}%</span>
                </div>
              </div>
              {#if Number(openedUserDetail.active_subscription.premium_limit_bytes || 0) > 0}
                <div class={`admin-traffic-card admin-traffic-card-premium${openedUserDetail.active_subscription.premium_is_limited ? " admin-traffic-card-warning" : ""}`}>
                  <div class="admin-traffic-head">
                    <span>Premium-сквады</span>
                    <strong>{trafficOfLabel(openedUserDetail.active_subscription.premium_used_bytes, openedUserDetail.active_subscription.premium_limit_bytes)}</strong>
                  </div>
                  <div class="admin-traffic-bar admin-traffic-bar-premium" aria-label="Использование premium-трафика">
                    <span style={`width: ${trafficPercentValue(openedUserDetail.active_subscription.premium_used_bytes, openedUserDetail.active_subscription.premium_limit_bytes)}%`}></span>
                  </div>
                  <div class="admin-traffic-meta">
                    <span>Осталось: {trafficLeftLabel(openedUserDetail.active_subscription.premium_used_bytes, openedUserDetail.active_subscription.premium_limit_bytes)}</span>
                    <span>{trafficPercentValue(openedUserDetail.active_subscription.premium_used_bytes, openedUserDetail.active_subscription.premium_limit_bytes)}%</span>
                  </div>
                </div>
              {/if}
            </div>
          {:else}
            <p class="admin-muted">Активной подписки нет</p>
          {/if}

          {#if (openedUserDetail.subscriptions || []).length}
            <Separator.Root class="admin-separator" />
            <div class="admin-subsection-title">История подписок · {openedUserDetail.subscriptions.length}</div>
            <div class="admin-mini-list">
              {#each openedUserDetail.subscriptions.slice(0, 8) as sub}
                <div class="admin-mini-list-row">
                  <div>
                    <strong>{sub.tariff_key || "Без тарифа"}</strong>
                    <small>до {fmtDate(sub.end_date)}</small>
                  </div>
                  {#if sub.is_active}
                    <span class="admin-badge admin-badge-success">Активна</span>
                  {:else}
                    <span class="admin-badge admin-badge-muted">{sub.status_from_panel || "История"}</span>
                  {/if}
                </div>
              {/each}
            </div>
          {/if}
        </Tabs.Content>

        <Tabs.Content value="activity" class="admin-tabs-content">
          <div class="admin-subsection-title">Последние платежи · {(openedUserDetail.recent_payments || []).length}</div>
          {#if (openedUserDetail.recent_payments || []).length}
            <div class="admin-mini-list">
              {#each openedUserDetail.recent_payments.slice(0, 8) as payment}
                <div class="admin-mini-list-row">
                  <div>
                    <strong>{fmtMoney(payment.amount, payment.currency)}</strong>
                    <small>{payment.provider} · {fmtDateShort(payment.created_at)}</small>
                  </div>
                  <span class="admin-badge admin-badge-{paymentStatusVariant(payment.status)}">{payment.status}</span>
                </div>
              {/each}
            </div>
          {:else}
            <p class="admin-muted">Платежей нет</p>
          {/if}
        </Tabs.Content>

        <Tabs.Content value="actions" class="admin-tabs-content admin-actions-tab">
          <div class="admin-user-quick-actions">
            <button type="button" class="admin-btn admin-reset-trial-btn" on:click={resetTrialUser} disabled={userActionBusy}>
              <RefreshCw size={14} /> Сбросить триал
            </button>
            <Label.Root class="admin-field-label admin-extend-field">
              <span>Продлить подписку</span>
              <div class="admin-extend-control">
                <input class="input" type="number" min="1" bind:value={userExtendDays} aria-label="Дней" />
                <button type="button" class="admin-btn" on:click={extendUser} disabled={userActionBusy}>
                  <Plus size={14} /> Продлить
                </button>
              </div>
            </Label.Root>
          </div>

          <Label.Root class="admin-field-label">
            <span>Сообщение в Telegram</span>
            <small>Поддерживается HTML-разметка Telegram</small>
            <textarea class="admin-textarea" rows="3" placeholder="Текст сообщения" bind:value={userMessageDraft}></textarea>
          </Label.Root>
          <div class="admin-message-actions">
            <button type="button" class="admin-btn" on:click={previewUserMessage} disabled={userActionBusy || !userMessageDraft.trim()}>
              <Eye size={14} /> Превью в Telegram
            </button>
            <button type="button" class="admin-btn admin-btn-primary" on:click={requestSendUserMessage} disabled={userActionBusy || !userMessageDraft.trim()}>
              <Send size={14} /> Отправить сообщение
            </button>
          </div>

          <section class="admin-danger-zone">
            <header class="admin-danger-zone-head">
              <strong>Опасные действия</strong>
              <small>Эти действия требуют подтверждения и (для удаления) необратимы</small>
            </header>
            <div class="admin-action-grid">
              {#if openedUser.is_banned}
                <button type="button" class="admin-btn admin-btn-danger-soft" on:click={requestBanToggle} disabled={userActionBusy}>
                  <UserPlus size={14} /> Разбанить пользователя
                </button>
              {:else}
                <button type="button" class="admin-btn admin-btn-danger" on:click={requestBanToggle} disabled={userActionBusy}>
                  <UserMinus size={14} /> Заблокировать
                </button>
              {/if}
              <button type="button" class="admin-btn admin-btn-danger" on:click={() => (userDeleteOpen = true)} disabled={userActionBusy}>
                <Trash2 size={14} /> Удалить аккаунт
              </button>
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
  open={userMessageConfirmOpen}
  title="Отправить сообщение пользователю?"
  description={openedUser ? `Получатель: ${userDisplayName(openedUser)}` : ""}
  closeLabel="Закрыть"
  onclose={() => (userMessageConfirmOpen = false)}
  class="admin-dialog"
>
  <div class="admin-confirm-message-preview">{userMessageDraft}</div>
  <div class="admin-dialog-actions">
    <button type="button" class="admin-btn" on:click={() => (userMessageConfirmOpen = false)}>Отмена</button>
    <button type="button" class="admin-btn admin-btn-primary" on:click={sendUserMessage} disabled={userActionBusy || !userMessageDraft.trim()}>
      <Send size={14} /> Подтвердить отправку
    </button>
  </div>
</Dialog>

<Dialog
  open={userBanConfirmOpen}
  title="Заблокировать пользователя?"
  description={openedUser ? `${userDisplayName(openedUser)} больше не сможет взаимодействовать с ботом. Действие можно отменить позже.` : ""}
  closeLabel="Закрыть"
  onclose={() => (userBanConfirmOpen = false)}
  class="admin-dialog"
>
  <div class="admin-dialog-actions">
    <button type="button" class="admin-btn" on:click={() => (userBanConfirmOpen = false)}>Отмена</button>
    <button type="button" class="admin-btn admin-btn-danger" on:click={() => applyBanToggle(true)} disabled={userActionBusy}>
      <UserMinus size={14} /> Заблокировать
    </button>
  </div>
</Dialog>

<Dialog
  open={userDeleteOpen}
  title="Удалить пользователя?"
  description="Действие необратимо. Удалятся все платежи, подписки и логи."
  closeLabel="Закрыть"
  onclose={() => (userDeleteOpen = false)}
  class="admin-dialog"
>
  <div class="admin-form-row">
    <button type="button" class="admin-btn" on:click={() => (userDeleteOpen = false)}>Отмена</button>
    <button type="button" class="admin-btn admin-btn-danger" on:click={deleteUser} disabled={userActionBusy}>
      <Trash2 size={14} /> Подтвердить удаление
    </button>
  </div>
</Dialog>

<Dialog open={promoCreateOpen} title="Новый промокод" closeLabel="Закрыть" onclose={() => (promoCreateOpen = false)} class="admin-dialog">
  <div class="admin-form">
    <Label.Root class="admin-field-label">
      <span>Код</span>
      <input class="input" type="text" placeholder="WELCOME10" bind:value={promoDraft.code} />
    </Label.Root>
    <div class="admin-form-row">
      <Label.Root class="admin-field-label">
        <span>Бонус (дней)</span>
        <input class="input" type="number" min="1" bind:value={promoDraft.bonus_days} />
      </Label.Root>
      <Label.Root class="admin-field-label">
        <span>Макс. активаций</span>
        <input class="input" type="number" min="1" bind:value={promoDraft.max_activations} />
      </Label.Root>
      <Label.Root class="admin-field-label">
        <span>Срок действия</span>
        <small>0 — бессрочно</small>
        <input class="input" type="number" min="0" bind:value={promoDraft.valid_days} />
      </Label.Root>
    </div>
    <button type="button" class="admin-btn admin-btn-primary" on:click={createPromo} disabled={!promoDraft.code.trim()}>
      <Check size={14} /> Создать
    </button>
  </div>
</Dialog>

<Dialog open={adCreateOpen} title="Новая кампания" closeLabel="Закрыть" onclose={() => (adCreateOpen = false)} class="admin-dialog">
  <div class="admin-form">
    <Label.Root class="admin-field-label">
      <span>Источник</span>
      <input class="input" type="text" placeholder="telegram_ads" bind:value={adDraft.source} />
    </Label.Root>
    <Label.Root class="admin-field-label">
      <span>start-параметр</span>
      <small>Передаётся в /start, должен быть уникален</small>
      <input class="input" type="text" placeholder="ads_summer25" bind:value={adDraft.start_param} />
    </Label.Root>
    <Label.Root class="admin-field-label">
      <span>Стоимость, RUB</span>
      <input class="input" type="number" step="0.01" min="0" bind:value={adDraft.cost} />
    </Label.Root>
    <button type="button" class="admin-btn admin-btn-primary" on:click={createAd} disabled={!adDraft.source.trim() || !adDraft.start_param.trim()}>
      <Check size={14} /> Создать
    </button>
  </div>
</Dialog>
