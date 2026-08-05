<script lang="ts">
  import { ScrollArea } from "$components/ui/index.js";
  import { User } from "$components/ui/icons.js";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminPagination,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import type { components } from "../../../lib/api/openapi.generated";
  import type { AdminBadgeVariant } from "$components/patterns/admin/types";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type PromoActivation = components["schemas"]["PromoActivationOut"];

  let {
    rows,
    loading,
    page,
    pageCount,
    total,
    at,
    fmtDate,
    fmtMoney,
    paymentStatusVariant,
    onOpenUserCard,
    onPageChange,
  }: {
    rows: PromoActivation[];
    loading: boolean;
    page: number;
    pageCount: number;
    total: number;
    at: TranslateFn;
    fmtDate: (value: string | null | undefined) => string;
    fmtMoney: (value: number, currency?: string | null) => string;
    paymentStatusVariant: (status: string | null | undefined) => AdminBadgeVariant;
    onOpenUserCard: (userId: number) => void;
    onPageChange: (page: number) => void;
  } = $props();

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

  function multiplierText(value: number | null | undefined): string | null {
    if (value == null || Number(value) === 1) return null;
    return `x${numberText(value)}`;
  }

  function effectPieces(row: PromoActivation): string[] {
    const parts: string[] = [];
    if (Number(row.bonus_days || 0) > 0) {
      parts.push(`+${row.bonus_days} ${at("days_short", {}, "d")}`);
    }
    if (Number(row.discount_percent || 0) > 0) {
      parts.push(`-${numberText(row.discount_percent)}%`);
    }
    const duration = multiplierText(row.duration_multiplier);
    if (duration) parts.push(`${duration} ${at("promo_effect_duration", {}, "duration")}`);
    const traffic = multiplierText(row.traffic_multiplier);
    if (traffic) parts.push(`${traffic} ${at("promo_effect_traffic", {}, "traffic")}`);
    return parts;
  }

  function activationEffectText(row: PromoActivation): string {
    if (row.effect_summary) return row.effect_summary;
    const parts = effectPieces(row);
    return parts.length ? parts.join(" + ") : "-";
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
            <th>{at("user", {}, "User")}</th>
            <th>{at("date", {}, "Date")}</th>
            <th>{at("payment_detail_payment_section", {}, "Payment")}</th>
            <th>{at("amount", {}, "Amount")}</th>
            <th>{at("promo_col_base_amount", {}, "Base")}</th>
            <th>{at("promo_col_discount_amount", {}, "Discount")}</th>
            <th>{at("promo_col_grant", {}, "Grant")}</th>
            <th>{at("promo_col_effect", {}, "Effect")}</th>
            <th>{at("status", {}, "Status")}</th>
            <th>{at("provider", {}, "Provider")}</th>
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
                    {row.user_label || row.user_id}
                    <small>ID {row.user_id}</small>
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
    grid-template-rows: minmax(0, 1fr) auto;
    gap: 12px;
    height: 100%;
    min-height: 0;
    min-width: 0;
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
      grid-template-rows: auto auto;
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
