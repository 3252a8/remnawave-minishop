import type { InstallGuideApp, InstallGuidePlatform } from "./types";

export type InstallTarget = { platform?: string; app?: string };

/** Legacy guide sources have names only; canonical documents carry an explicit stable ID. */
export function installAppId(app: Pick<InstallGuideApp, "id" | "name">): string {
  if (typeof app.id === "string" && app.id.trim()) return app.id.trim();
  return (
    String(app.name || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 64) || "app"
  );
}

export function installTargetFromSearch(search: string): InstallTarget {
  const query = new URLSearchParams(search);
  return { platform: query.get("platform")?.trim() || "", app: query.get("app")?.trim() || "" };
}

export function resolveInstallTarget(
  platforms: InstallGuidePlatform[],
  target: InstallTarget,
  detectedPlatform = ""
): { platform: string; appIndex: number } {
  const requestedPlatform = platforms.find((item) => item.key === target.platform);
  const platform =
    requestedPlatform || platforms.find((item) => item.key === detectedPlatform) || platforms[0];
  const appIndex =
    target.app && (!target.platform || requestedPlatform)
      ? (platform?.apps || []).findIndex((app) => installAppId(app) === target.app)
      : 0;
  return { platform: platform?.key || "", appIndex: Math.max(0, appIndex) };
}

/** Keep unrelated navigation parameters while replacing the optional install destination. */
export function installTargetSearch(search: string, target: InstallTarget): string {
  const query = new URLSearchParams(search);
  for (const key of ["platform", "app"] as const) {
    const value = target[key]?.trim();
    if (value) query.set(key, value);
    else query.delete(key);
  }
  const value = query.toString();
  return value ? `?${value}` : "";
}
