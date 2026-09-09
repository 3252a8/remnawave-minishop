<script lang="ts">
  import { ScrollArea } from "$components/ui/index.js";
  import * as Card from "$components/ui/card/index.js";
  import {
    AdminChartSkeleton,
    AdminDashboardGrid,
    AdminDashboardStack,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at,
    headers,
  }: {
    at: TranslateFn;
    headers: string[];
  } = $props();
</script>

<AdminDashboardStack>
  <AdminDashboardGrid columns={3}>
    {#each Array(3) as _, i (i)}
      <Card.Root class="admin-cn-card-skeleton admin-stats-audience-card">
        <Card.Header>
          <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span>
          <span
            class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"
            style="width:72%"
          ></span>
        </Card.Header>
        <Card.Footer class="admin-cn-card-footer--stack">
          <span class="admin-skeleton admin-skeleton-line" style="width:88%"></span>
          <span
            class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"
            style="width:60%"
          ></span>
        </Card.Footer>
      </Card.Root>
    {/each}
  </AdminDashboardGrid>

  <Card.Root class="admin-cn-card-skeleton admin-cn-card-skeleton--tall">
    <Card.Header>
      <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span>
      <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong" style="width:48%"
      ></span>
    </Card.Header>
    <Card.Content>
      <div class="admin-revenue-kpis" aria-hidden="true">
        {#each Array(6) as _, i (i)}
          <div class="admin-revenue-kpi">
            <span
              class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"
              style="width:72%"
            ></span>
            <span
              class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"
              style="width:58%;height:20px;margin-top:4px"
            ></span>
          </div>
        {/each}
        <div class="admin-revenue-kpi admin-revenue-kpi--wide">
          <span
            class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"
            style="width:46%"
          ></span>
          <span
            class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"
            style="width:36%;height:20px;margin-top:4px"
          ></span>
          <span
            class="admin-skeleton admin-skeleton-line"
            style="width:92%;height:9px;margin-top:6px"
          ></span>
        </div>
      </div>
      <div class="admin-revenue-chart">
        <div class="admin-revenue-chart-head">
          <div class="admin-revenue-chart-title">
            <span
              class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"
              style="width:138px"
            ></span>
          </div>
          <span class="admin-skeleton admin-chart-skeleton-control" style="width:292px"></span>
        </div>
        <div class="admin-revenue-granularity" aria-hidden="true">
          {#each [52, 68, 64] as width (width)}
            <span class="admin-skeleton admin-skeleton-badge" style={`width:${width}px;height:26px`}
            ></span>
          {/each}
        </div>
        <span class="admin-skeleton admin-skeleton-line" style="width:66%;height:9px"></span>
        <span class="admin-skeleton admin-skeleton-line" style="width:46%;height:9px"></span>
        <div class="admin-revenue-svg-frame admin-revenue-svg-frame--chart">
          <AdminChartSkeleton plotHeight={204} />
        </div>
      </div>
    </Card.Content>
  </Card.Root>

  <Card.Root class="admin-cn-card-skeleton admin-cn-card-skeleton--tall">
    <Card.Header class="admin-cn-card-header--lead">
      <Card.Title class="admin-cn-card-title--section">
        {at("stats_section_panel", {}, "")}
      </Card.Title>
      <Card.Description>{at("stats_section_panel_hint", {}, "")}</Card.Description>
    </Card.Header>
    <Card.Content class="admin-cn-card-content admin-panel-dash-card">
      <div class="admin-panel-dash">
        <div class="admin-panel-dash-tiles" aria-hidden="true">
          {#each Array(9) as _, k (k)}
            <div class="admin-panel-dash-tile">
              <span
                class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"
                style="width:58%"
              ></span>
              <span
                class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"
                style="width:44%;height:22px;margin-top:6px"
              ></span>
            </div>
          {/each}
        </div>
        <div class="admin-panel-dash-nodes">
          <div class="admin-panel-dash-nodes-head">
            <span class="admin-skeleton admin-skeleton-line" style="width:40%;height:12px"></span>
            <span
              class="admin-skeleton admin-skeleton-line"
              style="width:78%;height:9px;margin-top:6px"
            ></span>
          </div>
          <ScrollArea class="admin-panel-dash-nodes-scroll" maxHeight="240px">
            <div class="admin-panel-dash-nodes-grid">
              {#each Array(4) as _, m (m)}
                <div class="admin-panel-dash-node">
                  <span class="admin-skeleton admin-skeleton-line" style="width:82%"></span>
                  <span
                    class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"
                    style="width:52%;height:16px;margin-top:6px"
                  ></span>
                  <span
                    class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"
                    style="width:44%;margin-top:6px"
                  ></span>
                </div>
              {/each}
            </div>
          </ScrollArea>
        </div>
      </div>
    </Card.Content>
  </Card.Root>

  <Card.Root>
    <Card.Content
      class="admin-cn-card-content--flush"
      style="padding-top:12px;padding-bottom:12px;"
    >
      <div class="admin-sync-strip" style="border:0;background:transparent;padding:0;">
        <span
          class="admin-skeleton admin-skeleton-line"
          style="display:block;width:min(100%, 340px);height:12px"
        ></span>
        <span
          class="admin-skeleton admin-skeleton-line"
          style="display:block;width:min(100%, 220px);height:11px;margin-top:8px"
        ></span>
      </div>
    </Card.Content>
  </Card.Root>

  <Card.Root>
    <Card.Header class="admin-cn-card-header--lead">
      <span class="admin-skeleton admin-skeleton-line" style="width:44%;height:14px"></span>
    </Card.Header>
    <Card.Content class="admin-cn-card-content--flush">
      <AdminTableSkeleton
        {headers}
        rows={5}
        rowHeight={76}
        widths={["11%", "15.5%", "18%", "9%", "7%", "9%", "9.5%", "9%", "12%"]}
      />
    </Card.Content>
  </Card.Root>
</AdminDashboardStack>
