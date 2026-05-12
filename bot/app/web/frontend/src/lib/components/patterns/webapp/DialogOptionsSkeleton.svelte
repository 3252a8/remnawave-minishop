<script>
  import Skeleton from "$components/ui/skeleton.svelte";

  export let label = "";
  export let rows = 3;
  export let actions = 0;
  export let methods = 2;
  export let showNote = false;
  export let showPayButton = true;
  export let showMeta = true;
</script>

<div class="dialog-skeleton" aria-label={label}>
  {#if actions}
    <div class="tariff-action-list">
      {#each Array(actions) as _, index (index)}
        <div class="tariff-action-card skeleton-row">
          <span>
            <Skeleton variant="title" />
            <Skeleton variant="short" />
          </span>
          <Skeleton class="skeleton-line-price" />
        </div>
      {/each}
    </div>
    <div class="payment-divider" aria-hidden="true"></div>
  {/if}

  <div class="option-list">
    {#each Array(rows) as _, index (index)}
      <div class={`option-row ${showMeta ? "plan-row" : "change-action-row"} skeleton-row`}>
        <span class="option-row-main">
          <Skeleton variant="title" />
          <Skeleton variant="short" />
        </span>
        {#if showMeta}
          <span class="option-row-meta">
            <Skeleton class="skeleton-line-price" />
            <Skeleton variant="tiny" />
          </span>
        {/if}
      </div>
    {/each}
  </div>

  {#if showNote}
    <div class="topup-carryover-note skeleton-carryover-note">
      <Skeleton variant="line" />
      <Skeleton variant="short" />
    </div>
  {/if}

  {#if methods}
    <div class="method-grid">
      {#each Array(methods) as _, index (index)}
        <div class="method-card skeleton-method">
          <Skeleton variant="dot" />
          <Skeleton class="skeleton-line-method" />
        </div>
      {/each}
    </div>
  {/if}

  {#if showPayButton}
    <Skeleton class="skeleton-pay-button" />
  {/if}
</div>
