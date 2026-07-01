<script lang="ts">
  import { getBroadcastStore } from "$lib/admin/context";
  import { Textarea } from "$components/ui/index.js";
  import { Send } from "$components/ui/icons.js";
  import { onMount } from "svelte";
  import { Label } from "$components/ui/primitives.js";
  import { AdminButton, AdminSelect } from "$components/patterns/admin/index.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let { at }: { at: TranslateFn } = $props();
  const broadcastStore = getBroadcastStore();

  const broadcastTarget = $derived(broadcastStore.broadcastTarget);
  const broadcastText = $derived(broadcastStore.broadcastText);
  const broadcastBusy = $derived(broadcastStore.broadcastBusy);
  const broadcastResult = $derived(
    broadcastStore.broadcastResult as { queued: number; failed: number } | null
  );
  const broadcastCounts = $derived(broadcastStore.broadcastCounts as Record<string, number> | null);
  const broadcastCountsLoading = $derived(Boolean(broadcastStore.broadcastCountsLoading));
  const handleTargetChange = (value: string) => {
    broadcastStore.updateField({ broadcastTarget: value });
  };

  const BROADCAST_TARGET_OPTIONS = broadcastStore.BROADCAST_TARGET_OPTIONS;

  // Append the resolved audience size to each option once counts are loaded.
  const targetOptions = $derived(
    BROADCAST_TARGET_OPTIONS.map((option) => {
      const count = broadcastCounts?.[option.value];
      if (count != null) return { ...option, label: `${option.label} (${count})` };
      if (broadcastCountsLoading) return { ...option, label: `${option.label} (...)` };
      return option;
    })
  );

  onMount(() => {
    broadcastStore.loadCounts();
  });
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
          items={targetOptions}
          ariaLabel={at("broadcast_label_audience", {}, "Аудитория")}
          onValueChange={handleTargetChange}
        />
      </Label.Root>
      <Label.Root class="admin-field-label">
        <span>{at("broadcast_label_text", {}, "Текст сообщения")}</span>
        <small>{at("broadcast_hint_text", {}, "Поддерживается HTML-разметка Telegram")}</small>
        <Textarea
          class="admin-textarea"
          rows={6}
          value={broadcastText}
          oninput={(e) =>
            broadcastStore.updateField({
              broadcastText: (e.currentTarget as HTMLTextAreaElement).value,
            })}
        />
      </Label.Root>
      <div style="display:flex; gap:8px; align-items:center;">
        <AdminButton
          variant="primary"
          onclick={broadcastStore.runBroadcast}
          disabled={broadcastBusy || !broadcastText.trim()}
        >
          <Send size={14} />
          {broadcastBusy
            ? at("btn_sending", {}, "Отправка...")
            : at("btn_queue", {}, "Поставить в очередь")}
        </AdminButton>
        {#if broadcastResult}
          <span class="admin-muted"
            >{at("broadcast_stat_queued", {}, "В очереди")}: {broadcastResult.queued} · {at(
              "broadcast_stat_failed",
              {},
              "Неудач"
            )}: {broadcastResult.failed}</span
          >
        {/if}
      </div>
    </div>
  </div>
</div>
