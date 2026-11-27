export const EVENTS = ["register", "trial", "payment", "expired"] as const;
export const AREAS = ["usersTable", "users", "userCard", "ticket"] as const;

export type AlertEvent = (typeof EVENTS)[number];
export type DisplayArea = (typeof AREAS)[number];
export type DetailArea = "userCard" | "ticket";

export interface Settings {
  sources: string[];
  refreshHours: number;
  display: Record<DisplayArea, boolean>;
  chatId: string | null;
  topicId: string | null;
  events: AlertEvent[];
}

interface SourceStatus {
  url: string;
  lastSuccessAt: string | null;
  lastAttemptAt: string | null;
  lastError: string | null;
  count: number | null;
  invalidLines: number | null;
}

export interface SettingsData {
  settings: Settings;
  supportsUsersTable: boolean;
  sourceStatuses: SourceStatus[];
  refreshPending: boolean;
}

export interface Reason {
  text: string;
  links: string[];
}

export interface Status {
  state: "match" | "clear" | "unknown";
  reasons: Reason[];
  stale: boolean;
}

export interface MatchRow extends Status {
  userId: string;
  telegramId: string;
  name: string | null;
  username: string | null;
  profile: MatchProfile | null;
}

export interface TariffOption {
  tariff_key: string | null;
  tariff_names: Record<string, string>;
  is_configured: boolean;
  is_enabled: boolean | null;
}

export interface MatchProfile {
  user_id: number;
  minishop_id: string | null;
  telegram_id: number | null;
  first_name: string | null;
  last_name: string | null;
  username: string | null;
  email: string | null;
  avatar_url: string | null;
  telegram_photo_url: string | null;
  registration_date: string | null;
  is_banned: boolean;
  panel_status: string | null;
  panel_status_expired_at: string | null;
  subscription_expires_at: string | null;
  subscription_plan:
    (TariffOption & { kind: "trial" | "tariff" | "unassigned"; is_active: boolean }) | null;
  premium_traffic: {
    state: "none" | "unlimited" | "good" | "warn" | "critical";
    used_bytes: number;
    limit_bytes: number | null;
  };
  payments_total_amount: number;
  payments_count: number;
  payments_currency: string | null;
  invited_users_count: number;
  user_balance_amount_minor: number;
  partner_balance_amount_minor: number;
}

export interface MatchPage {
  enabled: boolean;
  rows: MatchRow[];
  total: number;
  user_balance_enabled: boolean;
  partner_balance_enabled: boolean;
  balance_currency: string;
  balance_currency_scale: number;
  tariff_options: TariffOption[];
}

export interface MatchFilters {
  q: string;
  sort: string;
  filter: string;
  panel_status: string;
  premium_traffic: string;
  tariff_filter: string;
}

export class ApiError extends Error {
  constructor(
    readonly code: string,
    readonly status?: number
  ) {
    super(code);
  }
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new ApiError("invalid_response");
  return value as Record<string, unknown>;
}

function string(value: unknown): string {
  if (typeof value !== "string") throw new ApiError("invalid_response");
  return value;
}

function boolean(value: unknown): boolean {
  if (typeof value !== "boolean") throw new ApiError("invalid_response");
  return value;
}

function integer(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value))
    throw new ApiError("invalid_response");
  return value;
}

function nullable<T>(value: unknown, decode: (value: unknown) => T): T | null {
  return value === null ? null : decode(value);
}

function array<T>(value: unknown, decode: (value: unknown) => T): T[] {
  if (!Array.isArray(value)) throw new ApiError("invalid_response");
  return value.map(decode);
}

function choice<T extends string>(value: unknown, choices: readonly T[]): T {
  const selected = choices.find((item) => item === value);
  if (selected === undefined) throw new ApiError("invalid_response");
  return selected;
}

function decodeSettingsData(payload: Record<string, unknown>): SettingsData {
  const settings = record(payload.settings);
  const display = record(settings.display);
  return {
    supportsUsersTable: boolean(payload.supportsUsersTable),
    refreshPending: boolean(payload.refreshPending),
    settings: {
      sources: array(settings.sources, string),
      refreshHours: integer(settings.refreshHours),
      display: {
        usersTable: boolean(display.usersTable),
        users: boolean(display.users),
        userCard: boolean(display.userCard),
        ticket: boolean(display.ticket),
      },
      chatId: nullable(settings.chatId, string),
      topicId: nullable(settings.topicId, string),
      events: array(settings.events, (value) => choice(value, EVENTS)),
    },
    sourceStatuses: array(payload.sourceStatuses, (value) => {
      const source = record(value);
      return {
        url: string(source.url),
        lastSuccessAt: nullable(source.lastSuccessAt, string),
        lastAttemptAt: nullable(source.lastAttemptAt, string),
        lastError: nullable(source.lastError, string),
        count: nullable(source.count, integer),
        invalidLines: nullable(source.invalidLines, integer),
      };
    }),
  };
}

function decodeStatus(value: unknown): Status {
  const status = record(value);
  return {
    state: choice(status.state, ["match", "clear", "unknown"]),
    reasons: array(status.reasons, (value) => {
      const reason = record(value);
      return { text: string(reason.text), links: array(reason.links, string) };
    }),
    stale: boolean(status.stale),
  };
}

async function request(path: string, signal: AbortSignal, method = "GET", body?: object) {
  const headers: Record<string, string> = { Accept: "application/json" };
  const options: RequestInit = { method, headers, credentials: "same-origin", signal };
  if (body !== undefined) {
    const csrfCookie = document.cookie.match(/(?:^|;\s*)rw_webapp_csrf=([^;]*)/)?.[1];
    headers["Content-Type"] = "application/json";
    if (csrfCookie) headers["X-CSRF-Token"] = decodeURIComponent(csrfCookie);
    options.body = JSON.stringify(body);
  }
  const response = await fetch(`/api/admin/minishop-blacklist${path}`, options);
  const data: unknown = await response.json().catch(() => null);
  const payload = data === null ? {} : record(data);
  if (!response.ok || payload.ok !== true) {
    throw new ApiError(
      typeof payload.error === "string" ? payload.error : "request_failed",
      response.status
    );
  }
  return payload;
}

export async function getSettings(signal: AbortSignal): Promise<SettingsData> {
  return decodeSettingsData(await request("/settings", signal));
}

export async function putSettings(settings: Settings, signal: AbortSignal): Promise<SettingsData> {
  return decodeSettingsData(await request("/settings", signal, "PUT", settings));
}

export async function startSourceRefresh(signal: AbortSignal): Promise<SettingsData> {
  return decodeSettingsData(await request("/sources/refresh", signal, "POST", {}));
}

function decodeTariff(value: Record<string, unknown>): TariffOption {
  return {
    tariff_key: nullable(value.tariff_key, string),
    tariff_names: Object.fromEntries(
      Object.entries(record(value.tariff_names)).map(([key, name]) => [key, string(name)])
    ),
    is_configured: boolean(value.is_configured),
    is_enabled: nullable(value.is_enabled, boolean),
  };
}

function decodeProfile(value: unknown): MatchProfile {
  const profile = record(value);
  const premium = record(profile.premium_traffic);
  const plan = profile.subscription_plan === null ? null : record(profile.subscription_plan);
  return {
    user_id: integer(profile.user_id),
    minishop_id: nullable(profile.minishop_id, string),
    telegram_id: nullable(profile.telegram_id, integer),
    first_name: nullable(profile.first_name, string),
    last_name: nullable(profile.last_name, string),
    username: nullable(profile.username, string),
    email: nullable(profile.email, string),
    avatar_url: nullable(profile.avatar_url, string),
    telegram_photo_url: nullable(profile.telegram_photo_url, string),
    registration_date: nullable(profile.registration_date, string),
    is_banned: boolean(profile.is_banned),
    panel_status: nullable(profile.panel_status, string),
    panel_status_expired_at: nullable(profile.panel_status_expired_at, string),
    subscription_expires_at: nullable(profile.subscription_expires_at, string),
    subscription_plan:
      plan === null
        ? null
        : {
            ...decodeTariff(plan),
            kind: choice(plan.kind, ["trial", "tariff", "unassigned"]),
            is_active: boolean(plan.is_active),
          },
    premium_traffic: {
      state: choice(premium.state, ["none", "unlimited", "good", "warn", "critical"]),
      used_bytes: premium.used_bytes == null ? 0 : integer(premium.used_bytes),
      limit_bytes: premium.limit_bytes == null ? null : integer(premium.limit_bytes),
    },
    payments_total_amount: Number(profile.payments_total_amount),
    payments_count: integer(profile.payments_count),
    payments_currency: nullable(profile.payments_currency, string),
    invited_users_count: integer(profile.invited_users_count),
    user_balance_amount_minor: integer(profile.user_balance_amount_minor),
    partner_balance_amount_minor: integer(profile.partner_balance_amount_minor),
  };
}

export async function getMatches(
  limit: number,
  offset: number,
  signal: AbortSignal,
  filters?: MatchFilters
): Promise<MatchPage> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset), ...filters });
  const payload = await request(`/matches?${params}`, signal);
  return {
    enabled: boolean(payload.enabled),
    rows: array(payload.rows, (value) => {
      const row = record(value);
      return {
        ...decodeStatus(row),
        userId: string(row.userId),
        telegramId: string(row.telegramId),
        name: nullable(row.name, string),
        username: nullable(row.username, string),
        profile: row.profile == null ? null : decodeProfile(row.profile),
      };
    }),
    total: integer(payload.total),
    user_balance_enabled: payload.user_balance_enabled === true,
    partner_balance_enabled: payload.partner_balance_enabled === true,
    balance_currency: payload.balance_currency == null ? "RUB" : string(payload.balance_currency),
    balance_currency_scale:
      payload.balance_currency_scale == null ? 2 : integer(payload.balance_currency_scale),
    tariff_options: array(payload.tariff_options ?? [], (value) => decodeTariff(record(value))),
  };
}

export async function getStatus(view: DetailArea, id: string | null, signal: AbortSignal) {
  const payload = await request("/status", signal, "POST", { view, telegramIds: id ? [id] : [] });
  const statuses = record(payload.statuses);
  const enabled = boolean(payload.enabled);
  return { enabled, status: enabled && id ? decodeStatus(statuses[id]) : null };
}
