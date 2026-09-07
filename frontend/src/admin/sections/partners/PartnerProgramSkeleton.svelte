<script lang="ts">
  import Skeleton from "$components/ui/skeleton.svelte";
  import {
    AdminChartSkeleton,
    AdminTableSkeleton,
    AdminListToolbar,
    AdminField,
  } from "$components/patterns/admin/index.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at,
    view = "dashboard",
  }: {
    at: TranslateFn;
    view?: string;
  } = $props();

  const isList = $derived(view === "partners" || view === "applications" || view === "withdrawals");
  const listHeaders = $derived(
    view === "applications"
      ? [
          at("partners_application", {}, "Application"),
          at("partners_applicant", {}, "Applicant"),
          at("partners_application_message", {}, "Application message"),
          at("partners_submitted", {}, "Submitted"),
          at("partners_col_status", {}, "Status"),
          at("actions", {}, "Actions"),
        ]
      : view === "withdrawals"
        ? [
            at("partners_col_withdrawal", {}, "Withdrawal"),
            at("partners_col_partner", {}, "Partner"),
            at("partners_col_method", {}, "Method"),
            at("partners_col_amount", {}, "Amount"),
            at("partners_col_status", {}, "Status"),
            at("partners_requested", {}, "Requested"),
            at("actions", {}, "Actions"),
          ]
        : [
            at("partners_col_user", {}, "User"),
            at("partners_col_status", {}, "Status"),
            at("partners_col_rate", {}, "Rate"),
            at("partners_col_clients", {}, "Clients"),
            at("partners_col_gross", {}, "Revenue"),
            at("partners_col_earned", {}, "Net commission"),
            at("partners_col_available", {}, "Available"),
          ]
  );
  const dashboardTableHeaders = $derived([
    [
      at("partners_col_partner", {}, "Partner"),
      at("partners_col_method", {}, "Method"),
      at("partners_col_amount", {}, "Amount"),
      at("partners_col_status", {}, "Status"),
    ],
    [
      at("partners_col_user", {}, "User"),
      at("partners_col_clients", {}, "Clients"),
      at("partners_col_earned", {}, "Net commission"),
      at("partners_col_status", {}, "Status"),
    ],
  ]);
</script>

<div class="partners-skeleton" role="status" aria-label={at("partners_loading", {}, "Loading")}>
  {#if view === "dashboard"}
    <div class="partners-kpi-grid">
      {#each Array(8) as _, index (index)}
        <article class="partners-kpi-card">
          <Skeleton variant="dot" width="38px" height="38px" />
          <div>
            <Skeleton variant="tiny" width={`${56 + (index % 3) * 9}%`} />
            <Skeleton variant="line" width={`${44 + (index % 2) * 14}%`} height="19px" />
          </div>
        </article>
      {/each}
    </div>

    <article class="admin-card admin-revenue-chart partners-chart-card">
      <div class="admin-revenue-chart-head">
        <Skeleton variant="tiny" width="168px" />
        <Skeleton class="partners-skeleton-control" width="292px" height="34px" />
      </div>
      <div class="admin-revenue-granularity">
        {#each [52, 68, 64] as width (width)}
          <Skeleton variant="badge" width={`${width}px`} height="26px" />
        {/each}
      </div>
      <div class="partners-chart-stack">
        {#each Array(2) as _, index (index)}
          <section class="partners-chart-block">
            <header>
              <Skeleton variant="dot" width="16px" height="16px" />
              <Skeleton variant="line" width={index ? "142px" : "196px"} height="13px" />
              <Skeleton variant="line" width="86px" height="13px" />
            </header>
            <div class="admin-revenue-svg-frame admin-revenue-svg-frame--chart">
              <AdminChartSkeleton plotHeight={208} />
            </div>
          </section>
        {/each}
      </div>
    </article>

    <section class="partners-preview-grid">
      {#each dashboardTableHeaders as headers}
        <article class="admin-card partners-preview-card partners-dashboard-table-card">
          <header>
            <div>
              <Skeleton variant="dot" width="17px" height="17px" />
              <Skeleton variant="line" width="132px" />
            </div>
            <Skeleton variant="line" width="72px" />
          </header>
          <AdminTableSkeleton
            {headers}
            rows={6}
            rowHeight={40}
            class="admin-table-compact partners-dashboard-table"
          />
        </article>
      {/each}
      <article class="admin-card partners-preview-card partners-preview-wide">
        <header>
          <div>
            <Skeleton variant="dot" width="17px" height="17px" />
            <Skeleton variant="line" width="184px" />
          </div>
          <Skeleton variant="line" width="72px" />
        </header>
        {#each Array(3) as _, rowIndex (rowIndex)}
          <div class="partners-preview-row">
            <span>
              <Skeleton variant="line" width={`${112 + rowIndex * 14}px`} />
              <Skeleton variant="tiny" width={`${82 + rowIndex * 9}px`} />
            </span>
            <Skeleton variant="line" width="74px" />
          </div>
        {/each}
      </article>
    </section>
  {:else if isList}
    <section class="partners-list-view">
      <AdminListToolbar class="partner-list-toolbar" columns={1}>
        {#snippet search()}<Skeleton width="100%" height="36px" />{/snippet}
        {#snippet searchActions()}<Skeleton width="68px" height="36px" />{/snippet}
        {#snippet filters()}<AdminField label={at("partners_col_status", {}, "Status")}
            ><Skeleton width="100%" height="36px" /></AdminField
          >{/snippet}
        {#snippet actions()}<Skeleton
            width="56px"
            height="20px"
          />{#if view === "partners"}<Skeleton width="150px" height="36px" />{/if}{/snippet}
      </AdminListToolbar>
      <AdminTableSkeleton
        headers={listHeaders}
        rows={6}
        rowHeight={54}
        actionColumn={view === "applications" || view === "withdrawals"}
      />
    </section>
  {:else}
    <section class="partners-detail-view">
      <Skeleton variant="line" width="148px" />
      <header class="admin-card partners-detail-head">
        <div class="partners-skeleton-entity">
          <Skeleton variant="dot" width="36px" height="36px" />
          <span>
            <Skeleton variant="line" width="164px" height="13px" />
            <Skeleton variant="tiny" width="112px" />
          </span>
        </div>
        <div class="partners-detail-head-meta">
          <Skeleton variant="badge" width="76px" />
          <Skeleton class="partners-skeleton-button" width="124px" height="32px" />
        </div>
      </header>
      <section class="partners-kpi-grid partners-kpi-detail">
        {#each Array(6) as _, index (index)}
          <article class="partners-kpi-card">
            <div>
              <Skeleton variant="tiny" width={`${48 + (index % 3) * 12}%`} />
              <Skeleton variant="line" width={`${42 + (index % 2) * 18}%`} height="19px" />
            </div>
          </article>
        {/each}
      </section>
      <article class="admin-card partners-record-card">
        <header>
          <Skeleton variant="line" width="168px" />
          <Skeleton variant="badge" />
        </header>
        <dl>
          {#each Array(4) as _, index (index)}
            <div>
              <dt><Skeleton variant="tiny" width={`${84 + index * 8}px`} /></dt>
              <dd><Skeleton variant="line" width={`${52 + index * 9}%`} /></dd>
            </div>
          {/each}
        </dl>
      </article>
    </section>
  {/if}
</div>
