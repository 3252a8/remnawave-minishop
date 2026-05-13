<script>
  import { Popover, RangeCalendar } from "bits-ui";
  import { parseDate } from "@internationalized/date";
  import Button from "$components/ui/button.svelte";
  import { ChevronLeft, ChevronRight } from "$components/ui/icons.js";
  import { cn } from "$lib/utils.js";

  let {
    open = $bindable(false),
    minIso = "",
    maxIso = "",
    committedFrom = "",
    committedTo = "",
    title = "",
    applyLabel = "",
    triggerLabel = "",
    isActive = false,
    onApply = () => {},
  } = $props();

  let value = $state({ start: undefined, end: undefined });
  let prevOpen = $state(false);

  function seedFromBounds() {
    if (!minIso || !maxIso) return;
    const minV = parseDate(minIso);
    const maxV = parseDate(maxIso);
    if (
      committedFrom &&
      committedTo &&
      committedFrom >= minIso &&
      committedTo <= maxIso &&
      committedFrom <= committedTo
    ) {
      value = { start: parseDate(committedFrom), end: parseDate(committedTo) };
      return;
    }
    let start = maxV.subtract({ days: 29 });
    if (start.compare(minV) < 0) start = minV;
    value = { start, end: maxV };
  }

  $effect(() => {
    if (open && !prevOpen) seedFromBounds();
    prevOpen = open;
  });

  function calendarDateToIso(d) {
    if (!d || typeof d !== "object") return "";
    const y = d.year;
    const m = String(d.month).padStart(2, "0");
    const day = String(d.day).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function handleApply() {
    const fromIso = calendarDateToIso(value?.start);
    const toIso = calendarDateToIso(value?.end);
    if (!fromIso || !toIso || fromIso > toIso) return;
    onApply({ fromIso, toIso });
    open = false;
  }
</script>

<Popover.Root bind:open>
  <Popover.Trigger
    type="button"
    class={cn("admin-revenue-period-btn", isActive && "is-active")}
    disabled={!minIso || !maxIso}
    aria-pressed={isActive}
  >
    {triggerLabel}
  </Popover.Trigger>
  <Popover.Portal>
    <Popover.Content
      class="admin-revenue-range-popover"
      side="bottom"
      align="end"
      sideOffset={8}
      trapFocus={true}
    >
      {#if title}
        <div class="admin-revenue-range-popover__title">{title}</div>
      {/if}
      {#if minIso && maxIso}
        <RangeCalendar.Root
          class="admin-revenue-rcal"
          bind:value
          minValue={parseDate(minIso)}
          maxValue={parseDate(maxIso)}
          weekdayFormat="short"
          fixedWeeks={true}
          weekStartsOn={1}
        >
          {#snippet children({ months, weekdays })}
            <RangeCalendar.Header class="admin-revenue-rcal__header">
              <RangeCalendar.PrevButton class="admin-revenue-rcal__nav">
                <ChevronLeft />
              </RangeCalendar.PrevButton>
              <RangeCalendar.Heading class="admin-revenue-rcal__heading" />
              <RangeCalendar.NextButton class="admin-revenue-rcal__nav">
                <ChevronRight />
              </RangeCalendar.NextButton>
            </RangeCalendar.Header>
            <div class="admin-revenue-rcal__grids">
              {#each months as month (month.value.month)}
                <RangeCalendar.Grid class="admin-revenue-rcal__grid">
                  <RangeCalendar.GridHead>
                    <RangeCalendar.GridRow class="admin-revenue-rcal__weekrow">
                      {#each weekdays as wd (wd)}
                        <RangeCalendar.HeadCell class="admin-revenue-rcal__headcell">
                          {wd.slice(0, 2)}
                        </RangeCalendar.HeadCell>
                      {/each}
                    </RangeCalendar.GridRow>
                  </RangeCalendar.GridHead>
                  <RangeCalendar.GridBody>
                    {#each month.weeks as weekDates, wi (wi)}
                      <RangeCalendar.GridRow class="admin-revenue-rcal__weekrow">
                        {#each weekDates as cellDate, di (`${wi}-${di}-${cellDate.toString()}`)}
                          <RangeCalendar.Cell
                            date={cellDate}
                            month={month.value}
                            class="admin-revenue-rcal__cell"
                          >
                            <RangeCalendar.Day class="admin-revenue-rcal__day">
                              {cellDate.day}
                            </RangeCalendar.Day>
                          </RangeCalendar.Cell>
                        {/each}
                      </RangeCalendar.GridRow>
                    {/each}
                  </RangeCalendar.GridBody>
                </RangeCalendar.Grid>
              {/each}
            </div>
          {/snippet}
        </RangeCalendar.Root>
      {/if}
      <div class="admin-revenue-range-popover__actions">
        <Button variant="default" size="sm" onclick={handleApply}>{applyLabel}</Button>
      </div>
    </Popover.Content>
  </Popover.Portal>
</Popover.Root>
