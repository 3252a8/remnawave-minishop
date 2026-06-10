function cloneCatalog(catalog) {
  return JSON.parse(JSON.stringify(catalog || { default_theme: "dark", themes: [] }));
}

import { writable } from "svelte/store";

const HOME_LOGO_SCALE_TOKEN = {
  desktop: "home_logo_scale_desktop",
  mobile: "home_logo_scale_mobile",
};

function normalizeHomeLogoScale(scale) {
  if (String(scale ?? "").trim() === "") scale = 100;
  const numeric = Number(scale);
  return Number.isFinite(numeric) ? Math.min(300, Math.max(50, Math.round(numeric))) : 100;
}

function resolveThemeHomeLogoScale(theme, mode = "desktop") {
  const tokens = theme?.tokens || {};
  const modeKey = HOME_LOGO_SCALE_TOKEN[mode] || HOME_LOGO_SCALE_TOKEN.desktop;
  return normalizeHomeLogoScale(tokens[modeKey] ?? tokens.home_logo_scale ?? 100);
}

export function createThemesStore({ api, onThemesSaved, flash, at }) {
  const state = writable({
    themesCatalog: { default_theme: "dark", themes: [] },
    themesDir: "",
    themesLoading: false,
    themesSaving: false,
  });

  async function loadThemes() {
    state.update((s) => ({ ...s, themesLoading: true }));
    try {
      const data = await api("/admin/themes");
      if (data?.ok) {
        state.update((s) => ({
          ...s,
          themesCatalog: cloneCatalog(data.catalog),
          themesDir: data.themes_dir || "",
        }));
      } else {
        flash(data?.message || data?.error || at("load_failed", {}, "Не удалось загрузить темы"));
      }
    } finally {
      state.update((s) => ({ ...s, themesLoading: false }));
    }
  }

  async function saveThemes(options = {}) {
    const silent = Boolean(options.silent);
    let catalog = null;
    state.update((s) => {
      catalog = cloneCatalog(s.themesCatalog);
      return { ...s, themesSaving: true };
    });
    try {
      const data = await api("/admin/themes", {
        method: "PUT",
        body: JSON.stringify({ catalog }),
      });
      if (data?.ok) {
        state.update((s) => ({
          ...s,
          themesCatalog: cloneCatalog(data.catalog),
          themesDir: data.themes_dir || s.themesDir,
        }));
        if (!silent) flash(at("themes_saved", {}, "Темы сохранены"));
        if (typeof onThemesSaved === "function") await onThemesSaved();
      } else {
        flash(data?.message || data?.error || at("themes_save_failed", {}, "Не удалось сохранить"));
      }
    } finally {
      state.update((s) => ({ ...s, themesSaving: false }));
    }
  }

  async function uploadLogoFile(file) {
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
        return { logoUrl: data.logo_url || "", faviconUrl: data.favicon_url || "" };
      }
      flash(
        data?.message ||
          data?.error ||
          at("appearance_logo_upload_failed", {}, "Не удалось загрузить логотип")
      );
      return null;
    } finally {
      state.update((s) => ({ ...s, themesSaving: false }));
    }
  }

  async function uploadLogoUrl(url) {
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
        return { logoUrl: data.logo_url || "", faviconUrl: data.favicon_url || "" };
      }
      flash(
        data?.message ||
          data?.error ||
          at("appearance_logo_upload_failed", {}, "Не удалось загрузить логотип")
      );
      return null;
    } finally {
      state.update((s) => ({ ...s, themesSaving: false }));
    }
  }

  async function uploadFaviconFile(file) {
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
        return { faviconUrl: data.favicon_url || "", variants: data.variants || {} };
      }
      flash(
        data?.message ||
          data?.error ||
          at("appearance_favicon_upload_failed", {}, "Не удалось загрузить favicon")
      );
      return null;
    } finally {
      state.update((s) => ({ ...s, themesSaving: false }));
    }
  }

  async function uploadFaviconUrl(url) {
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
        return { faviconUrl: data.favicon_url || "", variants: data.variants || {} };
      }
      flash(
        data?.message ||
          data?.error ||
          at("appearance_favicon_upload_failed", {}, "Не удалось загрузить favicon")
      );
      return null;
    } finally {
      state.update((s) => ({ ...s, themesSaving: false }));
    }
  }

  function setCurrentTheme(key) {
    state.update((s) => ({
      ...s,
      themesCatalog: {
        ...s.themesCatalog,
        default_theme: key,
        themes: (s.themesCatalog.themes || []).map((theme) => ({
          ...theme,
          default: theme.key === key,
        })),
      },
    }));
  }

  function togglePrimaryAccent(key, enabled) {
    state.update((s) => ({
      ...s,
      themesCatalog: {
        ...s.themesCatalog,
        themes: (s.themesCatalog.themes || []).map((theme) =>
          theme.key === key ? { ...theme, use_primary_accent: Boolean(enabled) } : theme
        ),
      },
    }));
  }

  function toggleAdminUse(key, enabled) {
    state.update((s) => ({
      ...s,
      themesCatalog: {
        ...s.themesCatalog,
        themes: (s.themesCatalog.themes || []).map((theme) =>
          theme.key === key ? { ...theme, use_in_admin: Boolean(enabled) } : theme
        ),
      },
    }));
  }

  function setThemeAccent(key, accent) {
    state.update((s) => ({
      ...s,
      themesCatalog: {
        ...s.themesCatalog,
        themes: (s.themesCatalog.themes || []).map((theme) =>
          theme.key === key
            ? {
                ...theme,
                tokens: {
                  ...(theme.tokens || {}),
                  accent: String(accent || "").trim() || null,
                },
              }
            : theme
        ),
      },
    }));
  }

  function setThemeHomeLogoScale(key, mode, scale) {
    const normalizedMode = mode === "mobile" ? "mobile" : "desktop";
    const nextScale = normalizeHomeLogoScale(scale);
    state.update((s) => ({
      ...s,
      themesCatalog: {
        ...s.themesCatalog,
        themes: (s.themesCatalog.themes || []).map((theme) => {
          if (theme.key !== key) return theme;
          const desktopScale =
            normalizedMode === "desktop" ? nextScale : resolveThemeHomeLogoScale(theme, "desktop");
          const mobileScale =
            normalizedMode === "mobile" ? nextScale : resolveThemeHomeLogoScale(theme, "mobile");
          return {
            ...theme,
            tokens: {
              ...(theme.tokens || {}),
              home_logo_scale: null,
              home_logo_scale_desktop: desktopScale === 100 ? null : desktopScale,
              home_logo_scale_mobile: mobileScale === 100 ? null : mobileScale,
            },
          };
        }),
      },
    }));
  }

  return {
    subscribe: state.subscribe,
    loadThemes,
    saveThemes,
    setCurrentTheme,
    setThemeAccent,
    setThemeHomeLogoScale,
    resolveThemeHomeLogoScale,
    togglePrimaryAccent,
    toggleAdminUse,
    uploadLogoFile,
    uploadLogoUrl,
    uploadFaviconFile,
    uploadFaviconUrl,
  };
}
