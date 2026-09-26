<script lang="ts">
  import { onMount, setContext, type Snippet } from "svelte";
  import { Button } from "$components/ui/index.js";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import {
    createExtensionHost,
    extensionPath,
    type UserExtensionPlugin,
    type UserNavigationItem,
  } from "$lib/webapp/extensionHost";
  import { stripRoutePrefix } from "$lib/webapp/routes";
  import { USER_COMPOSITION, type UserCompositionContext } from "./compositionContext";
  import UserExtensionPoint from "./UserExtensionPoint.svelte";
  import UserExtensionSlot from "./UserExtensionSlot.svelte";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  let {
    client,
    screen,
    language,
    t,
    routePrefix = "",
    context = {},
    children,
    navigation = $bindable<UserNavigationItem[]>([]),
    parentSection = $bindable(""),
    sections = $bindable<string[]>([]),
  }: {
    client?: ApiClient;
    screen: string;
    language: string;
    t: Translate;
    routePrefix?: string;
    context?: Record<string, unknown>;
    children?: Snippet;
    navigation?: UserNavigationItem[];
    parentSection?: string;
    sections?: string[];
  } = $props();
  let plugins = $state<UserExtensionPlugin[]>([]);
  let loading = $state(true);
  let pathname = $state(window.location.pathname);
  let revision = 0;
  const composition: UserCompositionContext = {
    get plugins() {
      return plugins;
    },
    get client() {
      return client;
    },
    get t() {
      return t;
    },
    get language() {
      return language;
    },
    get routePrefix() {
      return routePrefix;
    },
    get context() {
      return context;
    },
  };
  setContext(USER_COMPOSITION, composition);
  const pages = $derived(
    plugins.flatMap((plugin) =>
      (plugin.views || [])
        .filter((view) => view.target === "page")
        .map((view) => ({ plugin, view }))
    )
  );
  const sortedPages = $derived(
    [...pages].sort(
      (a, b) =>
        (a.view.order ?? 100) - (b.view.order ?? 100) ||
        `${a.plugin.id}:${a.view.id}`.localeCompare(`${b.plugin.id}:${b.view.id}`)
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
  const childPages = $derived(
    sortedPages.filter(({ view }) => view.parent === screen && view.navigation === "section")
  );
  const legacyTargets: Record<string, string[]> = {
    home: ["user.subscription.actions"],
    settings: ["user.profile.actions"],
    install: ["user.install.blocks"],
  };
  function navigate(path: string) {
    window.history.pushState(null, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }
  function backToSection() {
    if (client && selected?.view.parent)
      createExtensionHost(client, selected.plugin.id, t, routePrefix).navigateSection(
        selected.view.parent
      );
  }
  $effect(() => {
    parentSection = selected?.view.parent || "";
    sections = [
      ...new Set(
        plugins
          .flatMap((plugin) =>
            (plugin.views || []).map(
              (view) =>
                view.parent || (view.target?.startsWith("user.") ? view.target.split(".")[1] : "")
            )
          )
          .filter(Boolean)
      ),
    ];
    navigation = sortedPages
      .filter(({ view }) => view.navigation !== "hidden" && view.navigation !== "section")
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
    plugins = [];
    if (!client) {
      loading = false;
      return;
    }
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
    return () => controller.abort();
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
  <main class="content with-nav">
    {#if loading}<p role="status">{t("wa_loading")}</p>
    {:else if selected}
      {#if selected.view.parent}
        <Button variant="outline" onclick={backToSection}
          >{t("wa_extension_back_to_section")}</Button
        >
      {/if}
      {#key `${selected.plugin.digest}:${selected.view.id}:${language}`}
        <UserExtensionSlot plugin={selected.plugin} view={selected.view} {composition} />
      {/key}
    {:else}<p role="alert">{t("wa_extension_unavailable")}</p>{/if}
  </main>
{:else}
  {#if childPages.length}
    <nav class="content extension-subsections" aria-label={t("wa_extension_subsections")}>
      {#each childPages as { plugin, view } (`${plugin.id}:${view.id}`)}
        <Button
          variant="outline"
          onclick={() => navigate(extensionPath(plugin.id, view.id, routePrefix))}
        >
          {view.i18nKey ? t(view.i18nKey, {}, view.label) : view.label}
        </Button>
      {/each}
    </nav>
  {/if}
  <UserExtensionPoint target={`user.${screen}.content`}>{@render children?.()}</UserExtensionPoint>
  <div class="content with-nav extension-cards">
    <UserExtensionPoint target={`user.${screen}.cards`} />
    {#each legacyTargets[screen] || [] as target (target)}<UserExtensionPoint {target} />{/each}
  </div>
{/if}

<style>
  .extension-subsections {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  .extension-cards:empty {
    display: none;
  }
  :global(.phone-screen:has(> .extension-cards:not(:empty)) > main.content.with-nav) {
    padding-bottom: 0;
  }
</style>
