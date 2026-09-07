<script lang="ts">
  import { getPaymentsStore } from "$lib/admin/context";
  import { onMount } from "svelte";
  import {
    AdminPagination,
    AdminListToolbar,
    AdminButton,
  } from "$components/patterns/admin/index.js";
  import type { PaymentOut } from "$lib/admin/stores/paymentsStore";
  import type { AdminBadgeVariant } from "$components/patterns/admin/types";
  import { RefreshCw } from "$components/ui/icons.js";
  import Input from "$components/ui/input.svelte";
  import PaymentTable from "./PaymentTable.svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at = (key) => key,
    fmtDate = (value) => String(value || ""),
    fmtMoney = (value) => String(value),
    paymentStatusVariant = () => "muted",
    onOpenUserCard = () => {},
  }: {
    at?: TranslateFn;
    fmtDate?: (value: string | null | undefined) => string;
    fmtMoney?: (value: number, currency?: string | null) => string;
    paymentStatusVariant?: (status: string | null | undefined) => AdminBadgeVariant;
    onOpenUserCard?: (userId: number) => void;
  } = $props();

  const paymentsStore = getPaymentsStore();
  let searchQuery = $state(paymentsStore.paymentsSearch);
  const PAYMENTS_PAGE_SIZE = 25;
  const payments = $derived(paymentsStore.payments as PaymentOut[]);
  const paymentsTotal = $derived(Number(paymentsStore.paymentsTotal || 0));
  const paymentsPage = $derived(Number(paymentsStore.paymentsPage || 0));
  const paymentsSort = $derived(String(paymentsStore.paymentsSort || "date_desc"));
  const paymentsLoading = $derived(Boolean(paymentsStore.paymentsLoading));
  const paymentsPageCount = $derived(
    Math.max(1, Math.ceil(Number(paymentsTotal || 0) / PAYMENTS_PAGE_SIZE))
  );

  onMount(() => {
    paymentsStore.loadPayments();
  });
</script>

<AdminListToolbar
  total={paymentsTotal}
  totalLabel={at("total", {}, "Total")}
  onsubmit={() => paymentsStore.setSearch(searchQuery)}
>
  {#snippet search()}
    <Input
      type="search"
      class="input"
      bind:value={searchQuery}
      aria-label={at("payments_search_placeholder")}
      placeholder={at("payments_search_placeholder")}
    />
  {/snippet}
  {#snippet searchActions()}
    <AdminButton type="submit" variant="primary" disabled={paymentsLoading}
      >{at("find", {}, "Find")}</AdminButton
    >
  {/snippet}
  {#snippet actions()}
    <AdminButton
      variant="ghost"
      disabled={paymentsLoading}
      onclick={() => paymentsStore.loadPayments({ refresh: true })}
      ><RefreshCw size={15} />{at("refresh", {}, "Refresh")}</AdminButton
    >
  {/snippet}
</AdminListToolbar>

<PaymentTable
  {at}
  {payments}
  loading={paymentsLoading}
  sort={paymentsSort}
  {fmtDate}
  {fmtMoney}
  {paymentStatusVariant}
  onSort={paymentsStore.setSort}
  {onOpenUserCard}
/>

<AdminPagination
  page={paymentsPage}
  pageCount={paymentsPageCount}
  total={paymentsTotal}
  pageLabel={at("page_short", {}, "Page")}
  ofLabel={at("pagination_of", {}, "of")}
  totalLabel={at("total", {}, "Total")}
  jumpLabel={at("page_short", {}, "Page")}
  jumpAriaLabel={at("pagination_jump_aria", {}, "Go to page")}
  goLabel={at("pagination_go", {}, "Go")}
  prevLabel={at("back", {}, "Back")}
  nextLabel={at("next", {}, "Next")}
  onPageChange={(page) => paymentsStore.setPage(page)}
/>
