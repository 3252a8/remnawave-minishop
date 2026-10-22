<script lang="ts">
  import { AdminSelect } from "$components/patterns/admin/index.js";
  import { withUnavailableTarget } from "$lib/admin/messageButtonTargets.js";
  import type { InstallPlatformTarget } from "$lib/admin/messageTargets.svelte.js";
  import type { InstallTarget } from "$lib/webapp/installTargets.js";

  let {
    platform = "",
    app = "",
    platforms,
    at,
    onChange,
  }: InstallTarget & {
    platforms: InstallPlatformTarget[];
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
    onChange: (target: InstallTarget) => void;
  } = $props();

  const platformItems = $derived([
    { value: "", label: at("install_target_platform_auto") },
    ...platforms.map((item) => ({ value: item.id, label: item.label })),
  ]);
  const appItems = $derived([
    { value: "", label: at("install_target_app_auto") },
    ...(platforms.find((item) => item.id === platform)?.apps || []).map((item) => ({
      value: item.id,
      label: item.name,
    })),
  ]);
</script>

<div class="install-target-fields">
  <AdminSelect
    value={platform}
    items={withUnavailableTarget(platformItems, platform, (target) =>
      at("message_target_unavailable", { target })
    )}
    ariaLabel={at("install_target_platform")}
    controlSize="md"
    onValueChange={(platform) => onChange({ platform, app: "" })}
  />
  <AdminSelect
    value={app}
    items={withUnavailableTarget(appItems, app, (target) =>
      at("message_target_unavailable", { target })
    )}
    ariaLabel={at("install_target_app")}
    disabled={!platform}
    controlSize="md"
    onValueChange={(app) => onChange({ platform, app })}
  />
</div>

<style>
  .install-target-fields {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 8px;
    min-width: 0;
    width: 100%;
  }
</style>
