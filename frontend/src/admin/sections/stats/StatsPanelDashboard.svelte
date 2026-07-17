<script lang="ts">
  import { Activity, Radio, Server, Zap } from "$components/ui/icons.js";
  import { ScrollArea } from "$components/ui/index.js";
  import * as Card from "$components/ui/card/index.js";
  import type {
    PanelNodeTraffic,
    PanelStats,
    PanelSystemMetrics,
  } from "$lib/admin/statsDerivations";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  const PANEL_NODE_TILE_LIMIT = 10;

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
          <div class="admin-panel-dash-tile">
            <div class="admin-panel-dash-tile-label">
              <span class="admin-panel-dash-ico" aria-hidden="true"><Radio size={12} /></span>
              {at("stats_panel_online", {}, "")}
            </div>
            <div class="admin-panel-dash-tile-value">{panelMetrics.onlineNow}</div>
          </div>
          <div class="admin-panel-dash-tile">
            <div class="admin-panel-dash-tile-label">{at("stats_panel_active", {}, "")}</div>
            <div class="admin-panel-dash-tile-value">{panelMetrics.active}</div>
          </div>
          <div class="admin-panel-dash-tile">
            <div class="admin-panel-dash-tile-label">
              <span class="admin-panel-dash-ico" aria-hidden="true"><Activity size={12} /></span>
              {at("stats_panel_total_users", {}, "")}
            </div>
            <div class="admin-panel-dash-tile-value">{panelMetrics.totalPanelUsers}</div>
          </div>
          <div class="admin-panel-dash-tile">
            <div class="admin-panel-dash-tile-label">{at("stats_panel_expired", {}, "")}</div>
            <div class="admin-panel-dash-tile-value">{panelMetrics.expired}</div>
          </div>
          <div class="admin-panel-dash-tile">
            <div class="admin-panel-dash-tile-label">{at("stats_panel_disabled", {}, "")}</div>
            <div class="admin-panel-dash-tile-value">{panelMetrics.disabled}</div>
          </div>
          <div class="admin-panel-dash-tile">
            <div class="admin-panel-dash-tile-label">{at("stats_panel_limited", {}, "")}</div>
            <div class="admin-panel-dash-tile-value">{panelMetrics.limited}</div>
          </div>
          {#if panelNodesListedCount > 0}
            <div class="admin-panel-dash-tile" title={at("stats_panel_nodes_online_hint", {}, "")}>
              <div class="admin-panel-dash-tile-label">
                <span class="admin-panel-dash-ico" aria-hidden="true"><Server size={12} /></span>
                {at("stats_panel_nodes_online", {}, "")}
              </div>
              <div class="admin-panel-dash-tile-value">{panelNodesListedCount}</div>
            </div>
          {/if}
          {#if panelMetrics.memPct != null}
            <div class="admin-panel-dash-tile">
              <div class="admin-panel-dash-tile-label">{at("stats_panel_memory", {}, "")}</div>
              <div class="admin-panel-dash-tile-value">{panelMetrics.memPct.toFixed(1)}%</div>
            </div>
          {/if}
          {#if panelMetrics.cpuPct != null}
            <div class="admin-panel-dash-tile">
              <div class="admin-panel-dash-tile-label">
                <span class="admin-panel-dash-ico" aria-hidden="true"><Zap size={12} /></span>
                {at("stats_panel_cpu", {}, "")}
              </div>
              <div class="admin-panel-dash-tile-value">{panelMetrics.cpuPct.toFixed(1)}%</div>
            </div>
          {/if}
          {#if panelBw?.week != null}
            <div class="admin-panel-dash-tile admin-panel-dash-tile--wide">
              <div class="admin-panel-dash-tile-label">{at("stats_panel_bw_week", {}, "")}</div>
              <div class="admin-panel-dash-tile-value admin-panel-dash-tile-value--sm">
                {panelBw.week}
              </div>
            </div>
          {/if}
          {#if panelBw?.month != null}
            <div class="admin-panel-dash-tile admin-panel-dash-tile--wide">
              <div class="admin-panel-dash-tile-label">{at("stats_panel_bw_month", {}, "")}</div>
              <div class="admin-panel-dash-tile-value admin-panel-dash-tile-value--sm">
                {panelBw.month}
              </div>
            </div>
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
