<script lang="ts">
  import {
    CalendarDays,
    ChevronDown,
    ExternalLink,
    Plus,
    RefreshCw,
    RotateCcw,
    Trash2,
    X,
    Zap,
  } from "$components/ui/icons.js";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import { Popover } from "$components/ui/primitives.js";
  import Dialog from "$components/ui/dialog.svelte";
  import type { TranslateFn } from "$components/patterns/admin/types";
  import {
    bulkUserActionLabels,
    type BulkUserAction,
  } from "$lib/admin/stores/usersStoreBulkActions";
  import { MediaQuery } from "svelte/reactivity";
  import { tick } from "svelte";

  type Action = BulkUserAction["type"];
  const groups = [
    {
      label: "users_bulk_subscription_group",
      actions: [
        { type: "extend", icon: CalendarDays },
        { type: "tariff", icon: RefreshCw },
      ],
    },
    {
      label: "users_bulk_traffic_group",
      actions: [
        { type: "traffic-grant", icon: Plus },
        { type: "traffic-reset", icon: RotateCcw },
      ],
    },
    {
      label: "users_bulk_access_group",
      actions: [{ type: "subscription-reissue", icon: ExternalLink }],
    },
  ] as const;

  let {
    at,
    count,
    busy,
    onclear,
    onaction,
  }: {
    at: TranslateFn;
    count: number;
    busy: boolean;
    onclear: () => void;
    onaction: (type: Action, trigger: HTMLElement | null) => void;
  } = $props();
  const mobile = new MediaQuery("max-width: 720px", false);
  let open = $state(false);
  let trigger: HTMLElement | null = $state(null);
  let handoff = false;

  function choose(type: Action) {
    handoff = !mobile.current;
    open = false;
    onaction(type, trigger);
  }

  async function closeMobileMenu() {
    open = false;
    await tick();
    trigger?.focus();
  }
</script>

{#snippet triggerLabel()}
  <Zap size={14} />
  {at("users_bulk_actions")}
  <ChevronDown size={14} />
{/snippet}

{#snippet menuItems()}
  <div class="bulk-menu" data-users-bulk-menu>
    {#each groups as group (group.label)}
      <div class="bulk-group" role="group" aria-label={at(group.label)}>
        <span>{at(group.label)}</span>
        {#each group.actions as action (action.type)}
          <AdminButton
            class="bulk-option"
            variant="ghost"
            data-users-bulk-action={action.type}
            onclick={() => choose(action.type)}
          >
            <action.icon size={16} />
            {at(bulkUserActionLabels[action.type])}
          </AdminButton>
        {/each}
      </div>
    {/each}
    <div class="bulk-delete">
      <AdminButton
        class="bulk-option"
        variant="dangerSoft"
        data-users-bulk-action="delete"
        onclick={() => choose("delete")}
      >
        <Trash2 size={16} />
        {at(bulkUserActionLabels.delete)}
      </AdminButton>
    </div>
  </div>
{/snippet}

<div class="bulk-actions" data-users-bulk-actions>
  <div class="bulk-summary">
    <strong role="status">{at("users_bulk_selected", { count: count })}</strong>
    <AdminButton size="sm" variant="ghost" onclick={onclear}>
      <X size={14} />
      {at("users_bulk_clear")}
    </AdminButton>
  </div>
  {#if mobile.current}
    <AdminButton
      size="sm"
      aria-haspopup="dialog"
      aria-expanded={open}
      data-users-bulk-trigger
      disabled={busy}
      onclick={(event) => {
        trigger = event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
        open = true;
      }}
    >
      {@render triggerLabel()}
    </AdminButton>
    <Dialog
      {open}
      portal
      class="admin-users-bulk-sheet"
      title={at("users_bulk_actions")}
      closeLabel={at("close")}
      onclose={closeMobileMenu}
    >
      {@render menuItems()}
    </Dialog>
  {:else}
    <Popover.Root bind:open>
      <Popover.Trigger bind:ref={trigger}>
        {#snippet child({ props })}
          <AdminButton {...props} size="sm" data-users-bulk-trigger disabled={busy}>
            {@render triggerLabel()}
          </AdminButton>
        {/snippet}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          class="admin-users-bulk-popover"
          align="end"
          sideOffset={6}
          collisionPadding={12}
          onCloseAutoFocus={(event) => {
            if (handoff) event.preventDefault();
            handoff = false;
          }}
        >
          {@render menuItems()}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  {/if}
</div>

<style>
  .bulk-actions,
  .bulk-summary {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 10px;
  }

  .bulk-actions {
    position: sticky;
    top: 0;
    z-index: 2;
    justify-content: space-between;
    margin-bottom: 8px;
    padding: 8px 10px;
    border: 1px solid color-mix(in srgb, var(--accent) 32%, var(--admin-border));
    border-radius: 12px;
    background: color-mix(in srgb, var(--accent) 8%, var(--admin-card-bg));
    color: var(--admin-text);
  }

  .bulk-summary strong {
    font-size: 13px;
  }

  :global(.admin-users-bulk-popover) {
    z-index: 60;
    width: min(320px, calc(100vw - 24px));
    max-height: var(--bits-popover-content-available-height);
    overflow: auto;
    padding: 6px;
    border: 1px solid var(--admin-border);
    border-radius: 12px;
    background: var(--panel-2);
    box-shadow: var(--admin-card-shadow, 0 12px 36px rgb(0 0 0 / 18%));
  }

  .bulk-group {
    display: grid;
    gap: 2px;
    padding-block: 4px;
  }

  .bulk-group > span {
    padding-inline: 8px;
    font-size: 12px;
    color: var(--admin-muted);
  }

  .bulk-menu :global(.bulk-option) {
    width: 100%;
    justify-content: flex-start;
    white-space: normal;
    text-align: start;
  }

  .bulk-delete {
    margin-block-start: 4px;
    padding-block-start: 6px;
    border-top: 1px solid var(--admin-border);
  }

  @media (max-width: 720px) {
    :global(.dialog:has(.admin-users-bulk-sheet)) {
      align-items: end;
      padding: 0;
    }

    :global(.admin-users-bulk-sheet) {
      width: 100%;
      max-height: min(90dvh, var(--dialog-available-height));
      border-radius: 18px 18px 0 0;
    }

    .bulk-menu :global(.bulk-option) {
      min-height: 44px;
    }

    .bulk-actions :global(.admin-btn) {
      min-height: 36px;
    }
  }
</style>
