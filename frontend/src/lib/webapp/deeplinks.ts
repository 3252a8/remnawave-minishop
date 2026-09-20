import { normalizedEmail } from "./formatters.js";
import { CHECKOUT_PATH, PLANS_PATH, stripRoutePrefix, withRoutePrefix } from "./routes.js";

export type RenewalDeeplink = {
  tariffKey: string;
};

export type CheckoutAddonPreset = {
  deviceTotal: number | null;
  premiumLimitGb: number | null;
  regularLimitGb: number | null;
};

export type CheckoutDeeplink = {
  accessCode?: string;
  addons: CheckoutAddonPreset;
  months: number | null;
  plan: string;
};

type CheckoutLocationInput = {
  hash?: string;
  pathname?: string;
  search?: string;
  telegramStartParam?: string;
};

type CheckoutUrlInput = {
  accessCode?: string;
  origin: string;
  plan: string;
  routePrefix?: string;
};

const CHECKOUT_QUERY_KEYS = [
  "plan",
  "months",
  "period",
  "devices",
  "traffic",
  "traffic_gb",
  "regular_limit_gb",
  "premium",
  "premium_gb",
  "premium_limit_gb",
] as const;

const CHECKOUT_START_PARAM_KEYS = ["startapp", "start_param", "tgWebAppStartParam"] as const;

type TelegramWindow = Window & {
  Telegram?: {
    WebApp?: {
      initDataUnsafe?: {
        start_param?: string;
      };
    };
  };
};

export function currentSearchParams() {
  return new URLSearchParams(window.location.search);
}

export function readEmailCodeLoginDeeplink() {
  const params = currentSearchParams();
  if (params.get("login") !== "email_code") return null;
  const emailHint = normalizedEmail(params.get("login_email") || "");
  if (!emailHint || !emailHint.includes("@")) return null;
  return emailHint;
}

export function hasEmailCodeLoginDeeplink() {
  return Boolean(readEmailCodeLoginDeeplink());
}

export function readRenewalDeeplink(): RenewalDeeplink | null {
  const params = currentSearchParams();
  const shouldRenew = params.get("after_login") === "renew" || params.get("renew") === "1";
  if (!shouldRenew) return null;
  return {
    tariffKey: String(params.get("renew_tariff") || "").trim(),
  };
}

export function stripRenewalLoginQueryFromUrl() {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  const keys = ["login", "login_email", "after_login", "renew", "renew_tariff"];
  const changed = keys.some((key) => url.searchParams.has(key));
  if (!changed) return;
  for (const key of keys) url.searchParams.delete(key);
  const search = url.searchParams.toString();
  window.history.replaceState(null, "", `${url.pathname}${search ? `?${search}` : ""}${url.hash}`);
}

function telegramStartParam(): string {
  if (typeof window === "undefined") return "";
  return (
    ((window as TelegramWindow).Telegram?.WebApp?.initDataUnsafe?.start_param as string | undefined)
      ?.trim()
      .toString() || ""
  );
}

function finiteNonNegative(value: string | null): number | null {
  if (value == null || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function firstParam(params: URLSearchParams, keys: readonly string[]): string | null {
  for (const key of keys) {
    if (params.has(key)) return params.get(key);
  }
  return null;
}

function checkoutHashParams(hash: string): { checkout: boolean; params: URLSearchParams } {
  const normalized = String(hash || "")
    .replace(/^#/, "")
    .trim();
  if (!normalized) return { checkout: false, params: new URLSearchParams() };
  const [pathPart, queryPart = ""] = normalized.split("?", 2);
  const path = `/${pathPart}`
    .replace(/\/{2,}/g, "/")
    .replace(/\/+$/, "")
    .toLowerCase();
  return {
    checkout: path === "/checkout",
    params: new URLSearchParams(queryPart),
  };
}

function parseCheckoutStartParam(value: string | null): CheckoutDeeplink | null {
  const raw = String(value || "").trim();
  if (!/^plan_/i.test(raw)) return null;
  const [planPart, ...optionParts] = raw.slice("plan_".length).split("__");
  const plan = planPart.trim();
  if (!plan) return null;
  const options = new Map<string, string>();
  for (const part of optionParts) {
    const separator = part.indexOf("_");
    if (separator <= 0) continue;
    options.set(part.slice(0, separator).toLowerCase(), part.slice(separator + 1));
  }
  return {
    accessCode: "",
    plan,
    months: finiteNonNegative(options.get("months") || options.get("period") || null),
    addons: {
      deviceTotal: finiteNonNegative(options.get("devices") || null),
      regularLimitGb: finiteNonNegative(options.get("traffic") || null),
      premiumLimitGb: finiteNonNegative(options.get("premium") || null),
    },
  };
}

export function isCheckoutStartParam(value: unknown): boolean {
  return Boolean(parseCheckoutStartParam(String(value || "")));
}

export function parseCheckoutDeeplink({
  hash = "",
  pathname = "",
  search = "",
  telegramStartParam: telegramParam = "",
}: CheckoutLocationInput): CheckoutDeeplink | null {
  const query = new URLSearchParams(search);
  const hashRoute = checkoutHashParams(hash);
  const params = new URLSearchParams(hashRoute.params.toString());
  for (const [key, value] of query.entries()) {
    // Accept links such as `/?plan#/checkout?plan=8`: the empty outer
    // marker must not hide the actual plan stored in the hash route.
    if (value || !params.has(key)) params.set(key, value);
  }

  for (const key of CHECKOUT_START_PARAM_KEYS) {
    const parsed = parseCheckoutStartParam(params.get(key));
    if (parsed) return parsed;
  }
  const telegramParsed = parseCheckoutStartParam(telegramParam);
  if (telegramParsed) return telegramParsed;

  const path = String(pathname || "")
    .replace(/\/+$/, "")
    .toLowerCase();
  const accessMatch = path.match(/\/checkout\/([a-f0-9]{32})$/);
  const checkoutRoute =
    Boolean(accessMatch) ||
    path === "/checkout" ||
    path.endsWith("/checkout") ||
    hashRoute.checkout;
  const hasPlanParam = params.has("plan");
  if (!checkoutRoute && !hasPlanParam) return null;

  return {
    accessCode: accessMatch?.[1] || "",
    plan: String(params.get("plan") || "").trim(),
    months: finiteNonNegative(firstParam(params, ["months", "period"])),
    addons: {
      deviceTotal: finiteNonNegative(firstParam(params, ["devices"])),
      regularLimitGb: finiteNonNegative(
        firstParam(params, ["traffic", "traffic_gb", "regular_limit_gb"])
      ),
      premiumLimitGb: finiteNonNegative(
        firstParam(params, ["premium", "premium_gb", "premium_limit_gb"])
      ),
    },
  };
}

export function buildCheckoutUrl({
  accessCode = "",
  origin,
  plan,
  routePrefix = "",
}: CheckoutUrlInput): string {
  const normalizedOrigin = String(origin || "")
    .trim()
    .replace(/\/+$/, "");
  const normalizedPlan = String(plan || "").trim();
  const normalizedAccessCode = String(accessCode || "")
    .trim()
    .toLowerCase();
  if (!normalizedOrigin || (!normalizedPlan && !/^[a-f0-9]{32}$/.test(normalizedAccessCode))) {
    return "";
  }
  const checkoutPath = /^[a-f0-9]{32}$/.test(normalizedAccessCode)
    ? `${CHECKOUT_PATH}/${normalizedAccessCode}`
    : CHECKOUT_PATH;
  const url = new URL(withRoutePrefix(checkoutPath, routePrefix), `${normalizedOrigin}/`);
  if (normalizedAccessCode) return url.toString();
  url.searchParams.set("plan", normalizedPlan);
  return url.toString();
}

export function readCheckoutDeeplink(): CheckoutDeeplink | null {
  if (typeof window === "undefined") return null;
  return parseCheckoutDeeplink({
    hash: window.location.hash,
    pathname: window.location.pathname,
    search: window.location.search,
    telegramStartParam: telegramStartParam(),
  });
}

export function stripCheckoutDeeplinkFromUrl(): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  for (const key of CHECKOUT_QUERY_KEYS) url.searchParams.delete(key);
  for (const key of CHECKOUT_START_PARAM_KEYS) {
    if (isCheckoutStartParam(url.searchParams.get(key))) url.searchParams.delete(key);
  }
  if (checkoutHashParams(url.hash).checkout) url.hash = "";
  const search = url.searchParams.toString();
  window.history.replaceState(null, "", `${url.pathname}${search ? `?${search}` : ""}${url.hash}`);
}

export function writeCheckoutPlanToUrl(plan: string): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  const normalized = String(plan || "").trim();
  if (normalized) url.searchParams.set("plan", normalized);
  else url.searchParams.delete("plan");
  const search = url.searchParams.toString();
  window.history.replaceState(null, "", `${url.pathname}${search ? `?${search}` : ""}${url.hash}`);
}

function normalizeCheckoutPromoParam(value: string | null): string {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const lower = raw.toLowerCase();
  return lower.startsWith("promo_") ? raw.slice("promo_".length).trim() : raw;
}

/**
 * A start parameter is a promo code only when it says so.
 *
 * The same parameter also carries app routes (`plans`, `invite`, `ticket_7`),
 * and treating one of those as a code made the app open checkout and complain
 * about an invalid promo instead of going where the link pointed.
 */
function startParamPromoCode(value: string | null): string {
  const raw = String(value || "").trim();
  return raw.toLowerCase().startsWith("promo_") ? raw.slice("promo_".length).trim() : "";
}

export function readCheckoutPromoDeeplink(): string {
  const params = currentSearchParams();
  return (
    normalizeCheckoutPromoParam(params.get("promo_code")) ||
    normalizeCheckoutPromoParam(params.get("promo")) ||
    startParamPromoCode(params.get("startapp")) ||
    startParamPromoCode(params.get("start_param")) ||
    startParamPromoCode(params.get("tgWebAppStartParam")) ||
    startParamPromoCode(telegramStartParam())
  );
}

export function stripCheckoutPromoQueryFromUrl() {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  const keys = ["promo", "promo_code", "startapp", "start_param", "tgWebAppStartParam"];
  const changed = keys.some((key) => url.searchParams.has(key));
  if (!changed) return;
  for (const key of keys) url.searchParams.delete(key);
  const search = url.searchParams.toString();
  window.history.replaceState(null, "", `${url.pathname}${search ? `?${search}` : ""}${url.hash}`);
}

/** Marks the checkout route, which opens plan selection over the home screen. */
export function isPlansRoute(pathname: string, routePrefix = ""): boolean {
  return stripRoutePrefix(pathname, routePrefix).toLowerCase().replace(/\/+$/, "") === PLANS_PATH;
}

export function stripTopupQueryFromUrl() {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (!url.searchParams.has("topup")) return;
  url.searchParams.delete("topup");
  const search = url.searchParams.toString();
  window.history.replaceState(null, "", `${url.pathname}${search ? `?${search}` : ""}${url.hash}`);
}
