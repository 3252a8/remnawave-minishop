import { writable, type Writable } from "svelte/store";
import { adminErrorMessage } from "../errors.js";

type ThemeVariant = "dark" | "light";
type ThemeTokens = Record<string, unknown>;
type ThemeEntry = Record<string, unknown> & {
  active_variant?: string | null;
  default?: boolean;
  key?: string;
  tokens?: ThemeTokens | null;
  use_in_admin?: boolean;
  use_primary_accent?: boolean;
  variants?: Record<string, ThemeTokens | null> | null;
};
type ThemeCatalog = {
  default_theme: string;
  themes: ThemeEntry[];
};
type ThemesState = {
  themesCatalog: ThemeCatalog;
  savedThemesCatalog: ThemeCatalog;
  themesDirty: boolean;
  themesDir: string;
  themesLoading: boolean;
  themesSaving: boolean;
};
type AdminApi = (path: string, options?: RequestInit) => Promise<Record<string, unknown>>;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type ThemesStoreOptions = {
  api: AdminApi;
  onThemesSaved?: () => Promise<void> | void;
  flash: (message: string) => void;
  at: TranslateFn;
};
type SaveThemesOptions = { silent?: boolean };
type TokenOptions = { raw?: boolean; variant?: string | null };
type LogoMode = "desktop" | "mobile";
type LogoUploadResult = { logoUrl: string; faviconUrl: string };
type FaviconUploadResult = { faviconUrl: string; variants: Record<string, unknown> };

function asTokenMap(value: unknown): ThemeTokens {
  return value && typeof value === "object" ? { ...(value as ThemeTokens) } : {};
}

function cloneCatalog(catalog: unknown): ThemeCatalog {
  return JSON.parse(JSON.stringify(catalog || { default_theme: "dark", themes: [] }));
}

const HOME_LOGO_SCALE_TOKEN = {
  desktop: "home_logo_scale_desktop",
  mobile: "home_logo_scale_mobile",
} as const;
const HOME_LOGO_SCALE_STEP = 5;
const DEFAULT_THEME_KEY = "dark";
const THEME_VARIANTS = new Set(["dark", "light"]);
const DEFAULT_ADMIN_TOKEN_KEYS = new Set([
  "admin_bg",
  "admin_surface",
  "admin_surface_2",
  "admin_elev",
  "admin_border",
  "admin_border_strong",
  "admin_text",
  "admin_muted",
  "admin_dim",
  "admin_chart_stroke",
  "admin_chart_fill",
]);

function normalizeHomeLogoScale(scale: unknown) {
  if (String(scale ?? "").trim() === "") scale = 100;
  const numeric = Number(scale);
  if (!Number.isFinite(numeric)) return 100;
  const rounded = Math.round(numeric / HOME_LOGO_SCALE_STEP) * HOME_LOGO_SCALE_STEP;
  return Math.min(300, Math.max(50, rounded));
}

function normalizeThemeVariant(variant: unknown): ThemeVariant {
  const value = String(variant || "")
    .trim()
    .toLowerCase();
  return THEME_VARIANTS.has(value) ? (value as ThemeVariant) : "dark";
}

function resolveThemeTokens(theme: ThemeEntry | null | undefined, variant: string | null = null) {
  const base = asTokenMap(theme?.tokens);
  const activeVariant = normalizeThemeVariant(
    variant || theme?.active_variant || base.color_scheme
  );
  const variantTokens =
    theme?.variants?.[activeVariant] && typeof theme.variants[activeVariant] === "object"
      ? asTokenMap(theme.variants[activeVariant])
      : {};
  return { ...base, ...variantTokens };
}

function resolveThemeHomeLogoScale(
  theme: ThemeEntry | null | undefined,
  mode: LogoMode = "desktop",
  variant: string | null = null
) {
  const tokens = resolveThemeTokens(theme, variant);
  const modeKey = HOME_LOGO_SCALE_TOKEN[mode] || HOME_LOGO_SCALE_TOKEN.desktop;
  return normalizeHomeLogoScale(tokens[modeKey] ?? tokens.home_logo_scale ?? 100);
}

function normalizeTokenValue(value: unknown) {
  const text = String(value ?? "").trim();
  return text || null;
}

function normalizeLogoScaleTokens(tokens: unknown): ThemeTokens {
  if (!tokens || typeof tokens !== "object") return {};
  const nextTokens = { ...(tokens as ThemeTokens) };
  const desktopScale = normalizeHomeLogoScale(
    nextTokens.home_logo_scale_desktop ?? nextTokens.home_logo_scale ?? 100
  );
  const mobileScale = normalizeHomeLogoScale(
    nextTokens.home_logo_scale_mobile ?? nextTokens.home_logo_scale ?? 100
  );
  delete nextTokens.home_logo_scale;
  delete nextTokens.home_logo_scale_desktop;
  delete nextTokens.home_logo_scale_mobile;
  if (desktopScale !== 100) nextTokens.home_logo_scale_desktop = desktopScale;
  if (mobileScale !== 100) nextTokens.home_logo_scale_mobile = mobileScale;
  return nextTokens;
}

function normalizeThemeCatalogEntry(theme: ThemeEntry): ThemeEntry {
  if (!theme) return theme;
  const stripTokens = (tokens: unknown): ThemeTokens => {
    if (!tokens || typeof tokens !== "object") return {};
    const nextTokens = { ...(tokens as ThemeTokens) };
    if (theme.key === DEFAULT_THEME_KEY) {
      for (const key of DEFAULT_ADMIN_TOKEN_KEYS) {
        delete nextTokens[key];
      }
    }
    return normalizeLogoScaleTokens(nextTokens);
  };
  const variants = theme.variants && typeof theme.variants === "object" ? theme.variants : {};
  return {
    ...theme,
    tokens: stripTokens(theme.tokens || {}),
    variants: Object.fromEntries(
      Object.entries(variants).map(([variant, tokens]) => [variant, stripTokens(tokens)])
    ) as Record<string, ThemeTokens>,
  };
}

function normalizeThemeCatalog(catalog: unknown): ThemeCatalog {
  const nextCatalog = cloneCatalog(catalog);
  nextCatalog.default_theme = nextCatalog.default_theme || DEFAULT_THEME_KEY;
  nextCatalog.themes = (nextCatalog.themes || []).map(normalizeThemeCatalogEntry);
  return nextCatalog;
}

function catalogFingerprint(catalog: unknown) {
  return JSON.stringify(normalizeThemeCatalog(catalog));
}

function withCatalogState(state: ThemesState, nextCatalog: ThemeCatalog): ThemesState {
  const themesCatalog = normalizeThemeCatalog(nextCatalog);
  const savedThemesCatalog = normalizeThemeCatalog(state.savedThemesCatalog);
  return {
    ...state,
    themesCatalog,
    themesDirty: catalogFingerprint(themesCatalog) !== catalogFingerprint(savedThemesCatalog),
  };
}

function setTokenOnTheme(
  theme: ThemeEntry,
  tokenKey: string,
  value: unknown,
  options: TokenOptions = {}
): ThemeEntry {
  const variant = options.variant ? normalizeThemeVariant(options.variant) : "";
  const nextValue = options.raw === true ? value : normalizeTokenValue(value);
  if (variant && theme.key === DEFAULT_THEME_KEY) {
    return {
      ...theme,
      variants: {
        ...(theme.variants || {}),
        [variant]: {
          ...asTokenMap((theme.variants || {})[variant]),
          [tokenKey]: nextValue,
        },
      },
    };
  }
  return {
    ...theme,
    tokens: {
      ...asTokenMap(theme.tokens),
      [tokenKey]: nextValue,
    },
  };
}

function resetTokenOnTheme(
  theme: ThemeEntry,
  tokenKey: string,
  options: TokenOptions = {}
): ThemeEntry {
  const variant = options.variant ? normalizeThemeVariant(options.variant) : "";
  if (variant && theme.key === DEFAULT_THEME_KEY) {
    const nextVariant = { ...asTokenMap((theme.variants || {})[variant]) };
    delete nextVariant[tokenKey];
    return {
      ...theme,
      variants: {
        ...(theme.variants || {}),
        [variant]: nextVariant,
      },
    };
  }
  const nextTokens = { ...asTokenMap(theme.tokens) };
  delete nextTokens[tokenKey];
  return { ...theme, tokens: nextTokens };
}

function updateThemeInCatalog(
  catalog: ThemeCatalog,
  key: string,
  updater: (theme: ThemeEntry) => ThemeEntry
): ThemeCatalog {
  return {
    ...catalog,
    themes: (catalog.themes || []).map((theme) => (theme.key === key ? updater(theme) : theme)),
  };
}

export function createThemesStore({ api, onThemesSaved, flash, at }: ThemesStoreOptions) {
  const state: Writable<ThemesState> = writable({
    themesCatalog: { default_theme: "dark", themes: [] },
    savedThemesCatalog: { default_theme: "dark", themes: [] },
    themesDirty: false,
    themesDir: "",
    themesLoading: false,
    themesSaving: false,
  });

  async function loadThemes() {
    state.update((s) => ({ ...s, themesLoading: true }));
    try {
      const data = await api("/admin/themes");
      if (data?.ok) {
        const catalog = normalizeThemeCatalog(data.catalog);
        state.update((s) => ({
          ...s,
          themesCatalog: catalog,
          savedThemesCatalog: cloneCatalog(catalog),
          themesDirty: false,
          themesDir: String(data.themes_dir || ""),
        }));
      } else {
        flash(adminErrorMessage(data, at, at("load_failed", {}, "Не удалось загрузить темы")));
      }
    } finally {
      state.update((s) => ({ ...s, themesLoading: false }));
    }
  }

  async function saveThemes(options: SaveThemesOptions = {}) {
    const silent = Boolean(options.silent);
    let catalog: ThemeCatalog = { default_theme: DEFAULT_THEME_KEY, themes: [] };
    state.update((s) => {
      catalog = normalizeThemeCatalog(s.themesCatalog);
      return { ...s, themesCatalog: catalog, themesSaving: true };
    });
    try {
      const data = await api("/admin/themes", {
        method: "PUT",
        body: JSON.stringify({ catalog }),
      });
      if (data?.ok) {
        const savedCatalog = normalizeThemeCatalog(data.catalog);
        state.update((s) => ({
          ...s,
          themesCatalog: savedCatalog,
          savedThemesCatalog: cloneCatalog(savedCatalog),
          themesDirty: false,
          themesDir: String(data.themes_dir || s.themesDir),
        }));
        if (!silent) flash(at("themes_saved", {}, "Темы сохранены"));
        if (typeof onThemesSaved === "function") await onThemesSaved();
      } else {
        flash(adminErrorMessage(data, at, at("themes_save_failed", {}, "Не удалось сохранить")));
      }
    } finally {
      state.update((s) => ({ ...s, themesSaving: false }));
    }
  }

  async function uploadLogoFile(file: File | null): Promise<LogoUploadResult | null> {
    if (!file) return null;
    state.update((s) => ({ ...s, themesSaving: true }));
    try {
      const body = new FormData();
      body.append("file", file);
      const data = await api("/admin/appearance/logo", {
        method: "POST",
        body,
      });
      if (data?.ok) {
        flash(at("appearance_logo_uploaded_pending", {}, "Логотип загружен и применен."));
        return { logoUrl: String(data.logo_url || ""), faviconUrl: String(data.favicon_url || "") };
      }
      flash(
        adminErrorMessage(
          data,
          at,
          at("appearance_logo_upload_failed", {}, "Не удалось загрузить логотип")
        )
      );
      return null;
    } finally {
      state.update((s) => ({ ...s, themesSaving: false }));
    }
  }

  async function uploadLogoUrl(url: string): Promise<LogoUploadResult | null> {
    const sourceUrl = String(url || "").trim();
    if (!sourceUrl) return null;
    state.update((s) => ({ ...s, themesSaving: true }));
    try {
      const data = await api("/admin/appearance/logo", {
        method: "POST",
        body: JSON.stringify({ url: sourceUrl }),
      });
      if (data?.ok) {
        flash(at("appearance_logo_uploaded_pending", {}, "Логотип загружен и применен."));
        return { logoUrl: String(data.logo_url || ""), faviconUrl: String(data.favicon_url || "") };
      }
      flash(
        adminErrorMessage(
          data,
          at,
          at("appearance_logo_upload_failed", {}, "Не удалось загрузить логотип")
        )
      );
      return null;
    } finally {
      state.update((s) => ({ ...s, themesSaving: false }));
    }
  }

  async function uploadFaviconFile(file: File | null): Promise<FaviconUploadResult | null> {
    if (!file) return null;
    state.update((s) => ({ ...s, themesSaving: true }));
    try {
      const body = new FormData();
      body.append("file", file);
      const data = await api("/admin/appearance/favicon", {
        method: "POST",
        body,
      });
      if (data?.ok) {
        flash(at("appearance_favicon_uploaded_pending", {}, "Favicon загружена и применена."));
        return { faviconUrl: String(data.favicon_url || ""), variants: asTokenMap(data.variants) };
      }
      flash(
        adminErrorMessage(
          data,
          at,
          at("appearance_favicon_upload_failed", {}, "Не удалось загрузить favicon")
        )
      );
      return null;
    } finally {
      state.update((s) => ({ ...s, themesSaving: false }));
    }
  }

  async function uploadFaviconUrl(url: string): Promise<FaviconUploadResult | null> {
    const sourceUrl = String(url || "").trim();
    if (!sourceUrl) return null;
    state.update((s) => ({ ...s, themesSaving: true }));
    try {
      const data = await api("/admin/appearance/favicon", {
        method: "POST",
        body: JSON.stringify({ url: sourceUrl }),
      });
      if (data?.ok) {
        flash(at("appearance_favicon_uploaded_pending", {}, "Favicon загружена и применена."));
        return { faviconUrl: String(data.favicon_url || ""), variants: asTokenMap(data.variants) };
      }
      flash(
        adminErrorMessage(
          data,
          at,
          at("appearance_favicon_upload_failed", {}, "Не удалось загрузить favicon")
        )
      );
      return null;
    } finally {
      state.update((s) => ({ ...s, themesSaving: false }));
    }
  }

  function setCurrentTheme(key: string) {
    state.update((s) =>
      withCatalogState(s, {
        ...s.themesCatalog,
        default_theme: key,
        themes: (s.themesCatalog.themes || []).map((theme) => ({
          ...theme,
          default: theme.key === key,
        })),
      })
    );
  }

  function setDefaultThemeVariant(variant: string) {
    const nextVariant = normalizeThemeVariant(variant);
    state.update((s) =>
      withCatalogState(s, {
        ...s.themesCatalog,
        default_theme: DEFAULT_THEME_KEY,
        themes: (s.themesCatalog.themes || []).map((theme) => {
          if (theme.key === DEFAULT_THEME_KEY) {
            return { ...theme, default: true, active_variant: nextVariant };
          }
          return { ...theme, default: false };
        }),
      })
    );
  }

  function togglePrimaryAccent(key: string, enabled: boolean) {
    state.update((s) =>
      withCatalogState(s, {
        ...s.themesCatalog,
        themes: (s.themesCatalog.themes || []).map((theme) =>
          theme.key === key ? { ...theme, use_primary_accent: Boolean(enabled) } : theme
        ),
      })
    );
  }

  function toggleAdminUse(key: string, enabled: boolean) {
    state.update((s) =>
      withCatalogState(s, {
        ...s.themesCatalog,
        themes: (s.themesCatalog.themes || []).map((theme) =>
          theme.key === key ? { ...theme, use_in_admin: Boolean(enabled) } : theme
        ),
      })
    );
  }

  function setThemeAccent(key: string, accent: unknown) {
    setThemeToken(key, "accent", accent);
  }

  function setThemeToken(
    key: string,
    tokenKey: string,
    value: unknown,
    options: TokenOptions = {}
  ) {
    state.update((s) =>
      withCatalogState(
        s,
        updateThemeInCatalog(s.themesCatalog, key, (theme) =>
          setTokenOnTheme(theme, tokenKey, value, options)
        )
      )
    );
  }

  function resetThemeToken(key: string, tokenKey: string, options: TokenOptions = {}) {
    state.update((s) =>
      withCatalogState(
        s,
        updateThemeInCatalog(s.themesCatalog, key, (theme) =>
          resetTokenOnTheme(theme, tokenKey, options)
        )
      )
    );
  }

  function applyThemePreset(key: string, variant: string, tokens: unknown) {
    const normalizedVariant = normalizeThemeVariant(variant);
    const nextTokens = asTokenMap(tokens);
    state.update((s) =>
      withCatalogState(
        s,
        updateThemeInCatalog(s.themesCatalog, key, (theme) => {
          if (theme.key === DEFAULT_THEME_KEY) {
            return {
              ...theme,
              active_variant: normalizedVariant,
              variants: {
                ...(theme.variants || {}),
                [normalizedVariant]: {
                  ...asTokenMap((theme.variants || {})[normalizedVariant]),
                  ...nextTokens,
                },
              },
            };
          }
          return {
            ...theme,
            tokens: {
              ...asTokenMap(theme.tokens),
              ...nextTokens,
            },
          };
        })
      )
    );
  }

  function setThemeHomeLogoScale(key: string, mode: LogoMode, scale: unknown) {
    const normalizedMode = mode === "mobile" ? "mobile" : "desktop";
    const nextScale = normalizeHomeLogoScale(scale);
    state.update((s) =>
      withCatalogState(s, {
        ...s.themesCatalog,
        themes: (s.themesCatalog.themes || []).map((theme) => {
          if (theme.key !== key) return theme;
          const desktopScale =
            normalizedMode === "desktop" ? nextScale : resolveThemeHomeLogoScale(theme, "desktop");
          const mobileScale =
            normalizedMode === "mobile" ? nextScale : resolveThemeHomeLogoScale(theme, "mobile");
          return {
            ...setTokenOnTheme(
              setTokenOnTheme(
                setTokenOnTheme(theme, "home_logo_scale", null, {
                  raw: true,
                  variant: theme.key === DEFAULT_THEME_KEY ? theme.active_variant : null,
                }),
                "home_logo_scale_desktop",
                desktopScale === 100 ? null : desktopScale,
                {
                  raw: true,
                  variant: theme.key === DEFAULT_THEME_KEY ? theme.active_variant : null,
                }
              ),
              "home_logo_scale_mobile",
              mobileScale === 100 ? null : mobileScale,
              { raw: true, variant: theme.key === DEFAULT_THEME_KEY ? theme.active_variant : null }
            ),
          };
        }),
      })
    );
  }

  return {
    subscribe: state.subscribe,
    loadThemes,
    saveThemes,
    setCurrentTheme,
    setDefaultThemeVariant,
    setThemeAccent,
    setThemeToken,
    resetThemeToken,
    applyThemePreset,
    setThemeHomeLogoScale,
    resolveThemeHomeLogoScale,
    resolveThemeTokens,
    togglePrimaryAccent,
    toggleAdminUse,
    uploadLogoFile,
    uploadLogoUrl,
    uploadFaviconFile,
    uploadFaviconUrl,
  };
}
