<script lang="ts">
  import { Switch } from "$components/ui/primitives.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type BehaviorSetting = {
    key: string;
    labelKey: string;
    labelFallback: string;
    descriptionKey: string;
    descriptionFallback: string;
    enabled: boolean;
    onChange: (enabled: boolean) => void;
  };

  let {
    at,
    settings,
    disabled,
  }: { at: TranslateFn; settings: BehaviorSetting[]; disabled: boolean } = $props();
</script>

{#each settings as setting (setting.key)}
  <section class="appearance-theme-mode-setting">
    <div class="appearance-theme-mode-copy">
      <strong>{at(setting.labelKey, {}, setting.labelFallback)}</strong>
      <small>{at(setting.descriptionKey, {}, setting.descriptionFallback)}</small>
    </div>
    <div class="admin-setting-switch">
      <Switch.Root
        aria-label={at(setting.labelKey, {}, setting.labelFallback)}
        checked={setting.enabled}
        onCheckedChange={setting.onChange}
        {disabled}
        class="admin-switch-root"
      >
        <Switch.Thumb class="admin-switch-thumb" />
      </Switch.Root>
      <span>{setting.enabled ? at("enabled", {}, "Enabled") : at("disabled", {}, "Disabled")}</span>
    </div>
  </section>
{/each}
