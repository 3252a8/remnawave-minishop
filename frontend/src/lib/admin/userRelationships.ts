import { withRoutePrefix } from "$lib/webapp/routes";

export type RelationshipFilter = "all" | "referral" | "partner";
export function normalizeRelationshipFilter(value: unknown): RelationshipFilter {
  return value === "referral" || value === "partner" ? value : "all";
}

export function updateUserRelationshipsRoute(
  change: { filter?: RelationshipFilter; focus?: string },
  push = false
): void {
  const url = new URL(window.location.href);
  if (change.filter !== undefined) {
    if (change.filter === "all") url.searchParams.delete("graph_kind");
    else url.searchParams.set("graph_kind", change.filter);
  }
  if (change.focus !== undefined) {
    if (change.focus) url.searchParams.set("focus", change.focus);
    else url.searchParams.delete("focus");
  }
  const target = `${url.pathname}${url.search}${url.hash}`;
  if (target === `${window.location.pathname}${window.location.search}${window.location.hash}`)
    return;
  if (push) window.history.pushState(window.history.state, "", target);
  else window.history.replaceState(window.history.state, "", target);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function openUserRelationshipsGraph(userId?: number | string, routePrefix = ""): void {
  const url = new URL(window.location.href);
  url.pathname = withRoutePrefix("/admin/users", routePrefix);
  url.searchParams.set("view", "relationships");
  url.searchParams.delete("graph_kind");
  if (userId !== undefined) url.searchParams.set("focus", String(userId));
  else url.searchParams.delete("focus");
  window.history.pushState(null, "", `${url.pathname}${url.search}${url.hash}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function userRelationshipsRoute(): {
  open: boolean;
  focus: string;
  filter: RelationshipFilter;
} {
  if (typeof window === "undefined") return { open: false, focus: "", filter: "all" };
  const params = new URLSearchParams(window.location.search);
  return {
    open: params.get("view") === "relationships",
    focus: params.get("focus") || "",
    filter: normalizeRelationshipFilter(params.get("graph_kind")),
  };
}
