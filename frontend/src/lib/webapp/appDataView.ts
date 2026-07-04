import { normalizeBrand } from "./browser.js";
import { arrayField, recordArrayField, recordField, type WebappRecord } from "./domainTypes.js";
import type { PaymentMethod } from "./tariffs.js";

export type AppDataViewInput = {
  cfg: WebappRecord;
  data: WebappRecord | null;
  fallbackBrandTitle: string;
  mockData: WebappRecord;
};

export type AppDataView = {
  appSettings: WebappRecord;
  brand: WebappRecord;
  brandTitle: string;
  devicesEnabled: boolean;
  emailAuthEnabled: boolean;
  faviconBrand: WebappRecord;
  installGuidesEnabled: boolean;
  methods: PaymentMethod[];
  plans: WebappRecord[];
  rawEmailAuthEnabled: unknown;
  referral: WebappRecord;
  referralBonusDetails: WebappRecord[];
  referralOneBonusPerReferee: boolean;
  referralWelcomeBonusDays: number;
  subscription: WebappRecord;
  subscriptionPurchaseDescription: string;
  supportEnabled: boolean;
};

export function computeAppDataView({
  cfg,
  data,
  fallbackBrandTitle,
  mockData,
}: AppDataViewInput): AppDataView {
  const mock = recordField(mockData);
  const dataRecord = recordField(data);
  const brandTitle = String(cfg.title || fallbackBrandTitle);
  const brand = normalizeBrand({
    title: brandTitle,
    logoUrl: cfg.logoUrl,
  }) as WebappRecord;
  const faviconBrand = {
    ...brand,
    faviconUrl: String(cfg.faviconUrl || "").trim() || brand.logoUrl,
  };
  const plans = recordArrayField(
    arrayField(dataRecord.plans).length ? dataRecord.plans : mock.plans
  );
  const methods = (
    arrayField(dataRecord.payment_methods).length ? dataRecord.payment_methods : []
  ) as PaymentMethod[];
  const appSettings: WebappRecord = {
    ...recordField(dataRecord.settings || mock.settings),
    home_brand_visible: cfg.homeBrandVisible !== false,
    tariff_change_visible: cfg.tariffChangeVisible !== false,
  };
  const rawEmailAuthEnabled =
    recordField(dataRecord.settings).email_auth_enabled ??
    appSettings.email_auth_enabled ??
    cfg.emailAuthEnabled;
  const emailAuthEnabled = rawEmailAuthEnabled !== false && rawEmailAuthEnabled !== "false";
  const subscription = recordField(dataRecord.subscription || mock.subscription);
  const referral = recordField(dataRecord.referral || mock.referral);

  return {
    appSettings,
    brand,
    brandTitle,
    devicesEnabled: Boolean(appSettings.my_devices_enabled),
    emailAuthEnabled,
    faviconBrand,
    installGuidesEnabled: Boolean(appSettings.subscription_guides_enabled),
    methods,
    plans,
    rawEmailAuthEnabled,
    referral,
    referralBonusDetails: recordArrayField(referral.bonus_details),
    referralOneBonusPerReferee: Boolean(referral.one_bonus_per_referee),
    referralWelcomeBonusDays: Math.max(0, Number(referral.welcome_bonus_days || 0)),
    subscription,
    subscriptionPurchaseDescription: String(
      appSettings.subscription_purchase_description || ""
    ).trim(),
    supportEnabled: Boolean(appSettings.support_tickets_enabled ?? true),
  };
}
