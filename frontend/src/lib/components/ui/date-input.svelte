<script lang="ts">
  import { DatePicker } from "bits-ui";
  import { parseDate, parseDateTime, type DateValue } from "@internationalized/date";
  import { CalendarDays, ChevronLeft, ChevronRight, X } from "./icons.js";
  import Button from "./button.svelte";

  let {
    value = $bindable(""),
    ariaLabel,
    clearLabel = "Clear date",
    locale = "en",
    withTime = false,
    disabled = false,
  }: {
    value?: string;
    ariaLabel: string;
    clearLabel?: string;
    locale?: string;
    withTime?: boolean;
    disabled?: boolean;
  } = $props();
  let open = $state(false);
  let trigger = $state<HTMLButtonElement | null>(null);
  const date = $derived.by(() => {
    if (!value) return undefined;
    try {
      return withTime ? parseDateTime(value) : parseDate(value);
    } catch {
      return undefined;
    }
  });
  function update(next: DateValue | undefined) {
    value = next ? next.toString().slice(0, withTime ? 16 : 10) : "";
  }
</script>

<DatePicker.Root
  value={date}
  placeholder={withTime ? parseDateTime(new Date().toISOString().slice(0, 16)) : undefined}
  onValueChange={update}
  bind:open
  {disabled}
  {locale}
  granularity={withTime ? "minute" : "day"}
  hourCycle={24}
  weekdayFormat="short"
  fixedWeeks
  weekStartsOn={1}
>
  <DatePicker.Label class="sr-only">{ariaLabel}</DatePicker.Label>
  <div class="date-input-shell">
    <DatePicker.Input class="input date-input" aria-label={ariaLabel}>
      {#snippet children({ segments })}
        {#each segments as segment, index (`${segment.part}-${index}`)}
          <DatePicker.Segment part={segment.part} class="date-input-segment"
            >{segment.value}</DatePicker.Segment
          >
        {/each}
        <DatePicker.Trigger bind:ref={trigger} class="date-input-trigger" aria-label={ariaLabel}>
          <CalendarDays size={16} />
        </DatePicker.Trigger>
      {/snippet}
    </DatePicker.Input>
    {#if value}
      <Button
        variant="icon"
        size="icon"
        class="date-input-clear"
        aria-label={`${clearLabel}: ${ariaLabel}`}
        {disabled}
        onclick={() => {
          update(undefined);
          trigger?.focus();
        }}><X size={14} /></Button
      >
    {/if}
  </div>
  <DatePicker.Portal>
    <DatePicker.Content class="date-input-popover" sideOffset={6} collisionPadding={12} trapFocus>
      <DatePicker.Calendar class="date-input-calendar">
        {#snippet children({ months, weekdays })}
          <DatePicker.Header class="date-input-header">
            <DatePicker.PrevButton class="date-input-nav"
              ><ChevronLeft size={16} /></DatePicker.PrevButton
            >
            <DatePicker.Heading />
            <DatePicker.NextButton class="date-input-nav"
              ><ChevronRight size={16} /></DatePicker.NextButton
            >
          </DatePicker.Header>
          {#each months as month (month.value.toString())}
            <DatePicker.Grid class="date-input-grid">
              <DatePicker.GridHead
                ><DatePicker.GridRow>
                  {#each weekdays as weekday, index (index)}<DatePicker.HeadCell
                      class="date-input-weekday">{weekday.slice(0, 2)}</DatePicker.HeadCell
                    >{/each}
                </DatePicker.GridRow></DatePicker.GridHead
              >
              <DatePicker.GridBody>
                {#each month.weeks as week, index (index)}
                  <DatePicker.GridRow>
                    {#each week as cell (cell.toString())}
                      <DatePicker.Cell date={cell} month={month.value} class="date-input-cell"
                        ><DatePicker.Day class="date-input-day">{cell.day}</DatePicker.Day
                        ></DatePicker.Cell
                      >
                    {/each}
                  </DatePicker.GridRow>
                {/each}
              </DatePicker.GridBody>
            </DatePicker.Grid>
          {/each}
        {/snippet}
      </DatePicker.Calendar>
    </DatePicker.Content>
  </DatePicker.Portal>
</DatePicker.Root>

<style>
  :global(.date-input-shell) {
    display: flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
  }
  :global(.date-input) {
    display: flex;
    align-items: center;
    flex: 1;
    min-width: 0;
    gap: 1px;
  }
  :global(.date-input-segment) {
    padding: 2px;
    border-radius: 4px;
    outline: none;
  }
  :global(.date-input-segment:focus) {
    background: var(--admin-surface-2, var(--panel));
    box-shadow: 0 0 0 2px var(--accent);
  }
  :global(.date-input-trigger),
  :global(.date-input-nav) {
    display: grid;
    place-items: center;
    border: 0;
    background: transparent;
    color: inherit;
    border-radius: 6px;
    cursor: pointer;
    width: 30px;
    height: 30px;
    flex: 0 0 auto;
  }
  :global(.date-input-trigger) {
    margin-left: auto;
  }
  :global(.date-input-trigger:focus-visible),
  :global(.date-input-nav:focus-visible),
  :global(.date-input-day:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  :global(.date-input-popover) {
    z-index: 320;
    max-width: calc(100vw - 24px);
    padding: 12px;
    border: 1px solid var(--admin-border, var(--border));
    border-radius: 12px;
    background: var(--admin-surface, var(--panel));
    color: var(--admin-text, var(--text));
    box-shadow: var(--shadow-popover);
  }
  :global(.date-input-header) {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 8px;
    font-size: 13px;
  }
  :global(.date-input-grid) {
    border-collapse: collapse;
    table-layout: fixed;
    width: 252px;
    max-width: 100%;
  }
  :global(.date-input-weekday) {
    color: var(--admin-muted, var(--muted));
    font-size: 11px;
    font-weight: 500;
    height: 30px;
  }
  :global(.date-input-cell) {
    padding: 0;
    text-align: center;
  }
  :global(.date-input-day) {
    display: grid;
    place-items: center;
    width: 36px;
    height: 36px;
    border-radius: 7px;
    font-size: 13px;
    outline: none;
    cursor: pointer;
  }
  :global(.date-input-day:hover) {
    background: var(--admin-surface-2, var(--panel));
  }
  :global(.date-input-day[data-selected]) {
    background: var(--accent);
    color: var(--accent-contrast);
  }
  :global(.date-input-day[data-outside-month]),
  :global(.date-input-day[data-disabled]) {
    opacity: 0.35;
  }
  :global(.date-input-day[data-disabled]) {
    cursor: default;
  }
</style>
