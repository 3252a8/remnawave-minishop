<script lang="ts">
  import { ArrowRight, TrendingUp, WalletCards } from "$components/ui/icons.js";
  import {
    AdminBadge,
    AdminChartEmptyState,
    AdminEntityLink,
    AdminSortableHeader,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import type { PartnerRow, WithdrawalRow } from "$lib/admin/previewMock/partnerProgram.js";
  import { withdrawalSortColumns, partnerSortColumns } from "$lib/admin/partnerProgramSort.js";
  import { partnerStatusVariant } from "$lib/admin/partnerProgramUi.js";
  import { sortAdminRows } from "$lib/admin/tableSort.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at,
    partners,
    withdrawals,
    partnerSort,
    withdrawalSort,
    onWithdrawalSort,
    money,
    statusLabel,
    onPartnerSort,
    onOpenPartner,
    onOpenWithdrawal,
    onViewPartners,
    onViewWithdrawals,
  }: {
    at: TranslateFn;
    partners: PartnerRow[];
    withdrawals: WithdrawalRow[];
    partnerSort: string;
    withdrawalSort: string;
    onWithdrawalSort: (sort: string) => void;
    money: (value: number) => string;
    statusLabel: (status: string) => string;
    onPartnerSort: (sort: string) => void;
    onOpenPartner: (partner: PartnerRow) => void;
    onOpenWithdrawal: (withdrawal: WithdrawalRow) => void;
    onViewPartners: () => void;
    onViewWithdrawals: () => void;
  } = $props();

  const rowLimit = 6;
  const visibleWithdrawals = $derived(
    sortAdminRows(withdrawals, withdrawalSort, withdrawalSortColumns).slice(0, rowLimit)
  );
  const visiblePartners = $derived(partners.slice(0, rowLimit));
</script>

<article class="admin-card partners-preview-card partners-dashboard-table-card">
  <header>
    <div>
      <WalletCards size={17} /><strong
        >{at("partners_withdrawal_queue", {}, "Withdrawal queue")}</strong
      >
    </div>
    <button type="button" onclick={onViewWithdrawals}
      >{at("partners_view_all", {}, "View all")}<ArrowRight size={14} /></button
    >
  </header>
  {#if visibleWithdrawals.length}
    <AdminTable
      class="admin-table-compact partners-dashboard-table"
      aria-label={at("partners_withdrawal_queue", {}, "Withdrawal queue")}
    >
      <thead>
        <tr>
          <AdminSortableHeader
            label={at("partners_col_partner", {}, "Partner")}
            column={withdrawalSortColumns[1]}
            currentSort={withdrawalSort}
            {at}
            onSort={onWithdrawalSort}
          />
          <AdminSortableHeader
            label={at("partners_col_method", {}, "Method")}
            column={withdrawalSortColumns[2]}
            currentSort={withdrawalSort}
            {at}
            onSort={onWithdrawalSort}
          />
          <AdminSortableHeader
            label={at("partners_col_amount", {}, "Amount")}
            column={withdrawalSortColumns[3]}
            currentSort={withdrawalSort}
            {at}
            onSort={onWithdrawalSort}
          />
          <AdminSortableHeader
            label={at("partners_col_status", {}, "Status")}
            column={withdrawalSortColumns[4]}
            currentSort={withdrawalSort}
            {at}
            onSort={onWithdrawalSort}
          />
        </tr>
      </thead>
      <tbody>
        {#each visibleWithdrawals as withdrawal (withdrawal.id)}
          <tr>
            <td class="admin-cell-primary" data-label={at("partners_col_partner", {}, "Partner")}>
              <AdminEntityLink
                kind="withdrawal"
                label={withdrawal.partner}
                secondary={withdrawal.handle}
                idText={withdrawal.id}
                title={at("partners_open_withdrawal", {}, "Open withdrawal")}
                onclick={() => onOpenWithdrawal(withdrawal)}
              />
            </td>
            <td
              class="partners-dashboard-method"
              data-label={at("partners_col_method", {}, "Method")}
            >
              <span>{at(`partners_method_${withdrawal.method}`, {}, withdrawal.method)}</span>
              <small>{withdrawal.masked}</small>
            </td>
            <td data-label={at("partners_col_amount", {}, "Amount")}>{money(withdrawal.amount)}</td>
            <td data-label={at("partners_col_status", {}, "Status")}>
              <AdminBadge variant={partnerStatusVariant(withdrawal.status)}>
                {statusLabel(withdrawal.status)}
              </AdminBadge>
            </td>
          </tr>
        {/each}
      </tbody>
    </AdminTable>
  {:else}
    <AdminChartEmptyState
      label={at("partners_dashboard_withdrawals_empty", {}, "No withdrawal requests yet")}
      plotHeight={196}
    />
  {/if}
</article>

<article class="admin-card partners-preview-card partners-dashboard-table-card">
  <header>
    <div>
      <TrendingUp size={17} /><strong>{at("partners_top_partners", {}, "Top partners")}</strong>
    </div>
    <button type="button" onclick={onViewPartners}
      >{at("partners_view_all", {}, "View all")}<ArrowRight size={14} /></button
    >
  </header>
  {#if visiblePartners.length}
    <AdminTable
      class="admin-table-compact partners-dashboard-table"
      aria-label={at("partners_top_partners", {}, "Top partners")}
    >
      <thead>
        <tr>
          <AdminSortableHeader
            label={at("partners_col_user", {}, "User")}
            column={partnerSortColumns[0]}
            currentSort={partnerSort}
            {at}
            onSort={onPartnerSort}
          />
          <AdminSortableHeader
            label={at("partners_col_clients", {}, "Clients")}
            column={partnerSortColumns[3]}
            currentSort={partnerSort}
            {at}
            onSort={onPartnerSort}
          />
          <AdminSortableHeader
            label={at("partners_col_earned", {}, "Net commission")}
            column={partnerSortColumns[5]}
            currentSort={partnerSort}
            {at}
            onSort={onPartnerSort}
          />
          <AdminSortableHeader
            label={at("partners_col_status", {}, "Status")}
            column={partnerSortColumns[1]}
            currentSort={partnerSort}
            {at}
            onSort={onPartnerSort}
          />
        </tr>
      </thead>
      <tbody>
        {#each visiblePartners as partner (partner.id)}
          <tr>
            <td class="admin-cell-primary" data-label={at("partners_col_user", {}, "User")}>
              <AdminEntityLink
                kind="user"
                label={partner.name}
                secondary={partner.handle}
                idText={`#${partner.userId}`}
                avatarUrl={partner.avatarUrl}
                title={at("partners_open_partner_card", {}, "Open partner card")}
                onclick={() => onOpenPartner(partner)}
              />
            </td>
            <td data-label={at("partners_col_clients", {}, "Clients")}>{partner.clients}</td>
            <td data-label={at("partners_col_earned", {}, "Net commission")}>
              {money(partner.earned)}
            </td>
            <td data-label={at("partners_col_status", {}, "Status")}>
              <AdminBadge variant={partnerStatusVariant(partner.status)}>
                {statusLabel(partner.status)}
              </AdminBadge>
            </td>
          </tr>
        {/each}
      </tbody>
    </AdminTable>
  {:else}
    <AdminChartEmptyState
      label={at("partners_dashboard_partners_empty", {}, "No partner users yet")}
      plotHeight={196}
    />
  {/if}
</article>
