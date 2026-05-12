<script>
  import { ChevronLeft, ChevronRight } from "$components/ui/icons.js";
  import AdminButton from "./AdminButton.svelte";

  export let meta = "";
  export let prevLabel = "Back";
  export let nextLabel = "Next";
  export let prevDisabled = false;
  export let nextDisabled = false;
  export let onPrev = () => {};
  export let onNext = () => {};
</script>

<div class="admin-pagination">
  <span class="admin-pagination-meta">{meta}</span>
  <div class="admin-pagination-buttons">
    <AdminButton size="sm" disabled={prevDisabled} onclick={onPrev}>
      <ChevronLeft size={14} /> {prevLabel}
    </AdminButton>
    <AdminButton size="sm" disabled={nextDisabled} onclick={onNext}>
      {nextLabel} <ChevronRight size={14} />
    </AdminButton>
  </div>
</div>
