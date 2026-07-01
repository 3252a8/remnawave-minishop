import type { Component } from "svelte";

import type { AppDataView } from "./appDataView";
import type {
  WebappBillingAction,
  WebappBillingPlan,
  WebappBillingTarget,
  WebappData,
  WebappRecord,
} from "./domainTypes";
import { recordArrayField, recordField, recordOrNull, stringField } from "./domainTypes";
import type { InstallGuideRecord } from "./installGuideRuntime";
import type { LanguageOption } from "./languageView";
import type {
  BootstrapResponse,
  DevicesResponse,
  DeviceTopupOptionsResponse,
  MeResponse,
  MockApi,
  TariffChangeOptionsResponse,
  TariffTopupOptionsResponse,
  TrialActivateResponse,
} from "./publicApi";
import type { BillingPlan, PaymentMethod, TariffCatalogEntry } from "./tariffs";

export type {
  WebappBillingAction,
  WebappBillingPlan,
  WebappBillingTarget,
  WebappData,
  WebappRecord,
} from "./domainTypes";
export type { LanguageOption } from "./languageView";
export type { BillingPlan, PaymentMethod, TariffCatalogEntry } from "./tariffs";

export type Translate = (
  key: string,
  params?: Record<string, unknown>,
  fallback?: string
) => string;
export type VoidAction = () => void;
export type StringAction = (value: string) => void;
export type OpenLinkAction = (url: string) => void;
export type CopyTextAction = (text: string, message?: string) => Promise<void>;
export type BooleanAction = (value: boolean) => void;
export type TermUnitLabel = (value: number, unit: "day" | "month") => string;

type MeOkResponse = Extract<MeResponse, { ok: true }>;

export type UserProfile = MeOkResponse["user"] & WebappRecord;
export type SubscriptionView = MeOkResponse["subscription"] & BillingPlan & WebappRecord;
export type BrandConfig = WebappRecord & {
  faviconUrl?: string | null;
  logoUrl?: string | null;
  title?: string | null;
};
export type WebappConfig = BootstrapResponse["config"] &
  BrandConfig & {
    adminCssAsset?: unknown;
    adminJsAsset?: unknown;
    apiBase?: string;
    appRepositoryUrl?: unknown;
    appVersion?: unknown;
    emailAuthEnabled?: unknown;
    faviconUseCustom?: unknown;
    language?: string;
    languages?: LanguageOption[] | unknown[];
    themePreviewKey?: unknown;
  };
export type AppSettings = MeOkResponse["settings"] & WebappRecord;
export type ReferralState = MeOkResponse["referral"] & WebappRecord;
export type ReferralBonusDetail = NonNullable<ReferralState["bonus_details"]>[number] &
  WebappRecord;
export type DevicesData = DevicesResponse & WebappRecord;
export type DeviceView = NonNullable<DevicesData["devices"]>[number] & WebappRecord;
export type TrialActivationResult = TrialActivateResponse & WebappRecord;
export type BillingOptionsResponse = TariffTopupOptionsResponse & WebappRecord;
export type DeviceTopupOptions = DeviceTopupOptionsResponse & WebappRecord;
export type TariffChangeOptions = TariffChangeOptionsResponse & WebappRecord;
export type TariffChangeTarget = NonNullable<TariffChangeOptions["targets"]>[number] &
  WebappBillingTarget &
  WebappRecord;
export type TariffChangeAction = NonNullable<TariffChangeTarget["actions"]>[number] &
  WebappBillingAction &
  BillingPlan;

export type PlanView = BillingPlan;
export type PaymentMethodView = PaymentMethod;
export type TariffView = TariffCatalogEntry;

export type InstallLocalizedValue = string | Record<string, string | undefined>;
export type InstallGuideButton = InstallGuideRecord & {
  link?: unknown;
  text?: InstallLocalizedValue;
  type?: string;
};
export type InstallGuideBlock = InstallGuideRecord & {
  buttons?: InstallGuideButton[];
  description?: InstallLocalizedValue;
  svgIconColor?: unknown;
  svgIconKey?: unknown;
  title?: InstallLocalizedValue;
};
export type InstallGuideApp = InstallGuideRecord & {
  blocks?: InstallGuideBlock[];
  featured?: boolean;
  name?: string;
  svgIconKey?: unknown;
};
export type InstallGuidePlatform = InstallGuideRecord & {
  apps?: InstallGuideApp[];
  displayName?: InstallLocalizedValue;
  key: string;
  svgIconKey?: unknown;
};
export type InstallGuidesConfig = InstallGuideRecord & {
  baseTranslations?: InstallGuideRecord;
  platforms?: Record<string, InstallGuidePlatform>;
  svgLibrary?: Record<string, string>;
};

export type WebappMockSource = WebappRecord & {
  config?: WebappConfig;
  data?: WebappData;
};
export type PreviewBoardComponent = Component<{
  config: WebappConfig;
  mockData: WebappData;
}>;
export type WebappMockRuntime = WebappRecord & {
  PreviewBoard?: PreviewBoardComponent | null;
  applyPreviewMock?: (mockKey: string | null) => void;
  docsDemo?: boolean;
  mockApi?: MockApi | null;
  source?: WebappMockSource;
};
export type AdminPanelProps = Record<string, unknown>;
export type AppDataViewSnapshot = AppDataView;

export function isWebappRecord(value: unknown): value is WebappRecord {
  return Boolean(recordOrNull(value));
}

export function asWebappRecord(value: unknown): WebappRecord {
  return recordField(value);
}

export function asWebappRecordOrNull(value: unknown): WebappRecord | null {
  return recordOrNull(value);
}

export function asWebappRecordArray<T extends WebappRecord = WebappRecord>(value: unknown): T[] {
  return recordArrayField(value) as T[];
}

export function asString(value: unknown): string {
  return stringField(value);
}

export function asInstallGuidesConfig(value: unknown): InstallGuidesConfig | null {
  const record = recordOrNull(value);
  return record ? (record as InstallGuidesConfig) : null;
}

export function installPlatformsFromConfig(
  config: InstallGuidesConfig | null
): InstallGuidePlatform[] {
  const platforms = recordField(config?.platforms);
  return Object.entries(platforms)
    .map(([key, platform]) => {
      const platformRecord = recordOrNull(platform);
      return platformRecord ? ({ key, ...platformRecord } as InstallGuidePlatform) : null;
    })
    .filter(
      (platform): platform is InstallGuidePlatform =>
        Boolean(platform && Array.isArray(platform.apps) && platform.apps.length)
    );
}
