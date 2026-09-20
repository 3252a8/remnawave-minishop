export function colorInputValueChanged(current: string, next: string): boolean {
  return (
    (normalizeColorInput(current) ?? current.trim().toLowerCase()) !==
    (normalizeColorInput(next) ?? next.trim().toLowerCase())
  );
}

/** The shared picker's wire format is CSS HEX, with an optional alpha byte. */
export function normalizeColorInput(value: string, allowAlpha = true): string | null {
  const match = value.trim().match(/^#?([\da-f]{3}|[\da-f]{4}|[\da-f]{6}|[\da-f]{8})$/i);
  if (!match) return null;
  let hex = match[1].toLowerCase();
  if (hex.length <= 4) hex = [...hex].map((part) => part + part).join("");
  if (!allowAlpha || (hex.endsWith("ff") && hex.length === 8)) hex = hex.slice(0, 6);
  return `#${hex}`;
}

export function colorInputOpacity(value: string): number {
  const hex = normalizeColorInput(value);
  return hex?.length === 9 ? Math.round((Number.parseInt(hex.slice(7), 16) / 255) * 100) : 100;
}

export function colorInputWithOpacity(value: string, opacity: number): string {
  const hex = normalizeColorInput(value, false) ?? "#000000";
  const alpha = Math.round((Math.min(100, Math.max(0, opacity)) / 100) * 255);
  return alpha === 255 ? hex : `${hex}${alpha.toString(16).padStart(2, "0")}`;
}
