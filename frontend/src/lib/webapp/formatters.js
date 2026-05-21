export function formatTemplate(template, params = {}) {
  const text = String(template ?? "");
  return text.replace(/\{(\w+)\}/g, (_, key) => String(params[key] ?? `{${key}}`));
}

export function formatMoney(value, currency = "RUB") {
  const numeric = Number(value || 0);
  const formatted = Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2);
  const symbol = currency === "RUB" ? "₽" : currency;
  return `${formatted} ${symbol}`;
}

export function formatTrafficGb(value) {
  const numeric = Number(value || 0);
  const formatted = Number.isInteger(numeric)
    ? String(numeric)
    : numeric.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  return `${formatted} GB`;
}

export function formatTrafficBytes(value) {
  const gb = Number(value || 0) / 1073741824;
  return formatTrafficGb(gb);
}

export function formatCompactNumber(value) {
  const numeric = Number(value || 0);
  return Number.isInteger(numeric)
    ? String(numeric)
    : numeric.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

export function roundToHalf(value) {
  return Math.round(Number(value || 0) * 2) / 2;
}

export function formatFraction(value) {
  const n = Number(value || 0);
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(1);
}

export function normalizedEmail(value) {
  return String(value || "")
    .trim()
    .toLowerCase();
}

export function telegramName(profile, fallback) {
  const username = String(profile?.username || "").trim();
  if (username) return `@${username}`;
  const first = String(profile?.first_name || "").trim();
  const last = String(profile?.last_name || "").trim();
  if (first || last) return `${first} ${last}`.trim();
  return fallback;
}
