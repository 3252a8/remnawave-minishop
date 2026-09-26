<script lang="ts">
  import { CreditCard, FileText, WalletCards } from "$components/ui/icons.js";

  type EntityKind = "user" | "partner" | "payment" | "withdrawal" | "application" | "code";

  type Props = {
    /** Primary line — the person's name or the record's title. */
    label: string;
    /** Second line, e.g. `@handle` or the payout method. */
    secondary?: string;
    /** Monospace id line, e.g. `PT-104` or `#710024`. */
    idText?: string;
    kind?: EntityKind;
    /** Avatar initials for people; ignored for record kinds. */
    initials?: string;
    avatarUrl?: string;
    /** Accessible name for the action, e.g. "Open user card". */
    title?: string;
    /** Omit to render the same cell as plain, non-interactive text. */
    onclick?: () => void;
  };

  let {
    label,
    secondary = "",
    idText = "",
    kind = "user",
    initials = "",
    avatarUrl = "",
    title = "",
    onclick,
  }: Props = $props();

  const isPerson = $derived(kind === "user" || kind === "partner");
  const fallbackInitials = $derived(
    initials || label.replace(/^@/, "").slice(0, 2).toUpperCase() || "—"
  );
</script>

<!-- One cell shape for every cross-linked record in the admin: avatar or record
     glyph, then name / secondary / id. Rendered as a button when the row can be
     opened, so a partner, a client, a payment and a payout all look and behave
     the same wherever they are mentioned. -->
{#snippet body()}
  <span class="admin-entity-link-figure" aria-hidden="true">
    {#if isPerson}
      {#if avatarUrl}
        <img src={avatarUrl} alt="" loading="lazy" referrerpolicy="no-referrer" />
      {:else}
        <span>{fallbackInitials}</span>
      {/if}
    {:else if kind === "payment"}
      <CreditCard size={15} />
    {:else if kind === "withdrawal"}
      <WalletCards size={15} />
    {:else}
      <FileText size={15} />
    {/if}
  </span>
  <span class="admin-entity-link-text">
    <span class="admin-entity-link-label">{label}</span>
    {#if secondary || idText}
      <!-- Handle and id share one line: three stacked lines made every table row
           in a detail panel ~16px taller than it needed to be. -->
      <span class="admin-entity-link-meta">
        {#if secondary}<span class="admin-entity-link-secondary">{secondary}</span>{/if}
        {#if idText}<span class="admin-entity-link-id">{idText}</span>{/if}
      </span>
    {/if}
  </span>
{/snippet}

{#if onclick}
  <button
    type="button"
    class="admin-entity-link is-actionable"
    class:is-person={isPerson}
    title={title || label}
    {onclick}
  >
    {@render body()}
  </button>
{:else}
  <span class="admin-entity-link" class:is-person={isPerson}>
    {@render body()}
  </span>
{/if}

<style>
  .admin-entity-link {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
    padding: 0;
    border: 0;
    color: inherit;
    background: transparent;
    font: inherit;
    text-align: left;
  }

  .admin-entity-link.is-actionable {
    cursor: pointer;
  }

  .admin-entity-link-figure {
    width: 30px;
    height: 30px;
    display: grid;
    flex: 0 0 auto;
    place-items: center;
    overflow: hidden;
    border-radius: 9px;
    color: var(--admin-muted);
    background: var(--admin-surface-2);
    font-size: 11px;
    font-weight: 700;
  }

  .is-person .admin-entity-link-figure {
    border-radius: 999px;
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 14%, var(--admin-surface-2));
  }

  .admin-entity-link-figure img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .admin-entity-link-text {
    min-width: 0;
    display: grid;
    gap: 1px;
  }

  .admin-entity-link-meta {
    min-width: 0;
    display: flex;
    align-items: baseline;
    gap: 7px;
  }

  .admin-entity-link-label,
  .admin-entity-link-secondary,
  .admin-entity-link-id {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-entity-link-label {
    font-size: 13px;
    font-weight: 650;
    line-height: 1.25;
  }

  .is-actionable .admin-entity-link-label {
    color: var(--accent);
  }

  .is-actionable:hover .admin-entity-link-label {
    text-decoration: underline;
  }

  .admin-entity-link-secondary {
    color: var(--admin-dim);
    font-size: 11px;
  }

  .admin-entity-link-id {
    color: var(--admin-muted);
    font-family: var(--font-mono);
    font-size: 11px;
  }

  .admin-entity-link.is-actionable:focus-visible {
    outline: 2px solid var(--admin-ring);
    outline-offset: 2px;
    border-radius: 9px;
  }
</style>
