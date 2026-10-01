<script lang="ts">
  import { AdminTable, AdminEmptyState } from "$components/patterns/admin/index.js";
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

<p class="admin-muted">{at("ads_report_definition")}</p>
<div class="ad-metrics">
  {#each counters as [label, value]}
    <div class="ad-metric"><span>{at(label)}</span><strong>{value}</strong></div>
  {/each}
</div>
{#if stats.legacy_payment_count}
  <p role="status" class="admin-muted">
    {at("ads_legacy_payments", { count: stats.legacy_payment_count })}
  </p>
{/if}
{#if stats.currencies.length}
  <AdminTable>
    <thead
      ><tr
        ><th>{at("ads_currency")}</th><th>{at("ads_cash")}</th><th>{at("ads_product_gross")}</th><th
          >{at("ads_refunds")}</th
        ><th>{at("ads_product_net")}</th><th>{at("ads_spend")}</th><th>ROAS</th><th>CAC</th></tr
      ></thead
    >
    <tbody
      >{#each stats.currencies as row}
        <tr
          ><td data-label={at("ads_currency")}>{row.currency}</td>
          <td data-label={at("ads_cash")}>{adMoney(row.cash_minor, row.currency, row.scale)}</td>
          <td data-label={at("ads_product_gross")}
            >{adMoney(row.product_minor, row.currency, row.scale)}</td
          >
          <td data-label={at("ads_refunds")}
            >{adMoney(row.refund_minor, row.currency, row.scale)}</td
          >
          <td data-label={at("ads_product_net")}
            >{adMoney(row.net_minor, row.currency, row.scale)}</td
          >
          <td data-label={at("ads_spend")}>{adMoney(row.spend_minor, row.currency, row.scale)}</td>
          <td data-label="ROAS"
            >{row.roas === null || row.roas === undefined
              ? "—"
              : `${(row.roas * 100).toFixed(1)}%`}</td
          >
          <td data-label="CAC">{adMoney(row.cac_minor, row.currency, row.scale)}</td>
        </tr>
      {/each}</tbody
    >
  </AdminTable>
  <h3>{at("ads_cohorts")}</h3>
  <p class="admin-muted">{at("ads_cohorts_hint")}</p>
  <AdminTable
    ><thead
      ><tr
        ><th>{at("ads_currency")}</th><th>{at("ads_first_purchase_amount")}</th><th
          >{at("ads_repeat_purchase_amount")}</th
        ><th>{at("ads_average_order")}</th><th>D7</th><th>D30</th><th>D90</th></tr
      ></thead
    >
    <tbody
      >{#each stats.currencies as row}<tr>
          <td data-label={at("ads_currency")}>{row.currency}</td>
          <td data-label={at("ads_first_purchase_amount")}
            >{adMoney(row.first_purchase_minor, row.currency, row.scale)}</td
          >
          <td data-label={at("ads_repeat_purchase_amount")}
            >{adMoney(row.repeat_purchase_minor, row.currency, row.scale)}</td
          >
          <td data-label={at("ads_average_order")}
            >{adMoney(row.average_order_minor, row.currency, row.scale)}</td
          >
          {#each [7, 30, 90] as days}
            <td data-label={`D${days}`}
              >{adMoney(
                days === 7 ? row.d7_minor : days === 30 ? row.d30_minor : row.d90_minor,
                row.currency,
                row.scale
              )}<small class="admin-muted">
                · {stats.mature_cohorts[String(days)] || 0} {at("ads_mature")}</small
              ></td
            >
          {/each}
        </tr>{/each}</tbody
    >
  </AdminTable>
{:else}<AdminEmptyState><span>{at("ads_no_transactions")}</span></AdminEmptyState>{/if}
<h3>{at("ads_platform")}</h3>
<div class="ad-metrics">
  {#each Object.entries(stats.platform) as [label, count]}<div class="ad-metric">
      <span>{at(`ads_${label}`)}</span><strong>{count ?? "—"}</strong>
    </div>{/each}
  <div class="ad-metric">
    <span>CTR</span><strong
      >{stats.ctr === null || stats.ctr === undefined
        ? "—"
        : `${(stats.ctr * 100).toFixed(2)}%`}</strong
    >
  </div>
  <div class="ad-metric">
    <span>{at("ads_registration_conversion")}</span><strong
      >{stats.registration_conversion === null || stats.registration_conversion === undefined
        ? "—"
        : `${(stats.registration_conversion * 100).toFixed(2)}%`}</strong
    >
  </div>
</div>

<style>
  .ad-metrics {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 12px;
    margin: 16px 0;
  }
  .ad-metric {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 14px;
    border: 1px solid var(--border);
    border-radius: 12px;
  }
  .ad-metric strong {
    font-size: 1.5rem;
  }
</style>
