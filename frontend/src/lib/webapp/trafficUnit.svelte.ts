/**
 * Localized traffic unit for the cabinet.
 * The app sets it from the locale; formatters read it while rendering, so a
 * language switch updates every traffic figure.
 */
let label = $state("GB");

export function setTrafficUnitLabel(value: string): void {
  label = String(value || "").trim() || "GB";
}

export function trafficUnitLabel(): string {
  return label;
}
