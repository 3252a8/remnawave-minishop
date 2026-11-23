import type { components } from "$lib/api/openapi.generated";

let started = 0;
let jobTag = "";
let notifications: boolean | undefined;

export function coreUpdateResponse(path: string, options: RequestInit) {
  if (!path.startsWith("/admin/core-updates")) return undefined;
  const scenario = new URLSearchParams(location.search).get("mock");
  const bundled = scenario === "core-update-bundled";
  const demo = scenario === "core-update" || scenario === "core-update-offline" || bundled;
  const currentDev = scenario === "core-update-current";
  const body = JSON.parse(String(options.body || "{}"));
  if (path.endsWith("/notifications")) notifications = body.enabled === true;
  if (path.endsWith("/apply")) {
    started = Date.now();
    jobTag = body.tag;
  }
  const elapsed = Date.now() - started;
  const phase = !started
    ? ""
    : elapsed < 1000
      ? "queued"
      : elapsed < 5500
        ? "pulling"
        : elapsed < 8500
          ? "migrating"
          : elapsed < 12500
            ? "starting"
            : "complete";
  const tag = phase === "complete" ? jobTag : currentDev ? "dev" : "latest";
  const target = body.tag || tag;
  const available = (demo && phase !== "complete") || target !== tag;
  const state: components["schemas"]["CoreUpdateState"] = {
    current: currentDev
      ? "dev+gb38dce21"
      : demo && phase !== "complete"
        ? "v3.8.5+g7a51b934"
        : "v3.8.6+gb38dce21",
    current_published_at:
      demo && phase !== "complete" ? "2026-11-13T10:39:34Z" : "2026-11-20T20:38:56Z",
    tag,
    release: {
      tag: target,
      revision: "b".repeat(40),
      version: target === "latest" ? "v3.8.6" : target,
      published_at: "2026-11-20T20:38:56Z",
    },
    available,
    official: true,
    installable: !bundled,
    executor: scenario === "core-update",
    notifications: notifications ?? !currentDev,
    phase,
    job_tag: jobTag,
  };
  return { ok: true, state };
}
