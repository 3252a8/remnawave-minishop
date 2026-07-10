import { mount } from "svelte";

import App from "./App.svelte";
import { buildApiUrl } from "./lib/webapp/publicApi";
import "./styles.css";

const PUBLIC_INSTALL_PRELOAD_KEY = "__RW_PUBLIC_INSTALL_PRELOAD__";
const BOOTSTRAP_TIMEOUT_MS = 4000;

type PublicInstallPreload = {
  path: string;
  promise: Promise<unknown>;
};

function publicInstallTokenFromPath(pathname: string = window.location.pathname): string {
  const match = String(pathname || "").match(/^\/s\/([a-f0-9]{32})\/?$/i);
  return match ? match[1].toLowerCase() : "";
}

function startPublicInstallPreload(): PublicInstallPreload | null {
  const shareToken = publicInstallTokenFromPath();
  if (!shareToken) return null;
  const path = `/subscription-guides/public/${encodeURIComponent(shareToken)}`;
  const promise = fetch(buildApiUrl(path), {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  })
    .then((response) => (response.ok ? response.json() : null))
    .catch(() => null);
  const preload: PublicInstallPreload = { path, promise };
  (window as unknown as Record<string, unknown>)[PUBLIC_INSTALL_PRELOAD_KEY] = preload;
  return preload;
}

async function loadBootstrap(): Promise<void> {
  if (document.getElementById("webapp-config")) return;
  const controller = typeof AbortController === "undefined" ? null : new AbortController();
  let timedOut = false;
  let timeoutId: ReturnType<typeof window.setTimeout> | null = null;
  const timeout = new Promise<void>((resolve) => {
    timeoutId = window.setTimeout(() => {
      timedOut = true;
      if (controller) controller.abort();
      resolve();
    }, BOOTSTRAP_TIMEOUT_MS);
  });
  const bootstrap = (async () => {
    const response = await fetch(buildApiUrl("/bootstrap?i18n_scope=webapp"), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      signal: controller?.signal,
    });
    if (!response.ok || timedOut) return;
    const payload: { config?: unknown; i18n?: unknown } = await response.json();
    if (timedOut) return;
    for (const [id, value] of [
      ["webapp-config", payload.config],
      ["i18n", payload.i18n],
    ] as const) {
      const script = document.createElement("script");
      script.id = String(id);
      script.type = "application/json";
      script.textContent = JSON.stringify(value || {});
      document.head.appendChild(script);
    }
  })().catch((_error) => {
    void _error;
  });
  try {
    await Promise.race([bootstrap, timeout]);
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
}

const target = document.getElementById("app");

if (target) {
  startPublicInstallPreload();
  loadBootstrap().finally(() => {
    target.replaceChildren();
    mount(App, { target });
  });
}
