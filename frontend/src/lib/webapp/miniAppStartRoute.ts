import { APP_SECTION_PATHS } from "./constants";
import { isCheckoutStartParam } from "./deeplinks.js";
import { extensionLaunchPath } from "./launchParams.js";
import { CHECKOUT_PATH, PLANS_PATH } from "./routes.js";

const START_PARAM_KEYS = ["tgWebAppStartParam", "startapp", "start_param"] as const;

/**
 * App screens a start parameter may open.
 *
 * ``plans`` is handled separately because checkout is a modal over home
 * rather than a screen. The admin panel is deliberately absent: a bare
 * section payload travels in links authored for customers, and admin deep
 * links keep their own `admin_*` prefixes.
 */
const { admin: _admin, ...CUSTOMER_PATHS } = APP_SECTION_PATHS;
const PAGE_PATHS = {
  ...CUSTOMER_PATHS,
  plans: PLANS_PATH,
  ref: "/invite/referrals",
  gifts: "/invite/gifts",
  codes: "/invite/codes",
  "support-new": "/support/new",
  "partner-links": "/partner/links",
  "partner-balance": "/partner/balance",
  "partner-clients": "/partner/clients",
  "partner-commissions": "/partner/commissions",
  "partner-withdrawals": "/partner/withdrawals",
};

export function miniAppPathFromStartParam(value: unknown): string | null {
  const startParam = String(value || "").trim();
  if (isCheckoutStartParam(startParam)) return CHECKOUT_PATH;
  const adminTicket = startParam.match(/^admin_ticket_(\d+)$/i);
  if (adminTicket) return `/admin/support/${adminTicket[1]}`;

  const adminUser = startParam.match(/^admin_user_(-?\d+|ms_[0-9a-f]{32})$/i);
  if (adminUser) return `/admin/users/${adminUser[1]}`;

  const supportTicket = startParam.match(/^ticket_(\d+)$/i);
  if (supportTicket) return `/support/${supportTicket[1]}`;

  const section = startParam.toLowerCase();
  if (section.startsWith("page_")) {
    const page = section.slice(5);
    if (Object.hasOwn(PAGE_PATHS, page)) {
      return PAGE_PATHS[page as keyof typeof PAGE_PATHS];
    }
  }
  if (section === "plans") return PLANS_PATH;
  if (Object.hasOwn(CUSTOMER_PATHS, section)) {
    return CUSTOMER_PATHS[section as keyof typeof CUSTOMER_PATHS];
  }

  return extensionLaunchPath(startParam) || null;
}

export function miniAppPathFromSearch(search: string): string | null {
  const params = new URLSearchParams(search);
  for (const key of START_PARAM_KEYS) {
    const path = miniAppPathFromStartParam(params.get(key));
    if (path) return path;
  }
  return null;
}

export function miniAppLaunchPath(
  search: string,
  hash: string,
  initData: string,
  sdkStartParam?: string
): string | null {
  const launch = new URLSearchParams(hash.slice(1));
  const signed = new URLSearchParams(initData);
  const launchParam =
    sdkStartParam || signed.get("start_param") || launch.get("tgWebAppStartParam");
  return launchParam ? miniAppPathFromStartParam(launchParam) : miniAppPathFromSearch(search);
}
