<script>
  import { getContext, onMount } from "svelte";
  import {
    AdminBadge,
    AdminEmptyState,
    AdminPagination,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";

  export let at = (key) => key;
  export let fmtDate = (value) => value;
  export let fmtMoney = (value) => value;
  export let paymentStatusVariant = () => "muted";

  const paymentsStore = getContext("paymentsStore");

  $: ({
    payments,
    paymentsTotal,
    paymentsPage,
    paymentsLoading,
  } = $paymentsStore);

  $: paymentsHasMore = payments.length > 0 && paymentsTotal > (paymentsPage + 1) * 25; // 25 is PAYMENTS_PAGE_SIZE
  $: paymentHeaders = [
    at("id", {}, "ID"),
    at("user", {}, "Пользователь"),
    at("amount", {}, "Сумма"),
    at("provider", {}, "Провайдер"),
    at("description", {}, "Описание"),
    at("status", {}, "Статус"),
    at("date", {}, "Дата"),
  ];

  onMount(() => {
    paymentsStore.loadPayments();
  });
</script>

<div class="admin-table-wrap">
  {#if paymentsLoading}
    <AdminTableSkeleton headers={paymentHeaders} rows={8} widths={["48px", "120px", "78px", "82px", "180px", "72px", "96px"]} />
  {:else if !payments.length}
    <AdminEmptyState tone="card"><span class="admin-muted">{at("payments_empty", {}, "Нет платежей")}</span></AdminEmptyState>
  {:else}
    <AdminTable>
      <thead>
        <tr>
          <th>{at("id", {}, "ID")}</th>
          <th>{at("user", {}, "Пользователь")}</th>
          <th>{at("amount", {}, "Сумма")}</th>
          <th>{at("provider", {}, "Провайдер")}</th>
          <th>{at("description", {}, "Описание")}</th>
          <th>{at("status", {}, "Статус")}</th>
          <th>{at("date", {}, "Дата")}</th>
        </tr>
      </thead>
      <tbody>
        {#each payments as p}
          <tr>
            <td class="admin-cell-id" data-label="ID">#{p.payment_id}</td>
            <td data-label={at("user", {}, "Пользователь")}>{p.user_label || p.user_id}</td>
            <td data-label={at("amount", {}, "Сумма")}>{fmtMoney(p.amount, p.currency)}</td>
            <td data-label={at("provider", {}, "Провайдер")}>{p.provider}</td>
            <td class="admin-cell-wrap" data-label={at("description", {}, "Описание")}>{p.description || "—"}</td>
            <td data-label={at("status", {}, "Статус")}>
              <AdminBadge variant={paymentStatusVariant(p.status)}>{p.status}</AdminBadge>
            </td>
            <td data-label={at("date", {}, "Дата")}>{fmtDate(p.created_at)}</td>
          </tr>
        {/each}
      </tbody>
    </AdminTable>
  {/if}
</div>

<AdminPagination
  meta={`${at("page_short", {}, "Стр.")} ${paymentsPage + 1} · ${at("total", {}, "Всего")} ${paymentsTotal}`}
  prevLabel={at("back", {}, "Назад")}
  nextLabel={at("next", {}, "Далее")}
  prevDisabled={paymentsPage === 0}
  nextDisabled={!paymentsHasMore}
  onPrev={() => { paymentsStore.setPage(Math.max(0, paymentsPage - 1)); }}
  onNext={() => { paymentsStore.setPage(paymentsPage + 1); }}
/>
