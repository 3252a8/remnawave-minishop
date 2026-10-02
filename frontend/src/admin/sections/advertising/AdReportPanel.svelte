<script lang="ts">
  import * as Card from "$components/ui/card/index.js";
  import {
    AdminFormGrid,
    AdminSettingsGroup,
    AdminTable,
    AdminEmptyState,
  } from "$components/patterns/admin/index.js";
  import { adMoney, type AdDetail, type Translate } from "./types";
  let { data, at }: { data: AdDetail; at: Translate } = $props();
  const stats = $derived(data.report);
  const counters = $derived([
    ["ads_contacts", stats.contacts],
    ["ads_attributed_users", stats.attributed_users],
    ["ads_registrations", stats.registrations],
    ["ads_returning_users", stats.returning_users],
    ["ads_trials", stats.trials],
    ["ads_payers", stats.payers],
    ["ads_first_payers", stats.first_payers],
    ["ads_purchases", stats.purchases],
  ] as const);
</script>

<div class="ad-report-panel">
  <AdminSettingsGroup title={at("ads_contacts")} description={at("ads_report_definition")}>
    <AdminFormGrid columns={4} minWidth="140px" class="ad-report-metrics">
      {#each counters as [label, value] (label)}
        <Card.Root>
          <Card.Header>
            <Card.Description>{at(label)}</Card.Description>
            <Card.Title>{value}</Card.Title>
          </Card.Header>
        </Card.Root>
      {/each}
    </AdminFormGrid>
    {#if stats.legacy_payment_count}
      <p role="status" class="admin-muted ad-report-note">
        {at("ads_legacy_payments", { count: stats.legacy_payment_count })}
      </p>
    {/if}
  </AdminSettingsGroup>

  <AdminSettingsGroup title={at("ads_product_report")}>
    {#if stats.currencies.length}
      <AdminTable layout="fixed" class="admin-table-compact" aria-label={at("ads_product_report")}>
        <thead>
          <tr>
            <th>{at("ads_currency")}</th>
            <th>{at("ads_cash")}</th>
            <th>{at("ads_product_gross")}</th>
            <th>{at("ads_refunds")}</th>
            <th>{at("ads_product_net")}</th>
            <th>{at("ads_spend")}</th>
            <th>ROAS</th>
            <th>CAC</th>
          </tr>
        </thead>
        <tbody>
          {#each stats.currencies as row (row.currency)}
            <tr>
              <td class="admin-cell-primary" data-label={at("ads_currency")}
                ><strong>{row.currency}</strong></td
              >
              <td data-label={at("ads_cash")}>{adMoney(row.cash_minor, row.currency, row.scale)}</td
              >
              <td data-label={at("ads_product_gross")}
                >{adMoney(row.product_minor, row.currency, row.scale)}</td
              >
              <td data-label={at("ads_refunds")}
                >{adMoney(row.refund_minor, row.currency, row.scale)}</td
              >
              <td data-label={at("ads_product_net")}
                ><strong>{adMoney(row.net_minor, row.currency, row.scale)}</strong></td
              >
              <td data-label={at("ads_spend")}
                >{adMoney(row.spend_minor, row.currency, row.scale)}</td
              >
              <td data-label="ROAS"
                >{row.roas === null || row.roas === undefined
                  ? "—"
                  : `${(row.roas * 100).toFixed(1)}%`}</td
              >
              <td data-label="CAC">{adMoney(row.cac_minor, row.currency, row.scale)}</td>
            </tr>
          {/each}
        </tbody>
      </AdminTable>
    {:else}
      <AdminEmptyState>{at("ads_no_transactions")}</AdminEmptyState>
    {/if}
  </AdminSettingsGroup>

  {#if stats.currencies.length}
    <AdminSettingsGroup title={at("ads_cohorts")} description={at("ads_cohorts_hint")}>
      <AdminTable layout="fixed" class="admin-table-compact" aria-label={at("ads_cohorts")}>
        <thead>
          <tr>
            <th>{at("ads_currency")}</th>
            <th>{at("ads_first_purchase_amount")}</th>
            <th>{at("ads_repeat_purchase_amount")}</th>
            <th>{at("ads_average_order")}</th>
            <th>D7</th>
            <th>D30</th>
            <th>D90</th>
          </tr>
        </thead>
        <tbody>
          {#each stats.currencies as row (row.currency)}
            <tr>
              <td class="admin-cell-primary" data-label={at("ads_currency")}
                ><strong>{row.currency}</strong></td
              >
              <td data-label={at("ads_first_purchase_amount")}
                >{adMoney(row.first_purchase_minor, row.currency, row.scale)}</td
              >
              <td data-label={at("ads_repeat_purchase_amount")}
                >{adMoney(row.repeat_purchase_minor, row.currency, row.scale)}</td
              >
              <td data-label={at("ads_average_order")}
                >{adMoney(row.average_order_minor, row.currency, row.scale)}</td
              >
              {#each [7, 30, 90] as days (days)}
                <td data-label={`D${days}`}>
                  <div class="ad-report-cell">
                    <span
                      >{adMoney(
                        days === 7 ? row.d7_minor : days === 30 ? row.d30_minor : row.d90_minor,
                        row.currency,
                        row.scale
                      )}</span
                    >
                    <small class="admin-muted"
                      >{stats.mature_cohorts[String(days)] || 0} {at("ads_mature")}</small
                    >
                  </div>
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </AdminTable>
    </AdminSettingsGroup>
  {/if}

  <AdminSettingsGroup title={at("ads_platform")}>
    <AdminFormGrid columns={3} minWidth="140px" class="ad-report-metrics">
      {#each Object.entries(stats.platform) as [label, count] (label)}
        <Card.Root>
          <Card.Header>
            <Card.Description>{at(`ads_${label}`)}</Card.Description>
            <Card.Title>{count ?? "—"}</Card.Title>
          </Card.Header>
        </Card.Root>
      {/each}
      <Card.Root>
        <Card.Header>
          <Card.Description>CTR</Card.Description>
          <Card.Title
            >{stats.ctr === null || stats.ctr === undefined
              ? "—"
              : `${(stats.ctr * 100).toFixed(2)}%`}</Card.Title
          >
        </Card.Header>
      </Card.Root>
      <Card.Root>
        <Card.Header>
          <Card.Description>{at("ads_registration_conversion")}</Card.Description>
          <Card.Title
            >{stats.registration_conversion === null || stats.registration_conversion === undefined
              ? "—"
              : `${(stats.registration_conversion * 100).toFixed(2)}%`}</Card.Title
          >
        </Card.Header>
      </Card.Root>
    </AdminFormGrid>
  </AdminSettingsGroup>
</div>

<style>
  .ad-report-panel {
    display: grid;
    gap: 18px;
    min-width: 0;
  }
  .ad-report-note {
    margin: 0;
    line-height: 1.5;
  }
  .ad-report-panel :global(.ad-report-metrics .admin-cn-card-header) {
    padding-bottom: 14px;
  }
  .ad-report-panel :global(th:not(:first-child)),
  .ad-report-panel :global(td:not(:first-child)) {
    text-align: right;
  }
  .ad-report-panel :global(td) {
    font-variant-numeric: tabular-nums;
  }
  .ad-report-cell {
    display: grid;
    gap: 4px;
    min-width: 0;
  }
  @media (max-width: 720px) {
    .ad-report-panel :global(td:not(:first-child)) {
      text-align: left;
    }
  }
</style>
