import { computeAccountView } from "./accountView.js";
import { computeAppDataView } from "./appDataView.js";
import { computeBillingView } from "./billingView.js";
import { computeLanguageView } from "./languageView.js";
import { computeTelegramLoginView } from "./telegramLoginView.js";
import { computeThemeView } from "./themeView.js";

type AnyRecord = Record<string, any>;
type Translate = (key: string) => string;

export type AppShellViewInput = {
  authBusy: boolean;
  authStatus: string;
  cfg: AnyRecord;
  data: AnyRecord | null;
  emailAvatarUrl: string;
  fallbackBrandTitle: string;
  guestLanguage: string;
  hasTelegramLaunchParams: () => boolean;
  i18nMessages: AnyRecord;
  isDemoAuthMock: () => boolean;
  languageName: (language: string) => string;
  mockData: AnyRecord;
  mockEnabled: boolean;
  normalizeLangCode: (language: string) => string;
  readTelegramMiniAppInitDataFromLocation: () => string;
  screen: string;
  selectedTariffKey: string;
  telegramLoginBusy: boolean;
  telegramSdkStatus: string;
  tg: { initData?: string } | null;
  themePreviewDraft: AnyRecord | null;
  themePreviewKey: string;
  topupUnlockPercent: number;
  t: Translate;
};

export function computeAppShellView({
  authBusy,
  authStatus,
  cfg,
  data,
  emailAvatarUrl,
  fallbackBrandTitle,
  guestLanguage,
  hasTelegramLaunchParams,
  i18nMessages,
  isDemoAuthMock,
  languageName,
  mockData,
  mockEnabled,
  normalizeLangCode,
  readTelegramMiniAppInitDataFromLocation,
  screen,
  selectedTariffKey,
  telegramLoginBusy,
  telegramSdkStatus,
  tg,
  themePreviewDraft,
  themePreviewKey,
  topupUnlockPercent,
  t,
}: AppShellViewInput) {
  const appDataView = computeAppDataView({
    cfg,
    data,
    fallbackBrandTitle,
    mockData,
  });
  const user = (data?.user || {}) as AnyRecord;
  const billingView = computeBillingView({
    appSettings: appDataView.appSettings,
    plans: appDataView.plans,
    selectedTariffKey,
    subscription: appDataView.subscription,
    topupUnlockPercent,
  });
  const themeView = computeThemeView({
    themePreviewDraft,
    themePreviewKey,
    data,
    user,
    screen,
    cfgThemesCatalog: cfg.themesCatalog,
    primaryColor: cfg.primaryColor,
  });
  const isAdmin = Boolean(user?.is_admin);
  const currentLang = normalizeLangCode(
    user?.language_code || guestLanguage || cfg.language || "ru"
  );
  const languageView = computeLanguageView({
    cfgLanguages: cfg.languages,
    currentLang,
    i18nMessages,
  });
  const accountView = computeAccountView({
    appSettings: appDataView.appSettings,
    cfg,
    emailAuthEnabled: appDataView.emailAuthEnabled,
    emailAvatarUrl,
    t,
    user,
  });
  const telegramLoginBotId = Number(cfg.telegramLoginBotId || 0);
  const telegramOAuthClientId = Number(cfg.telegramOAuthClientId || telegramLoginBotId || 0);
  const telegramMiniAppInitData = tg?.initData || readTelegramMiniAppInitDataFromLocation();
  const telegramMiniAppAuthAvailable = Boolean(telegramMiniAppInitData);
  const telegramMiniAppContext = hasTelegramLaunchParams();
  const demoAuthLogin = mockEnabled && isDemoAuthMock();
  const telegramLoginView = computeTelegramLoginView({
    authBusy,
    authStatus,
    demoAuthLogin,
    telegramLoginBusy,
    telegramMiniAppAuthAvailable,
    telegramOAuthClientId,
    telegramSdkStatus,
    t,
  });

  return {
    accountView,
    appDataView,
    billingView,
    currentLang,
    demoAuthLogin,
    isAdmin,
    languageView,
    telegramLoginBotId,
    telegramOAuthClientId,
    telegramMiniAppAuthAvailable,
    telegramMiniAppContext,
    telegramMiniAppInitData,
    telegramLoginView,
    themeView,
    user,
    userLanguage: languageName(currentLang),
  };
}

export type AppShellView = ReturnType<typeof computeAppShellView>;
