<script lang="ts">
  import { onMount } from "svelte";
  import { Dialog, Button } from "$components/ui/index.js";
  import {
    createExtensionHost,
    type UserExtensionPlugin,
    type UserExtensionView,
    type ExtensionHost,
  } from "$lib/webapp/extensionHost";
  import type { ApiClient } from "$lib/webapp/publicApi";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type PluginProps = { host: ExtensionHost; language: string; context: Record<string, unknown> };
  type Module = {
    mountView: (view: string, target: HTMLElement, viewProps: PluginProps) => unknown;
    unmountView: (instance: unknown) => void;
    updateView?: (instance: unknown, viewProps: PluginProps) => void;
  };
  let {
    plugin,
    view,
    client,
    t,
    language,
    routePrefix = "",
    context = {},
    status = $bindable<"loading" | "ready" | "failed">("loading"),
  }: {
    plugin: UserExtensionPlugin;
    view: UserExtensionView;
    client: ApiClient;
    t: Translate;
    language: string;
    routePrefix?: string;
    context?: Record<string, unknown>;
    status?: "loading" | "ready" | "failed";
  } = $props();
  let target: HTMLElement;
  let module = $state<Module | null>(null);
  let instance: unknown;
  let instanceMounted = false;
  let removeStyles = () => {};
  let previousProps: PluginProps | null = null;
  let notice = $state("");
  let confirmation = $state("");
  let confirmOpen = $state(false);
  let resolveConfirmation: ((value: boolean) => void) | null = null;
  function resolveDialog(value: boolean) {
    resolveConfirmation?.(value);
    resolveConfirmation = null;
    confirmOpen = false;
  }
  function unmountInstance() {
    if (!module || !instanceMounted) return;
    instanceMounted = false;
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
    removeStyles();
    resolveDialog(false);
  }
  const host = $derived(
    createExtensionHost(client, plugin.id, t, routePrefix, {
      notify: (message) => {
        notice = String(message).slice(0, 2000);
      },
      confirm: (message) =>
        new Promise<boolean>((resolve) => {
          resolveConfirmation?.(false);
          confirmation = String(message).slice(0, 2000);
          resolveConfirmation = resolve;
          confirmOpen = true;
        }),
    })
  );
  const viewProps = $derived({ host, language, context });

  $effect(() => {
    if (!module || status === "failed" || previousProps === viewProps) return;
    try {
      if (module.updateView) module.updateView(instance, viewProps);
      else {
        unmountInstance();
        instance = module.mountView(view.view, target, viewProps);
        instanceMounted = true;
      }
      previousProps = viewProps;
    } catch {
      failView();
    }
  });

  onMount(() => {
    let disposed = false;
    const styles: HTMLLinkElement[] = [];
    removeStyles = () => styles.forEach((link) => link.remove());
    const prefix = `/api/extensions/assets/${plugin.id}/${plugin.digest}/`;
    if (
      !plugin.entry.startsWith(prefix) ||
      plugin.styles?.some((path) => !path.startsWith(prefix))
    ) {
      status = "failed";
      return;
    }
    for (const path of plugin.styles || []) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = path;
      document.head.appendChild(link);
      styles.push(link);
    }
    void import(/* @vite-ignore */ plugin.entry)
      .then((loaded: Module) => {
        if (disposed) return;
        if (typeof loaded.mountView !== "function" || typeof loaded.unmountView !== "function")
          throw new Error("invalid_extension_module");
        module = loaded;
        instance = loaded.mountView(view.view, target, viewProps);
        instanceMounted = true;
        previousProps = viewProps;
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
        /* Keep host navigation usable. */
      }
      removeStyles();
      resolveDialog(false);
      module = null;
    };
  });
</script>

{#if status === "failed"}<p role="alert">{t("wa_extension_unavailable")}</p>{/if}
{#if notice}<p role="status">{notice}</p>{/if}
<div
  bind:this={target}
  class="plugin-host"
  data-user-plugin={plugin.id}
  data-plugin-view={view.id}
  hidden={status === "failed"}
></div>
<Dialog
  open={confirmOpen}
  title={t("wa_confirm")}
  description={confirmation}
  closeLabel={t("wa_cancel")}
  onclose={() => resolveDialog(false)}
>
  <Button variant="outline" onclick={() => resolveDialog(false)}>{t("wa_cancel")}</Button>
  <Button onclick={() => resolveDialog(true)}>{t("wa_confirm")}</Button>
</Dialog>
