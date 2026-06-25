import {
  adminPaymentIdFromPath,
  adminPaymentsUserIdFromPath,
  adminSettingsPathFromPath,
  adminUserIdFromPath,
} from "./routes.js";

type AnyRecord = Record<string, unknown>;

export type AdminPanelPropsInput = {
  adminActiveSection: string;
  api: unknown;
  appFaviconUrl: unknown;
  appFaviconUseCustom: unknown;
  appRepositoryUrl: unknown;
  appVersion: unknown;
  brand: unknown;
  brandTitle: string;
  currentLang: string;
  fallbackAdminSection: string;
  languageBusy: boolean;
  languageOptions: unknown;
  onClose: () => void;
  onLanguageChange: (...args: never[]) => unknown;
  onSectionChange: (...args: never[]) => unknown;
  onSettingsSaved: (...args: never[]) => unknown;
  onTariffsSaved: (...args: never[]) => unknown;
  onThemesSaved: (...args: never[]) => unknown;
  onToast: (text: string) => void;
  onTranslationsSaved: (...args: never[]) => unknown;
  pathname: string;
  routePrefix: string;
  screen: string;
  t: (...args: never[]) => unknown;
};

export function buildAdminPanelProps({
  adminActiveSection,
  api,
  appFaviconUrl,
  appFaviconUseCustom,
  appRepositoryUrl,
  appVersion,
  brand,
  brandTitle,
  currentLang,
  fallbackAdminSection,
  languageBusy,
  languageOptions,
  onClose,
  onLanguageChange,
  onSectionChange,
  onSettingsSaved,
  onTariffsSaved,
  onThemesSaved,
  onToast,
  onTranslationsSaved,
  pathname,
  routePrefix,
  screen,
  t,
}: AdminPanelPropsInput): AnyRecord {
  return {
    api,
    onClose,
    onToast,
    initialSection: screen === "admin" ? adminActiveSection : fallbackAdminSection,
    initialSettingsPath: adminSettingsPathFromPath(pathname, routePrefix),
    initialPaymentId: adminPaymentIdFromPath(pathname, routePrefix),
    initialPaymentUserId: adminPaymentsUserIdFromPath(pathname, routePrefix),
    initialUserId: adminUserIdFromPath(pathname, routePrefix),
    onSectionChange,
    onSettingsSaved,
    onTariffsSaved,
    onThemesSaved,
    onTranslationsSaved,
    routePrefix,
    brandTitle,
    brand,
    appFaviconUrl,
    appFaviconUseCustom,
    appVersion,
    appRepositoryUrl,
    currentLang,
    languageOptions,
    languageBusy,
    onLanguageChange,
    t,
  };
}
