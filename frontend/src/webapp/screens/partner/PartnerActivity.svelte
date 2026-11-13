<script lang="ts">
  import { History, UsersRound, WalletCards } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import { Tabs, Tooltip } from "$components/ui/primitives.js";
  import {
    AdminPagination,
    AdminSortableHeader,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import type { AdminSortColumn } from "$lib/admin/tableSort.js";
  import type {
    PartnerClientPreview,
    PartnerCommissionPreview,
    PartnerCurrency,
    PartnerWithdrawalPreview,
  } from "$lib/webapp/previewMock/partnerProgram.js";
  import type { Translate } from "$lib/webapp/types.js";

  type ActivityTab = "clients" | "commissions" | "withdrawals";
  type TableTranslate = (
    key: string,
    params?: Record<string, unknown>,
    fallback?: string
  ) => string;

  let {
    t,
    commissionBps,
    selectedCurrency,
    currencyClients,
    currencyCommissions,
    currencyWithdrawals,
    pagedClients,
    pagedCommissions,
    pagedWithdrawals,
    clientColumns,
    commissionColumns,
    withdrawalColumns,
    activeTab = $bindable(),
    activitySort = $bindable(),
    activityPage = $bindable(),
    activityPageCount,
    activityTotal,
    changeActivityTab,
    changeActivitySort,
    tableTranslate,
    formatMoney,
    formatDate,
    commissionStatusLabel,
    cancelWithdrawal,
  }: {
    t: Translate;
    commissionBps: number;
    selectedCurrency: PartnerCurrency;
    currencyClients: PartnerClientPreview[];
    currencyCommissions: PartnerCommissionPreview[];
    currencyWithdrawals: PartnerWithdrawalPreview[];
    pagedClients: PartnerClientPreview[];
    pagedCommissions: PartnerCommissionPreview[];
    pagedWithdrawals: PartnerWithdrawalPreview[];
    clientColumns: AdminSortColumn<PartnerClientPreview>[];
    commissionColumns: AdminSortColumn<PartnerCommissionPreview>[];
    withdrawalColumns: AdminSortColumn<PartnerWithdrawalPreview>[];
    activeTab: ActivityTab;
    activitySort: string;
    activityPage: number;
    activityPageCount: number;
    activityTotal: number;
    changeActivityTab: (value: string) => void;
    changeActivitySort: (value: string) => void;
    tableTranslate: TableTranslate;
    formatMoney: (amount: number, currency: PartnerCurrency) => string;
    formatDate: (value: string) => string;
    commissionStatusLabel: (item: PartnerCommissionPreview) => string;
    cancelWithdrawal: (id: string) => Promise<void>;
  } = $props();
</script>

<Card id="partner-activity" class="partner-stats-card" data-tour="clients">
  <div class="partner-section-head">
    <div class="partner-section-title">
      <History size={30} />
      <div>
        <strong>{t("wa_partner_stats_title")}</strong>
        <p>{t("wa_partner_stats_hint")}</p>
      </div>
    </div>
  </div>
  <section class="partner-kpis" aria-label={t("wa_partner_stats_title")}>
    <div>
      <span>{t("wa_partner_rate")}</span><strong>{commissionBps / 100}%</strong>
    </div>
    <div><span>{t("wa_partner_clients")}</span><strong>{currencyClients.length}</strong></div>
    <div>
      <span>{t("wa_partner_external_purchases")}</span><strong
        >{currencyClients.reduce((sum, item) => sum + item.payments, 0)}</strong
      >
    </div>
    <div>
      <span>{t("wa_partner_client_revenue")}</span><strong
        >{formatMoney(
          currencyClients.reduce((sum, item) => sum + item.gross, 0),
          selectedCurrency
        )}</strong
      >
    </div>
  </section>

  <div class="partner-activity">
    <Tabs.Root class="partner-tabs-root" value={activeTab} onValueChange={changeActivityTab}>
      <Tabs.List class="partner-tabs" aria-label={t("wa_partner_stats_title")}>
        {#each ["clients", "commissions", "withdrawals"] as tab (tab)}
          <Tabs.Trigger class="partner-tabs-trigger" value={tab}>
            {t(`wa_partner_tab_${tab}`)}
            <b
              >{tab === "clients"
                ? currencyClients.length
                : tab === "commissions"
                  ? currencyCommissions.length
                  : currencyWithdrawals.length}</b
            >
          </Tabs.Trigger>
        {/each}
      </Tabs.List>
    </Tabs.Root>

    {#if activeTab === "clients" && currencyClients.length}
      <div class="partner-activity-table">
        <AdminTable class="admin-table-compact partner-data-table">
          <thead>
            <tr>
              <AdminSortableHeader
                label={t("wa_partner_table_client")}
                column={clientColumns[0]}
                currentSort={activitySort}
                at={tableTranslate}
                onSort={changeActivitySort}
              />
              <AdminSortableHeader
                label={t("wa_partner_table_date")}
                column={clientColumns[1]}
                currentSort={activitySort}
                at={tableTranslate}
                onSort={changeActivitySort}
              />
              <AdminSortableHeader
                label={t("wa_partner_client_source")}
                column={clientColumns[2]}
                currentSort={activitySort}
                at={tableTranslate}
                onSort={changeActivitySort}
              />
              <AdminSortableHeader
                label={t("wa_partner_client_payments")}
                column={clientColumns[3]}
                currentSort={activitySort}
                at={tableTranslate}
                onSort={changeActivitySort}
              />
              <AdminSortableHeader
                label={t("wa_partner_client_gross")}
                column={clientColumns[4]}
                currentSort={activitySort}
                at={tableTranslate}
                onSort={changeActivitySort}
              />
            </tr>
          </thead>
          <tbody>
            {#each pagedClients as client (client.id)}
              <tr>
                <td class="admin-cell-primary" data-label={t("wa_partner_table_client")}>
                  <span class="partner-table-primary">
                    <strong>{client.label}</strong><small>{client.id}</small>
                  </span>
                </td>
                <td data-label={t("wa_partner_table_date")}>{formatDate(client.attributedAt)}</td>
                <td data-label={t("wa_partner_client_source")}
                  >{t(`wa_partner_source_${client.source}`)}</td
                >
                <td data-label={t("wa_partner_client_payments")}>{client.payments}</td>
                <td data-label={t("wa_partner_client_gross")}
                  >{formatMoney(client.gross, client.currency)}</td
                >
              </tr>
            {/each}
          </tbody>
        </AdminTable>
      </div>
    {:else if activeTab === "commissions" && currencyCommissions.length}
      <div class="partner-activity-table">
        <AdminTable class="admin-table-compact partner-data-table">
          <thead>
            <tr>
              <AdminSortableHeader
                label={t("wa_partner_table_client")}
                column={commissionColumns[0]}
                currentSort={activitySort}
                at={tableTranslate}
                onSort={changeActivitySort}
              />
              <AdminSortableHeader
                label={t("wa_partner_table_date")}
                column={commissionColumns[1]}
                currentSort={activitySort}
                at={tableTranslate}
                onSort={changeActivitySort}
              />
              <AdminSortableHeader
                label={t("wa_partner_commission_basis")}
                column={commissionColumns[2]}
                currentSort={activitySort}
                at={tableTranslate}
                onSort={changeActivitySort}
              />
              <AdminSortableHeader
                label={t("wa_partner_commission")}
                column={commissionColumns[3]}
                currentSort={activitySort}
                at={tableTranslate}
                onSort={changeActivitySort}
              />
              <AdminSortableHeader
                label={t("wa_partner_table_status")}
                column={commissionColumns[4]}
                currentSort={activitySort}
                at={tableTranslate}
                onSort={changeActivitySort}
              />
            </tr>
          </thead>
          <tbody>
            {#each pagedCommissions as commission (commission.id)}
              <tr>
                <td class="admin-cell-primary" data-label={t("wa_partner_table_client")}>
                  <span class="partner-table-primary">
                    <strong>{commission.clientLabel}</strong><small>{commission.id}</small>
                  </span>
                </td>
                <td data-label={t("wa_partner_table_date")}>{formatDate(commission.createdAt)}</td>
                <td data-label={t("wa_partner_commission_basis")}
                  >{formatMoney(commission.gross, commission.currency)} · {commission.rate}%</td
                >
                <td data-label={t("wa_partner_commission")}>
                  <strong class:negative={commission.amount < 0}
                    >{formatMoney(commission.amount, commission.currency)}</strong
                  >
                </td>
                <td data-label={t("wa_partner_table_status")}>
                  {#if commission.status === "reversed"}
                    <Tooltip.Root>
                      <Tooltip.Trigger
                        class="partner-status partner-status-reversed partner-status-tooltip-trigger"
                        type="button"
                        aria-label={`${commissionStatusLabel(commission)}. ${t("wa_partner_commission_status_reversed_hint")}`}
                      >
                        {commissionStatusLabel(commission)}
                      </Tooltip.Trigger>
                      <Tooltip.Portal>
                        <Tooltip.Content
                          class="payment-method-tooltip partner-status-tooltip-content"
                          side="top"
                        >
                          {t("wa_partner_commission_status_reversed_hint")}
                        </Tooltip.Content>
                      </Tooltip.Portal>
                    </Tooltip.Root>
                  {:else}
                    <span class="partner-status partner-status-{commission.status}"
                      >{commissionStatusLabel(commission)}</span
                    >
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </AdminTable>
      </div>
    {:else if activeTab === "withdrawals" && currencyWithdrawals.length}
      <div class="partner-activity-table">
        <AdminTable class="admin-table-compact partner-data-table">
          <thead>
            <tr>
              <AdminSortableHeader
                label={t("wa_partner_table_method")}
                column={withdrawalColumns[0]}
                currentSort={activitySort}
                at={tableTranslate}
                onSort={changeActivitySort}
              />
              <AdminSortableHeader
                label={t("wa_partner_table_date")}
                column={withdrawalColumns[1]}
                currentSort={activitySort}
                at={tableTranslate}
                onSort={changeActivitySort}
              />
              <AdminSortableHeader
                label={t("wa_partner_withdrawal_amount")}
                column={withdrawalColumns[2]}
                currentSort={activitySort}
                at={tableTranslate}
                onSort={changeActivitySort}
              />
              <AdminSortableHeader
                label={t("wa_partner_table_status")}
                column={withdrawalColumns[3]}
                currentSort={activitySort}
                at={tableTranslate}
                onSort={changeActivitySort}
              />
              <th>{t("wa_partner_table_action")}</th>
            </tr>
          </thead>
          <tbody>
            {#each pagedWithdrawals as withdrawal (withdrawal.id)}
              <tr>
                <td class="admin-cell-primary" data-label={t("wa_partner_table_method")}>
                  <span class="partner-table-primary">
                    <strong>{t(`wa_partner_method_${withdrawal.method}`)}</strong>
                    <small>{withdrawal.id} · {withdrawal.masked}</small>
                    {#if withdrawal.message}<small class="partner-table-message"
                        >{withdrawal.message}</small
                      >{/if}
                  </span>
                </td>
                <td data-label={t("wa_partner_table_date")}>{formatDate(withdrawal.createdAt)}</td>
                <td data-label={t("wa_partner_withdrawal_amount")}
                  >{formatMoney(withdrawal.amount, withdrawal.currency)}</td
                >
                <td data-label={t("wa_partner_table_status")}>
                  <span class="partner-status partner-status-{withdrawal.status}"
                    >{t(`wa_partner_withdrawal_status_${withdrawal.status}`)}</span
                  >
                </td>
                <td class="admin-cell-actions" data-label={t("wa_partner_table_action")}>
                  {#if withdrawal.status === "requested"}
                    <Button
                      variant="outline"
                      size="sm"
                      onclick={() => cancelWithdrawal(withdrawal.id)}
                      >{t("wa_partner_withdrawal_cancel")}</Button
                    >
                  {:else}
                    <span class="partner-table-no-action">—</span>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </AdminTable>
      </div>
    {:else}
      <div class="partner-empty">
        {#if activeTab === "clients"}
          <UsersRound size={24} /><strong>{t("wa_partner_clients_empty_title")}</strong>
          <p>{t("wa_partner_clients_empty_hint")}</p>
        {:else if activeTab === "commissions"}
          <WalletCards size={24} /><strong>{t("wa_partner_commissions_empty_title")}</strong>
          <p>{t("wa_partner_commissions_empty_hint")}</p>
        {:else}
          <WalletCards size={24} /><strong>{t("wa_partner_withdrawals_empty_title")}</strong>
          <p>{t("wa_partner_withdrawals_empty_hint")}</p>
        {/if}
      </div>
    {/if}

    <AdminPagination
      page={activityPage}
      pageCount={activityPageCount}
      total={activityTotal}
      pageLabel={t("wa_partner_pagination_page")}
      ofLabel={t("wa_partner_pagination_of")}
      totalLabel={t("wa_partner_pagination_total")}
      jumpLabel={t("wa_partner_pagination_page")}
      jumpAriaLabel={t("wa_partner_pagination_jump")}
      goLabel={t("wa_partner_pagination_go")}
      prevLabel={t("wa_partner_pagination_previous")}
      nextLabel={t("wa_partner_pagination_next")}
      onPageChange={(nextPage) => (activityPage = nextPage)}
    />
  </div>
</Card>
