<script lang="ts">
  import { Popover } from "bits-ui";

  import { panelVersionBadgeState } from "$lib/admin/panelVersionBadge.js";
  import type { PanelCompatibility } from "$lib/admin/stores/healthStore.svelte.js";
  import { AdminBadge } from "$components/patterns/admin/index.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at,
    compatibility,
  }: {
    at: TranslateFn;
    compatibility: PanelCompatibility | null;
  } = $props();

  const badge = $derived(panelVersionBadgeState(compatibility));

  function statusLabel(verification: NonNullable<typeof badge>["verification"]): string {
    const fallbacks = {
      verified: "Exact version verified",
      same_minor: "Patch version not verified",
      unverified: "Version not verified",
      historical: "Historical version",
      unsupported: "Unsupported version",
      unknown: "Version unknown",
    } as const;
    return at(`stats_panel_version_status_${verification}`, {}, fallbacks[verification]);
  }

  function detailText(state: NonNullable<typeof badge>): string {
    if (state.verification === "verified") {
      return at(
        "stats_panel_version_verified_detail",
        { version: state.version },
        `Core verified Remnawave ${state.version} with its live read/write compatibility suite.`
      );
    }
    if (state.verification === "same_minor") {
      return at(
        "stats_panel_version_same_minor_detail",
        { version: state.version, line: state.versionLine || "" },
        `Remnawave ${state.version} is on the verified ${state.versionLine} patch line, but this exact patch has not been certified.`
      );
    }
    if (state.verification === "historical") {
      return at(
        "health_panel_api_version_historical",
        { version: state.version },
        `Remnawave ${state.version} is a historical, no-longer-tested target.`
      );
    }
    if (state.verification === "unsupported") {
      return at(
        "health_panel_api_version_unsupported",
        { version: state.version },
        `Remnawave ${state.version} is explicitly incompatible with this Core release.`
      );
    }
    if (state.verification === "unknown") {
      return at(
        "health_panel_api_version_unknown",
        {},
        "The Remnawave version could not be detected."
      );
    }
    return at(
      "stats_panel_version_unverified_detail",
      { version: state.version },
      `Remnawave ${state.version} is outside the verified major.minor lines. Review compatibility before enabling panel writes.`
    );
  }
</script>

{#if badge}
  <Popover.Root>
    <Popover.Trigger
      type="button"
      class="admin-panel-version-trigger"
      aria-label={at(
        "stats_panel_version_aria",
        { version: badge.version, status: statusLabel(badge.verification) },
        `Panel version ${badge.version}: ${statusLabel(badge.verification)}`
      )}
    >
      <AdminBadge variant={badge.tone}>{badge.displayVersion}</AdminBadge>
    </Popover.Trigger>
    <Popover.Portal>
      <Popover.Content class="admin-panel-version-popover" side="bottom" align="end" sideOffset={8}>
        <div class="admin-panel-version-popover__head">
          <AdminBadge variant={badge.tone}>{badge.displayVersion}</AdminBadge>
          <strong>{statusLabel(badge.verification)}</strong>
        </div>
        <p>{detailText(badge)}</p>
        {#if badge.certifiedVersions.length}
          <p class="admin-panel-version-popover__tested">
            {at(
              "stats_panel_version_certified_versions",
              { versions: badge.certifiedVersions.join(", ") },
              `Verified versions: ${badge.certifiedVersions.join(", ")}`
            )}
          </p>
        {/if}
      </Popover.Content>
    </Popover.Portal>
  </Popover.Root>
{/if}

<style>
  :global(.admin-panel-version-trigger) {
    display: inline-flex;
    border: 0;
    border-radius: 999px;
    padding: 0;
    background: transparent;
    color: inherit;
    cursor: pointer;
  }

  :global(.admin-panel-version-trigger:focus-visible) {
    outline: 2px solid var(--admin-ring);
    outline-offset: 3px;
  }

  :global(.admin-panel-version-popover) {
    z-index: 120;
    display: grid;
    gap: 8px;
    width: min(390px, calc(100vw - 32px));
    padding: 12px 14px;
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    background: var(--admin-surface);
    color: var(--admin-text);
    box-shadow: var(--shadow-popover);
    font-size: 12px;
    line-height: 1.45;
  }

  :global(.admin-panel-version-popover__head) {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  :global(.admin-panel-version-popover p) {
    margin: 0;
    overflow-wrap: anywhere;
  }

  :global(.admin-panel-version-popover__tested) {
    color: var(--admin-muted);
  }
</style>
