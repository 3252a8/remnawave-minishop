<script>
  import { getContext, onMount } from "svelte";
  import { fade, slide } from "svelte/transition";
  import { Check, ChevronsUpDown, LifeBuoy, MessageSquarePlus } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import { Skeleton } from "$components/ui/index.js";
  import { TicketCard } from "$components/patterns/webapp/index.js";
  import { Select, Tabs } from "$components/ui/primitives.js";

  export let t = (key) => key;
  export let maxSubjectLength = 160;
  export let maxBodyLength = 4000;

  const supportStore = getContext("supportStore");
  let subject = "";
  let body = "";
  let category = "other";
  let priority = "normal";
  let createOpen = false;

  $: ({ tickets, loading, creating, statusFilter, counts } = $supportStore);
  $: categoryOptions = [
    { value: "billing", label: t("wa_support_category_billing") },
    { value: "technical", label: t("wa_support_category_technical") },
    { value: "account", label: t("wa_support_category_account") },
    { value: "other", label: t("wa_support_category_other") },
  ];
  $: priorityOptions = [
    { value: "normal", label: t("wa_support_priority_normal") },
    { value: "high", label: t("wa_support_priority_high") },
  ];
  $: statusTabs = [
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
  ];
  $: selectedCategory =
    categoryOptions.find((option) => option.value === category) || categoryOptions[0];
  $: selectedPriority =
    priorityOptions.find((option) => option.value === priority) || priorityOptions[0];

  onMount(() => {
    supportStore.loadList();
  });

  async function createTicket() {
    const ticket = await supportStore.createTicket({ subject, body, category, priority });
    if (ticket) {
      subject = "";
      body = "";
      category = "other";
      priority = "normal";
      createOpen = false;
    }
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
      on:click={() => (createOpen = !createOpen)}
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
            <input
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
                onValueChange={(value) => (category = value)}
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
                onValueChange={(value) => (priority = value)}
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
            <textarea
              class="textarea support-message-input"
              bind:value={body}
              maxlength={maxBodyLength}
              rows="5"
              placeholder={t("wa_support_message_placeholder")}
            ></textarea>
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
    {:else if !tickets.length}
      <div class="support-empty-state" in:fade={{ duration: 180 }}>
        <MessageSquarePlus size={34} />
        <strong>{t("wa_support_no_open_tickets")}</strong>
        <small>{t("wa_support_empty_hint")}</small>
      </div>
    {:else}
      <div class="ticket-list">
        {#each tickets as ticket}
          <TicketCard {ticket} {t} onOpen={(item) => supportStore.openTicket(item.ticket_id)} />
        {/each}
      </div>
    {/if}
  </Card>
</main>
