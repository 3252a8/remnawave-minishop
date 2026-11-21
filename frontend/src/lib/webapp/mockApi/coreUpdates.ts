import type { components } from "$lib/api/openapi.generated";

let started = 0;
let jobTag = "";
let notifications = true;

export function coreUpdateResponse(path: string, options: RequestInit) {
  if (!path.startsWith("/admin/core-updates")) return undefined;
  const scenario = new URLSearchParams(location.search).get("mock");
  const demo = scenario === "core-update" || scenario === "core-update-offline";
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
  const tag = phase === "complete" ? jobTag : "latest";
  const target = body.tag || tag;
  const available = (demo && phase !== "complete") || target !== tag;
  const state: components["schemas"]["CoreUpdateState"] = {
    current: demo && phase !== "complete" ? "v3.8.5+g7a51b934" : "v3.8.6+gb38dce21",
    tag,
    release: {
      tag: target,
      revision: "b".repeat(40),
      version: target === "latest" ? "v3.8.6" : target,
    },
    available,
    official: true,
    executor: scenario === "core-update",
    notifications,
    phase,
    job_tag: jobTag,
  };
  return { ok: true, state };
}
