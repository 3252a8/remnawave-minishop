<script lang="ts">
  import { onDestroy } from "svelte";
  import { FileText, Plus, UsersRound, WalletCards } from "$components/ui/icons.js";
  import { Input } from "$components/ui/index.js";
  import {
    AdminBadge,
    AdminButton,
    AdminListToolbar,
    AdminField,
    AdminEmptyState,
    AdminPagination,
    AdminEntityLink,
    AdminSelect,
    AdminSortableHeader,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import { sortAdminRows } from "$lib/admin/tableSort.js";
  import {
    applicationSortColumns,
    partnerSortColumns,
    withdrawalSortColumns,
  } from "$lib/admin/partnerProgramSort.js";
  import { USERS_PAGE_SIZE } from "$lib/admin/stores/usersStoreState.js";
  import type {
    ApplicationRow,
    PartnerRow,
    WithdrawalRow,
  } from "$lib/admin/previewMock/partnerProgram.js";
  import { partnerStatusVariant } from "$lib/admin/partnerProgramUi.js";
  import type { AdminPartnerListQuery } from "$lib/admin/partnerProgramApi.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type View = "partners" | "applications" | "withdrawals";
  type Partner = PartnerRow;
  type Application = ApplicationRow;
  type Withdrawal = WithdrawalRow;

  let {
    at,
    partners,
    partnerTotal,
    partnerQuery,
    applications,
    withdrawals,
    view,
    money,
    onAddPartner,
    onOpenPartner,
    onOpenApplication,
    onOpenWithdrawal,
    onOpenUserCard,
    onPartnerQueryChange,
  }: {
    at: TranslateFn;
    partners: PartnerRow[];
    partnerTotal: number;
    partnerQuery: AdminPartnerListQuery;
    applications: ApplicationRow[];
    withdrawals: WithdrawalRow[];
    view: View;
    money: (value: number) => string;
    onAddPartner: () => void;
    onOpenPartner: (partner: Partner) => void;
    onOpenApplication: (application: Application) => void;
    onOpenWithdrawal: (withdrawal: Withdrawal) => void;
    onOpenUserCard: (userId: number) => void;
    onPartnerQueryChange: (query: AdminPartnerListQuery) => Promise<void>;
  } = $props();

  function openPartnerById(partnerId: string): void {
    const target = partners.find((partner) => partner.id === partnerId);
    if (target) onOpenPartner(target);
  }

  const openPartnerLabel = $derived(at("partners_open_partner_card", {}, "Open partner card"));
  const openUserLabel = $derived(at("partners_open_user_card", {}, "Open user card"));
  const openApplicationLabel = $derived(at("partners_open_application", {}, "Open application"));
  const openWithdrawalLabel = $derived(at("partners_open_withdrawal", {}, "Open withdrawal"));

  const pageSize = USERS_PAGE_SIZE;
  function initialPartnerQuery(): AdminPartnerListQuery {
    return partnerQuery;
  }
  let partnerSearch = $state(initialPartnerQuery().search);
  let partnerStatus = $state(initialPartnerQuery().status);
  let partnerSort = $state(initialPartnerQuery().sort);
  let partnerPage = $state(initialPartnerQuery().page);
  let partnerSearchTimer: ReturnType<typeof setTimeout> | undefined;
  let applicationSearch = $state("");
  let applicationStatus = $state("all");
  let applicationSort = $state("submitted_desc");
  let applicationPage = $state(0);
  let withdrawalSearch = $state("");
  let withdrawalStatus = $state("all");
  let withdrawalSort = $state("requested_desc");
  let withdrawalPage = $state(0);

  const sortedPartners = $derived(partners);
  const partnerPageCount = $derived(Math.max(1, Math.ceil(partnerTotal / pageSize)));
  const pagedPartners = $derived(partners);

  const filteredApplications = $derived(
    applications.filter((application) => {
      const query = applicationSearch.trim().toLocaleLowerCase();
      const matchesQuery =
        !query ||
        `${application.user} ${application.handle} ${application.id}`
          .toLocaleLowerCase()
          .includes(query);
      return (
        matchesQuery && (applicationStatus === "all" || application.status === applicationStatus)
      );
    })
  );
  const sortedApplications = $derived(
    sortAdminRows(filteredApplications, applicationSort, applicationSortColumns)
  );
  const applicationPageCount = $derived(
    Math.max(1, Math.ceil(sortedApplications.length / pageSize))
  );
  const pagedApplications = $derived(
    sortedApplications.slice(applicationPage * pageSize, (applicationPage + 1) * pageSize)
  );

  const filteredWithdrawals = $derived(
    withdrawals.filter((withdrawal) => {
      const query = withdrawalSearch.trim().toLocaleLowerCase();
      const matchesQuery =
        !query ||
        `${withdrawal.partner} ${withdrawal.handle} ${withdrawal.id} ${withdrawal.masked}`
          .toLocaleLowerCase()
          .includes(query);
      return matchesQuery && (withdrawalStatus === "all" || withdrawal.status === withdrawalStatus);
    })
  );
  const sortedWithdrawals = $derived(
    sortAdminRows(filteredWithdrawals, withdrawalSort, withdrawalSortColumns)
  );
  const withdrawalPageCount = $derived(Math.max(1, Math.ceil(sortedWithdrawals.length / pageSize)));
  const pagedWithdrawals = $derived(
    sortedWithdrawals.slice(withdrawalPage * pageSize, (withdrawalPage + 1) * pageSize)
  );

  const paginationLabels = $derived({
    page: at("page_short", {}, "Page"),
    of: at("pagination_of", {}, "of"),
    total: at("total", {}, "Total"),
    jump: at("pagination_jump_aria", {}, "Go to page"),
    go: at("pagination_go", {}, "Go"),
    back: at("back", {}, "Back"),
    next: at("next", {}, "Next"),
  });

  function statusLabel(status: string): string {
    return at(`partners_status_${status}`, {}, status);
  }

  function partnerQueryValue(): AdminPartnerListQuery {
    return {
      page: partnerPage,
      search: partnerSearch,
      status: partnerStatus,
      sort: partnerSort,
    };
  }

  function loadPartnerQuery(): void {
    if (partnerSearchTimer) clearTimeout(partnerSearchTimer);
    partnerSearchTimer = undefined;
    void onPartnerQueryChange(partnerQueryValue());
  }

  function updatePartnerSearch(next: string): void {
    partnerSearch = next;
    partnerPage = 0;
    if (partnerSearchTimer) clearTimeout(partnerSearchTimer);
    partnerSearchTimer = setTimeout(loadPartnerQuery, 250);
  }

  function resetPartnerFilter(next: string): void {
    partnerStatus = next;
    partnerPage = 0;
    loadPartnerQuery();
  }

  function updatePartnerSort(next: string): void {
    partnerSort = next;
    partnerPage = 0;
    loadPartnerQuery();
  }

  function updatePartnerPage(next: number): void {
    partnerPage = next;
    loadPartnerQuery();
  }

  function resetApplicationFilter(next: string): void {
    applicationStatus = next;
    applicationPage = 0;
  }

  function resetWithdrawalFilter(next: string): void {
    withdrawalStatus = next;
    withdrawalPage = 0;
  }

  function resetPartnerFilters(): void {
    partnerSearch = "";
    partnerStatus = "all";
    partnerPage = 0;
    if (partnerSearchTimer) clearTimeout(partnerSearchTimer);
    loadPartnerQuery();
  }

  function resetApplicationFilters(): void {
    applicationSearch = "";
    resetApplicationFilter("all");
  }

  function resetWithdrawalFilters(): void {
    withdrawalSearch = "";
    resetWithdrawalFilter("all");
  }

  onDestroy(() => {
    if (partnerSearchTimer) clearTimeout(partnerSearchTimer);
  });
</script>

{#if view === "partners"}
  <section class="partners-list-view">
    <AdminListToolbar
      class="partner-list-toolbar"
      total={partnerTotal}
      totalLabel={at("total", {}, "Total")}
      columns={1}
      onsubmit={() => {
        partnerPage = 0;
        loadPartnerQuery();
      }}
    >
      {#snippet search()}
        <Input
          class="input"
          type="search"
          value={partnerSearch}
          oninput={(event) => updatePartnerSearch(event.currentTarget.value)}
          aria-label={at("partners_search", {}, "Search by user or partner ID")}
          placeholder={at("partners_search", {}, "Search by user or partner ID")}
        />
      {/snippet}
      {#snippet searchActions()}
        <AdminButton type="submit" variant="primary">{at("find", {}, "Find")}</AdminButton>
      {/snippet}
      {#snippet filters()}
        <AdminField label={at("partners_col_status", {}, "Status")}>
          <AdminSelect
            value={partnerStatus}
            items={[
              { value: "all", label: at("partners_filter_all", {}, "All statuses") },
              { value: "active", label: statusLabel("active") },
              { value: "paused", label: statusLabel("paused") },
            ]}
            ariaLabel={at("partners_col_status", {}, "Status")}
            onValueChange={resetPartnerFilter}
          />
        </AdminField>
      {/snippet}
      {#snippet actions()}
        <AdminButton variant="primary" onclick={onAddPartner}
          ><Plus size={15} />{at("partners_add", {}, "Add partner")}</AdminButton
        >
      {/snippet}
    </AdminListToolbar>
    <AdminTable>
      <thead
        ><tr>
          <AdminSortableHeader
            label={at("partners_col_user", {}, "User")}
            column={partnerSortColumns[0]}
            currentSort={partnerSort}
            {at}
            onSort={updatePartnerSort}
          />
          <AdminSortableHeader
            label={at("partners_col_status", {}, "Status")}
            column={partnerSortColumns[1]}
            currentSort={partnerSort}
            {at}
            onSort={updatePartnerSort}
          />
          <AdminSortableHeader
            label={at("partners_col_rate", {}, "Rate")}
            column={partnerSortColumns[2]}
            currentSort={partnerSort}
            {at}
            onSort={updatePartnerSort}
          />
          <AdminSortableHeader
            label={at("partners_col_clients", {}, "Clients")}
            column={partnerSortColumns[3]}
            currentSort={partnerSort}
            {at}
            onSort={updatePartnerSort}
          />
          <AdminSortableHeader
            label={at("partners_col_gross", {}, "Gross")}
            column={partnerSortColumns[4]}
            currentSort={partnerSort}
            {at}
            onSort={updatePartnerSort}
          />
          <AdminSortableHeader
            label={at("partners_col_earned", {}, "Net commission")}
            column={partnerSortColumns[5]}
            currentSort={partnerSort}
            {at}
            onSort={updatePartnerSort}
          />
          <AdminSortableHeader
            label={at("partners_col_available", {}, "Available")}
            column={partnerSortColumns[6]}
            currentSort={partnerSort}
            {at}
            onSort={updatePartnerSort}
          />
          <th>{at("actions", {}, "Actions")}</th>
        </tr></thead
      >
      <tbody>
        {#each pagedPartners as partner (partner.id)}
          <tr>
            <td class="admin-cell-primary" data-label={at("partners_col_user", {}, "User")}>
              <AdminEntityLink
                kind="partner"
                label={partner.name}
                secondary={partner.handle}
                idText={partner.id}
                avatarUrl={partner.avatarUrl}
                title={openPartnerLabel}
                onclick={() => onOpenPartner(partner)}
              />
            </td>
            <td data-label={at("partners_col_status", {}, "Status")}>
              <AdminBadge variant={partnerStatusVariant(partner.status)}
                >{statusLabel(partner.status)}</AdminBadge
              >
            </td>
            <td data-label={at("partners_col_rate", {}, "Rate")}>{partner.rate}%</td>
            <td data-label={at("partners_col_clients", {}, "Clients")}>{partner.clients}</td>
            <td data-label={at("partners_col_gross", {}, "Gross")}>{money(partner.gross)}</td>
            <td data-label={at("partners_col_earned", {}, "Net commission")}
              >{money(partner.earned)}</td
            >
            <td data-label={at("partners_col_available", {}, "Available")}
              ><span class:partners-negative={partner.available < 0}
                >{money(partner.available)}</span
              ></td
            >
            <td class="admin-cell-actions" data-label={at("actions", {}, "Actions")}>
              <AdminButton size="sm" onclick={() => onOpenPartner(partner)}
                >{at("partners_open", {}, "Open")}</AdminButton
              >
            </td>
          </tr>
        {/each}
      </tbody>
    </AdminTable>
    {#if !sortedPartners.length}
      <AdminEmptyState class="partners-table-empty">
        <UsersRound size={24} />
        <strong>{at("partners_list_empty_title", {}, "No partners match the filters")}</strong>
        <p>{at("partners_list_empty_hint", {}, "Clear the search or pick another status.")}</p>
        <AdminButton onclick={resetPartnerFilters}
          >{at("partners_reset_filters", {}, "Reset filters")}</AdminButton
        >
      </AdminEmptyState>
    {/if}
    {#if sortedPartners.length}
      <AdminPagination
        page={partnerPage}
        pageCount={partnerPageCount}
        total={partnerTotal}
        pageLabel={paginationLabels.page}
        ofLabel={paginationLabels.of}
        totalLabel={paginationLabels.total}
        jumpLabel={paginationLabels.page}
        jumpAriaLabel={paginationLabels.jump}
        goLabel={paginationLabels.go}
        prevLabel={paginationLabels.back}
        nextLabel={paginationLabels.next}
        onPageChange={updatePartnerPage}
      />
    {/if}
  </section>
{:else if view === "applications"}
  <section class="partners-list-view">
    <AdminListToolbar
      class="partner-list-toolbar"
      total={filteredApplications.length}
      totalLabel={at("total", {}, "Total")}
      columns={1}
      onsubmit={() => {
        applicationPage = 0;
      }}
    >
      {#snippet search()}
        <Input
          class="input"
          type="search"
          value={applicationSearch}
          oninput={(event) => {
            applicationSearch = event.currentTarget.value;
            applicationPage = 0;
          }}
          aria-label={at("partners_search_applications", {}, "Search applications")}
          placeholder={at("partners_search_applications", {}, "Search applications")}
        />
      {/snippet}
      {#snippet searchActions()}
        <AdminButton type="submit" variant="primary">{at("find", {}, "Find")}</AdminButton>
      {/snippet}
      {#snippet filters()}
        <AdminField label={at("partners_col_status", {}, "Status")}>
          <AdminSelect
            value={applicationStatus}
            items={[
              { value: "all", label: at("partners_filter_all", {}, "All statuses") },
              {
                value: "pending",
                label: `${statusLabel("pending")} (${applications.filter((item) => item.status === "pending").length})`,
              },
              {
                value: "approved",
                label: `${statusLabel("approved")} (${applications.filter((item) => item.status === "approved").length})`,
              },
              {
                value: "rejected",
                label: `${statusLabel("rejected")} (${applications.filter((item) => item.status === "rejected").length})`,
              },
            ]}
            ariaLabel={at("partners_col_status", {}, "Status")}
            onValueChange={resetApplicationFilter}
          />
        </AdminField>
      {/snippet}
    </AdminListToolbar>
    <AdminTable>
      <thead
        ><tr>
          <AdminSortableHeader
            label={at("partners_application", {}, "Application")}
            column={applicationSortColumns[0]}
            currentSort={applicationSort}
            {at}
            onSort={(sort) => {
              applicationSort = sort;
              applicationPage = 0;
            }}
          />
          <AdminSortableHeader
            label={at("partners_applicant", {}, "Applicant")}
            column={applicationSortColumns[1]}
            currentSort={applicationSort}
            {at}
            onSort={(sort) => {
              applicationSort = sort;
              applicationPage = 0;
            }}
          />
          <AdminSortableHeader
            label={at("partners_application_message", {}, "Application message")}
            column={applicationSortColumns[2]}
            currentSort={applicationSort}
            {at}
            onSort={(sort) => {
              applicationSort = sort;
              applicationPage = 0;
            }}
          />
          <AdminSortableHeader
            label={at("partners_submitted", {}, "Submitted")}
            column={applicationSortColumns[3]}
            currentSort={applicationSort}
            {at}
            onSort={(sort) => {
              applicationSort = sort;
              applicationPage = 0;
            }}
          />
          <AdminSortableHeader
            label={at("partners_col_status", {}, "Status")}
            column={applicationSortColumns[4]}
            currentSort={applicationSort}
            {at}
            onSort={(sort) => {
              applicationSort = sort;
              applicationPage = 0;
            }}
          />
          <th>{at("actions", {}, "Actions")}</th>
        </tr></thead
      >
      <tbody>
        {#each pagedApplications as application (application.id)}
          <tr>
            <td
              class="partners-ref-cell"
              data-label={at("partners_application", {}, "Application")}
            >
              <AdminEntityLink
                kind="application"
                label={application.id}
                title={openApplicationLabel}
                onclick={() => onOpenApplication(application)}
              />
            </td>
            <td class="admin-cell-primary" data-label={at("partners_applicant", {}, "Applicant")}>
              <AdminEntityLink
                kind="user"
                label={application.user}
                secondary={application.handle}
                avatarUrl={application.avatarUrl}
                title={openUserLabel}
                onclick={() => onOpenUserCard(application.userId)}
              />
            </td>
            <td
              class="admin-cell-wrap"
              data-label={at("partners_application_message", {}, "Application message")}
              >{at(application.messageKey, {}, application.messageKey)}</td
            >
            <td data-label={at("partners_submitted", {}, "Submitted")}>{application.submitted}</td>
            <td data-label={at("partners_col_status", {}, "Status")}>
              <AdminBadge variant={partnerStatusVariant(application.status)}
                >{statusLabel(application.status)}</AdminBadge
              >
            </td>
            <td class="admin-cell-actions" data-label={at("actions", {}, "Actions")}>
              <AdminButton size="sm" onclick={() => onOpenApplication(application)}
                >{at("partners_open", {}, "Open")}</AdminButton
              >
            </td>
          </tr>
        {/each}
      </tbody>
    </AdminTable>
    {#if !sortedApplications.length}
      <AdminEmptyState class="partners-table-empty">
        <FileText size={24} />
        <strong>
          {at("partners_applications_empty_title", {}, "No applications match the filters")}
        </strong>
        <p>
          {at("partners_applications_empty_hint", {}, "Clear the search or pick another status.")}
        </p>
        <AdminButton onclick={resetApplicationFilters}
          >{at("partners_reset_filters", {}, "Reset filters")}</AdminButton
        >
      </AdminEmptyState>
    {/if}
    {#if sortedApplications.length}
      <AdminPagination
        page={applicationPage}
        pageCount={applicationPageCount}
        total={filteredApplications.length}
        pageLabel={paginationLabels.page}
        ofLabel={paginationLabels.of}
        totalLabel={paginationLabels.total}
        jumpLabel={paginationLabels.page}
        jumpAriaLabel={paginationLabels.jump}
        goLabel={paginationLabels.go}
        prevLabel={paginationLabels.back}
        nextLabel={paginationLabels.next}
        onPageChange={(page) => (applicationPage = page)}
      />
    {/if}
  </section>
{:else}
  <section class="partners-list-view">
    <AdminListToolbar
      class="partner-list-toolbar"
      total={filteredWithdrawals.length}
      totalLabel={at("total", {}, "Total")}
      columns={1}
      onsubmit={() => {
        withdrawalPage = 0;
      }}
    >
      {#snippet search()}
        <Input
          class="input"
          type="search"
          value={withdrawalSearch}
          oninput={(event) => {
            withdrawalSearch = event.currentTarget.value;
            withdrawalPage = 0;
          }}
          aria-label={at("partners_search_withdrawals", {}, "Search withdrawals")}
          placeholder={at("partners_search_withdrawals", {}, "Search withdrawals")}
        />
      {/snippet}
      {#snippet searchActions()}
        <AdminButton type="submit" variant="primary">{at("find", {}, "Find")}</AdminButton>
      {/snippet}
      {#snippet filters()}
        <AdminField label={at("partners_col_status", {}, "Status")}>
          <AdminSelect
            value={withdrawalStatus}
            items={[
              { value: "all", label: at("partners_filter_all", {}, "All statuses") },
              ...["requested", "processing", "paid", "rejected"].map((status) => ({
                value: status,
                label: `${statusLabel(status)} (${withdrawals.filter((item) => item.status === status).length})`,
              })),
            ]}
            ariaLabel={at("partners_col_status", {}, "Status")}
            onValueChange={resetWithdrawalFilter}
          />
        </AdminField>
      {/snippet}
    </AdminListToolbar>
    <AdminTable>
      <thead
        ><tr>
          <AdminSortableHeader
            label={at("partners_col_withdrawal", {}, "Withdrawal")}
            column={withdrawalSortColumns[0]}
            currentSort={withdrawalSort}
            {at}
            onSort={(sort) => {
              withdrawalSort = sort;
              withdrawalPage = 0;
            }}
          />
          <AdminSortableHeader
            label={at("partners_col_partner", {}, "Partner")}
            column={withdrawalSortColumns[1]}
            currentSort={withdrawalSort}
            {at}
            onSort={(sort) => {
              withdrawalSort = sort;
              withdrawalPage = 0;
            }}
          />
          <AdminSortableHeader
            label={at("partners_col_method", {}, "Method")}
            column={withdrawalSortColumns[2]}
            currentSort={withdrawalSort}
            {at}
            onSort={(sort) => {
              withdrawalSort = sort;
              withdrawalPage = 0;
            }}
          />
          <AdminSortableHeader
            label={at("partners_col_amount", {}, "Amount")}
            column={withdrawalSortColumns[3]}
            currentSort={withdrawalSort}
            {at}
            onSort={(sort) => {
              withdrawalSort = sort;
              withdrawalPage = 0;
            }}
          />
          <AdminSortableHeader
            label={at("partners_col_status", {}, "Status")}
            column={withdrawalSortColumns[4]}
            currentSort={withdrawalSort}
            {at}
            onSort={(sort) => {
              withdrawalSort = sort;
              withdrawalPage = 0;
            }}
          />
          <AdminSortableHeader
            label={at("partners_requested", {}, "Requested")}
            column={withdrawalSortColumns[5]}
            currentSort={withdrawalSort}
            {at}
            onSort={(sort) => {
              withdrawalSort = sort;
              withdrawalPage = 0;
            }}
          />
          <th>{at("actions", {}, "Actions")}</th>
        </tr></thead
      >
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
                title={openWithdrawalLabel}
                onclick={() => onOpenWithdrawal(withdrawal)}
              />
            </td>
            <td class="admin-cell-primary" data-label={at("partners_col_partner", {}, "Partner")}>
              <AdminEntityLink
                kind="partner"
                label={withdrawal.partner}
                secondary={withdrawal.handle}
                idText={withdrawal.partnerId}
                avatarUrl={withdrawal.avatarUrl}
                title={openPartnerLabel}
                onclick={() => openPartnerById(withdrawal.partnerId)}
              />
            </td>
            <td class="partners-method-cell" data-label={at("partners_col_method", {}, "Method")}>
              <span>
                {at(`partners_method_${withdrawal.method}`, {}, withdrawal.method)}
                <small>{withdrawal.masked}</small>
              </span>
            </td>
            <td data-label={at("partners_col_amount", {}, "Amount")}>{money(withdrawal.amount)}</td>
            <td data-label={at("partners_col_status", {}, "Status")}>
              <AdminBadge variant={partnerStatusVariant(withdrawal.status)}
                >{statusLabel(withdrawal.status)}</AdminBadge
              >
            </td>
            <td data-label={at("partners_requested", {}, "Requested")}>{withdrawal.requested}</td>
            <td class="admin-cell-actions" data-label={at("actions", {}, "Actions")}>
              <AdminButton size="sm" onclick={() => onOpenWithdrawal(withdrawal)}
                >{at("partners_open", {}, "Open")}</AdminButton
              >
            </td>
          </tr>
        {/each}
      </tbody>
    </AdminTable>
    {#if !sortedWithdrawals.length}
      <AdminEmptyState class="partners-table-empty">
        <WalletCards size={24} />
        <strong>
          {at("partners_withdrawals_empty_title", {}, "No withdrawals match the filters")}
        </strong>
        <p>
          {at("partners_withdrawals_empty_hint", {}, "Clear the search or pick another status.")}
        </p>
        <AdminButton onclick={resetWithdrawalFilters}
          >{at("partners_reset_filters", {}, "Reset filters")}</AdminButton
        >
      </AdminEmptyState>
    {/if}
    {#if sortedWithdrawals.length}
      <AdminPagination
        page={withdrawalPage}
        pageCount={withdrawalPageCount}
        total={filteredWithdrawals.length}
        pageLabel={paginationLabels.page}
        ofLabel={paginationLabels.of}
        totalLabel={paginationLabels.total}
        jumpLabel={paginationLabels.page}
        jumpAriaLabel={paginationLabels.jump}
        goLabel={paginationLabels.go}
        prevLabel={paginationLabels.back}
        nextLabel={paginationLabels.next}
        onPageChange={(page) => (withdrawalPage = page)}
      />
    {/if}
  </section>
{/if}
