<script lang="ts">
  import { ScrollArea } from "$components/ui/index.js";
  import { User } from "$components/ui/icons.js";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminPagination,
    AdminSortableHeader,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import type { components } from "../../../lib/api/openapi.generated";
  import type { AdminBadgeVariant } from "$components/patterns/admin/types";
  import type { AdminSortColumn } from "$lib/admin/tableSort.js";
  import { formatAdminPromoEffect } from "$lib/admin/promoEffectDisplay.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type PromoActivation = components["schemas"]["PromoActivationOut"];
  type PromoRevenueSummary = components["schemas"]["PromoRevenueSummaryOut"];

  let {
    rows,
    loading,
    page,
    pageCount,
    total,
    revenueSummary,
    at,
    fmtDate,
    fmtMoney,
    paymentStatusVariant,
    onOpenUserCard,
    currentSort,
    onSort,
    onPageChange,
  }: {
    rows: PromoActivation[];
    loading: boolean;
    page: number;
    pageCount: number;
    total: number;
    revenueSummary: PromoRevenueSummary;
    at: TranslateFn;
    fmtDate: (value: string | null | undefined) => string;
    fmtMoney: (value: number, currency?: string | null) => string;
    paymentStatusVariant: (status: string | null | undefined) => AdminBadgeVariant;
    onOpenUserCard: (userId: number) => void;
    currentSort: string;
    onSort: (sort: string) => void;
    onPageChange: (page: number) => void;
  } = $props();

  const activationSortColumns = [
    { asc: "user_asc", desc: "user_desc", defaultDirection: "asc" },
    { asc: "date_asc", desc: "date_desc", defaultDirection: "desc" },
    { asc: "payment_asc", desc: "payment_desc", defaultDirection: "desc" },
    { asc: "amount_asc", desc: "amount_desc", defaultDirection: "desc" },
    { asc: "base_asc", desc: "base_desc", defaultDirection: "desc" },
    { asc: "discount_asc", desc: "discount_desc", defaultDirection: "desc" },
    { asc: "grant_asc", desc: "grant_desc", defaultDirection: "desc" },
    { asc: "effect_asc", desc: "effect_desc", defaultDirection: "asc" },
    { asc: "status_asc", desc: "status_desc", defaultDirection: "asc" },
    { asc: "provider_asc", desc: "provider_desc", defaultDirection: "asc" },
  ] satisfies AdminSortColumn<never>[];

  const activationHeaders = $derived([
    at("user", {}, "User"),
    at("date", {}, "Date"),
    at("payment_detail_payment_section", {}, "Payment"),
    at("amount", {}, "Amount"),
    at("promo_col_base_amount", {}, "Base"),
    at("promo_col_discount_amount", {}, "Discount"),
    at("promo_col_grant", {}, "Grant"),
    at("promo_col_effect", {}, "Effect"),
    at("status", {}, "Status"),
    at("provider", {}, "Provider"),
  ]);

  function numberText(value: number | string | null | undefined): string {
    if (value == null || value === "") return "-";
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return "-";
    return Math.abs(parsed - Math.round(parsed)) < 1e-9
      ? String(Math.round(parsed))
      : String(Math.round(parsed * 100) / 100);
  }

  function activationEffectText(row: PromoActivation): string {
    return formatAdminPromoEffect(row, at);
  }

  function paymentLabel(row: PromoActivation): string {
    if (!row.payment_id) return at("promo_activation_standalone", {}, "Standalone");
    return `#${row.payment_id}`;
  }

  function amountLabel(row: PromoActivation): string {
    if (row.payment_amount == null) return "-";
    return fmtMoney(Number(row.payment_amount), row.payment_currency);
  }

  function baseAmountLabel(row: PromoActivation): string {
    if (row.base_amount == null) return "-";
    return fmtMoney(Number(row.base_amount), row.payment_currency);
  }

  function discountAmountLabel(row: PromoActivation): string {
    if (row.discount_amount == null || Number(row.discount_amount || 0) <= 0) return "-";
    return fmtMoney(Number(row.discount_amount), row.payment_currency);
  }

  function gbText(value: number | null | undefined): string {
    if (value == null) return "";
    return `${numberText(value)} GB`;
  }

  function grantLabel(row: PromoActivation): string {
    const parts: string[] = [];
    if (Number(row.granted_days || 0) > 0) {
      parts.push(`+${numberText(row.granted_days)} ${at("days_short", {}, "d")}`);
    }
    if (row.charged_gb != null && row.granted_gb != null) {
      parts.push(`${gbText(row.charged_gb)} -> ${gbText(row.granted_gb)}`);
    } else if (row.granted_gb != null) {
      parts.push(gbText(row.granted_gb));
    }
    if (row.charged_months != null && Number(row.granted_days || 0) > 0) {
      parts.push(`${numberText(row.charged_months)} mo`);
    }
    return parts.join(", ") || "-";
  }
</script>

<div class="admin-promo-activations-body">
  <section
    class="admin-promo-revenue"
    aria-label={at("promo_revenue_title", {}, "Revenue from code payments")}
    aria-busy={loading}
  >
    <header class="admin-promo-revenue-head">
      <strong>{at("promo_revenue_title", {}, "Revenue from code payments")}</strong>
      <small>
        {at(
          "promo_revenue_hint",
          {},
          "Successful external payments are summed separately for each currency."
        )}
      </small>
    </header>
    <div class="admin-promo-revenue-grid">
      <div class="admin-promo-revenue-card">
        <span>{at("promo_revenue_all_payments", {}, "All linked payments")}</span>
        <strong>{loading ? "—" : revenueSummary.payments_total}</strong>
      </div>
      <div class="admin-promo-revenue-card">
        <span>{at("promo_revenue_counted_payments", {}, "Successful revenue payments")}</span>
        <strong>{loading ? "—" : revenueSummary.revenue_payments}</strong>
      </div>
      {#each revenueSummary.currencies as item (item.currency)}
        <div class="admin-promo-revenue-card admin-promo-revenue-currency">
          <span>{item.currency}</span>
          <strong>{fmtMoney(Number(item.amount), item.currency)}</strong>
          <small>
            {at("promo_revenue_payment_count", { count: item.payments }, "{count} payments")}
          </small>
        </div>
      {:else}
        {#if !loading}
          <div class="admin-promo-revenue-card admin-promo-revenue-empty">
            <span>{at("promo_revenue_empty", {}, "No successful external payments")}</span>
          </div>
        {/if}
      {/each}
    </div>
  </section>

  {#if loading}
    <AdminTableSkeleton
      headers={activationHeaders}
      rows={6}
      rowHeight={62}
      class="admin-promo-activations-table"
      widths={["160px", "104px", "72px", "86px", "86px", "86px", "120px", "120px", "86px", "90px"]}
    />
  {:else if !rows.length}
    <AdminEmptyState tone="card">
      <span class="admin-muted">{at("promo_activations_empty", {}, "No activations")}</span>
    </AdminEmptyState>
  {:else}
    <ScrollArea class="admin-promo-activations-scroll" maxHeight="none">
      <AdminTable class="admin-promo-activations-table">
        <thead>
          <tr>
            <AdminSortableHeader
              label={at("user", {}, "User")}
              column={activationSortColumns[0]}
              {currentSort}
              {at}
              {onSort}
            />
            <AdminSortableHeader
              label={at("date", {}, "Date")}
              column={activationSortColumns[1]}
              {currentSort}
              {at}
              {onSort}
            />
            <AdminSortableHeader
              label={at("payment_detail_payment_section", {}, "Payment")}
              column={activationSortColumns[2]}
              {currentSort}
              {at}
              {onSort}
            />
            <AdminSortableHeader
              label={at("amount", {}, "Amount")}
              column={activationSortColumns[3]}
              {currentSort}
              {at}
              {onSort}
            />
            <AdminSortableHeader
              label={at("promo_col_base_amount", {}, "Base")}
              column={activationSortColumns[4]}
              {currentSort}
              {at}
              {onSort}
            />
            <AdminSortableHeader
              label={at("promo_col_discount_amount", {}, "Discount")}
              column={activationSortColumns[5]}
              {currentSort}
              {at}
              {onSort}
            />
            <AdminSortableHeader
              label={at("promo_col_grant", {}, "Grant")}
              column={activationSortColumns[6]}
              {currentSort}
              {at}
              {onSort}
            />
            <AdminSortableHeader
              label={at("promo_col_effect", {}, "Effect")}
              column={activationSortColumns[7]}
              {currentSort}
              {at}
              {onSort}
            />
            <AdminSortableHeader
              label={at("status", {}, "Status")}
              column={activationSortColumns[8]}
              {currentSort}
              {at}
              {onSort}
            />
            <AdminSortableHeader
              label={at("provider", {}, "Provider")}
              column={activationSortColumns[9]}
              {currentSort}
              {at}
              {onSort}
            />
          </tr>
        </thead>
        <tbody>
          {#each rows as row (row.activation_id)}
            <tr>
              <td class="admin-cell-user-with-action" data-label={at("user", {}, "User")}>
                <span class="admin-promos-user-cell">
                  <AdminButton
                    class="admin-promos-user-btn"
                    variant="ghost"
                    size="icon"
                    title={at("payments_open_user", {}, "Open user card")}
                    aria-label={at("payments_open_user", {}, "Open user card")}
                    onclick={() => onOpenUserCard(row.user_id)}
                  >
                    <User size={14} />
                  </AdminButton>
                  <span class="admin-promos-user-name">
                    {row.user_label || row.user_minishop_id || "—"}
                    {#if row.user_minishop_id}<small>ID {row.user_minishop_id}</small>{/if}
                  </span>
                </span>
              </td>
              <td data-label={at("date", {}, "Date")}>{fmtDate(row.activated_at)}</td>
              <td
                class="admin-cell-mono"
                data-label={at("payment_detail_payment_section", {}, "Payment")}
              >
                {paymentLabel(row)}
              </td>
              <td data-label={at("amount", {}, "Amount")}>{amountLabel(row)}</td>
              <td data-label={at("promo_col_base_amount", {}, "Base")}>
                {baseAmountLabel(row)}
              </td>
              <td data-label={at("promo_col_discount_amount", {}, "Discount")}>
                {discountAmountLabel(row)}
              </td>
              <td class="admin-cell-wrap" data-label={at("promo_col_grant", {}, "Grant")}>
                {grantLabel(row)}
              </td>
              <td class="admin-cell-wrap" data-label={at("promo_col_effect", {}, "Effect")}>
                {activationEffectText(row)}
              </td>
              <td data-label={at("status", {}, "Status")}>
                {#if row.payment_status}
                  <AdminBadge variant={paymentStatusVariant(row.payment_status)}>
                    {row.payment_status}
                  </AdminBadge>
                {:else}
                  <AdminBadge variant="muted">
                    {at("promo_activation_standalone", {}, "Standalone")}
                  </AdminBadge>
                {/if}
              </td>
              <td data-label={at("provider", {}, "Provider")}>
                {row.payment_provider || "-"}
              </td>
            </tr>
          {/each}
        </tbody>
      </AdminTable>
    </ScrollArea>
  {/if}
  <AdminPagination
    {page}
    {pageCount}
    {total}
    pageLabel={at("page_short", {}, "Page")}
    ofLabel={at("pagination_of", {}, "of")}
    totalLabel={at("total", {}, "Total")}
    jumpLabel={at("page_short", {}, "Page")}
    jumpAriaLabel={at("pagination_jump_aria", {}, "Go to page")}
    goLabel={at("pagination_go", {}, "Go")}
    prevLabel={at("back", {}, "Back")}
    nextLabel={at("next", {}, "Next")}
    {onPageChange}
  />
</div>

<style>
  .admin-promo-activations-body {
    display: grid;
    grid-template-rows: auto minmax(0, 1fr) auto;
    gap: 12px;
    height: 100%;
    min-height: 0;
    min-width: 0;
  }

  .admin-promo-revenue {
    display: grid;
    gap: 10px;
    padding: 12px;
    border: 1px solid var(--admin-border);
    border-radius: 12px;
    background: var(--admin-surface-2);
  }

  .admin-promo-revenue-head {
    display: grid;
    gap: 3px;
  }

  .admin-promo-revenue-head small,
  .admin-promo-revenue-card span,
  .admin-promo-revenue-card small {
    color: var(--admin-muted);
  }

  .admin-promo-revenue-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 8px;
  }

  .admin-promo-revenue-card {
    display: grid;
    align-content: center;
    gap: 3px;
    min-height: 64px;
    padding: 10px;
    border: 1px solid var(--admin-border);
    border-radius: 9px;
    background: var(--admin-card-bg);
  }

  .admin-promo-revenue-card strong {
    font-size: 17px;
    font-variant-numeric: tabular-nums;
  }

  .admin-promo-revenue-empty {
    grid-column: span 2;
  }

  :global(.admin-promo-activations-scroll) {
    height: 100%;
    min-height: 0;
    width: 100%;
    max-height: none !important;
  }

  :global(.admin-promo-activations-scroll .scroll-area__viewport) {
    min-height: 0;
  }

  :global(.admin-promo-activations-table) {
    min-width: 1180px;
  }

  .admin-promos-user-cell {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  .admin-promos-user-name {
    display: grid;
    min-width: 0;
    gap: 2px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-promos-user-name small {
    color: var(--admin-muted);
    font-family: var(--font-mono);
    font-size: 11px;
  }

  .admin-cell-user-with-action :global(.admin-promos-user-btn.admin-btn) {
    width: 30px;
    height: 30px;
    min-width: 30px;
    min-height: 30px;
    flex-shrink: 0;
    padding: 0;
    border-radius: 7px;
  }

  @media (max-width: 720px) {
    .admin-promo-activations-body {
      grid-template-rows: auto auto auto;
      height: auto;
    }

    :global(.admin-promo-activations-scroll) {
      height: auto;
      max-height: min(58vh, 520px) !important;
    }

    :global(.admin-promo-activations-table) {
      min-width: 0;
    }
  }
</style>
