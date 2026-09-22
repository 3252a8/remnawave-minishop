<script lang="ts">
  import { onMount } from "svelte";
  import type { AdminSectionComponentProps, AdminUserDetailPanelProps } from "./extensionTypes";

  type PluginModule = {
    mountView: (view: string, target: HTMLElement, props: Record<string, unknown>) => unknown;
    unmountView: (instance: unknown) => void;
  };

  type HostProps = Partial<AdminSectionComponentProps & AdminUserDetailPanelProps> & {
    runtimeViewId?: string;
    runtimeEntry?: string;
  };
  let props: HostProps = $props();
  let target: HTMLElement;
  let failed = $state(false);

  onMount(() => {
    let disposed = false;
    let instance: unknown;
    let module: PluginModule | null = null;
    if (!props.runtimeEntry || !props.runtimeViewId) {
      failed = true;
      return;
    }
    void import(/* @vite-ignore */ props.runtimeEntry)
      .then((loaded: PluginModule) => {
        if (disposed) return;
        module = loaded;
        instance = loaded.mountView(
          props.runtimeViewId as string,
          target,
          props as Record<string, unknown>
        );
      })
      .catch(() => {
        failed = true;
      });
    return () => {
      disposed = true;
      if (module && instance) module.unmountView(instance);
    };
  });
</script>

{#if failed}
  <p role="alert">
    {typeof props.at === "function"
      ? (props.at as (key: string, params: object, fallback: string) => string)(
          "plugin_view_failed",
          {},
          "This plugin view could not be loaded. Open Plugins to disable or repair it."
        )
      : "This plugin view could not be loaded."}
  </p>
{/if}
<div bind:this={target} class="plugin-host" data-plugin-view={props.runtimeViewId}></div>
