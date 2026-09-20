<script lang="ts">
  import { Tabs, Tooltip } from "$components/ui/primitives.js";
  import {
    AdminBadge,
    AdminEntityLink,
    AdminPagination,
    AdminSortableHeader,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import type {
    PartnerAuditRow,
    PartnerClientRow,
    PartnerCommissionRow,
    PartnerLedgerRow,
    WithdrawalRow,
  } from "$lib/admin/previewMock/partnerProgram.js";
  import { partnerStatusVariant } from "$lib/admin/partnerProgramUi.js";
  import { sortAdminRows, type AdminSortColumn } from "$lib/admin/tableSort.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type ActivityTab = "clients" | "commissions" | "withdrawals" | "ledger" | "audit";

  let {
    at,
    money,
    partnerId,
    partnerClients,
    partnerCommissions,
    partnerLedger,
    partnerAudit,
    withdrawals,
    onOpenUserCard,
    onOpenPaymentCard,
    onOpenWithdrawal,
  }: {
    at: TranslateFn;
    money: (value: number) => string;
    partnerId: string;
    partnerClients: PartnerClientRow[];
    partnerCommissions: PartnerCommissionRow[];
    partnerLedger: PartnerLedgerRow[];
    partnerAudit: PartnerAuditRow[];
    withdrawals: WithdrawalRow[];
    onOpenUserCard: (userId: number) => void;
    onOpenPaymentCard: (paymentId: number) => void;
    onOpenWithdrawal: (withdrawal: WithdrawalRow) => void;
  } = $props();

  const tabs: ActivityTab[] = ["clients", "commissions", "withdrawals", "ledger", "audit"];
  // Five stacked lists share one page control; four rows made every tab look
  // emptier than the data behind it.
  const pageSize = 8;

  const partnerWithdrawals = $derived(
    withdrawals.filter((withdrawal) => withdrawal.partnerId === partnerId)
  );

  const clientColumns: AdminSortColumn<PartnerClientRow>[] = [
    { asc: "client_asc", desc: "client_desc", defaultDirection: "asc", value: (row) => row.label },
    {
      asc: "attributed_asc",
      desc: "attributed_desc",
      defaultDirection: "desc",
      value: (row) => row.attributed,
    },
    {
      asc: "payments_asc",
      desc: "payments_desc",
      defaultDirection: "desc",
      value: (row) => row.payments,
    },
    { asc: "gross_asc", desc: "gross_desc", defaultDirection: "desc", value: (row) => row.gross },
  ];
  const commissionColumns: AdminSortColumn<PartnerCommissionRow>[] = [
    {
      asc: "commission_asc",
      desc: "commission_desc",
      defaultDirection: "desc",
      value: (row) => row.id,
    },
    { asc: "client_asc", desc: "client_desc", defaultDirection: "asc", value: (row) => row.client },
    {
      asc: "created_asc",
      desc: "created_desc",
      defaultDirection: "desc",
      value: (row) => row.created,
    },
    { asc: "basis_asc", desc: "basis_desc", defaultDirection: "desc", value: (row) => row.gross },
    {
      asc: "amount_asc",
      desc: "amount_desc",
      defaultDirection: "desc",
      value: (row) => row.amount,
    },
  ];
  const withdrawalColumns: AdminSortColumn<WithdrawalRow>[] = [
    {
      asc: "withdrawal_asc",
      desc: "withdrawal_desc",
      defaultDirection: "desc",
      value: (row) => row.id,
    },
    { asc: "method_asc", desc: "method_desc", defaultDirection: "asc", value: (row) => row.method },
    {
      asc: "amount_asc",
      desc: "amount_desc",
      defaultDirection: "desc",
      value: (row) => row.amount,
    },
    {
      asc: "requested_asc",
      desc: "requested_desc",
      defaultDirection: "desc",
      value: (row) => row.requested,
    },
  ];
  const ledgerColumns: AdminSortColumn<PartnerLedgerRow>[] = [
    { asc: "ledger_asc", desc: "ledger_desc", defaultDirection: "desc", value: (row) => row.id },
    { asc: "kind_asc", desc: "kind_desc", defaultDirection: "asc", value: (row) => row.kindKey },
    {
      asc: "created_asc",
      desc: "created_desc",
      defaultDirection: "desc",
      value: (row) => row.created,
    },
    {
      asc: "amount_asc",
      desc: "amount_desc",
      defaultDirection: "desc",
      value: (row) => row.amount,
    },
  ];
  const auditColumns: AdminSortColumn<PartnerAuditRow>[] = [
    { asc: "audit_asc", desc: "audit_desc", defaultDirection: "desc", value: (row) => row.id },
    {
      asc: "created_asc",
      desc: "created_desc",
      defaultDirection: "desc",
      value: (row) => row.created,
    },
    { asc: "actor_asc", desc: "actor_desc", defaultDirection: "asc", value: (row) => row.actor },
    {
      asc: "action_asc",
      desc: "action_desc",
      defaultDirection: "asc",
      value: (row) => row.actionKey,
    },
  ];

  let activeTab = $state<ActivityTab>("clients");
  let currentSort = $state("gross_desc");
  let page = $state(0);

  // Each tab is a different entity, so a tab switch resets both the page and
  // the sort — a sort id from another tab has no matching column here.
  const defaultSortByTab: Record<ActivityTab, string> = {
    clients: "gross_desc",
    commissions: "commission_desc",
    withdrawals: "withdrawal_desc",
    ledger: "ledger_desc",
    audit: "audit_desc",
  };

  const sortedClients = $derived(sortAdminRows(partnerClients, currentSort, clientColumns));
  const sortedCommissions = $derived(
    sortAdminRows(partnerCommissions, currentSort, commissionColumns)
  );
  const sortedWithdrawals = $derived(
    sortAdminRows(partnerWithdrawals, currentSort, withdrawalColumns)
  );
  const sortedLedger = $derived(sortAdminRows(partnerLedger, currentSort, ledgerColumns));
  const sortedAudit = $derived(sortAdminRows(partnerAudit, currentSort, auditColumns));

  const totalRows = $derived(
    activeTab === "clients"
      ? sortedClients.length
      : activeTab === "commissions"
        ? sortedCommissions.length
        : activeTab === "withdrawals"
          ? sortedWithdrawals.length
          : activeTab === "ledger"
            ? sortedLedger.length
            : sortedAudit.length
  );
  const pageCount = $derived(Math.max(1, Math.ceil(totalRows / pageSize)));
  const from = $derived(page * pageSize);
  const to = $derived(from + pageSize);
  const pagedClients = $derived(sortedClients.slice(from, to));
  const pagedCommissions = $derived(sortedCommissions.slice(from, to));
  const pagedWithdrawals = $derived(sortedWithdrawals.slice(from, to));
  const pagedLedger = $derived(sortedLedger.slice(from, to));
  const pagedAudit = $derived(sortedAudit.slice(from, to));

  function changeTab(value: string): void {
    activeTab = value as ActivityTab;
    currentSort = defaultSortByTab[activeTab];
    page = 0;
  }

  function changeSort(sort: string): void {
    currentSort = sort;
    page = 0;
  }

  function statusLabel(status: string): string {
    return at(`partners_status_${status}`, {}, status);
  }

  const openUserLabel = $derived(at("partners_open_user_card", {}, "Open user card"));
  const openPaymentLabel = $derived(at("partners_open_payment_card", {}, "Open payment"));
  const openWithdrawalLabel = $derived(at("partners_open_withdrawal", {}, "Open withdrawal"));
</script>

<article class="admin-card partners-detail-tabs">
  <Tabs.Root class="admin-tabs-root" value={activeTab} onValueChange={changeTab}>
    <Tabs.List class="admin-tabs-list partners-detail-tab-list">
      {#each tabs as tab (tab)}
        <Tabs.Trigger value={tab} class="admin-tabs-trigger">
          {at(`partners_detail_tab_${tab}`, {}, tab)}
        </Tabs.Trigger>
      {/each}
    </Tabs.List>
  </Tabs.Root>

  <AdminTable class="admin-table-compact">
    {#if activeTab === "clients"}
      <thead>
        <tr>
          <AdminSortableHeader
            label={at("partners_col_client", {}, "Client")}
            column={clientColumns[0]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <AdminSortableHeader
            label={at("partners_col_attributed", {}, "Attributed")}
            column={clientColumns[1]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <th>{at("partners_col_source", {}, "Source")}</th>
          <AdminSortableHeader
            label={at("partners_col_payments", {}, "Payments")}
            column={clientColumns[2]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <AdminSortableHeader
            label={at("partners_col_gross", {}, "Gross")}
            column={clientColumns[3]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
        </tr>
      </thead>
      <tbody>
        {#each pagedClients as client (client.id)}
          <tr>
            <td class="admin-cell-primary" data-label={at("partners_col_client", {}, "Client")}>
              <AdminEntityLink
                kind="user"
                label={client.label}
                secondary={client.handle}
                idText={client.id}
                title={client.userId ? openUserLabel : ""}
                onclick={client.userId ? () => onOpenUserCard(client.userId) : undefined}
              />
            </td>
            <td class="admin-cell-mono" data-label={at("partners_col_attributed", {}, "Attributed")}
              >{client.attributed}</td
            >
            <td data-label={at("partners_col_source", {}, "Source")}
              >{at(`partners_source_${client.source}`, {}, client.source)}</td
            >
            <td data-label={at("partners_col_payments", {}, "Payments")}>{client.payments}</td>
            <td data-label={at("partners_col_gross", {}, "Gross")}>{money(client.gross)}</td>
          </tr>
        {/each}
      </tbody>
    {:else if activeTab === "commissions"}
      <thead>
        <tr>
          <AdminSortableHeader
            label={at("partners_col_commission_id", {}, "Commission")}
            column={commissionColumns[0]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <AdminSortableHeader
            label={at("partners_col_payment", {}, "Payment")}
            column={commissionColumns[1]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <AdminSortableHeader
            label={at("partners_col_created", {}, "Created")}
            column={commissionColumns[2]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <AdminSortableHeader
            label={at("partners_col_basis", {}, "Basis")}
            column={commissionColumns[3]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <AdminSortableHeader
            label={at("partners_col_commission", {}, "Commission")}
            column={commissionColumns[4]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <th>{at("partners_col_status", {}, "Status")}</th>
        </tr>
      </thead>
      <tbody>
        {#each pagedCommissions as commission (commission.id)}
          <tr>
            <td
              class="admin-cell-mono"
              data-label={at("partners_col_commission_id", {}, "Commission")}
            >
              {commission.id}
            </td>
            <td class="admin-cell-primary" data-label={at("partners_col_payment", {}, "Payment")}>
              <AdminEntityLink
                kind="payment"
                label={`#${commission.paymentId}`}
                secondary={commission.client}
                idText={commission.clientHandle}
                title={openPaymentLabel}
                onclick={() => onOpenPaymentCard(commission.paymentId)}
              />
            </td>
            <td class="admin-cell-mono" data-label={at("partners_col_created", {}, "Created")}
              >{commission.created}</td
            >
            <td data-label={at("partners_col_basis", {}, "Basis")}
              >{money(commission.gross)} · {commission.rate}%</td
            >
            <td data-label={at("partners_col_commission", {}, "Commission")}>
              <span class:partners-negative={commission.amount < 0}>{money(commission.amount)}</span
              >
            </td>
            <td data-label={at("partners_col_status", {}, "Status")}>
              {#if commission.status === "reversed"}
                <Tooltip.Root>
                  <Tooltip.Trigger
                    class="partners-status-tooltip-trigger"
                    type="button"
                    aria-label={`${statusLabel(commission.status)}. ${at(
                      "partners_status_reversed_hint",
                      {},
                      "The commission was cancelled because the customer payment was refunded or voided."
                    )}`}
                  >
                    <AdminBadge variant={partnerStatusVariant(commission.status)}
                      >{statusLabel(commission.status)}</AdminBadge
                    >
                  </Tooltip.Trigger>
                  <Tooltip.Portal>
                    <Tooltip.Content class="partners-status-tooltip" side="top">
                      {at(
                        "partners_status_reversed_hint",
                        {},
                        "The commission was cancelled because the customer payment was refunded or voided."
                      )}
                    </Tooltip.Content>
                  </Tooltip.Portal>
                </Tooltip.Root>
              {:else}
                <AdminBadge variant={partnerStatusVariant(commission.status)}
                  >{statusLabel(commission.status)}</AdminBadge
                >
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    {:else if activeTab === "withdrawals"}
      <thead>
        <tr>
          <AdminSortableHeader
            label={at("partners_col_withdrawal", {}, "Withdrawal")}
            column={withdrawalColumns[0]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <AdminSortableHeader
            label={at("partners_col_method", {}, "Method")}
            column={withdrawalColumns[1]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <AdminSortableHeader
            label={at("partners_col_amount", {}, "Amount")}
            column={withdrawalColumns[2]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <AdminSortableHeader
            label={at("partners_requested", {}, "Requested")}
            column={withdrawalColumns[3]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <th>{at("partners_col_status", {}, "Status")}</th>
        </tr>
      </thead>
      <tbody>
        {#each pagedWithdrawals as withdrawal (withdrawal.id)}
          <tr>
            <td
              class="partners-ref-cell"
              data-label={at("partners_col_withdrawal", {}, "Withdrawal")}
            >
              <AdminEntityLink
                kind="withdrawal"
                label={withdrawal.id}
                secondary={at(`partners_method_${withdrawal.method}`, {}, withdrawal.method)}
                idText={withdrawal.masked}
                title={openWithdrawalLabel}
                onclick={() => onOpenWithdrawal(withdrawal)}
              />
            </td>
            <td data-label={at("partners_col_method", {}, "Method")}>
              {at(`partners_method_${withdrawal.method}`, {}, withdrawal.method)}
            </td>
            <td data-label={at("partners_col_amount", {}, "Amount")}>{money(withdrawal.amount)}</td>
            <td class="admin-cell-mono" data-label={at("partners_requested", {}, "Requested")}
              >{withdrawal.requested}</td
            >
            <td data-label={at("partners_col_status", {}, "Status")}>
              <AdminBadge variant={partnerStatusVariant(withdrawal.status)}
                >{statusLabel(withdrawal.status)}</AdminBadge
              >
            </td>
          </tr>
        {/each}
      </tbody>
    {:else if activeTab === "ledger"}
      <thead>
        <tr>
          <AdminSortableHeader
            label={at("partners_col_entry", {}, "Entry")}
            column={ledgerColumns[0]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <AdminSortableHeader
            label={at("partners_col_operation", {}, "Operation")}
            column={ledgerColumns[1]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <AdminSortableHeader
            label={at("partners_col_created", {}, "Created")}
            column={ledgerColumns[2]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <AdminSortableHeader
            label={at("partners_col_amount", {}, "Amount")}
            column={ledgerColumns[3]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <th>{at("partners_col_balance_after", {}, "Balance after")}</th>
        </tr>
      </thead>
      <tbody>
        {#each pagedLedger as entry (entry.id)}
          {@const linkedCommission =
            entry.refKind === "commission"
              ? partnerCommissions.find((commission) => commission.id === entry.refId)
              : undefined}
          <tr>
            <td class="admin-cell-mono" data-label={at("partners_col_entry", {}, "Entry")}
              >{entry.id}</td
            >
            <td
              class="admin-cell-primary"
              data-label={at("partners_col_operation", {}, "Operation")}
            >
              {#if entry.refKind === "withdrawal"}
                <AdminEntityLink
                  kind="withdrawal"
                  label={at(`partners_ledger_${entry.kindKey}`, {}, entry.kindKey)}
                  idText={entry.refId}
                  title={openWithdrawalLabel}
                  onclick={() => {
                    const target = partnerWithdrawals.find((item) => item.id === entry.refId);
                    if (target) onOpenWithdrawal(target);
                  }}
                />
              {:else}
                <AdminEntityLink
                  kind={entry.refKind === "commission" ? "payment" : "application"}
                  label={at(`partners_ledger_${entry.kindKey}`, {}, entry.kindKey)}
                  idText={entry.refId}
                  title={linkedCommission ? openPaymentLabel : ""}
                  onclick={linkedCommission
                    ? () => onOpenPaymentCard(linkedCommission.paymentId)
                    : undefined}
                />
              {/if}
            </td>
            <td class="admin-cell-mono" data-label={at("partners_col_created", {}, "Created")}
              >{entry.created}</td
            >
            <td data-label={at("partners_col_amount", {}, "Amount")}>
              <span class:partners-negative={entry.amount < 0}>{money(entry.amount)}</span>
            </td>
            <td data-label={at("partners_col_balance_after", {}, "Balance after")}
              >{money(entry.balanceAfter)}</td
            >
          </tr>
        {/each}
      </tbody>
    {:else}
      <thead>
        <tr>
          <AdminSortableHeader
            label={at("partners_col_entry", {}, "Entry")}
            column={auditColumns[0]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <AdminSortableHeader
            label={at("partners_col_created", {}, "Created")}
            column={auditColumns[1]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <AdminSortableHeader
            label={at("partners_col_actor", {}, "Actor")}
            column={auditColumns[2]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <AdminSortableHeader
            label={at("partners_col_action", {}, "Action")}
            column={auditColumns[3]}
            {currentSort}
            {at}
            onSort={changeSort}
          />
          <th>{at("partners_col_detail", {}, "Detail")}</th>
        </tr>
      </thead>
      <tbody>
        {#each pagedAudit as entry (entry.id)}
          <tr>
            <td class="admin-cell-mono" data-label={at("partners_col_entry", {}, "Entry")}
              >{entry.id}</td
            >
            <td class="admin-cell-mono" data-label={at("partners_col_created", {}, "Created")}
              >{entry.created}</td
            >
            <td class="admin-cell-primary" data-label={at("partners_col_actor", {}, "Actor")}>
              <AdminEntityLink
                kind="user"
                label={entry.actor}
                title={openUserLabel}
                onclick={() => onOpenUserCard(entry.actorUserId)}
              />
            </td>
            <td data-label={at("partners_col_action", {}, "Action")}
              >{at(`partners_audit_${entry.actionKey}`, {}, entry.actionKey)}</td
            >
            <td class="admin-cell-mono" data-label={at("partners_col_detail", {}, "Detail")}
              >{entry.detail}</td
            >
          </tr>
        {/each}
      </tbody>
    {/if}
  </AdminTable>

  <AdminPagination
    {page}
    {pageCount}
    total={totalRows}
    pageLabel={at("page_short", {}, "Page")}
    ofLabel={at("pagination_of", {}, "of")}
    totalLabel={at("total", {}, "Total")}
    jumpLabel={at("page_short", {}, "Page")}
    jumpAriaLabel={at("pagination_jump_aria", {}, "Go to page")}
    goLabel={at("pagination_go", {}, "Go")}
    prevLabel={at("back", {}, "Back")}
    nextLabel={at("next", {}, "Next")}
    onPageChange={(nextPage) => (page = nextPage)}
  />
</article>
