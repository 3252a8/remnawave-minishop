<script>
  import {
    ArrowLeft,
    ArrowRight,
    CheckCircle2,
    Circle,
    Copy,
    CreditCard,
    Crown,
    Database,
    Download,
    Gift,
    Globe2,
    Home,
    LockKeyhole,
    Mail,
    RefreshCw,
    Repeat2,
    Send,
    Settings as SettingsIcon,
    Ticket,
    UserRound,
    WalletCards,
    Zap,
  } from "lucide-svelte";
  import { onMount, tick } from "svelte";

  import Button from "./lib/components/ui/button.svelte";
  import Card from "./lib/components/ui/card.svelte";
  import Dialog from "./lib/components/ui/dialog.svelte";
  import Input from "./lib/components/ui/input.svelte";
  import PreviewBoard from "./PreviewBoard.svelte";

  const TELEGRAM_LOGIN_WIDGET_URL = "https://telegram.org/js/telegram-widget.js?23";
  const TELEGRAM_LOGIN_WIDGET_RENDER_TIMEOUT_MS = 8000;
  const MANUAL_LOGOUT_FLAG_KEY = "rw_webapp_manual_logout";
  const LANGUAGE_LABELS = {
    ru: "Русский",
    en: "English",
    de: "Deutsch",
    es: "Español",
    fr: "Français",
    tr: "Türkçe",
    uk: "Українська",
  };

  const DEV_MOCK = {
    config: {
      title: "/minishop",
      primaryColor: "#00fe7a",
      logoUrl: "",
      logoEmoji: "🫥",
      apiBase: "/api",
      supportUrl: "https://t.me/support",
      privacyPolicyUrl: "https://example.com/privacy",
      userAgreementUrl: "https://example.com/agreement",
      currency: "RUB",
      language: "ru",
      emailAuthEnabled: true,
      telegramLoginBotUsername: "preview_bot",
    },
    data: {
      ok: true,
      user: {
        id: 100200300,
        username: "username",
        email: "user@example.com",
        email_verified: true,
        telegram_id: 100200300,
        telegram_linked: true,
        telegram_photo_url: "",
        first_name: "Preview",
        language_code: "ru",
      },
      subscription: {
        active: true,
        status: "ACTIVE",
        remaining_text: "25 д. 8 ч.",
        end_date_text: "24.05.2026",
        days_left: 25,
        config_link: "https://sub.example.com/sub/preview-token",
        connect_url: "https://sub.example.com/connect/preview-token",
        traffic_used: "18.4 GB",
        traffic_limit: "100 GB",
        traffic_used_bytes: 19756849561,
        traffic_limit_bytes: 107374182400,
      },
      plans: [
        { months: 1, price: 290, currency: "RUB", title: "1 месяц" },
        { months: 3, price: 790, currency: "RUB", title: "3 месяца" },
        { months: 6, price: 1490, currency: "RUB", title: "6 месяцев" },
        { months: 12, price: 2690, currency: "RUB", title: "12 месяцев" },
      ],
      payment_methods: [
        { id: "yookassa", name: "Карта" },
        { id: "platega_sbp", name: "Telegram Pay" },
        { id: "cryptopay", name: "Криптовалюта" },
        { id: "freekassa", name: "Другие способы" },
      ],
      referral: {
        code: "ABCD1234",
        bot_link: "https://t.me/preview_bot?start=ref_uABCD1234",
        webapp_link: "https://minishop.app/ref/ABCD1234",
        invited_count: 4,
        purchased_count: 2,
        bonus_details: [
          { months: 1, title: "1 месяц", inviter_days: 7, friend_days: 3 },
          { months: 3, title: "3 месяца", inviter_days: 14, friend_days: 7 },
        ],
      },
      settings: {
        support_url: "https://t.me/support",
        traffic_mode: false,
        email_auth_enabled: true,
      },
    },
  };

  const demoTariffs = [
    {
      id: "subscription",
      title: "Подписка",
      caption: "Безлимитный трафик",
      details: "Идеально для постоянного использования",
      icon: "infinity",
      billing: "period",
    },
    {
      id: "traffic",
      title: "Трафик",
      caption: "Пакеты гигабайт",
      details: "Платите только за нужный объем",
      icon: "database",
      billing: "traffic",
    },
    {
      id: "premium",
      title: "Премиум",
      caption: "Максимальная скорость",
      details: "Приоритетные серверы и поддержка",
      icon: "crown",
      billing: "period",
    },
  ];

  const trafficPackages = [
    { gb: 20, price: 290 },
    { gb: 50, price: 590 },
    { gb: 100, price: 990 },
    { gb: 300, price: 2190 },
  ];

  const changeTariffs = [
    { ...demoTariffs[0], recalculation: "Доплата 190 ₽" },
    { ...demoTariffs[1], recalculation: "Доплата не требуется" },
    { ...demoTariffs[2], recalculation: "Доплата 390 ₽" },
  ];

  const query = new URLSearchParams(window.location.search);
  const isPreviewBoard = query.get("preview") === "all";
  const injectedConfig = readJsonScript("webapp-config");
  const isLocalShell =
    window.location.protocol === "file:" ||
    ["", "localhost", "127.0.0.1"].includes(window.location.hostname);
  const MOCK = !injectedConfig && isLocalShell ? DEV_MOCK : null;
  const CFG = {
    ...DEV_MOCK.config,
    ...(MOCK ? MOCK.config : {}),
    ...(injectedConfig || {}),
  };
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

  let mode = isPreviewBoard ? "preview" : "loading";
  let activeTab = "home";
  let screen = "home";
  let data = isPreviewBoard ? structuredCloneSafe(DEV_MOCK.data) : null;
  let selectedTariff = "subscription";
  let selectedChangeTariff = "traffic";
  let selectedPlan = null;
  let selectedTrafficPackage = trafficPackages[2];
  let selectedMethod = "";
  let payBusy = false;
  let promoCode = "";
  let promoBusy = false;
  let promoStatus = "";
  let promoIsError = false;
  let toastText = "";
  let toastTimer = null;
  let authMode = CFG.emailAuthEnabled === false ? "telegram" : "email";
  let authStatus = "";
  let authIsError = false;
  let authBusy = false;
  let email = "";
  let pendingEmail = "";
  let emailCode = "";
  let emailAvatarUrl = "";
  let avatarHashToken = "";
  let loginTelegramNode;
  let token = MOCK ? "local-preview" : localStorage.getItem("rw_webapp_token") || "";
  let csrfToken = MOCK ? "" : readCookie("rw_webapp_csrf") || "";
  let confirmTariffOpen = false;

  $: brandTitle = CFG.title || "/minishop";
  $: brandEmoji = CFG.logoEmoji || "🫥";
  $: accent = CFG.primaryColor || "#00fe7a";
  $: plans = data?.plans?.length ? data.plans : DEV_MOCK.data.plans;
  $: methods = data?.payment_methods?.length ? data.payment_methods : [];
  $: subscription = data?.subscription || DEV_MOCK.data.subscription;
  $: user = data?.user || {};
  $: referral = data?.referral || DEV_MOCK.data.referral;
  $: userLanguage = languageName(user?.language_code || CFG.language || "ru");
  $: telegramProfileName = telegramName(user);
  $: profileEmail = user?.email || "Почта не привязана";
  $: profileTelegramId = user?.telegram_id ? `TG ID ${user.telegram_id}` : "TG ID не привязан";
  $: profileAvatarUrl = user?.telegram_photo_url || emailAvatarUrl || "";
  $: if (!selectedPlan && plans.length) selectedPlan = plans[Math.min(1, plans.length - 1)];
  $: if (!selectedMethod && methods.length) selectedMethod = methods[0].id;
  $: {
    const emailKey = normalizedEmail(user?.email);
    if (!emailKey) {
      avatarHashToken = "";
      emailAvatarUrl = "";
    } else if (avatarHashToken !== emailKey) {
      avatarHashToken = emailKey;
      buildGravatarUrl(emailKey).then((url) => {
        if (avatarHashToken === emailKey) emailAvatarUrl = url;
      });
    }
  }

  onMount(() => {
    if (isPreviewBoard) return;
    boot();
  });

  function readJsonScript(id) {
    const node = document.getElementById(id);
    if (!node || !node.textContent) return null;
    try {
      return JSON.parse(node.textContent);
    } catch (error) {
      console.warn(`Failed to parse JSON config from #${id}`, error);
      return null;
    }
  }

  function structuredCloneSafe(value) {
    try {
      return structuredClone(value);
    } catch {
      return JSON.parse(JSON.stringify(value));
    }
  }

  async function boot() {
    mode = "loading";
    if (tg) {
      try {
        tg.ready();
        tg.expand();
      } catch {}
    }

    if (MOCK) {
      await loadData();
      return;
    }

    const magicToken = readMagicLoginToken();
    if (magicToken && (await finalizeMagicLogin(magicToken))) return;

    if (isManuallyLoggedOut()) {
      showLogin();
      return;
    }

    const widgetAuthData = readTelegramLoginWidgetAuthData();
    if (widgetAuthData && (await finalizeTelegramAuth(widgetAuthData, "auth_data"))) return;

    if (tg?.initData) {
      try {
        if (await finalizeTelegramAuth(tg.initData, "init_data")) return;
      } catch {}
    }

    if (token || csrfToken) {
      try {
        await loadData();
        return;
      } catch {
        clearToken();
      }
    }

    showLogin();
  }

  async function loadData() {
    const payload = await api("/me");
    if (!payload.ok) throw new Error(payload.error || "load_failed");
    data = payload;
    selectedPlan = payload.plans?.[Math.min(1, payload.plans.length - 1)] || payload.plans?.[0] || null;
    selectedMethod = payload.payment_methods?.[0]?.id || "";
    screen = "home";
    mode = "app";
  }

  function showLogin() {
    mode = "login";
    screen = "login";
    activeTab = "home";
    renderTelegramWidgetWhenNeeded();
  }

  async function api(path, options = {}) {
    if (MOCK) return mockApi(path, options);
    const method = String(options.method || "GET").toUpperCase();
    const headers = { ...(options.headers || {}) };
    if (token) headers.Authorization = `Bearer ${token}`;
    const csrf = csrfToken || readCookie("rw_webapp_csrf") || "";
    if (csrf && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      headers["X-CSRF-Token"] = csrf;
    }
    if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    const response = await fetch(`${CFG.apiBase}${path}`, { ...options, headers });
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401) {
      clearToken();
      showLogin();
    }
    return payload;
  }

  async function publicApi(path, payload = {}) {
    if (MOCK) {
      return mockApi(path, { method: "POST", body: JSON.stringify(payload) });
    }
    const response = await fetch(`${CFG.apiBase}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return response.json();
  }

  async function mockApi(path, options = {}) {
    await new Promise((resolve) => window.setTimeout(resolve, 120));
    if (path === "/me") return structuredCloneSafe(DEV_MOCK.data);
    if (path === "/auth/email/request") return { ok: true };
    if (path === "/auth/email/verify" || path === "/auth/email/magic") {
      return { ok: true, token: "local-preview", csrf_token: "local-preview-csrf" };
    }
    if (path === "/auth/token") {
      return { ok: true, token: "local-preview", csrf_token: "local-preview-csrf" };
    }
    if (path === "/promo/apply") return { ok: true, end_date_text: "31.05.2026" };
    if (path === "/auth/logout") return { ok: true };
    if (path === "/payments" && String(options.method || "").toUpperCase() === "POST") {
      return {
        ok: true,
        action: "open_link",
        payment_url: "https://example.com/payment-preview",
        payment_id: 10001,
      };
    }
    return { ok: false, error: "not_found" };
  }

  function readCookie(name) {
    const prefix = `${name}=`;
    const cookie = document.cookie.split("; ").find((part) => part.startsWith(prefix));
    return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : "";
  }

  function setToken(nextToken, nextCsrf = "") {
    clearManualLogoutFlag();
    token = nextToken || "";
    csrfToken = nextCsrf || readCookie("rw_webapp_csrf") || "";
    if (token && !MOCK) localStorage.setItem("rw_webapp_token", token);
  }

  function clearToken() {
    token = "";
    csrfToken = "";
    localStorage.removeItem("rw_webapp_token");
  }

  function markManualLogout() {
    try {
      localStorage.setItem(MANUAL_LOGOUT_FLAG_KEY, "1");
    } catch {}
  }

  function clearManualLogoutFlag() {
    try {
      localStorage.removeItem(MANUAL_LOGOUT_FLAG_KEY);
    } catch {}
  }

  function isManuallyLoggedOut() {
    try {
      return localStorage.getItem(MANUAL_LOGOUT_FLAG_KEY) === "1";
    } catch {
      return false;
    }
  }

  function readReferralParam() {
    const params = new URLSearchParams(window.location.search);
    const fromQuery = params.get("ref") || params.get("start") || params.get("start_param") || "";
    const fromTelegram = tg?.initDataUnsafe?.start_param || "";
    const value = String(fromTelegram || fromQuery || "").trim();
    if (value) {
      localStorage.setItem("rw_webapp_referral", value);
      return value;
    }
    return localStorage.getItem("rw_webapp_referral") || "";
  }

  function readMagicLoginToken() {
    const params = new URLSearchParams(window.location.search);
    return (params.get("login_token") || "").trim() || null;
  }

  function readTelegramLoginWidgetAuthData() {
    const params = new URLSearchParams(window.location.search);
    const keys = ["id", "first_name", "last_name", "username", "photo_url", "auth_date", "hash"];
    const authData = {};
    let hasAuthValue = false;
    keys.forEach((key) => {
      if (!params.has(key)) return;
      authData[key] = params.get(key) || "";
      hasAuthValue = true;
    });
    if (!hasAuthValue || !authData.id || !authData.auth_date || !authData.hash) return null;
    return authData;
  }

  function clearAuthQuery() {
    const url = new URL(window.location.href);
    ["login_token", "login_purpose", "id", "first_name", "last_name", "username", "photo_url", "auth_date", "hash"].forEach((key) =>
      url.searchParams.delete(key),
    );
    window.history?.replaceState?.({}, document.title, url.pathname + url.search + url.hash);
  }

  async function finalizeMagicLogin(loginToken) {
    if (authBusy) return false;
    authBusy = true;
    setAuthStatus("Проверяем вход...");
    try {
      const payload = { token: loginToken };
      const referralParam = readReferralParam();
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi("/auth/email/magic", payload);
      if (response.ok && response.token) {
        setToken(response.token, response.csrf_token);
        clearAuthQuery();
        await loadData();
        return true;
      }
      setAuthStatus("Не удалось подтвердить вход", true);
    } catch {
      setAuthStatus("Не удалось подтвердить вход", true);
    } finally {
      authBusy = false;
    }
    return false;
  }

  async function finalizeTelegramAuth(authData, source = "auth_data") {
    if (authBusy) return false;
    authBusy = true;
    setAuthStatus("Проверяем Telegram...");
    try {
      const payload = source === "init_data" ? { init_data: authData } : { auth_data: authData };
      const referralParam = readReferralParam();
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi("/auth/token", payload);
      if (response.ok && response.token) {
        setToken(response.token, response.csrf_token);
        clearAuthQuery();
        setAuthStatus("");
        await loadData();
        return true;
      }
      setAuthStatus(response.error === "banned" ? "Доступ запрещен" : "Telegram-вход не подтвержден", true);
    } catch {
      setAuthStatus("Telegram-вход сейчас недоступен", true);
    } finally {
      authBusy = false;
    }
    return false;
  }

  async function requestEmailCode() {
    const normalized = email.trim().toLowerCase();
    if (!normalized || !normalized.includes("@")) {
      setAuthStatus("Введите корректный email", true);
      return;
    }
    authBusy = true;
    setAuthStatus("Отправляем код...");
    try {
      const payload = { email: normalized, language: "ru" };
      const referralParam = readReferralParam();
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi("/auth/email/request", payload);
      if (!response.ok) throw response;
      pendingEmail = normalized;
      emailCode = "";
      screen = "code";
      mode = "login";
      setAuthStatus("");
    } catch (error) {
      setAuthStatus(emailError(error, "Не удалось отправить код"), true);
    } finally {
      authBusy = false;
    }
  }

  async function verifyEmailCode() {
    const code = emailCode.replace(/\D/g, "").slice(0, 6);
    if (code.length !== 6) {
      setAuthStatus("Введите 6 цифр из письма", true);
      return;
    }
    authBusy = true;
    setAuthStatus("Проверяем код...");
    try {
      const payload = { email: pendingEmail, code };
      const referralParam = readReferralParam();
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi("/auth/email/verify", payload);
      if (!response.ok || !response.token) throw response;
      setToken(response.token, response.csrf_token);
      await loadData();
      setAuthStatus("");
    } catch (error) {
      setAuthStatus(emailError(error, "Неверный код"), true);
    } finally {
      authBusy = false;
    }
  }

  function emailError(error, fallback) {
    if (error?.error === "rate_limited") return `Повторная отправка через ${error.retry_after || 60} сек.`;
    if (error?.error === "invalid_email") return "Введите корректный email";
    if (error?.error === "expired_code") return "Код устарел";
    if (error?.error === "invalid_code" || error?.error === "too_many_attempts") return "Неверный код";
    return fallback;
  }

  function setAuthStatus(message, isError = false) {
    authStatus = message;
    authIsError = isError;
  }

  async function renderTelegramWidgetWhenNeeded() {
    await tick();
    if (authMode !== "telegram" || !loginTelegramNode) return;
    loginTelegramNode.innerHTML = "";
    if (tg?.initData) return;
    const botUsername = String(CFG.telegramLoginBotUsername || "").trim();
    if (!botUsername) {
      setAuthStatus("Telegram Login Widget не настроен", true);
      return;
    }
    window.onTelegramAuth = async (telegramUser) => {
      await finalizeTelegramAuth(telegramUser, "auth_data");
    };
    appendTelegramLoginWidget(loginTelegramNode, botUsername, "onTelegramAuth", () =>
      setAuthStatus("Telegram Login Widget сейчас недоступен", true),
    );
  }

  function appendTelegramLoginWidget(container, botUsername, callbackName, onUnavailable) {
    const script = document.createElement("script");
    let unavailableShown = false;
    const showUnavailable = () => {
      if (unavailableShown) return;
      unavailableShown = true;
      onUnavailable();
    };
    script.async = true;
    script.src = TELEGRAM_LOGIN_WIDGET_URL;
    script.setAttribute("data-telegram-login", botUsername);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-userpic", "true");
    script.setAttribute("data-request-access", "write");
    script.setAttribute("data-onauth", `${callbackName}(user)`);
    script.onerror = showUnavailable;
    script.onload = () => {
      window.setTimeout(() => {
        if (!container.contains(script) || container.querySelector("iframe")) return;
        showUnavailable();
      }, TELEGRAM_LOGIN_WIDGET_RENDER_TIMEOUT_MS);
    };
    container.appendChild(script);
  }

  async function openTelegramLogin() {
    authMode = "telegram";
    if (tg?.initData) {
      await finalizeTelegramAuth(tg.initData, "init_data");
      return;
    }
    renderTelegramWidgetWhenNeeded();
  }

  async function createPayment() {
    if (!selectedPlan || !selectedMethod || payBusy) return;
    payBusy = true;
    try {
      const response = await api("/payments", {
        method: "POST",
        body: JSON.stringify({ months: selectedPlan.months, method: selectedMethod }),
      });
      if (!response.ok || !response.payment_url) throw response;
      showToast("Платеж создан");
      openExternalLink(response.payment_url);
    } catch (error) {
      showToast(error?.message || "Не удалось создать платеж");
    } finally {
      payBusy = false;
    }
  }

  function openExternalLink(url) {
    if (!url) return;
    if (tg?.openLink) tg.openLink(url);
    else window.open(url, "_blank", "noopener");
  }

  function openConnectLink() {
    const url = subscription?.connect_url || subscription?.config_link;
    if (!url) {
      showToast("Ссылка для подключения пока недоступна");
      return;
    }
    openExternalLink(url);
  }

  async function copyText(value, success = "Скопировано") {
    if (!value) {
      showToast("Пока недоступно");
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      const area = document.createElement("textarea");
      area.value = value;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    showToast(success);
  }

  async function applyPromo() {
    const code = promoCode.trim();
    if (!code) {
      promoStatus = "Введите промокод";
      promoIsError = true;
      return;
    }
    promoBusy = true;
    promoStatus = "";
    try {
      const response = await api("/promo/apply", {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      if (!response.ok) throw response;
      promoCode = "";
      promoStatus = response.end_date_text
        ? `Промокод активирован. Подписка до ${response.end_date_text}`
        : "Промокод активирован";
      promoIsError = false;
      await loadData();
    } catch (error) {
      promoStatus = error?.message || "Не удалось активировать промокод";
      promoIsError = true;
    } finally {
      promoBusy = false;
    }
  }

  async function logout() {
    markManualLogout();
    clearToken();
    try {
      await publicApi("/auth/logout", { keepalive: true });
    } catch {}
    showLogin();
  }

  function showToast(message) {
    toastText = message;
    if (toastTimer) window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      toastText = "";
    }, 2400);
  }

  function goHome() {
    activeTab = "home";
    screen = "home";
  }

  function goInvite() {
    activeTab = "invite";
    screen = "invite";
  }

  function goSettings() {
    activeTab = "settings";
    screen = "settings";
  }

  function methodMeta(method) {
    const id = String(method?.id || "").toLowerCase();
    if (id.includes("yookassa") || id.includes("card")) {
      return { title: method.name || "Карта", note: "Visa, Mastercard", icon: CreditCard };
    }
    if (id.includes("platega") || id.includes("sbp")) {
      return { title: method.name || "СБП", note: "Быстро и удобно", icon: Send };
    }
    if (id.includes("crypto")) {
      return { title: method.name || "Криптовалюта", note: "USDT, BTC, ETH", icon: WalletCards };
    }
    if (id.includes("stars")) {
      return { title: "Telegram Stars", note: "Оплата звездами", icon: Zap };
    }
    return { title: method.name || "Другие способы", note: "ЮMoney, СБП и др.", icon: WalletCards };
  }

  function formatMoney(value, currency = CFG.currency || "RUB") {
    const numeric = Number(value || 0);
    const formatted = Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2);
    const symbol = currency === "RUB" ? "₽" : currency;
    return `${formatted} ${symbol}`;
  }

  function trafficPercent(sub) {
    const used = Number(sub?.traffic_used_bytes || 0);
    const limit = Number(sub?.traffic_limit_bytes || 0);
    if (!limit || limit <= 0) return 100;
    return Math.max(0, Math.min(100, Math.round((used / limit) * 100)));
  }

  function trafficLabel(sub) {
    if (!sub?.traffic_limit_bytes || Number(sub.traffic_limit_bytes) <= 0) return "Безлимитный трафик";
    return `${sub.traffic_used || "0 GB"} из ${sub.traffic_limit || "0 GB"}`;
  }

  function normalizedEmail(value) {
    return String(value || "").trim().toLowerCase();
  }

  function languageName(code) {
    const key = String(code || "").trim().toLowerCase();
    if (!key) return "Русский";
    return LANGUAGE_LABELS[key] || key.toUpperCase();
  }

  function telegramName(profile) {
    const first = String(profile?.first_name || "").trim();
    const last = String(profile?.last_name || "").trim();
    if (first || last) return `${first} ${last}`.trim();
    const username = String(profile?.username || "").trim();
    if (username) return `@${username}`;
    return "Telegram не привязан";
  }

  function bytesToHex(buffer) {
    return Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  async function sha256Hex(value) {
    const data = new TextEncoder().encode(value);
    const hashBuffer = await window.crypto.subtle.digest("SHA-256", data);
    return bytesToHex(hashBuffer);
  }

  async function buildGravatarUrl(emailValue) {
    if (!emailValue || !window.crypto?.subtle) return "";
    try {
      const hash = await sha256Hex(emailValue);
      return `https://www.gravatar.com/avatar/${hash}?d=mp&s=160`;
    } catch {
      return "";
    }
  }

  function tariffIcon(id) {
    if (id === "traffic") return Database;
    if (id === "premium") return Crown;
    return Zap;
  }
</script>

<svelte:head>
  <title>{brandTitle}</title>
</svelte:head>

{#if isPreviewBoard}
  <PreviewBoard config={CFG} mockData={DEV_MOCK.data} />
{:else}
  <div class="app-shell" style={`--accent: ${accent};`}>
    {#if mode === "loading"}
      <div class="loader">
        <div class="brand-mark brand-mark-lg">
          {#if CFG.logoUrl}
            <img src={CFG.logoUrl} alt="" />
          {:else}
            <span>{brandEmoji}</span>
          {/if}
        </div>
        <div>Загрузка...</div>
      </div>
    {:else if mode === "login"}
      <div class="phone-screen auth-screen">
        {#if screen === "code"}
          <header class="screen-head center-title">
            <Button variant="icon" size="icon" onclick={() => (screen = "login")} aria-label="Назад">
              <ArrowLeft size={19} />
            </Button>
            <div>
              <h1>Подтверждение по email</h1>
              <p>Мы отправили код на <strong>{pendingEmail}</strong></p>
            </div>
            <span></span>
          </header>
          <div class="otp-wrap">
            <label class="otp-input-wrap">
              <input
                bind:value={emailCode}
                inputmode="numeric"
                autocomplete="one-time-code"
                maxlength="6"
                aria-label="Код подтверждения"
              />
              <span class="otp-slots" aria-hidden="true">
                {#each Array.from({ length: 6 }) as _, index}
                  <span class:filled={emailCode[index]}>{emailCode[index] || ""}</span>
                {/each}
              </span>
            </label>
            <Button class="wide" onclick={verifyEmailCode} disabled={authBusy}>
              Подтвердить
            </Button>
            {#if authStatus}
              <div class:error={authIsError} class="status-line">{authStatus}</div>
            {/if}
            <button class="link-button" type="button" on:click={requestEmailCode} disabled={authBusy}>
              <RefreshCw size={15} />
              Отправить код повторно
            </button>
          </div>
        {:else}
          <div class="auth-card-wrap">
            <div class="login-brand">
              <div class="brand-mark brand-mark-xl">
                {#if CFG.logoUrl}
                  <img src={CFG.logoUrl} alt="" />
                {:else}
                  <span>{brandEmoji}</span>
                {/if}
              </div>
              <h1>{brandTitle}</h1>
              <p>Войдите в свой аккаунт</p>
            </div>
            <Card class="auth-card">
              <div class="segmented">
                <button class:active={authMode === "email"} type="button" on:click={() => (authMode = "email")}>
                  Email
                </button>
                <button class:active={authMode === "telegram"} type="button" on:click={openTelegramLogin}>
                  Telegram
                </button>
              </div>
              {#if authMode === "email"}
                <div class="auth-pane">
                  <div class="field-label">Вход по email</div>
                  <div class="email-row">
                    <Input bind:value={email} type="email" placeholder="Email" autocomplete="email" />
                    <Button variant="outline" onclick={requestEmailCode} disabled={authBusy}>
                      <Mail size={18} />
                      Код
                    </Button>
                  </div>
                </div>
              {:else}
                <div class="auth-pane">
                  <div class="field-label">Вход через Telegram</div>
                  {#if tg?.initData}
                    <Button variant="telegram" onclick={openTelegramLogin} disabled={authBusy}>
                      <Send size={19} />
                      Войти через Telegram
                    </Button>
                  {:else}
                    <div class="telegram-widget" bind:this={loginTelegramNode}></div>
                  {/if}
                </div>
              {/if}
              {#if authStatus}
                <div class:error={authIsError} class="status-line">{authStatus}</div>
              {/if}
            </Card>
            <div class="auth-bottom">
              Нет аккаунта? <strong>Создать</strong>
            </div>
          </div>
        {/if}
      </div>
    {:else}
      <div class="phone-screen">
        {#if screen === "invite" || screen === "settings"}
          <header class="app-header accent-title">
            <div class="brand-row">
              <div class="brand-mark">
                {#if CFG.logoUrl}
                  <img src={CFG.logoUrl} alt="" />
                {:else}
                  <span>{brandEmoji}</span>
                {/if}
              </div>
              <strong>{brandTitle}</strong>
            </div>
          </header>
        {/if}

        {#if screen === "home"}
          <main class="home-layout">
            <div class="login-brand home-brand">
              <div class="brand-mark brand-mark-xl">
                {#if CFG.logoUrl}
                  <img src={CFG.logoUrl} alt="" />
                {:else}
                  <span>{brandEmoji}</span>
                {/if}
              </div>
              <h1>{brandTitle}</h1>
            </div>

            <div class="home-bottom">
              <Card class="status-card">
                <div class="sub-status">
                  <CheckCircle2 size={23} />
                  <div>
                    <h2>{subscription.active ? "Подписка активна" : "Подписка не активна"}</h2>
                    <p>{subscription.end_date_text ? `до ${subscription.end_date_text}` : subscription.remaining_text}</p>
                  </div>
                </div>
              </Card>

              <Card>
                <div class="traffic-top">
                  <span>Использовано трафика</span>
                  <strong>{trafficLabel(subscription)}</strong>
                </div>
                <div class="progress">
                  <span style={`width: ${trafficPercent(subscription)}%`}></span>
                </div>
                <div class="traffic-percent">{trafficPercent(subscription)}%</div>
              </Card>

              <div class="action-stack">
                <Button class="wide" onclick={openConnectLink}>
                  <Download size={18} />
                  Установить и настроить
                </Button>
                <Button variant="secondary" class="wide" onclick={() => (screen = "payment")}>
                  <RefreshCw size={18} />
                  Продлить
                </Button>
                <Button variant="secondary" class="wide" onclick={() => (screen = "change-tariff")}>
                  <Repeat2 size={18} />
                  Сменить тариф
                </Button>
              </div>
            </div>
          </main>
        {:else if screen === "tariff-select"}
          <main class="content">
            <header class="screen-head">
              <Button variant="icon" size="icon" onclick={goHome} aria-label="Назад">
                <ArrowLeft size={19} />
              </Button>
              <div class="center-copy">
                <h1>Выбор тарифа</h1>
                <p>Экраны тарифов пока сверстаны без подключения</p>
              </div>
              <span></span>
            </header>
            <div class="tariff-list">
              {#each demoTariffs as tariff}
                <button
                  class:active={selectedTariff === tariff.id}
                  class="select-card"
                  type="button"
                  on:click={() => (selectedTariff = tariff.id)}
                >
                  <span class="select-icon">
                    <svelte:component this={tariffIcon(tariff.id)} size={25} />
                  </span>
                  <span>
                    <strong>{tariff.title}</strong>
                    <small>{tariff.caption}</small>
                    <em>{tariff.details}</em>
                  </span>
                  {#if selectedTariff === tariff.id}
                    <CheckCircle2 size={22} />
                  {:else}
                    <Circle size={22} />
                  {/if}
                </button>
              {/each}
            </div>
            <Button class="wide bottom-action" onclick={() => showToast("Тарифы пока не подключены")}>
              Далее
              <ArrowRight size={18} />
            </Button>
          </main>
        {:else if screen === "payment"}
          <main class="content">
            <header class="screen-head">
              <Button variant="icon" size="icon" onclick={goHome} aria-label="Назад">
                <ArrowLeft size={19} />
              </Button>
              <div class="center-copy">
                <h1>Подписка</h1>
                <p>Выберите срок подписки</p>
              </div>
              <span></span>
            </header>
            <div class="period-grid">
              {#each plans as plan}
                <button
                  class:active={selectedPlan?.months === plan.months}
                  class="period-card"
                  type="button"
                  on:click={() => (selectedPlan = plan)}
                >
                  <strong>{plan.title}</strong>
                  <span>{formatMoney(plan.price, plan.currency)}</span>
                  {#if plan.months > 1}
                    <small>{formatMoney(plan.price / plan.months, plan.currency)}/мес</small>
                  {/if}
                  {#if selectedPlan?.months === plan.months}
                    <CheckCircle2 size={18} />
                  {/if}
                </button>
              {/each}
            </div>
            <Card class="total-card">
              <span>Итого<br /><small>К оплате</small></span>
              <strong>{selectedPlan ? formatMoney(selectedPlan.price, selectedPlan.currency) : "..."}</strong>
            </Card>
            <div class="method-grid">
              {#if methods.length}
                {#each methods as method}
                  {@const meta = methodMeta(method)}
                  <button
                    class:active={selectedMethod === method.id}
                    class="method-card"
                    type="button"
                    on:click={() => (selectedMethod = method.id)}
                  >
                    <svelte:component this={meta.icon} size={19} />
                    <span>
                      <strong>{meta.title}</strong>
                      <small>{meta.note}</small>
                    </span>
                  </button>
                {/each}
              {:else}
                <Card class="empty-card">Способы оплаты пока не настроены</Card>
              {/if}
            </div>
            <Button class="wide bottom-action" onclick={createPayment} disabled={!methods.length || payBusy}>
              Оплатить {selectedPlan ? formatMoney(selectedPlan.price, selectedPlan.currency) : ""}
              <LockKeyhole size={17} />
            </Button>
          </main>
        {:else if screen === "traffic-payment"}
          <main class="content">
            <header class="screen-head">
              <Button variant="icon" size="icon" onclick={goHome} aria-label="Назад">
                <ArrowLeft size={19} />
              </Button>
              <div class="center-copy">
                <h1>Трафик</h1>
                <p>Выберите пакет трафика</p>
              </div>
              <span></span>
            </header>
            <div class="period-grid">
              {#each trafficPackages as pack}
                <button
                  class:active={selectedTrafficPackage.gb === pack.gb}
                  class="period-card"
                  type="button"
                  on:click={() => (selectedTrafficPackage = pack)}
                >
                  <strong>{pack.gb} ГБ</strong>
                  <span>{formatMoney(pack.price)}</span>
                  <small>{formatMoney(pack.price / pack.gb)}/ГБ</small>
                  {#if selectedTrafficPackage.gb === pack.gb}
                    <CheckCircle2 size={18} />
                  {/if}
                </button>
              {/each}
            </div>
            <Card class="total-card">
              <span>Итого<br /><small>К оплате</small></span>
              <strong>{formatMoney(selectedTrafficPackage.price)}</strong>
            </Card>
            <div class="method-grid">
              {#each DEV_MOCK.data.payment_methods as method}
                {@const meta = methodMeta(method)}
                <button class="method-card" type="button">
                  <svelte:component this={meta.icon} size={19} />
                  <span>
                    <strong>{meta.title}</strong>
                    <small>{meta.note}</small>
                  </span>
                </button>
              {/each}
            </div>
            <Button class="wide bottom-action" onclick={() => showToast("Пакеты трафика пока не подключены")}>
              Оплатить {formatMoney(selectedTrafficPackage.price)}
              <LockKeyhole size={17} />
            </Button>
          </main>
        {:else if screen === "change-tariff"}
          <main class="content">
            <header class="screen-head">
              <Button variant="icon" size="icon" onclick={goHome} aria-label="Назад">
                <ArrowLeft size={19} />
              </Button>
              <div class="center-copy">
                <h1>Смена тарифа</h1>
                <p>Остаток 12 дней будет пересчитан</p>
              </div>
              <span></span>
            </header>
            <div class="tariff-list compact">
              {#each changeTariffs as tariff}
                <button
                  class:active={selectedChangeTariff === tariff.id}
                  class="select-card"
                  type="button"
                  on:click={() => (selectedChangeTariff = tariff.id)}
                >
                  <span>
                    <strong>{tariff.title}</strong>
                    <small>{tariff.caption}</small>
                  </span>
                  <em>{tariff.recalculation}</em>
                  {#if selectedChangeTariff === tariff.id}
                    <CheckCircle2 size={20} />
                  {:else}
                    <Circle size={20} />
                  {/if}
                </button>
              {/each}
            </div>
            <Button
              class="wide bottom-action"
              onclick={() =>
                selectedChangeTariff === "traffic"
                  ? (confirmTariffOpen = true)
                  : showToast("Оплата смены тарифа пока не подключена")}
            >
              Далее
              <ArrowRight size={18} />
            </Button>
          </main>
        {:else if screen === "invite"}
          <main class="content with-nav">
            <Card>
              <div class="card-label">Ваша реферальная ссылка</div>
              <div class="copy-row">
                <code>{referral.webapp_link || referral.bot_link || "Ссылка пока недоступна"}</code>
                <Button onclick={() => copyText(referral.webapp_link || referral.bot_link, "Ссылка скопирована")}>
                  Копировать
                  <Copy size={17} />
                </Button>
              </div>
            </Card>
            <Card class="bonus-card">
              <Gift size={42} />
              <div>
                <span>Ваш бонус</span>
                <strong>+7 дней за каждого друга</strong>
                <p>Друг получит +3 дня к подписке после регистрации.</p>
              </div>
            </Card>
            <Card>
              <div class="card-label">Промокод</div>
              <div class="copy-row">
                <Input bind:value={promoCode} placeholder="PROMO2026" />
                <Button variant="outline" onclick={applyPromo} disabled={promoBusy}>
                  <Ticket size={17} />
                  Активировать
                </Button>
              </div>
              {#if promoStatus}
                <p class:error={promoIsError} class="status-line">{promoStatus}</p>
              {/if}
            </Card>
          </main>
        {:else if screen === "settings"}
          <main class="content with-nav">
            <Card class="settings-profile">
              <div class="settings-avatar">
                {#if profileAvatarUrl}
                  <img src={profileAvatarUrl} alt="Аватар пользователя" loading="lazy" referrerpolicy="no-referrer" />
                {:else}
                  <UserRound size={30} />
                {/if}
              </div>
              <div class="settings-profile-meta">
                <strong>{telegramProfileName}</strong>
                <small>{profileEmail}</small>
                <small>{profileTelegramId}</small>
              </div>
            </Card>
            <div class="settings-list">
              <button class="settings-row" type="button">
                <Globe2 size={21} />
                <span><strong>Выбор языка</strong><small>{userLanguage}</small></span>
                <ArrowRight size={17} />
              </button>
              <button class="settings-row" type="button">
                <Send size={21} />
                <span><strong>Привязка Telegram</strong><small>{user.telegram_linked ? `@${user.username || "username"}` : "Не привязан"}</small></span>
                <ArrowRight size={17} />
              </button>
              <button class="settings-row" type="button">
                <Mail size={21} />
                <span><strong>Привязка почты</strong><small>{user.email || "Не привязана"}</small></span>
                <ArrowRight size={17} />
              </button>
              <button class="settings-row" type="button" on:click={logout}>
                <UserRound size={21} />
                <span><strong>Выйти</strong><small>Завершить сессию</small></span>
                <ArrowRight size={17} />
              </button>
            </div>
          </main>
        {/if}

        {#if screen === "home" || screen === "invite" || screen === "settings"}
          <nav class="bottom-nav" aria-label="Навигация">
            <button class:active={activeTab === "home"} type="button" on:click={goHome}>
              <Home size={21} />
              <span>Главная</span>
            </button>
            <button class:active={activeTab === "invite"} type="button" on:click={goInvite}>
              <Gift size={21} />
              <span>Пригласить</span>
            </button>
            <button class:active={activeTab === "settings"} type="button" on:click={goSettings}>
              <SettingsIcon size={21} />
              <span>Настройки</span>
            </button>
          </nav>
        {/if}
      </div>
    {/if}

    <Dialog
      open={confirmTariffOpen}
      title="Сменить тариф без доплаты?"
      description="Остаток 12 дней будет пересчитан по новому тарифу."
      onclose={() => (confirmTariffOpen = false)}
    >
      <div class="dialog-actions">
        <Button
          onclick={() => {
            confirmTariffOpen = false;
            showToast("Смена тарифа пока не подключена");
          }}
        >
          Да, сменить
        </Button>
        <Button variant="secondary" onclick={() => (confirmTariffOpen = false)}>Отмена</Button>
      </div>
    </Dialog>

    {#if toastText}
      <div class="toast" role="status">{toastText}</div>
    {/if}
  </div>
{/if}
