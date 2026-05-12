<script>
  import { Send } from "$components/ui/icons.js";
  import { getContext } from "svelte";
  import { Label } from "$components/ui/primitives.js";
  import { AdminButton, AdminSelect } from "$components/patterns/admin/index.js";

  export let at;
  const broadcastStore = getContext("broadcastStore");

  $: ({
    broadcastTarget,
    broadcastText,
    broadcastBusy,
    broadcastResult,
  } = $broadcastStore);

  const BROADCAST_TARGET_OPTIONS = broadcastStore.BROADCAST_TARGET_OPTIONS;
</script>

<div class="admin-card">
  <header class="admin-card-head">
    <h3>{at("broadcast_title", {}, "Рассылка")}</h3>
    <small>{at("broadcast_subtitle", {}, "Доставка через очередь сообщений")}</small>
  </header>
  <div class="admin-card-body">
    <div class="admin-form">
      <Label.Root class="admin-field-label">
        <span>{at("broadcast_label_audience", {}, "Аудитория")}</span>
        <AdminSelect
          value={broadcastTarget}
          items={BROADCAST_TARGET_OPTIONS}
          ariaLabel={at("broadcast_label_audience", {}, "Аудитория")}
          onValueChange={(value) => broadcastStore.updateField({ broadcastTarget: value })}
        />
      </Label.Root>
      <Label.Root class="admin-field-label">
        <span>{at("broadcast_label_text", {}, "Текст сообщения")}</span>
        <small>{at("broadcast_hint_text", {}, "Поддерживается HTML-разметка Telegram")}</small>
        <textarea class="admin-textarea" rows="6" value={broadcastText} on:input={(e) => broadcastStore.updateField({ broadcastText: e.target.value })}></textarea>
      </Label.Root>
      <div style="display:flex; gap:8px; align-items:center;">
        <AdminButton variant="primary" onclick={broadcastStore.runBroadcast} disabled={broadcastBusy || !broadcastText.trim()}>
          <Send size={14} /> {broadcastBusy ? at("btn_sending", {}, "Отправка...") : at("btn_queue", {}, "Поставить в очередь")}
        </AdminButton>
        {#if broadcastResult}
          <span class="admin-muted">{at("broadcast_stat_queued", {}, "В очереди")}: {broadcastResult.queued} · {at("broadcast_stat_failed", {}, "Неудач")}: {broadcastResult.failed}</span>
        {/if}
      </div>
    </div>
  </div>
</div>
