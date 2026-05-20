<script>
  import { Send } from "$components/ui/icons.js";
  import { Button, Spinner, Textarea } from "$components/ui/index.js";

  export let value = "";
  export let maxLength = 4000;
  export let disabled = false;
  export let sending = false;
  export let placeholder = "";
  export let sendLabel = "";
  export let onSend = () => {};

  function submit() {
    if (disabled || sending || !value.trim()) return;
    onSend(value.trim());
  }
</script>

<div class="ticket-composer">
  <Textarea
    bind:value
    rows={3}
    maxlength={maxLength}
    {disabled}
    {placeholder}
    ariaLabel={placeholder}
    class="ticket-composer-textarea"
  />
  <div class="ticket-composer-row">
    <small>{value.length}/{maxLength}</small>
    <Button
      type="button"
      class="ticket-composer-send"
      disabled={disabled || sending || !value.trim()}
      onclick={submit}
    >
      {#if sending}<Spinner size="sm" />{:else}<Send size={16} />{/if}
      <span>{sendLabel}</span>
    </Button>
  </div>
</div>
