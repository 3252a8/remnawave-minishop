import { mount } from "svelte";

import App from "./App.svelte";
import PreviewBoard from "./PreviewBoard.svelte";
import { mockApi } from "./lib/webapp/mockApi.js";
import { DEV_MOCK, applyPreviewMock } from "./lib/webapp/previewMock.js";
import "./styles.css";

const RUNTIME_BASE = "/demo/runtime";
const DEFAULT_FAVICON_DIGEST = "19b2a242e5b7bc2d";
const DEMO_HOME_LOGO_SCALE = 68;

function runtimePath(path) {
  return `${RUNTIME_BASE}/${String(path || "").replace(/^\/+/, "")}`;
}

function copyThemeAssets(catalog) {
  const themes = catalog?.themes || [];
  for (const theme of themes) {
    const cssFile = String(theme?.css_file || "").trim();
    if (!theme?.key || !cssFile || cssFile.startsWith("/") || /^(?:https?:)?\/\//i.test(cssFile)) {
      continue;
    }
    theme.css_file = runtimePath(`themes/${theme.key}/${cssFile}`);
  }
}

function applyDemoThemeTokens(catalog) {
  const themes = catalog?.themes || [];
  for (const theme of themes) {
    theme.tokens = theme.tokens || {};
    const logoScaleKeys = ["home_logo_scale_desktop", "home_logo_scale_mobile"];
    for (const key of ["home_logo_scale", ...logoScaleKeys]) {
      if (key !== "home_logo_scale" && !(key in theme.tokens)) continue;
      const currentScale = Number(theme.tokens[key]);
      if (!Number.isFinite(currentScale) || currentScale > DEMO_HOME_LOGO_SCALE) {
        theme.tokens[key] = DEMO_HOME_LOGO_SCALE;
      }
    }
  }
}

async function loadInstallGuidesConfig() {
  const response = await fetch(runtimePath("subscription-guides-config.json"), {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`demo_install_guides_config_load_failed:${response.status}`);
  }
  const config = await response.json();
  DEV_MOCK.data.settings.subscription_guides_enabled = true;
  DEV_MOCK.data.subscription_guides = {
    ...DEV_MOCK.data.subscription_guides,
    enabled: true,
    config,
  };
}

function prepareMockConfig() {
  const logoUrl = runtimePath("default-brand/default-logo.webp");
  const faviconUrl = runtimePath(`default-brand/favicons/${DEFAULT_FAVICON_DIGEST}/icon-180.png`);
  DEV_MOCK.config.logoUrl = logoUrl;
  DEV_MOCK.config.faviconUrl = faviconUrl;
  DEV_MOCK.config.languages = (DEV_MOCK.config.languages || []).filter(
    (item) => item?.code !== "uk"
  );
  DEV_MOCK.config.adminJsAsset = runtimePath("subscription_webapp_admin.js");
  DEV_MOCK.config.adminCssAsset = runtimePath("subscription_webapp_admin.css");
  DEV_MOCK.config.appVersion = "demo";
  DEV_MOCK.config.apiBase = "/api";
  applyDemoThemeTokens(DEV_MOCK.config.themesCatalog);
  applyDemoThemeTokens(DEV_MOCK.data.themes_catalog);
  copyThemeAssets(DEV_MOCK.config.themesCatalog);
  copyThemeAssets(DEV_MOCK.data.themes_catalog);
}

function parentSearchParams() {
  try {
    if (window.parent === window) return null;
    return new URLSearchParams(window.parent.location.search);
  } catch (_error) {
    return null;
  }
}

async function bootstrap() {
  const params = new URLSearchParams(window.location.search);
  const parentParams = parentSearchParams();
  applyPreviewMock(params.get("mock") || parentParams?.get("mock"));
  prepareMockConfig();
  try {
    await loadInstallGuidesConfig();
  } catch (error) {
    console.warn(error);
  }

  const target = document.getElementById("app");
  if (target) {
    target.replaceChildren();
    mount(App, {
      target,
      props: {
        mockRuntime: {
          source: DEV_MOCK,
          applyPreviewMock: () => {},
          mockApi,
          PreviewBoard,
          docsDemo: true,
        },
      },
    });
  }
}

void bootstrap();
