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
    status?: "loading" | "ready" | "failed";
  };
  let { status = $bindable<"loading" | "ready" | "failed">("loading"), ...props }: HostProps =
    $props();
  let target: HTMLElement;
  let instance: unknown;
  let module: PluginModule | null = null;
  let mounted = $state(false);
  let lastPropsSignature = "";
  function unmountInstance() {
    if (!module || !mounted) return;
    mounted = false;
    module.unmountView(instance);
  }
  function failView() {
    status = "failed";
    try {
      unmountInstance();
    } catch {
      /* Continue restoring Core. */
    }
    target?.replaceChildren();
  }

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
      props.context,
    ]);
  }

  $effect(() => {
    const signature = propsSignature();
    if (!mounted || !module || status === "failed" || signature === lastPropsSignature) return;
    lastPropsSignature = signature;
    try {
      if (module.updateView) {
        module.updateView(instance, props as Record<string, unknown>);
      } else {
        // Older plugins have no update hook. Remount only when their inputs change.
        unmountInstance();
        instance = module.mountView(
          props.runtimeViewId as string,
          target,
          props as Record<string, unknown>
        );
        mounted = true;
      }
    } catch {
      failView();
    }
  });

  onMount(() => {
    let disposed = false;
    if (!props.runtimeEntry || !props.runtimeViewId) {
      status = "failed";
      return;
    }
    void import(/* @vite-ignore */ props.runtimeEntry)
      .then((loaded: PluginModule) => {
        if (disposed) return;
        if (typeof loaded.mountView !== "function" || typeof loaded.unmountView !== "function")
          throw new Error("invalid_extension_module");
        module = loaded;
        lastPropsSignature = propsSignature();
        instance = loaded.mountView(
          props.runtimeViewId as string,
          target,
          props as Record<string, unknown>
        );
        mounted = true;
        status = "ready";
      })
      .catch(() => {
        if (!disposed) failView();
      });
    return () => {
      disposed = true;
      try {
        unmountInstance();
      } catch {
        /* Preserve the Core shell. */
      }
      mounted = false;
    };
  });
</script>

{#if status === "failed"}
  <p role="alert">
    {props.at?.("plugin_view_failed")}
  </p>
{/if}
<div
  bind:this={target}
  class="plugin-host"
  data-plugin-view={props.runtimeViewId}
  hidden={status === "failed"}
></div>
