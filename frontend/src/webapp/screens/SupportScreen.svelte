<script lang="ts">
  import { getSupportStore } from "$lib/webapp/context";
  import { onDestroy, onMount, tick } from "svelte";
  import { fade } from "svelte/transition";
  import { ArrowLeft, ChevronRight, LifeBuoy, MessageSquarePlus } from "$components/ui/icons.js";
  import Card from "$components/ui/card.svelte";
  import { Button, Input, ScrollArea, Skeleton } from "$components/ui/index.js";
  import { isSupportCreatePath, withRoutePrefix } from "$lib/webapp/routes.js";
  import { webappRichTextLabels } from "$lib/webapp/richTextLabels.js";
  import { TicketCard } from "$components/patterns/webapp/index.js";
  import TicketComposer from "$components/patterns/webapp/TicketComposer.svelte";
  import { Tabs } from "$components/ui/primitives.js";
  import {
    clearSupportDraft,
    readSupportDraft,
    supportDraftScope,
    writeSupportDraft,
  } from "$lib/webapp/supportDrafts.js";
  import type { SupportTicketCounts } from "$lib/webapp/supportListHint.js";
  import {
    expectedTicketCount,
    readSupportCountsHint,
    writeSupportCountsHint,
  } from "$lib/webapp/supportListHint.js";
  import type { SupportListRevealState } from "$lib/webapp/supportListReveal.js";
  import { createSupportListReveal } from "$lib/webapp/supportListReveal.js";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type TicketRecord = Record<string, unknown> & { ticket_id?: number };
  type DraftPayload = {
    body: string;
    maxSubjectLength: number;
    open: boolean;
    subject: string;
  };

  let {
    t = (key) => key,
    maxSubjectLength = 160,
    maxBodyLength = 4000,
    user = {},
    routePrefix = "",
  }: {
    t?: Translate;
    maxSubjectLength?: number;
    maxBodyLength?: number;
    user?: Record<string, unknown>;
    routePrefix?: string;
  } = $props();

  const supportStore = getSupportStore();
  // Stagger the ticket entrance, but cap it: a long list must not take a second to finish arriving.
  const CARD_STAGGER_MS = 42;
  const MAX_STAGGER_STEPS = 6;
  let subject = $state("");
  let body = $state("");
  let image = $state<File | null>(null);
  let createOpen = $state(false);
  let viewportHeight = $state("100dvh");
  let viewportTop = $state("0px");
  let compactViewport = $state(false);
  let createHeading = $state<HTMLHeadingElement | null>(null);
  let loadedCreateDraftScope = $state("");
  let countsHint = $state<SupportTicketCounts | null>(null);
  let loadedCountsHintScope = $state("");
  let listReveal = $state<SupportListRevealState>({ phase: "pending", skeletonCount: 0 });
  let persistedCountsKey = "";
  const revealController = createSupportListReveal({ onChange: (next) => (listReveal = next) });

  const tickets = $derived(supportStore.tickets);
  const creating = $derived(supportStore.creating);
  const statusFilter = $derived(supportStore.statusFilter);
  const counts = $derived(supportStore.counts);
  const activeFilter = $derived(statusFilter || "all");
  // The store keeps the previous tab's tickets until the new request lands; they are not an answer
  // for the tab the user is looking at now.
  const listResolved = $derived(supportStore.loadedFilter === activeFilter);
  const visibleTickets = $derived(listResolved ? tickets : []);
  // Live counts beat the cached ones the moment a list response has landed in this session.
  const expectedCount = $derived(
    expectedTicketCount(supportStore.loadedFilter ? counts : countsHint, activeFilter)
  );
  const statusTabs = $derived([
    {
      value: "active",
      label: t("wa_support_filter_active", {}, "Open"),
      count: counts?.active || 0,
    },
    {
      value: "closed",
      label: t("wa_support_filter_history", {}, "History"),
      count: counts?.closed || 0,
    },
  ]);
  const emptyState = $derived(
    activeFilter === "closed"
      ? {
          title: t("wa_support_no_history_tickets", {}, "No ticket history"),
          hint: t(
            "wa_support_history_empty_hint",
            {},
            "Resolved and closed requests will appear here."
          ),
        }
      : {
          title: t("wa_support_no_open_tickets", {}, "No open requests"),
          hint: t("wa_support_empty_hint"),
        }
  );
  const draftScope = $derived(supportDraftScope(user));
  const editorLabels = $derived(webappRichTextLabels(t));
  const imageLabels = $derived({
    drop: t("wa_message_image_drop"),
    choose: t("wa_message_image_choose"),
    upload: t("wa_message_image_upload"),
    remove: t("wa_message_image_remove"),
    hint: t("wa_message_image_hint"),
    invalidType: t("wa_message_image_invalid_type"),
    tooLarge: t("wa_message_image_too_large"),
    previewAlt: t("wa_message_image_preview_alt"),
  });
  // A stored draft is markup, so it cannot be cut at the message limit without
  // splitting a tag. The message limit is enforced on the visible text below;
  // this only keeps a runaway draft out of local storage.
  const DRAFT_BODY_STORAGE_CAP = 32_000;

  $effect.pre(() => {
    if (!draftScope || draftScope === loadedCreateDraftScope) return;
    loadCreateDraft(draftScope);
  });

  $effect.pre(() => {
    if (!draftScope || draftScope === loadedCountsHintScope) return;
    countsHint = readSupportCountsHint(draftScope);
    loadedCountsHintScope = draftScope;
  });

  $effect.pre(() => {
    listReveal = revealController.sync({ expectedCount, resolved: listResolved });
  });

  $effect(() => {
    if (!draftScope || !supportStore.loadedFilter) return;
    const key = `${draftScope}:${JSON.stringify(counts)}`;
    if (key === persistedCountsKey) return;
    persistedCountsKey = key;
    writeSupportCountsHint(draftScope, counts);
  });

  $effect(() => {
    if (!draftScope || draftScope !== loadedCreateDraftScope) return;
    persistCreateDraft(draftScope, {
      subject,
      body,
      open: createOpen,
      maxSubjectLength,
    });
  });

  onMount(() => {
    const viewport = window.visualViewport;
    const syncViewport = () => {
      const height = viewport?.height ?? window.innerHeight;
      viewportHeight = `${height}px`;
      viewportTop = `${viewport?.offsetTop ?? 0}px`;
      compactViewport = height <= 600;
    };
    const syncCreateRoute = () => {
      createOpen = isSupportCreatePath(window.location.pathname, routePrefix);
    };
    syncViewport();
    syncCreateRoute();
    viewport?.addEventListener("resize", syncViewport);
    viewport?.addEventListener("scroll", syncViewport);
    window.addEventListener("resize", syncViewport);
    window.addEventListener("popstate", syncCreateRoute);
    supportStore.loadList();
    return () => {
      viewport?.removeEventListener("resize", syncViewport);
      viewport?.removeEventListener("scroll", syncViewport);
      window.removeEventListener("resize", syncViewport);
      window.removeEventListener("popstate", syncCreateRoute);
    };
  });

  onDestroy(() => revealController.destroy());

  async function openCreatePage() {
    createOpen = true;
    const target = withRoutePrefix("/support/new", routePrefix);
    if (window.location.protocol !== "file:" && window.location.pathname !== target) {
      window.history.pushState(
        { minishopSupportCreate: true },
        "",
        `${target}${window.location.search}${window.location.hash}`
      );
    }
    await tick();
    createHeading?.focus();
    window.scrollTo(0, 0);
  }

  function closeCreatePage() {
    if (window.history.state?.minishopSupportCreate === true) {
      window.history.back();
      return;
    }
    createOpen = false;
    const target = withRoutePrefix("/support", routePrefix);
    if (window.location.protocol !== "file:" && window.location.pathname !== target) {
      window.history.pushState(
        null,
        "",
        `${target}${window.location.search}${window.location.hash}`
      );
    }
    window.scrollTo(0, 0);
  }

  async function createTicket() {
    const currentDraftScope = draftScope;
    const ticket = await supportStore.createTicket(
      {
        subject,
        body,
        body_format: "html",
        category: "other",
        priority: "normal",
      },
      image
    );
    if (ticket) {
      clearSupportDraft("new", currentDraftScope);
      subject = "";
      body = "";
      image = null;
      createOpen = false;
    }
  }

  function ticketMotionStyle(index: number) {
    return `--motion-delay:${Math.min(Math.max(0, index), MAX_STAGGER_STEPS) * CARD_STAGGER_MS}ms;`;
  }

  function loadCreateDraft(scope: string) {
    const draft = readSupportDraft("new", scope);
    subject = typeof draft?.subject === "string" ? draft.subject.slice(0, maxSubjectLength) : "";
    body = typeof draft?.body === "string" ? draft.body.slice(0, DRAFT_BODY_STORAGE_CAP) : "";
    loadedCreateDraftScope = scope;
  }

  function persistCreateDraft(scope: string, draft: DraftPayload) {
    const draftSubject = String(draft.subject || "").slice(0, draft.maxSubjectLength);
    const draftBody = String(draft.body || "").slice(0, DRAFT_BODY_STORAGE_CAP);
    const hasDraft = Boolean(draftSubject.trim()) || Boolean(draftBody.trim());

    if (!hasDraft) {
      clearSupportDraft("new", scope);
      return;
    }

    writeSupportDraft("new", scope, "new", {
      subject: draftSubject,
      body: draftBody,
      open: draft.open || Boolean(draftSubject.trim() || draftBody.trim()),
    });
  }
</script>

<main
  class="content with-nav support-screen"
  class:support-screen--create={createOpen}
  class:support-screen--compact={createOpen && compactViewport}
  style={`--support-create-viewport-height:${viewportHeight};--support-create-viewport-top:${viewportTop}`}
>
  <Card class={createOpen ? "support-overview-card support-create-card" : "support-overview-card"}>
    {#if createOpen}
      <header class="support-create-header">
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("wa_back")}
          title={t("wa_back")}
          onclick={closeCreatePage}
        >
          <ArrowLeft size={20} />
        </Button>
        <h1 bind:this={createHeading} tabindex="-1">{t("wa_support_new_ticket")}</h1>
      </header>
    {:else}
      <div class="support-heading-row">
        <span class="support-heading-icon" aria-hidden="true">
          <LifeBuoy size={42} />
        </span>
        <div class="support-heading-copy">
          <h1>{t("wa_support_title")}</h1>
          <p>{t("wa_support_subtitle")}</p>
        </div>
      </div>

      <button class="support-new-ticket-button" type="button" onclick={openCreatePage}>
        <span class="support-new-ticket-icon">
          <MessageSquarePlus size={20} />
        </span>
        <span>
          <strong>{t("wa_support_new_ticket")}</strong>
          <small>{t("wa_support_contact_support")}</small>
        </span>
        <ChevronRight size={18} />
      </button>
    {/if}

    {#if createOpen}
      <div class="support-create-panel">
        <div class="support-create-panel-inner">
          <label class="support-field">
            <span>{t("wa_support_subject")}</span>
            <Input
              class="input"
              bind:value={subject}
              maxlength={maxSubjectLength}
              placeholder={t("wa_support_subject_placeholder")}
            />
          </label>

          <div class="support-field support-create-message-field">
            <span>{t("wa_support_message")}</span>
            <TicketComposer
              bind:value={body}
              bind:image
              labels={editorLabels}
              {imageLabels}
              placeholder={t("wa_support_message_placeholder")}
              sendLabel={creating ? t("wa_support_creating") : t("wa_support_create")}
              showSendLabel
              fillAvailable
              sending={creating}
              sendDisabled={!subject.trim()}
              maxLength={maxBodyLength}
              onSend={createTicket}
            />
          </div>
        </div>
      </div>
    {/if}
  </Card>

  {#if !createOpen}
    <Card class="support-list-card">
      <Tabs.Root
        value={statusFilter}
        onValueChange={(value) => supportStore.setStatusFilter(value || "all")}
        class="support-status-tabs"
      >
        <Tabs.List class="support-status-tabs-list" aria-label={t("wa_support_filter_label")}>
          {#each statusTabs as tab (tab.value)}
            <Tabs.Trigger value={tab.value} class="support-status-tabs-trigger">
              <span>{tab.label}</span>
              <b>{tab.count}</b>
            </Tabs.Trigger>
          {/each}
        </Tabs.List>
      </Tabs.Root>

      {#if listReveal.phase === "skeleton"}
        <ScrollArea class="support-ticket-list-scroll" maxHeight="none">
          <div
            class="support-user-list-skeleton motion-fade-up"
            role="status"
            aria-label={t("wa_loading")}
          >
            {#each Array(listReveal.skeletonCount) as _, index (index)}
              <article class="support-user-ticket-skeleton">
                <span class="support-user-ticket-skeleton-main">
                  <Skeleton variant="title" width="min(420px, 76%)" />
                  <Skeleton variant="short" width="min(260px, 58%)" />
                </span>
                <span class="support-user-ticket-skeleton-side">
                  <Skeleton variant="badge" width="92px" />
                  <Skeleton variant="tiny" width="64px" />
                </span>
              </article>
            {/each}
          </div>
        </ScrollArea>
      {:else if listReveal.phase === "pending"}
        <div class="support-list-probe" aria-hidden="true"></div>
      {:else if visibleTickets.length}
        <ScrollArea class="support-ticket-list-scroll" maxHeight="none">
          <div class="ticket-list">
            {#each visibleTickets as ticket, index (ticket.ticket_id)}
              <div class="ticket-list-item motion-enter-card" style={ticketMotionStyle(index)}>
                <TicketCard
                  {ticket}
                  {t}
                  onOpen={(item: TicketRecord) => supportStore.openTicket(item.ticket_id || 0)}
                />
              </div>
            {/each}
          </div>
        </ScrollArea>
      {:else}
        <div class="support-empty-state" in:fade={{ duration: 180 }}>
          <MessageSquarePlus size={34} />
          <strong>{emptyState.title}</strong>
          <small>{emptyState.hint}</small>
        </div>
      {/if}
    </Card>
  {/if}
</main>

<style>
  .support-create-header {
    display: grid;
    grid-template-columns: 44px minmax(0, 1fr);
    align-items: center;
    gap: 12px;
  }

  .support-create-header h1 {
    margin: 0;
    outline: none;
    font-size: 20px;
    line-height: 1.3;
  }

  :global(.phone-screen > main.content.support-screen--create) {
    height: calc(100dvh - 68px);
    min-height: 0;
    grid-template-rows: minmax(0, 1fr);
    align-content: stretch;
    overflow: hidden;
    padding-bottom: 0;
  }

  :global(.support-screen--create > .support-create-card) {
    min-height: 0;
    grid-template-rows: auto minmax(0, 1fr);
    gap: 18px;
    overflow: hidden;
    padding: 18px;
  }

  :global(.support-create-card .support-create-panel) {
    min-height: 0;
    grid-template-rows: minmax(0, 1fr);
    border: 0;
    background: transparent;
    box-shadow: none;
  }

  :global(.support-create-card .support-create-panel-inner) {
    min-height: 0;
    grid-template-rows: auto minmax(0, 1fr);
    gap: 18px;
    padding: 0;
  }

  .support-create-message-field {
    min-height: 0;
    grid-template-rows: auto minmax(0, 1fr);
  }

  @media (min-width: 1024px) {
    :global(.phone-screen > main.content.support-screen--create) {
      width: 100%;
      max-width: none;
    }
  }

  @media (max-width: 1023px) {
    :global(body:has(.support-screen--create)) {
      overflow: hidden;
    }

    :global(.phone-screen:has(.support-screen--create)) {
      min-height: 0;
      padding: 0;
    }

    :global(.phone-screen:has(.support-screen--create) > .app-header),
    :global(.phone-screen:has(.support-screen--create) > .bottom-nav) {
      display: none;
    }

    :global(.phone-screen > main.content.support-screen--create) {
      position: fixed;
      inset-inline: 0;
      top: var(--support-create-viewport-top, 0px);
      width: min(100%, 560px);
      height: var(--support-create-viewport-height, 100dvh);
      margin: 0 auto;
      padding: var(--content-safe-area-top) 0 var(--content-safe-area-bottom);
      animation: none;
    }

    :global(.support-screen--create > .support-create-card) {
      border: 0;
      border-radius: 0;
      box-shadow: none;
    }
    :global(.support-screen--compact > .support-create-card) {
      gap: 10px;
      padding: 10px 12px;
    }

    :global(.support-screen--compact .support-create-panel-inner) {
      gap: 10px;
    }
  }
</style>
