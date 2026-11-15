<script lang="ts">
  import { getHealthStore } from "$lib/admin/context";
  import { Activity, Radio, Server, Zap } from "$components/ui/icons.js";
  import { ScrollArea } from "$components/ui/index.js";
  import * as Card from "$components/ui/card/index.js";
  import type {
    PanelNodeTraffic,
    PanelStats,
    PanelSystemMetrics,
  } from "$lib/admin/statsDerivations";
  import PanelVersionBadge from "./PanelVersionBadge.svelte";
  import { AdminKpiTile } from "$components/patterns/admin/index.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  const PANEL_NODE_TILE_LIMIT = 10;
  const healthStore = getHealthStore();
  const panelCompatibility = $derived(healthStore.panelCompatibility);

  let {
    at,
    panelPayload,
    panelMetrics,
    panelBw,
    panelNodeTraffic,
    panelNodesListedCount,
  }: {
    at: TranslateFn;
    panelPayload: PanelStats | null;
    panelMetrics: PanelSystemMetrics | null;
    panelBw: { week: unknown; month: unknown } | null;
    panelNodeTraffic: PanelNodeTraffic | null;
    panelNodesListedCount: number;
  } = $props();
</script>

<Card.Root>
  <Card.Header class="admin-cn-card-header--lead">
    <Card.Title class="admin-cn-card-title--section">
      {at("stats_section_panel", {}, "")}
    </Card.Title>
    {#if panelPayload?.error}
      <Card.Description>{at("stats_panel_unavailable", {}, "")}</Card.Description>
    {:else if panelMetrics}
      <Card.Description>{at("stats_section_panel_hint", {}, "")}</Card.Description>
    {/if}
    <Card.Action>
      <PanelVersionBadge {at} compatibility={panelCompatibility} />
    </Card.Action>
  </Card.Header>

  {#if panelPayload?.error}
    <Card.Content class="admin-cn-card-content">
      <p class="admin-muted" style="margin:0;">{at("stats_panel_unavailable_detail", {}, "")}</p>
    </Card.Content>
  {:else if panelMetrics}
    <Card.Content class="admin-cn-card-content admin-panel-dash-card">
      <div class="admin-panel-dash">
        <div
          class="admin-panel-dash-tiles"
          role="group"
          aria-label={at("stats_section_panel", {}, "")}
        >
          <AdminKpiTile label={at("stats_panel_online", {}, "")} value={panelMetrics.onlineNow}>
            {#snippet icon()}<Radio size={13} />{/snippet}
          </AdminKpiTile>
          <AdminKpiTile label={at("stats_panel_active", {}, "")} value={panelMetrics.active} />
          <AdminKpiTile
            label={at("stats_panel_total_users", {}, "")}
            value={panelMetrics.totalPanelUsers}
          >
            {#snippet icon()}<Activity size={13} />{/snippet}
          </AdminKpiTile>
          <AdminKpiTile label={at("stats_panel_expired", {}, "")} value={panelMetrics.expired} />
          <AdminKpiTile label={at("stats_panel_disabled", {}, "")} value={panelMetrics.disabled} />
          <AdminKpiTile label={at("stats_panel_limited", {}, "")} value={panelMetrics.limited} />
          {#if panelNodesListedCount > 0}
            <AdminKpiTile
              label={at("stats_panel_nodes_online", {}, "")}
              value={panelNodesListedCount}
              title={at("stats_panel_nodes_online_hint", {}, "")}
            >
              {#snippet icon()}<Server size={13} />{/snippet}
            </AdminKpiTile>
          {/if}
          {#if panelMetrics.memPct != null}
            <AdminKpiTile
              label={at("stats_panel_memory", {}, "")}
              value={`${panelMetrics.memPct.toFixed(1)}%`}
            />
          {/if}
          {#if panelMetrics.cpuPct != null}
            <AdminKpiTile
              label={at("stats_panel_cpu", {}, "")}
              value={`${panelMetrics.cpuPct.toFixed(1)}%`}
            >
              {#snippet icon()}<Zap size={13} />{/snippet}
            </AdminKpiTile>
          {/if}
          {#if panelBw?.week != null}
            <AdminKpiTile label={at("stats_panel_bw_week", {}, "")} value={panelBw.week} />
          {/if}
          {#if panelBw?.month != null}
            <AdminKpiTile label={at("stats_panel_bw_month", {}, "")} value={panelBw.month} />
          {/if}
        </div>

        {#if panelNodeTraffic?.seven?.length}
          <div class="admin-panel-dash-nodes">
            <div class="admin-panel-dash-nodes-head">
              <h3 class="admin-panel-dash-nodes-title">
                {at("stats_panel_inner_nodes", {}, "")}
              </h3>
              <p class="admin-panel-dash-nodes-hint">
                {at("stats_panel_inner_nodes_hint", {}, "")}
              </p>
            </div>
            <ScrollArea class="admin-panel-dash-nodes-scroll" maxHeight="240px">
              <div class="admin-panel-dash-nodes-grid">
                {#each panelNodeTraffic.seven.slice(0, PANEL_NODE_TILE_LIMIT) as node}
                  <div class="admin-panel-dash-node">
                    <div class="admin-panel-dash-node-name">{node.label}</div>
                    <div class="admin-panel-dash-node-value">{node.value}</div>
                    {#if node.online != null}
                      <div class="admin-panel-dash-node-meta">
                        {at("stats_panel_node_users_online", { count: node.online }, "")}
                      </div>
                    {/if}
                  </div>
                {/each}
              </div>
            </ScrollArea>
            {#if panelNodeTraffic.seven.length > PANEL_NODE_TILE_LIMIT}
              <p class="admin-panel-dash-nodes-more">
                {at(
                  "stats_panel_nodes_overflow",
                  { count: panelNodeTraffic.seven.length - PANEL_NODE_TILE_LIMIT },
                  ""
                )}
              </p>
            {/if}
          </div>
        {:else if panelPayload?.nodes && typeof panelPayload.nodes === "object" && Object.keys(panelPayload.nodes).length > 0}
          <p class="admin-panel-dash-nodes-empty">{at("stats_panel_nodes_empty", {}, "")}</p>
        {/if}
      </div>
    </Card.Content>
  {/if}
</Card.Root>
