<script lang="ts">
  import { getContext, onMount } from "svelte";
  import { fade, slide } from "svelte/transition";
  import { Check, ChevronsUpDown, LifeBuoy, MessageSquarePlus } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import { Input, ScrollArea, Skeleton, Textarea } from "$components/ui/index.js";
  import { TicketCard } from "$components/patterns/webapp/index.js";
  import { Select, Tabs } from "$components/ui/primitives.js";
  import {
    clearSupportDraft,
    readSupportDraft,
    supportDraftScope,
    writeSupportDraft,
  } from "$lib/webapp/supportDrafts.js";
  import type { SupportStore } from "$lib/webapp/stores/supportStore";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type SupportCategory = "billing" | "technical" | "account" | "other";
  type SupportPriority = "normal" | "high";
  type TicketRecord = Record<string, unknown> & { ticket_id?: number };
  type DraftPayload = {
    body: string;
    category: SupportCategory;
    maxBodyLength: number;
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

  const supportStore = getContext("supportStore") as SupportStore;
  let subject = $state("");
  let body = $state("");
  let category = $state<SupportCategory>("other");
  let priority = $state<SupportPriority>("normal");
  let createOpen = $state(false);
  let loadedCreateDraftScope = $state("");
  const selectContentProps = { trapFocus: false } as Record<string, unknown>;

  const tickets = $derived(supportStore.tickets);
  const loading = $derived(supportStore.loading);
  const creating = $derived(supportStore.creating);
  const statusFilter = $derived(supportStore.statusFilter);
  const counts = $derived(supportStore.counts);
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
      label: t("wa_support_filter_active", {}, "Активные"),
      count: counts?.active || 0,
    },
    {
      value: "awaiting_admin",
      label: t("wa_support_status_awaiting_admin", {}, "Ждет админа"),
      count: counts?.awaiting_admin || 0,
    },
    {
      value: "awaiting_user",
      label: t("wa_support_status_awaiting_user", {}, "Ждет пользователя"),
      count: counts?.awaiting_user || 0,
    },
    {
      value: "closed",
      label: t("wa_support_status_closed", {}, "Закрытые"),
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

  $effect.pre(() => {
    if (!draftScope || draftScope === loadedCreateDraftScope) return;
    loadCreateDraft(draftScope);
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
      maxBodyLength,
    });
  });

  onMount(() => {
    supportStore.loadList();
  });

  async function createTicket() {
    const currentDraftScope = draftScope;
    const ticket = await supportStore.createTicket({ subject, body, category, priority });
    if (ticket) {
      clearSupportDraft("new", currentDraftScope);
      subject = "";
      body = "";
      category = "other";
      priority = "normal";
      createOpen = false;
    }
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
    body = typeof draft?.body === "string" ? draft.body.slice(0, maxBodyLength) : "";
    category = optionValue(categoryOptions, draft?.category, "other");
    priority = optionValue(priorityOptions, draft?.priority, "normal");
    createOpen = Boolean(draft?.open || subject.trim() || body.trim());
    loadedCreateDraftScope = scope;
  }

  function persistCreateDraft(scope: string, draft: DraftPayload) {
    const draftSubject = String(draft.subject || "").slice(0, draft.maxSubjectLength);
    const draftBody = String(draft.body || "").slice(0, draft.maxBodyLength);
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

          <label class="support-field">
            <span>{t("wa_support_message")}</span>
            <Textarea
              class="textarea support-message-input"
              bind:value={body}
              maxlength={maxBodyLength}
              rows={5}
              placeholder={t("wa_support_message_placeholder")}
            />
            <small>{body.length}/{maxBodyLength}</small>
          </label>

          <Button
            class="wide support-submit-button"
            size="lg"
            disabled={creating || !subject.trim() || !body.trim()}
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

    {#if loading}
      <ScrollArea class="support-ticket-list-scroll" maxHeight="none">
        <div class="support-user-list-skeleton" aria-label={t("wa_loading")}>
          {#each Array(5) as _, index (index)}
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
    {:else if !tickets.length}
      <div class="support-empty-state" in:fade={{ duration: 180 }}>
        <MessageSquarePlus size={34} />
        <strong>{t("wa_support_no_open_tickets")}</strong>
        <small>{t("wa_support_empty_hint")}</small>
      </div>
    {:else}
      <ScrollArea class="support-ticket-list-scroll" maxHeight="none">
        <div class="ticket-list">
          {#each tickets as ticket}
            <TicketCard
              {ticket}
              {t}
              onOpen={(item: TicketRecord) => supportStore.openTicket(item.ticket_id || 0)}
            />
          {/each}
        </div>
      </ScrollArea>
    {/if}
  </Card>
</main>
