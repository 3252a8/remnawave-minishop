/** UI composition v1: ordering is stable and ambiguous replacements fail open to Core. */
export type Placement = "before" | "after" | "replace";
export interface UiContribution {
  id: string;
  target: string;
  order?: number;
  placement?: string;
}

export function composeUi<T extends UiContribution>(items: readonly T[], target: string) {
  const sorted = items
    .filter((item) => item.target === target)
    .sort((a, b) => (a.order ?? 100) - (b.order ?? 100) || a.id.localeCompare(b.id));
  const replacements = sorted.filter((item) => item.placement === "replace");
  return {
    before: sorted.filter((item) => item.placement === "before"),
    after: sorted.filter((item) => !item.placement || item.placement === "after"),
    replacement: replacements.length === 1 ? replacements[0] : null,
    conflict: replacements.length > 1,
  };
}

export function selectExtensionTab(tabs: readonly { id: string }[], search: string): string {
  const id = new URLSearchParams(search).get("extensionTab") || "";
  return tabs.some((tab) => tab.id === id) ? id : "";
}
