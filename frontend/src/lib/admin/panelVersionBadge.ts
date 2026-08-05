import type { PanelCompatibility } from "./stores/healthStore.svelte.js";

export type PanelVersionBadgeTone = "success" | "warning" | "danger";
export type PanelVersionVerification =
  "verified" | "same_minor" | "unverified" | "historical" | "unsupported" | "unknown";

export type PanelVersionBadgeState = {
  tone: PanelVersionBadgeTone;
  verification: PanelVersionVerification;
  version: string;
  displayVersion: string;
  versionLine: string | null;
  certifiedVersions: string[];
};

function versionLine(value: unknown): string | null {
  const match = String(value ?? "").match(/(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?/);
  return match ? `${Number(match[1])}.${Number(match[2])}` : null;
}

function displayVersion(value: string): string {
  return /^v/i.test(value) ? value : `v${value}`;
}

export function panelVersionBadgeState(
  compatibility: PanelCompatibility | null
): PanelVersionBadgeState | null {
  if (!compatibility) return null;
  const version = String(compatibility.version ?? "").trim();
  const certifiedVersions = Array.isArray(compatibility.certified_versions)
    ? compatibility.certified_versions.filter((item) => String(item).trim())
    : [];
  const status = String(compatibility.support_status || "unknown").toLowerCase();
  const line = versionLine(version);
  const base = {
    version: version || "unknown",
    displayVersion: version ? displayVersion(version) : "—",
    versionLine: line,
    certifiedVersions,
  };

  if (!version) return { ...base, tone: "danger", verification: "unknown" };
  if (status === "current" || status === "maintenance") {
    return { ...base, tone: "success", verification: "verified" };
  }
  if (status === "historical") {
    return { ...base, tone: "danger", verification: "historical" };
  }
  if (status === "unsupported") {
    return { ...base, tone: "danger", verification: "unsupported" };
  }
  if (line && certifiedVersions.some((candidate) => versionLine(candidate) === line)) {
    return { ...base, tone: "warning", verification: "same_minor" };
  }
  return { ...base, tone: "danger", verification: "unverified" };
}
