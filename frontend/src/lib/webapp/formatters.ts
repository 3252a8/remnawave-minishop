type TemplateParams = Record<string, unknown>;

type TelegramProfile =
  | (Record<string, unknown> & {
      first_name?: unknown;
      last_name?: unknown;
      username?: unknown;
    })
  | null
  | undefined;

export function formatTemplate(template: unknown, params: TemplateParams = {}): string {
  const text = String(template ?? "");
  return text.replace(/\{(\w+)\}/g, (_, key) => String(params[key] ?? `{${key}}`));
}

export function formatMoney(value: unknown, currency = "RUB"): string {
  const numeric = Number(value || 0);
  const formatted = Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2);
  const currencyCode = String(currency || "RUB").trim();
  const symbol = currencyCode.toUpperCase() === "RUB" ? "₽" : currencyCode;
  const [integer, fraction] = formatted.split(".");
  const sign = integer.startsWith("-") ? "-" : "";
  const digits = sign ? integer.slice(1) : integer;
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
  const amount = `${sign}${grouped}${fraction === undefined ? "" : `.${fraction}`}`;
  return `${amount} ${symbol}`;
}

export function formatTrafficGb(value: unknown): string {
  const numeric = Number(value || 0);
  const formatted = Number.isInteger(numeric)
    ? String(numeric)
    : numeric.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  return `${formatted} GB`;
}

export function formatTrafficBytes(value: unknown): string {
  const gb = Number(value || 0) / 1073741824;
  return formatTrafficGb(gb);
}

export function formatCompactNumber(value: unknown): string {
  const numeric = Number(value || 0);
  return Number.isInteger(numeric)
    ? String(numeric)
    : numeric.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

export function roundToHalf(value: unknown): number {
  return Math.round(Number(value || 0) * 2) / 2;
}

export function formatFraction(value: unknown): string {
  const n = Number(value || 0);
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(1);
}

export function normalizedEmail(value: unknown): string {
  return String(value || "")
    .trim()
    .toLowerCase();
}

export function telegramName(profile: TelegramProfile, fallback = ""): string {
  const username = String(profile?.username || "").trim();
  if (username) return `@${username}`;
  const first = String(profile?.first_name || "").trim();
  const last = String(profile?.last_name || "").trim();
  if (first || last) return `${first} ${last}`.trim();
  return fallback;
}
