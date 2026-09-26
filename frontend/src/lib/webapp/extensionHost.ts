import type { components } from "$lib/api/openapi.generated";
import { builtApiPath, unwrap, type ApiClient } from "./publicApi";
import { withRoutePrefix } from "./routes";
import { APP_SECTION_PATHS } from "./constants";

export type UserExtensionPlugin = components["schemas"]["ExtensionPluginOut"];
export type UserExtensionView = components["schemas"]["ExtensionViewOut"];
export type UserNavigationItem = { id: string; path: string; label: string; icon: string };
type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

export function extensionPath(owner: string, view: string, prefix = ""): string {
  if (!/^[a-z][a-z0-9-]{1,63}$/.test(owner) || !/^[a-z][a-z0-9-]{1,63}$/.test(view)) {
    throw new Error("invalid_extension_route");
  }
  return withRoutePrefix(`/extensions/${owner}/${view}`, prefix);
}

export function extensionRequestPath(owner: string, path: string): string {
  if (!/^[a-z][a-z0-9-]{1,63}$/.test(owner) || !path.startsWith("/")) {
    throw new Error("invalid_extension_api_path");
  }
  const base = `/api/plugins/${owner}`;
  const url = new URL(base + path, "https://extension.invalid");
  if (
    url.origin !== "https://extension.invalid" ||
    !url.pathname.startsWith(`${base}/`) ||
    /%2f|%5c|%2e/i.test(url.pathname) ||
    path.includes("\\")
  ) {
    throw new Error("invalid_extension_api_path");
  }
  return url.pathname + url.search;
}

export function createExtensionHost(
  client: ApiClient,
  owner: string,
  t: Translate,
  prefix = "",
  ui?: {
    notify: (message: string) => void;
    confirm: (message: string) => Promise<boolean>;
  }
) {
  return Object.freeze({
    version: 1,
    t,
    notify: (message: string) => ui?.notify(message),
    confirm: (message: string) => ui?.confirm(message) ?? Promise.resolve(false),
    appearance: Object.freeze({ version: 1, rootClass: "plugin-host" }),
    back: () => window.history.back(),
    async request(path: string, options: RequestInit = {}) {
      const result = await client.apiUnchecked(extensionRequestPath(owner, path), options);
      if (result.ok !== true) throw result;
      const { ok: _ok, ...data } = result;
      return data;
    },
    navigate(view: string) {
      window.history.pushState(null, "", extensionPath(owner, view, prefix));
      window.dispatchEvent(new PopStateEvent("popstate"));
    },
    navigateSection(section: string) {
      if (
        !Object.hasOwn(APP_SECTION_PATHS, section) ||
        section === "admin" ||
        section === "extensions"
      ) {
        throw new Error("invalid_extension_section");
      }
      const path = APP_SECTION_PATHS[section as keyof typeof APP_SECTION_PATHS];
      window.history.pushState(null, "", withRoutePrefix(path, prefix));
      window.dispatchEvent(new PopStateEvent("popstate"));
    },
    async createOrder(product: string, options: Record<string, unknown>, idempotencyKey: string) {
      if (!/^[a-z][a-z0-9_-]{0,63}$/.test(product)) throw new Error("invalid_extension_product");
      return unwrap(
        await client.api(builtApiPath<"/api/extensions/orders">("/api/extensions/orders"), {
          method: "POST" as const,
          body: JSON.stringify({
            product: `${owner}:${product}`,
            options,
            idempotency_key: idempotencyKey,
          }),
        })
      ).order;
    },
    async checkout(
      orderId: string,
      method: string,
      contact: { payer_email?: string; payer_phone?: string } = {}
    ) {
      return unwrap(
        await client.api(builtApiPath<"/api/extensions/checkout">("/api/extensions/checkout"), {
          method: "POST" as const,
          body: JSON.stringify({ order_id: orderId, method, ...contact }),
        })
      );
    },
    async paymentMethods(orderId: string) {
      return unwrap(
        await client.api(
          builtApiPath<"/api/extensions/payment-methods">(
            `/api/extensions/payment-methods?${new URLSearchParams({ order_id: orderId })}`
          )
        )
      ).methods.map((method) => ({
        ...method,
        label: method.label_key ? t(method.label_key, {}, method.label) : method.label,
      }));
    },
    async orders(cursor = "") {
      return unwrap(
        await client.api(
          builtApiPath<"/api/extensions/orders">(
            `/api/extensions/orders?${new URLSearchParams({ owner, cursor })}`
          )
        )
      ).orders;
    },
    async order(orderId: string, refresh = false) {
      return unwrap(
        await client.api(
          builtApiPath<"/api/extensions/order">(
            `/api/extensions/order?${new URLSearchParams({ order_id: orderId, refresh: String(refresh) })}`
          )
        )
      ).order;
    },
    async resource(provider: string, key: string) {
      if (!/^[a-z][a-z0-9_-]{0,63}$/.test(provider)) throw new Error("invalid_extension_resource");
      return client.apiBlob(
        `/api/extensions/resource?provider=${encodeURIComponent(`${owner}:${provider}`)}&key=${encodeURIComponent(key)}`
      );
    },
  });
}

export type ExtensionHost = ReturnType<typeof createExtensionHost>;
