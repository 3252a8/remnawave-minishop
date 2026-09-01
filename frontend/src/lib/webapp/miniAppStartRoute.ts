import { APP_SECTION_PATHS } from "./constants";
import { isCheckoutStartParam } from "./deeplinks.js";
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
const START_PARAM_SECTIONS = [
  "home",
  "install",
  "trial",
  "invite",
  "partner",
  "devices",
  "support",
  "settings",
] as const;

type StartParamSection = (typeof START_PARAM_SECTIONS)[number];

function isStartParamSection(value: string): value is StartParamSection {
  return (START_PARAM_SECTIONS as readonly string[]).includes(value);
}

export function miniAppPathFromStartParam(value: unknown): string | null {
  const startParam = String(value || "").trim();
  if (isCheckoutStartParam(startParam)) return CHECKOUT_PATH;
  const adminTicket = startParam.match(/^admin_ticket_(\d+)$/i);
  if (adminTicket) return `/admin/support/${adminTicket[1]}`;

  const adminUser = startParam.match(/^admin_user_(-?\d+)$/i);
  if (adminUser) return `/admin/users/${adminUser[1]}`;

  const supportTicket = startParam.match(/^ticket_(\d+)$/i);
  if (supportTicket) return `/support/${supportTicket[1]}`;

  const section = startParam.toLowerCase();
  if (section === "plans") return PLANS_PATH;
  if (isStartParamSection(section)) return APP_SECTION_PATHS[section];

  return null;
}

export function miniAppPathFromSearch(search: string): string | null {
  const params = new URLSearchParams(search);
  for (const key of START_PARAM_KEYS) {
    const path = miniAppPathFromStartParam(params.get(key));
    if (path) return path;
  }
  return null;
}
