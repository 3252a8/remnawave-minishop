const RADIUS_MIN = 4;
const RADIUS_MAX = 28;
const TRANSPARENCY_MIN = 0;
const TRANSPARENCY_MAX = 100;

function finiteNumber(value: unknown): number | null {
  if (value == null || (typeof value === "string" && value.trim() === "")) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function clampRounded(value: unknown, min: number, max: number): number | null {
  const numeric = finiteNumber(value);
  return numeric == null ? null : Math.min(max, Math.max(min, Math.round(numeric)));
}

export function normalizeAppearanceRadius(value: unknown, fallback = 8, min = RADIUS_MIN): number {
  const text = String(value ?? "").trim();
  const match = text.match(/^(-?(?:\d+(?:\.\d+)?|\.\d+))(?:px)?$/i);
  return clampRounded(match?.[1], min, RADIUS_MAX) ?? fallback;
}

export function radiusToken(value: unknown, min = RADIUS_MIN): string | null {
  const normalized = clampRounded(value, min, RADIUS_MAX);
  return normalized == null ? null : `${normalized}px`;
}

export function normalizeAppearanceTransparency(value: unknown, fallback = 100): number {
  return clampRounded(value, TRANSPARENCY_MIN, TRANSPARENCY_MAX) ?? fallback;
}

export function transparencyToken(value: unknown): number | null {
  return clampRounded(value, TRANSPARENCY_MIN, TRANSPARENCY_MAX);
}
