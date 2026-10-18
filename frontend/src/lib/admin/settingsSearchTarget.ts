import { settingsFieldAnchorKey } from "./settingsSections";

export function settingsSearchTargetKey(): string {
  if (typeof window === "undefined") return "";
  const prefix = `#${settingsFieldAnchorKey("")}`;
  return window.location.hash.startsWith(prefix) ? window.location.hash.slice(prefix.length) : "";
}

export function focusSettingsSearchTarget(key: string): boolean {
  const row = Array.from(document.querySelectorAll<HTMLElement>(".admin-setting")).find((element) =>
    Array.from(element.querySelectorAll("code")).some((code) => code.textContent === key)
  );
  if (!row) return false;
  row.classList.add("is-search-highlighted");
  row.tabIndex = -1;
  row.focus({ preventScroll: true });
  row.scrollIntoView({ block: "center" });
  return true;
}
