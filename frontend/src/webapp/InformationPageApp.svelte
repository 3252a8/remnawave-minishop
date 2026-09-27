<script lang="ts">
  import { onMount } from "svelte";
  import { FileText, Home, TriangleAlert } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import {
    buildDocumentApiPath,
    buildInformationPageApiPath,
    documentHref,
    hasInformationPageMarkdown,
    publicInformationDocuments,
    sidebarInformationDocumentGroups,
    type InformationPageNavigationGroup,
  } from "$lib/webapp/informationPages.js";
  import { renderMarkdown } from "$lib/webapp/markdown.js";
  import { createApiClient, unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import type { Translate } from "$lib/webapp/types.js";

  const { api } = createApiClient();

  let {
    documentSlug = "",
    pagePath = "",
    request = api,
    routePrefix = "",
    shellStyle = "",
    shellThemeClass = "",
    shellToneClass = "theme-dark",
    themeCssHref = "",
    t,
  }: {
    documentSlug?: string;
    pagePath?: string;
    request?: ApiClient["api"];
    routePrefix?: string;
    shellStyle?: string;
    shellThemeClass?: string;
    shellToneClass?: string;
    themeCssHref?: string;
    t: Translate;
  } = $props();

  let markdown = $state("");
  let loading = $state(true);
  let unavailable = $state(false);
  let navigationGroups = $state<InformationPageNavigationGroup[]>([]);
  let documentTitle = $state("");
  const renderedMarkdown = $derived(renderMarkdown(markdown));
  const currentHref = $derived(documentSlug ? documentHref(documentSlug) : pagePath);
  const heading = $derived(
    documentTitle || (documentSlug ? t("wa_information_page_title", {}, "Information") : pagePath)
  );

  onMount(() => {
    let mounted = true;
    const loadPage = async (): Promise<{ markdown: string; title: string } | null> => {
      try {
        if (documentSlug) {
          const document = unwrap(await request(buildDocumentApiPath(documentSlug)));
          return { markdown: document.markdown, title: document.title };
        }
      } catch {
        // A managed document may share a route with a legacy file-backed page.
        // The backend resolves documents first; retain the legacy page as fallback.
      }
      if (!pagePath) return null;
      try {
        const page = unwrap(await request(buildInformationPageApiPath(pagePath)));
        return { markdown: page.markdown, title: "" };
      } catch {
        return null;
      }
    };

    const loadDocuments = async () => {
      try {
        return publicInformationDocuments(unwrap(await request("/documents")));
      } catch {
        return [];
      }
    };

    void (async () => {
      const [currentPage, documents] = await Promise.all([loadPage(), loadDocuments()]);
      if (!mounted) return;

      if (currentPage && hasInformationPageMarkdown(currentPage.markdown)) {
        markdown = currentPage.markdown;
      } else unavailable = true;
      navigationGroups = sidebarInformationDocumentGroups(documents);
      documentTitle =
        currentPage?.title ||
        documents.find((document) => document.slug === documentSlug)?.title ||
        "";
      loading = false;
    })();

    return () => {
      mounted = false;
    };
  });
</script>

<svelte:head>
  {#if themeCssHref}<link rel="stylesheet" href={themeCssHref} />{/if}
</svelte:head>

<div class="app-shell {shellToneClass} {shellThemeClass}" style={shellStyle}>
  <main class="information-page content">
    <div class="information-page-topbar">
      <Button
        href={`${routePrefix}/`}
        variant="secondary"
        size="icon"
        aria-label={t("wa_nav_home", {}, "Home")}
        title={t("wa_nav_home", {}, "Home")}
      >
        <Home size={20} />
      </Button>
      <div>
        <h1>{heading}</h1>
        <p>{currentHref}</p>
      </div>
    </div>

    <div class="information-page-layout">
      {#if navigationGroups.length > 0}
        <aside class="information-page-sidebar">
          <Card class="information-page-navigation">
            <h2>{t("wa_information_page_navigation", {}, "Documents")}</h2>
            <nav aria-label={t("wa_information_page_navigation", {}, "Documents")}>
              {#each navigationGroups as group (group.title)}
                {#if group.title}<h3>{group.title}</h3>{/if}
                <div class="information-page-navigation-group">
                  {#each group.documents as document (document.slug)}
                    <Button
                      href={`${routePrefix}${documentHref(document.slug)}`}
                      variant={documentSlug === document.slug ? "secondary" : "ghost"}
                      class="information-page-navigation-link"
                      aria-current={documentSlug === document.slug ? "page" : undefined}
                    >
                      <FileText size={18} />
                      <span>{document.title}</span>
                    </Button>
                  {/each}
                </div>
              {/each}
            </nav>
          </Card>
        </aside>
      {/if}

      <div class="information-page-content">
        {#if loading}
          <Card class="information-page-message" aria-label={t("wa_loading", {}, "Loading")}>
            <span class="information-page-skeleton"></span>
            <span class="information-page-skeleton"></span>
            <span class="information-page-skeleton information-page-skeleton--short"></span>
          </Card>
        {:else if unavailable}
          <Card class="information-page-message information-page-message--error">
            <TriangleAlert size={25} />
            <strong>{t("wa_information_page_unavailable_title", {}, "Page unavailable")}</strong>
            <p>
              {t(
                "wa_information_page_unavailable_description",
                {},
                "This page could not be loaded."
              )}
            </p>
          </Card>
        {:else}
          <Card class="information-page-card">
            <article class="information-markdown">{@html renderedMarkdown}</article>
          </Card>
        {/if}
      </div>
    </div>
  </main>
</div>

<style>
  .information-page {
    box-sizing: border-box;
    width: min(100%, 1264px);
    min-height: 100dvh;
    margin: 0 auto;
    padding: max(18px, var(--content-safe-area-top)) max(16px, var(--safe-inline))
      max(28px, var(--content-safe-area-bottom)) max(16px, var(--safe-inline));
    align-content: start;
    gap: clamp(18px, 2.5vw, 28px);
  }
  .information-page-topbar {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .information-page-topbar h1,
  .information-page-topbar p {
    margin: 0;
  }
  .information-page-topbar h1 {
    font-size: clamp(1.1rem, 2vw, 1.3rem);
    line-height: 1.2;
  }
  .information-page-topbar p {
    margin-top: 3px;
    color: var(--muted);
    font-size: 0.8rem;
  }
  .information-page-layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    align-items: start;
    gap: clamp(18px, 2.5vw, 28px);
  }
  .information-page-content {
    min-width: 0;
  }
  .information-page-sidebar {
    min-width: 0;
  }
  .information-page :global(.information-page-navigation) {
    padding: 10px;
  }
  .information-page-sidebar h2,
  .information-page-sidebar h3 {
    margin: 4px 8px 10px;
    color: var(--muted);
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .information-page-sidebar nav {
    display: grid;
    gap: 14px;
  }
  .information-page-sidebar h3 {
    margin-top: 0;
  }
  .information-page-navigation-group {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 6px;
  }
  .information-page-sidebar :global(.information-page-navigation-link) {
    min-width: 0;
    min-height: 42px;
    padding: 8px 10px;
    gap: 8px;
    justify-content: flex-start;
    text-align: left;
    white-space: normal;
    overflow-wrap: anywhere;
  }
  .information-page-sidebar :global(.information-page-navigation-link svg) {
    flex: 0 0 auto;
  }
  .information-page-message {
    display: grid;
    justify-items: start;
    gap: 10px;
  }
  .information-page-message--error {
    color: var(--text);
  }
  .information-page-message p {
    margin: 0;
    color: var(--muted);
  }
  .information-page-skeleton {
    width: 100%;
    height: 14px;
    border-radius: 8px;
    background: color-mix(in srgb, var(--text) 9%, transparent);
  }
  .information-page-skeleton--short {
    width: 56%;
  }
  .information-page :global(.information-page-card) {
    overflow: hidden;
    padding: clamp(18px, 4vw, 36px);
  }
  .information-markdown {
    max-width: 76ch;
    margin: 0 auto;
    overflow-wrap: anywhere;
    color: var(--text);
    font-size: clamp(0.975rem, 1.1vw, 1.05rem);
    line-height: 1.72;
  }
  .information-markdown :global(:first-child) {
    margin-top: 0;
  }
  .information-markdown :global(:last-child) {
    margin-bottom: 0;
  }
  .information-markdown :global(h1),
  .information-markdown :global(h2),
  .information-markdown :global(h3),
  .information-markdown :global(h4) {
    margin: 1.7em 0 0.65em;
    color: var(--text);
    line-height: 1.22;
    font-weight: 800;
  }
  .information-markdown :global(h1) {
    font-size: clamp(1.7rem, 3vw, 2.15rem);
  }
  .information-markdown :global(h2) {
    font-size: clamp(1.35rem, 2.3vw, 1.65rem);
  }
  .information-markdown :global(h3) {
    font-size: clamp(1.12rem, 1.8vw, 1.3rem);
  }
  .information-markdown :global(h4) {
    font-size: 1rem;
  }
  .information-markdown :global(p),
  .information-markdown :global(ul),
  .information-markdown :global(ol),
  .information-markdown :global(blockquote) {
    margin: 0 0 1.15em;
  }
  .information-markdown :global(ul),
  .information-markdown :global(ol) {
    padding-left: 1.5em;
  }
  .information-markdown :global(li + li) {
    margin-top: 0.38em;
  }
  .information-markdown :global(a) {
    color: var(--accent);
    text-underline-offset: 2px;
  }
  .information-markdown :global(blockquote) {
    padding: 0.1em 0 0.1em 16px;
    border-left: 3px solid var(--accent);
    color: var(--muted);
  }
  .information-markdown :global(code) {
    padding: 0.15em 0.35em;
    border-radius: 5px;
    background: var(--panel-2);
    font-size: 0.9em;
  }
  .information-markdown :global(pre) {
    overflow-x: auto;
    margin: 0 0 1.15em;
    padding: 16px;
    border-radius: var(--radius-inner);
    background: var(--panel-2);
  }
  .information-markdown :global(pre code) {
    padding: 0;
    background: transparent;
  }
  .information-markdown :global(img) {
    display: block;
    max-width: 100%;
    height: auto;
    margin: 1em auto;
    border-radius: var(--radius-inner);
  }
  .information-markdown :global(table) {
    display: block;
    margin: 0 0 1.15em;
    width: max-content;
    max-width: 100%;
    overflow-x: auto;
    border-collapse: collapse;
  }
  .information-markdown :global(th),
  .information-markdown :global(td) {
    padding: 10px 12px;
    border: 1px solid var(--border);
    text-align: left;
  }
  .information-markdown :global(hr) {
    height: 1px;
    margin: 1.8em 0;
    border: 0;
    background: var(--border);
  }
  @media (min-width: 640px) {
    .information-page {
      padding-right: max(28px, var(--safe-inline));
      padding-left: max(28px, var(--safe-inline));
    }
    .information-page-navigation-group {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
  @media (min-width: 900px) {
    .information-page-layout {
      grid-template-columns: 300px minmax(0, 1fr);
    }
    .information-page-sidebar {
      position: sticky;
      top: max(18px, var(--content-safe-area-top));
    }
    .information-page-navigation-group {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
