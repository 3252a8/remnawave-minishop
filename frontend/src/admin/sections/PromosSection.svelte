<script lang="ts">
  import { Input } from "$components/ui/index.js";
  import { Trash2 } from "$components/ui/icons.js";
  import { getContext, onMount } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminField,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import { TableHandler } from "@vincjo/datatables";
  import type { PromosStore } from "../../lib/admin/stores/promosStore";
  import type { components } from "../../lib/api/openapi.generated";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Promo = components["schemas"]["PromoOut"];
  type PromoDraft = components["schemas"]["PromoCreateBody"];

  let {
    at,
    fmtDateShort,
  }: {
    at: TranslateFn;
    fmtDateShort: (value: string) => string;
  } = $props();

  const promosStore = getContext<PromosStore>("promosStore");
  const promosTable = new TableHandler<Promo>();

  const promos = $derived(promosStore.promos as Promo[]);
  const promosTotal = $derived(Number(promosStore.promosTotal || 0));
  const promosPage = $derived(Number(promosStore.promosPage || 0));
  const promosLoading = $derived(Boolean(promosStore.promosLoading));
  const promoCreateOpen = $derived(Boolean(promosStore.promoCreateOpen));
  const promoDraft = $derived(
    (promosStore.promoDraft || {
      code: "",
      bonus_days: 7,
      max_activations: 1,
      valid_days: 30,
    }) as PromoDraft
  );
  const promoRows = $derived(promosTable.rows as Promo[]);

  $effect(() => promosTable.setRows(promos));

  const promosHasMore = $derived(promos.length < promosTotal);
  const promoHeaders = $derived([
    at("promo_col_code", {}, "Код"),
    at("promo_col_bonus", {}, "Бонус"),
    at("promo_col_activations", {}, "Активаций"),
    at("promo_col_valid_until", {}, "Действует до"),
    at("promo_col_status", {}, "Статус"),
    at("actions", {}, "Действия"),
  ]);

  onMount(() => {
    promosStore.loadPromos();
  });
</script>

<div class="admin-table-wrap">
  {#if promosLoading}
    <AdminTableSkeleton
      headers={promoHeaders}
      rows={6}
      actionColumn
      widths={["92px", "52px", "64px", "96px", "72px", "92px"]}
    />
  {:else if !promos.length}
    <AdminEmptyState tone="card"
      ><span class="admin-muted">{at("promos_empty", {}, "Промокодов нет")}</span></AdminEmptyState
    >
  {:else}
    <AdminTable>
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
        {#each promoRows as p (p.id)}
          <tr>
            <td class="admin-cell-mono" data-label={at("promo_col_code", {}, "Код")}>{p.code}</td>
            <td data-label={at("promo_col_bonus", {}, "Бонус")}
              >+{p.bonus_days} {at("days_short", {}, "дн.")}</td
            >
            <td data-label={at("promo_col_activations", {}, "Активаций")}
              >{p.current_activations}/{p.max_activations}</td
            >
            <td data-label={at("promo_col_valid_until", {}, "Действует до")}
              >{p.valid_until ? fmtDateShort(p.valid_until) : "∞"}</td
            >
            <td data-label={at("promo_col_status", {}, "Статус")}>
              {#if p.is_active}
                <AdminBadge variant="success">{at("status_active", {}, "Активен")}</AdminBadge>
              {:else}
                <AdminBadge variant="muted">{at("status_disabled", {}, "Выключен")}</AdminBadge>
              {/if}
            </td>
            <td class="admin-cell-actions" data-label={at("actions", {}, "Действия")}>
              <AdminButton size="sm" onclick={() => promosStore.togglePromo(p)}>
                {p.is_active ? at("btn_disable", {}, "Выкл") : at("btn_enable", {}, "Вкл")}
              </AdminButton>
              <AdminButton size="sm" variant="danger" onclick={() => promosStore.deletePromo(p)}>
                <Trash2 size={13} />
              </AdminButton>
            </td>
          </tr>
        {/each}
      </tbody>
    </AdminTable>
  {/if}
  {#if promosHasMore}
    <div style="padding: 12px; text-align: center;">
      <AdminButton onclick={() => promosStore.setPage(promosPage + 1)}
        >{at("btn_show_more", {}, "Показать еще")}</AdminButton
      >
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
      <AdminField label={at("promo_label_code", {}, "Код")}>
        <Input
          type="text"
          class="input"
          value={promoDraft.code}
          oninput={(e) =>
            promosStore.updateDraft({ code: (e.currentTarget as HTMLInputElement).value })}
          placeholder="FREE-7-DAYS"
        />
      </AdminField>
    </div>
    <div class="admin-dialog-form-section">
      <div class="admin-form-row-2">
        <AdminField label={at("promo_label_bonus_days", {}, "Бонус (дней)")}>
          <Input
            type="number"
            class="input"
            min="1"
            value={String(promoDraft.bonus_days)}
            oninput={(e) =>
              promosStore.updateDraft({
                bonus_days: Number((e.currentTarget as HTMLInputElement).value),
              })}
          />
        </AdminField>
        <AdminField label={at("promo_label_max_activations", {}, "Макс. активаций")}>
          <Input
            type="number"
            class="input"
            min="1"
            value={String(promoDraft.max_activations)}
            oninput={(e) =>
              promosStore.updateDraft({
                max_activations: Number((e.currentTarget as HTMLInputElement).value),
              })}
          />
        </AdminField>
      </div>
      <AdminField label={at("promo_label_valid_days", {}, "Срок действия (дней от текущего)")}>
        <Input
          type="number"
          class="input"
          min="1"
          value={String(promoDraft.valid_days)}
          oninput={(e) =>
            promosStore.updateDraft({
              valid_days: Number((e.currentTarget as HTMLInputElement).value),
            })}
        />
      </AdminField>
    </div>
    <div class="admin-dialog-actions">
      <AdminButton onclick={() => promosStore.setCreateOpen(false)}
        >{at("btn_cancel", {}, "Отмена")}</AdminButton
      >
      <AdminButton
        variant="primary"
        onclick={promosStore.createPromo}
        disabled={!promoDraft.code.trim()}
      >
        {at("btn_create", {}, "Создать")}
      </AdminButton>
    </div>
  </div>
</Dialog>
