export type PreviewThemeTokens = Record<string, unknown>;

export type PreviewTheme = {
  key: string;
  names?: Record<string, string>;
  enabled?: boolean;
  default?: boolean;
  hidden?: boolean;
  active_variant?: string;
  variant_alias_for?: string;
  css_file?: string;
  assets_version?: number;
  tokens?: PreviewThemeTokens;
  variants?: Record<string, PreviewThemeTokens>;
};

export type PreviewThemesCatalog = {
  default_theme: string;
  themes: PreviewTheme[];
};

export type PreviewMockConfig = Record<string, unknown> & {
  language: string;
  languages: { code: string; label: string; flag: string; base?: boolean }[];
  themesCatalog: PreviewThemesCatalog;
  userThemeModeEnabled: boolean;
};

export type PreviewMockData = Record<string, unknown> & {
  ok: boolean;
  user: Record<string, unknown>;
  auth_demo: Record<string, unknown>;
  subscription: Record<string, unknown>;
  subscription_guides: Record<string, unknown>;
  devices: Record<string, unknown>;
  plans: Record<string, unknown>[];
  payment_methods: Record<string, unknown>[];
  referral: Record<string, unknown>;
  themes_catalog: PreviewThemesCatalog;
  settings: Record<string, unknown>;
  tariff_change_options?: Record<string, unknown>;
  topup_options?: Record<string, unknown>;
  device_topup_options?: Record<string, unknown>;
};

export type PreviewMock = {
  config: PreviewMockConfig;
  data: PreviewMockData;
};
