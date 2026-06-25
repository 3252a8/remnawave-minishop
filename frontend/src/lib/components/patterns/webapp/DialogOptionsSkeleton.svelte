<script>
  import Skeleton from "$components/ui/skeleton.svelte";

  let {
    label = "",
    rows = 3,
    actions = 0,
    methods = 2,
    showNote = false,
    showPayButton = true,
    showMeta = true,
  } = $props();
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
