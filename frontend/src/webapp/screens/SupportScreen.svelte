<script lang="ts">
  import { getSupportStore } from "$lib/webapp/context";
  import { onDestroy, onMount } from "svelte";
  import { fade, slide } from "svelte/transition";
  import { Check, ChevronsUpDown, LifeBuoy, MessageSquarePlus } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import { Input, ScrollArea, Skeleton } from "$components/ui/index.js";
  import RichTextEditor from "$lib/richtext/RichTextEditor.svelte";
  import { wireTextLength } from "$lib/richtext/telegramHtml";
  import { webappRichTextLabels } from "$lib/webapp/richTextLabels.js";
  import { TicketCard } from "$components/patterns/webapp/index.js";
  import { Select, Tabs } from "$components/ui/primitives.js";
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
  type SupportCategory = "billing" | "technical" | "account" | "other";
  type SupportPriority = "normal" | "high";
  type TicketRecord = Record<string, unknown> & { ticket_id?: number };
  type DraftPayload = {
    body: string;
    category: SupportCategory;
    maxSubjectLength: number;
    open: boolean;
    priority: SupportPriority;
    subject: string;
  };

  let {
    t = (key) => key,
    maxSubjectLength = 160,
    maxBodyLength = 4000,
    user = {},
  }: {
    t?: Translate;
    maxSubjectLength?: number;
    maxBodyLength?: number;
    user?: Record<string, unknown>;
  } = $props();

  const supportStore = getSupportStore();
  // Stagger the ticket entrance, but cap it: a long list must not take a second to finish arriving.
  const CARD_STAGGER_MS = 42;
  const MAX_STAGGER_STEPS = 6;
  let subject = $state("");
  let body = $state("");
  let category = $state<SupportCategory>("other");
  let priority = $state<SupportPriority>("normal");
  let createOpen = $state(false);
  let loadedCreateDraftScope = $state("");
  let countsHint = $state<SupportTicketCounts | null>(null);
  let loadedCountsHintScope = $state("");
  let listReveal = $state<SupportListRevealState>({ phase: "pending", skeletonCount: 0 });
  let persistedCountsKey = "";
  const selectContentProps = { trapFocus: false } as Record<string, unknown>;
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
  const categoryOptions = $derived([
    { value: "billing", label: t("wa_support_category_billing") },
    { value: "technical", label: t("wa_support_category_technical") },
    { value: "account", label: t("wa_support_category_account") },
    { value: "other", label: t("wa_support_category_other") },
  ] as { value: SupportCategory; label: string }[]);
  const priorityOptions = $derived([
    { value: "normal", label: t("wa_support_priority_normal") },
    { value: "high", label: t("wa_support_priority_high") },
  ] as { value: SupportPriority; label: string }[]);
  const statusTabs = $derived([
    {
      value: "active",
      label: t("wa_support_filter_active", {}, "Active"),
      count: counts?.active || 0,
    },
    {
      value: "awaiting_admin",
      label: t("wa_support_status_awaiting_admin", {}, "Awaiting admin"),
      count: counts?.awaiting_admin || 0,
    },
    {
      value: "awaiting_user",
      label: t("wa_support_status_awaiting_user", {}, "Awaiting user"),
      count: counts?.awaiting_user || 0,
    },
    {
      value: "closed",
      label: t("wa_support_status_closed", {}, "Closed"),
      count: counts?.closed || 0,
    },
  ]);
  const selectedCategory = $derived(
    categoryOptions.find((option) => option.value === category) || categoryOptions[0]
  );
  const selectedPriority = $derived(
    priorityOptions.find((option) => option.value === priority) || priorityOptions[0]
  );
  const draftScope = $derived(supportDraftScope(user));
  const editorLabels = $derived(webappRichTextLabels(t));
  // A stored draft is markup, so it cannot be cut at the message limit without
  // splitting a tag. The message limit is enforced on the visible text below;
  // this only keeps a runaway draft out of local storage.
  const DRAFT_BODY_STORAGE_CAP = 32_000;
  // The server limit counts what an admin reads, not the markup around it.
  const bodyLength = $derived(wireTextLength(body, "html"));

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
      category,
      priority,
      open: createOpen,
      maxSubjectLength,
    });
  });

  onMount(() => {
    supportStore.loadList();
  });

  onDestroy(() => revealController.destroy());

  async function createTicket() {
    const currentDraftScope = draftScope;
    const ticket = await supportStore.createTicket({
      subject,
      body,
      body_format: "html",
      category,
      priority,
    });
    if (ticket) {
      clearSupportDraft("new", currentDraftScope);
      subject = "";
      body = "";
      category = "other";
      priority = "normal";
      createOpen = false;
    }
  }

  function ticketMotionStyle(index: number) {
    return `--motion-delay:${Math.min(Math.max(0, index), MAX_STAGGER_STEPS) * CARD_STAGGER_MS}ms;`;
  }

  function optionValue<T extends string>(
    options: { value: T; label: string }[],
    value: unknown,
    fallback: T
  ) {
    return options.some((option) => option.value === value) ? (value as T) : fallback;
  }

  function loadCreateDraft(scope: string) {
    const draft = readSupportDraft("new", scope);
    subject = typeof draft?.subject === "string" ? draft.subject.slice(0, maxSubjectLength) : "";
    body = typeof draft?.body === "string" ? draft.body.slice(0, DRAFT_BODY_STORAGE_CAP) : "";
    category = optionValue(categoryOptions, draft?.category, "other");
    priority = optionValue(priorityOptions, draft?.priority, "normal");
    createOpen = Boolean(draft?.open || subject.trim() || body.trim());
    loadedCreateDraftScope = scope;
  }

  function persistCreateDraft(scope: string, draft: DraftPayload) {
    const draftSubject = String(draft.subject || "").slice(0, draft.maxSubjectLength);
    const draftBody = String(draft.body || "").slice(0, DRAFT_BODY_STORAGE_CAP);
    const hasDraft =
      Boolean(draftSubject.trim()) ||
      Boolean(draftBody.trim()) ||
      draft.category !== "other" ||
      draft.priority !== "normal";

    if (!hasDraft) {
      clearSupportDraft("new", scope);
      return;
    }

    writeSupportDraft("new", scope, "new", {
      subject: draftSubject,
      body: draftBody,
      category: draft.category,
      priority: draft.priority,
      open: draft.open || Boolean(draftSubject.trim() || draftBody.trim()),
    });
  }
</script>

<main class="content with-nav support-screen">
  <Card class="support-overview-card">
    <div class="support-heading-row">
      <span class="support-heading-icon" aria-hidden="true">
        <LifeBuoy size={42} />
      </span>
      <div class="support-heading-copy">
        <h1>{t("wa_support_title")}</h1>
        <p>{t("wa_support_subtitle")}</p>
      </div>
    </div>

    <button
      class:active={createOpen}
      class="support-new-ticket-button"
      type="button"
      aria-expanded={createOpen}
      onclick={() => (createOpen = !createOpen)}
    >
      <span class="support-new-ticket-icon">
        <MessageSquarePlus size={20} />
      </span>
      <span>
        <strong>{t("wa_support_new_ticket")}</strong>
        <small>{t("wa_support_contact_support")}</small>
      </span>
      <ChevronsUpDown size={18} />
    </button>

    {#if createOpen}
      <div class="support-create-panel" in:slide={{ duration: 180 }} out:slide={{ duration: 140 }}>
        <div class="support-create-panel-inner" in:fade={{ duration: 140 }}>
          <label class="support-field">
            <span>{t("wa_support_subject")}</span>
            <Input
              class="input"
              bind:value={subject}
              maxlength={maxSubjectLength}
              placeholder={t("wa_support_subject_placeholder")}
            />
          </label>

          <div class="support-create-grid">
            <label class="support-field">
              <span>{t("wa_support_category")}</span>
              <Select.Root
                type="single"
                value={category}
                items={categoryOptions}
                onValueChange={(value: string) =>
                  (category = optionValue(categoryOptions, value, "other"))}
              >
                <Select.Trigger
                  class="support-select-trigger"
                  aria-label={t("wa_support_category")}
                >
                  <span>{selectedCategory.label}</span>
                  <ChevronsUpDown size={16} />
                </Select.Trigger>
                <Select.Content
                  class="support-select-content"
                  side="bottom"
                  align="start"
                  sideOffset={6}
                  {...selectContentProps}
                >
                  <Select.Viewport class="support-select-viewport">
                    {#each categoryOptions as option (option.value)}
                      <Select.Item
                        value={option.value}
                        label={option.label}
                        class="support-select-item"
                      >
                        <span>{option.label}</span>
                        <Check size={15} class="support-select-check" />
                      </Select.Item>
                    {/each}
                  </Select.Viewport>
                </Select.Content>
              </Select.Root>
            </label>

            <label class="support-field">
              <span>{t("wa_support_priority")}</span>
              <Select.Root
                type="single"
                value={priority}
                items={priorityOptions}
                onValueChange={(value: string) =>
                  (priority = optionValue(priorityOptions, value, "normal"))}
              >
                <Select.Trigger
                  class="support-select-trigger"
                  aria-label={t("wa_support_priority")}
                >
                  <span>{selectedPriority.label}</span>
                  <ChevronsUpDown size={16} />
                </Select.Trigger>
                <Select.Content
                  class="support-select-content"
                  side="bottom"
                  align="start"
                  sideOffset={6}
                  {...selectContentProps}
                >
                  <Select.Viewport class="support-select-viewport">
                    {#each priorityOptions as option (option.value)}
                      <Select.Item
                        value={option.value}
                        label={option.label}
                        class="support-select-item"
                      >
                        <span>{option.label}</span>
                        <Check size={15} class="support-select-check" />
                      </Select.Item>
                    {/each}
                  </Select.Viewport>
                </Select.Content>
              </Select.Root>
            </label>
          </div>

          <div class="support-field">
            <span>{t("wa_support_message")}</span>
            <RichTextEditor
              value={body}
              onInput={(next) => (body = next)}
              labels={editorLabels}
              placeholder={t("wa_support_message_placeholder")}
              minHeight="120px"
              autolink
            />
            <small class:is-over={bodyLength > maxBodyLength}>{bodyLength}/{maxBodyLength}</small>
          </div>

          <Button
            class="wide support-submit-button"
            size="lg"
            disabled={creating || !subject.trim() || !bodyLength || bodyLength > maxBodyLength}
            onclick={createTicket}
          >
            <MessageSquarePlus size={18} />
            {creating ? t("wa_support_creating") : t("wa_support_create")}
          </Button>
        </div>
      </div>
    {/if}
  </Card>

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
        <strong>{t("wa_support_no_open_tickets")}</strong>
        <small>{t("wa_support_empty_hint")}</small>
      </div>
    {/if}
  </Card>
</main>
