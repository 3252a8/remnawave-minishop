import { mount } from "svelte";

import App from "./App.svelte";
import NotificationUnsubscribeApp from "./webapp/NotificationUnsubscribeApp.svelte";
import { buildApiUrl } from "./lib/webapp/publicApi";
import "./styles.css";

const PUBLIC_INSTALL_PRELOAD_KEY = "__RW_PUBLIC_INSTALL_PRELOAD__";
const BOOTSTRAP_TIMEOUT_MS = 4000;
const BOOTSTRAP_RETRY_WINDOW_MS = 90_000;

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

async function loadBootstrapOnce(): Promise<"loaded" | "retry" | "fatal"> {
  const controller = typeof AbortController === "undefined" ? null : new AbortController();
  let timedOut = false;
  let timeoutId: ReturnType<typeof window.setTimeout> | null = null;
  const timeout = new Promise<"retry">((resolve) => {
    timeoutId = window.setTimeout(() => {
      timedOut = true;
      if (controller) controller.abort();
      resolve("retry");
    }, BOOTSTRAP_TIMEOUT_MS);
  });
  const bootstrap = (async (): Promise<"loaded" | "retry" | "fatal"> => {
    const response = await fetch(buildApiUrl("/bootstrap?i18n_scope=webapp"), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      signal: controller?.signal,
    });
    if (timedOut) return "retry";
    if (!response.ok) {
      return response.status === 429 || response.status >= 500 ? "retry" : "fatal";
    }
    const payload: { config?: unknown; i18n?: unknown } = await response.json();
    if (timedOut) return "retry";
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
    return "loaded";
  })().catch(() => "retry" as const);
  try {
    return await Promise.race([bootstrap, timeout]);
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
}

async function loadBootstrap(): Promise<void> {
  if (document.getElementById("webapp-config")) return;
  const retryUntil = Date.now() + BOOTSTRAP_RETRY_WINDOW_MS;
  let delay = 1_000;
  while (true) {
    const result = await loadBootstrapOnce();
    if (result !== "retry" || Date.now() + delay >= retryUntil) return;
    await new Promise<void>((resolve) => window.setTimeout(resolve, delay));
    delay = Math.min(delay * 2, 4_000);
  }
}

const target = document.getElementById("app");

if (target) {
  startPublicInstallPreload();
  loadBootstrap().finally(() => {
    target.replaceChildren();
    if (window.location.pathname.replace(/\/$/, "").endsWith("/unsubscribe")) {
      mount(NotificationUnsubscribeApp, { target });
    } else {
      mount(App, { target });
    }
  });
}
