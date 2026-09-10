import type { ThemeVariant } from "./appearanceOptions";

export function selectedThemeVariant(
  selected: ThemeVariant | undefined,
  persisted: ThemeVariant
): ThemeVariant {
  return selected === "light" || selected === "dark" ? selected : persisted;
}
