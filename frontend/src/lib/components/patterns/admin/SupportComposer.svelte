<script>
  import { Lock, Send } from "$components/ui/icons.js";
  import { Spinner, Textarea } from "$components/ui/index.js";
  import { Switch } from "$components/ui/primitives.js";
  import { AdminButton } from "$components/patterns/admin/index.js";

  export let value = "";
  export let internal = false;
  export let sending = false;
  export let at = (key) => key;
  export let onToggleInternal = () => {};
  export let onSend = () => {};

  function submit() {
    if (sending || !value.trim()) return;
    onSend(value.trim());
  }
</script>

<div class="support-admin-composer">
  <Textarea
    bind:value
    rows={4}
    placeholder={at("support_reply_placeholder", {}, "Ответ")}
    ariaLabel={at("support_reply_placeholder", {}, "Ответ")}
    class="support-admin-composer-textarea"
  />

  <div class="support-admin-composer-row">
    <div class="support-admin-note-toggle">
      <Switch.Root
        id="support-internal-note"
        checked={internal}
        onCheckedChange={onToggleInternal}
        class="admin-switch-root"
      >
        <Switch.Thumb class="admin-switch-thumb" />
      </Switch.Root>
      <label for="support-internal-note">
        <Lock size={14} />
        <span>{at("support_internal_note", {}, "Внутренняя заметка")}</span>
      </label>
    </div>

    <AdminButton variant="primary" disabled={sending || !value.trim()} onclick={submit}>
      {#if sending}<Spinner size="sm" />{:else}<Send size={14} />{/if}
      {at("send", {}, "Отправить")}
    </AdminButton>
  </div>
</div>
