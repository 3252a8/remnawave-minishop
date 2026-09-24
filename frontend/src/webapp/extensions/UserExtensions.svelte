<script lang="ts">
  import { onMount } from "svelte";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import {
    extensionPath,
    type UserExtensionPlugin,
    type UserNavigationItem,
  } from "$lib/webapp/extensionHost";
  import { stripRoutePrefix } from "$lib/webapp/routes";
  import UserPluginHost from "./UserPluginHost.svelte";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  let {
    client,
    screen,
    language,
    t,
    routePrefix = "",
    context = {},
    navigation = $bindable<UserNavigationItem[]>([]),
  }: {
    client: ApiClient;
    screen: string;
    language: string;
    t: Translate;
    routePrefix?: string;
    context?: Record<string, unknown>;
    navigation?: UserNavigationItem[];
  } = $props();
  let plugins = $state<UserExtensionPlugin[]>([]);
  let loading = $state(true);
  let pathname = $state(window.location.pathname);
  let revision = 0;
  const pages = $derived(
    plugins.flatMap((plugin) =>
      (plugin.views || [])
        .filter((view) => view.target === "page")
        .map((view) => ({ plugin, view }))
    )
  );
  const route = $derived(
    stripRoutePrefix(pathname, routePrefix).match(
      /^\/extensions\/([a-z][a-z0-9-]+)\/([a-z][a-z0-9-]+)$/
    )
  );
  const selected = $derived(
    route ? pages.find(({ plugin, view }) => plugin.id === route[1] && view.id === route[2]) : null
  );
  const targets: Record<string, string[]> = {
    home: ["user.home.cards", "user.subscription.actions"],
    settings: ["user.profile.actions"],
    install: ["user.install.blocks"],
  };
  const slots = $derived(
    plugins
      .flatMap((plugin) =>
        (plugin.views || [])
          .filter((view) => targets[screen]?.includes(view.target || ""))
          .map((view) => ({ plugin, view }))
      )
      .sort(
        (a, b) =>
          (a.view.order ?? 100) - (b.view.order ?? 100) ||
          `${a.plugin.id}:${a.view.id}`.localeCompare(`${b.plugin.id}:${b.view.id}`)
      )
  );

  $effect(() => {
    navigation = [...pages]
      .filter(({ view }) => view.navigation !== "hidden")
      .sort(
        (a, b) =>
          (a.view.order ?? 100) - (b.view.order ?? 100) ||
          `${a.plugin.id}:${a.view.id}`.localeCompare(`${b.plugin.id}:${b.view.id}`)
      )
      .map(({ plugin, view }) => ({
        id: `${plugin.id}:${view.id}`,
        path: extensionPath(plugin.id, view.id, routePrefix),
        label: view.i18nKey ? t(view.i18nKey, {}, view.label) : view.label,
        icon: view.icon || "star",
      }));
  });
  $effect(() => {
    const requestKey = `${screen}:${language}`;
    void requestKey;
    const token = ++revision;
    const controller = new AbortController();
    loading = true;
    void client
      .api(builtApiPath<"/api/extensions/runtime">("/api/extensions/runtime"), {
        signal: controller.signal,
      })
      .then((response) => {
        if (revision === token) plugins = unwrap(response).plugins;
      })
      .catch(() => {
        if (revision === token) plugins = [];
      })
      .finally(() => {
        if (revision === token) loading = false;
      });
    return () => {
      controller.abort();
    };
  });
  onMount(() => {
    const update = () => {
      pathname = window.location.pathname;
    };
    window.addEventListener("popstate", update);
    return () => {
      window.removeEventListener("popstate", update);
      revision++;
      navigation = [];
    };
  });
</script>

{#if screen === "extensions"}
  <section class="extension-content" aria-label={selected?.view.label}>
    {#if loading}<p role="status">{t("wa_loading")}</p>
    {:else if selected}
      {#key `${selected.plugin.digest}:${selected.view.id}:${language}`}
        <UserPluginHost
          plugin={selected.plugin}
          view={selected.view}
          {client}
          {t}
          {language}
          {routePrefix}
          {context}
        />
      {/key}
    {:else}<p role="alert">{t("wa_extension_unavailable")}</p>{/if}
  </section>
{:else}
  {#each slots as { plugin, view } (`${plugin.id}:${plugin.digest}:${view.id}:${language}`)}
    <section class="extension-content" aria-label={view.label}>
      <UserPluginHost {plugin} {view} {client} {t} {language} {routePrefix} {context} />
    </section>
  {/each}
{/if}

<style>
  .extension-content {
    display: grid;
    gap: 1rem;
    min-width: 0;
    margin-block: 1rem;
  }
</style>
