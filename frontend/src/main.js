import { mount } from "svelte";

import App from "./App.svelte";
import "./styles.css";

const PUBLIC_INSTALL_PRELOAD_KEY = "__RW_PUBLIC_INSTALL_PRELOAD__";
const BOOTSTRAP_TIMEOUT_MS = 4000;

function publicInstallTokenFromPath(pathname = window.location.pathname) {
  const match = String(pathname || "").match(/^\/s\/([a-f0-9]{32})\/?$/i);
  return match ? match[1].toLowerCase() : "";
}

function startPublicInstallPreload() {
  const shareToken = publicInstallTokenFromPath();
  if (!shareToken) return null;
  const path = `/subscription-guides/public/${encodeURIComponent(shareToken)}`;
  const promise = fetch(`/api${path}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  })
    .then((response) => (response.ok ? response.json() : null))
    .catch(() => null);
  const preload = { path, promise };
  window[PUBLIC_INSTALL_PRELOAD_KEY] = preload;
  return preload;
}

async function loadBootstrap() {
  if (document.getElementById("webapp-config")) return;
  const controller = typeof AbortController === "undefined" ? null : new AbortController();
  const timeoutId = controller
    ? window.setTimeout(() => {
        controller.abort();
      }, BOOTSTRAP_TIMEOUT_MS)
    : 0;
  try {
    const response = await fetch("/api/bootstrap?i18n_scope=webapp", {
      credentials: "include",
      headers: { Accept: "application/json" },
      signal: controller?.signal,
    });
    if (!response.ok) return;
    const payload = await response.json();
    for (const [id, value] of [
      ["webapp-config", payload.config],
      ["i18n", payload.i18n],
    ]) {
      const script = document.createElement("script");
      script.id = id;
      script.type = "application/json";
      script.textContent = JSON.stringify(value || {});
      document.head.appendChild(script);
    }
  } catch (_error) {
    void _error;
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
