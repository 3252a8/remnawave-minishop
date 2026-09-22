<script lang="ts">
  import { onMount } from "svelte";
  import type { AdminSectionComponentProps, AdminUserDetailPanelProps } from "./extensionTypes";

  type PluginModule = {
    mountView: (view: string, target: HTMLElement, props: Record<string, unknown>) => unknown;
    unmountView: (instance: unknown) => void;
    updateView?: (instance: unknown, props: Record<string, unknown>) => void;
  };

  type HostProps = Partial<AdminSectionComponentProps & AdminUserDetailPanelProps> & {
    runtimeViewId?: string;
    runtimeEntry?: string;
    currentLang?: string;
  };
  let props: HostProps = $props();
  let target: HTMLElement;
  let failed = $state(false);
  let instance: unknown;
  let module: PluginModule | null = null;
  let mounted = $state(false);
  let lastPropsSignature = "";

  function propsSignature(): string {
    return JSON.stringify([
      props.featureAvailable,
      props.featuresResolved,
      props.availableFeatures,
      props.routePrefix,
      props.currentLang,
      props.active,
      props.user,
      props.userDetail,
    ]);
  }

  $effect(() => {
    const signature = propsSignature();
    if (!mounted || !module || !instance || signature === lastPropsSignature) return;
    lastPropsSignature = signature;
    if (module.updateView) {
      module.updateView(instance, props as Record<string, unknown>);
    } else {
      // Older plugins have no update hook. Remount only when their inputs change.
      module.unmountView(instance);
      instance = module.mountView(
        props.runtimeViewId as string,
        target,
        props as Record<string, unknown>
      );
    }
  });

  onMount(() => {
    let disposed = false;
    if (!props.runtimeEntry || !props.runtimeViewId) {
      failed = true;
      return;
    }
    void import(/* @vite-ignore */ props.runtimeEntry)
      .then((loaded: PluginModule) => {
        if (disposed) return;
        module = loaded;
        lastPropsSignature = propsSignature();
        instance = loaded.mountView(
          props.runtimeViewId as string,
          target,
          props as Record<string, unknown>
        );
        mounted = true;
      })
      .catch(() => {
        failed = true;
      });
    return () => {
      disposed = true;
      if (module && instance) module.unmountView(instance);
      mounted = false;
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
