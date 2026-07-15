<script lang="ts">
  let { label = "" }: { label?: string } = $props();
</script>

<div class="ticket-typing-indicator" role="status" aria-live="polite">
  <span class="ticket-typing-dots" aria-hidden="true">
    <i></i><i></i><i></i>
  </span>
  <span>{label}</span>
</div>
