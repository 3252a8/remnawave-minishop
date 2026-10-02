import type { components } from "$lib/api/openapi.generated";

export type AdDetail = components["schemas"]["AdDetailOut"];
export type Translate = (
  key: string,
  params?: Record<string, unknown>,
  fallback?: string
) => string;
export type AdMutation =
  | "edit"
  | "archive"
  | "links"
  | "linkToggle"
  | "bindings"
  | "endBinding"
  | "spend"
  | "confirm"
  | "revert"
  | "candidates"
  | "decide";
export type Mutate = (
  action: AdMutation,
  body?: object,
  childId?: string | number
) => Promise<boolean>;

export function adMoney(
  amount: string | number | null | undefined,
  currency: string,
  scale = 2
): string {
  if (amount === null || amount === undefined) return "—";
  if (typeof amount === "number" && !Number.isInteger(amount))
    return `${(amount / 10 ** scale).toLocaleString(undefined, { maximumFractionDigits: scale })} ${currency}`;
  const minor = BigInt(amount);
  const absolute = minor < 0n ? -minor : minor;
  const divisor = 10n ** BigInt(scale);
  const whole = (absolute / divisor).toLocaleString();
  const fraction = (absolute % divisor).toString().padStart(scale, "0").replace(/0+$/, "");
  const separator =
    new Intl.NumberFormat().formatToParts(1.1).find((part) => part.type === "decimal")?.value ||
    ".";
  return `${minor < 0n ? "-" : ""}${whole}${fraction ? separator + fraction : ""} ${currency}`;
}

export function adDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "—";
}

export function adError(value: unknown): string {
  if (!value || typeof value !== "object") return "";
  const record = value as Record<string, unknown>;
  return String(record.error || record.message || "");
}
