<script lang="ts">
  import { Send } from "$components/ui/icons.js";
  import { Button, Spinner, Textarea } from "$components/ui/index.js";

  let {
    value = $bindable(""),
    maxLength = 4000,
    disabled = false,
    sending = false,
    placeholder = "",
    sendLabel = "",
    onSend = () => {},
  }: {
    value?: string;
    maxLength?: number;
    disabled?: boolean;
    sending?: boolean;
    placeholder?: string;
    sendLabel?: string;
    onSend?: (value: string) => void | Promise<void>;
  } = $props();

  function submit() {
    if (disabled || sending || !value.trim()) return;
    onSend(value.trim());
  }

  function handleKeydown(event: KeyboardEvent) {
    if (!(event.ctrlKey || event.metaKey) || event.key !== "Enter") return;
    event.preventDefault();
    submit();
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
    onkeydown={handleKeydown}
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
