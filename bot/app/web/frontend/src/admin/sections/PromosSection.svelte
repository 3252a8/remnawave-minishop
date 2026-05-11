<script>
  import { Trash2 } from "lucide-svelte";
  import { getContext, onMount } from "svelte";
  import Dialog from "../../lib/components/ui/dialog.svelte";
  import { Label } from "bits-ui";

  export let at;
  export let fmtDateShort;

  const promosStore = getContext("promosStore");

  $: ({
    promos,
    promosTotal,
    promosPage,
    promosLoading,
    promoCreateOpen,
    promoDraft,
  } = $promosStore);

  $: promosHasMore = promos.length < promosTotal;

  onMount(() => {
    promosStore.loadPromos();
  });
</script>

<div class="admin-table-wrap">
  {#if promosLoading}
    <table class="admin-table admin-table-skeleton" aria-hidden="true">
      <thead>
        <tr>
          <th>{at("promo_col_code", {}, "Код")}</th>
          <th>{at("promo_col_bonus", {}, "Бонус")}</th>
          <th>{at("promo_col_activations", {}, "Активаций")}</th>
          <th>{at("promo_col_valid_until", {}, "Действует до")}</th>
          <th>{at("promo_col_status", {}, "Статус")}</th>
          <th class="admin-cell-actions">{at("actions", {}, "Действия")}</th>
        </tr>
      </thead>
      <tbody>
        {#each Array(6) as _, i (i)}
          <tr>
            <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span></td>
            <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span></td>
            <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span></td>
            <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span></td>
            <td><span class="admin-skeleton admin-skeleton-badge"></span></td>
            <td><span class="admin-skeleton admin-skeleton-line"></span></td>
          </tr>
        {/each}
      </tbody>
    </table>
  {:else if !promos.length}
    <div class="admin-card-body"><span class="admin-muted">{at("promos_empty", {}, "Промокодов нет")}</span></div>
  {:else}
    <table class="admin-table">
      <thead>
        <tr>
          <th>{at("promo_col_code", {}, "Код")}</th>
          <th>{at("promo_col_bonus", {}, "Бонус")}</th>
          <th>{at("promo_col_activations", {}, "Активаций")}</th>
          <th>{at("promo_col_valid_until", {}, "Действует до")}</th>
          <th>{at("promo_col_status", {}, "Статус")}</th>
          <th class="admin-cell-actions">{at("actions", {}, "Действия")}</th>
        </tr>
      </thead>
      <tbody>
        {#each promos as p}
          <tr>
            <td class="admin-cell-mono" data-label={at("promo_col_code", {}, "Код")}>{p.code}</td>
            <td data-label={at("promo_col_bonus", {}, "Бонус")}>+{p.bonus_days} {at("days_short", {}, "дн.")}</td>
            <td data-label={at("promo_col_activations", {}, "Активаций")}>{p.current_activations}/{p.max_activations}</td>
            <td data-label={at("promo_col_valid_until", {}, "Действует до")}>{p.valid_until ? fmtDateShort(p.valid_until) : "∞"}</td>
            <td data-label={at("promo_col_status", {}, "Статус")}>
              {#if p.is_active}
                <span class="admin-badge admin-badge-success">{at("status_active", {}, "Активен")}</span>
              {:else}
                <span class="admin-badge admin-badge-muted">{at("status_disabled", {}, "Выключен")}</span>
              {/if}
            </td>
            <td class="admin-cell-actions" data-label={at("actions", {}, "Действия")}>
              <button type="button" class="admin-btn admin-btn-sm" on:click={() => promosStore.togglePromo(p)}>
                {p.is_active ? at("btn_disable", {}, "Выкл") : at("btn_enable", {}, "Вкл")}
              </button>
              <button type="button" class="admin-btn admin-btn-sm admin-btn-danger" on:click={() => promosStore.deletePromo(p)}>
                <Trash2 size={13} />
              </button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
  {#if promosHasMore}
    <div style="padding: 12px; text-align: center;">
      <button type="button" class="admin-btn" on:click={() => promosStore.setPage(promosPage + 1)}>{at("btn_show_more", {}, "Показать еще")}</button>
    </div>
  {/if}
</div>

<Dialog
  open={promoCreateOpen}
  title={at("promo_create_title", {}, "Создать промокод")}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={() => promosStore.setCreateOpen(false)}
  class="admin-dialog admin-dialog-compact"
>
  <div class="admin-form" data-dialog-content>
    <div class="admin-dialog-form-section">
      <Label.Root class="admin-field-label">
        <span>{at("promo_label_code", {}, "Код")}</span>
        <input type="text" class="input" value={promoDraft.code} on:input={(e) => promosStore.updateDraft({ code: e.target.value })} placeholder="FREE-7-DAYS" />
      </Label.Root>
    </div>
    <div class="admin-dialog-form-section">
      <div class="admin-form-row-2">
        <Label.Root class="admin-field-label">
          <span>{at("promo_label_bonus_days", {}, "Бонус (дней)")}</span>
          <input type="number" class="input" min="1" value={promoDraft.bonus_days} on:input={(e) => promosStore.updateDraft({ bonus_days: Number(e.target.value) })} />
        </Label.Root>
        <Label.Root class="admin-field-label">
          <span>{at("promo_label_max_activations", {}, "Макс. активаций")}</span>
          <input type="number" class="input" min="1" value={promoDraft.max_activations} on:input={(e) => promosStore.updateDraft({ max_activations: Number(e.target.value) })} />
        </Label.Root>
      </div>
      <Label.Root class="admin-field-label">
        <span>{at("promo_label_valid_days", {}, "Срок действия (дней от текущего)")}</span>
        <input type="number" class="input" min="1" value={promoDraft.valid_days} on:input={(e) => promosStore.updateDraft({ valid_days: Number(e.target.value) })} />
      </Label.Root>
    </div>
    <div class="admin-dialog-actions">
      <button type="button" class="admin-btn" on:click={() => promosStore.setCreateOpen(false)}>{at("btn_cancel", {}, "Отмена")}</button>
      <button type="button" class="admin-btn admin-btn-primary" on:click={promosStore.createPromo} disabled={!promoDraft.code.trim()}>
        {at("btn_create", {}, "Создать")}
      </button>
    </div>
  </div>
</Dialog>
