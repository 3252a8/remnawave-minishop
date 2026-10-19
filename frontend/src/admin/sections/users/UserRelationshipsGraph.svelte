<script lang="ts">
  import { onMount, tick, untrack } from "svelte";
  import type { Core } from "cytoscape";
  import RelationshipsLayoutWorker from "./relationshipsLayout.worker?worker";
  import type {
    RelationshipLayoutRequest,
    RelationshipLayoutResult,
  } from "./relationshipsLayout.worker";
  import { Input } from "$components/ui/index.js";
  import { ArrowLeft, ExternalLink, Minus, Plus, RefreshCw, X } from "$components/ui/icons.js";
  import {
    AdminButton,
    AdminEmptyState,
    AdminField,
    AdminListToolbar,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { getAdminApi } from "$lib/admin/context";
  import { buildAdminUserRelationshipsPath, unwrap } from "$lib/webapp/publicApi";
  import type { AdminUser, TranslateFn } from "$lib/admin/stores/usersStoreState";
  import type { GetResponse } from "$lib/webapp/publicApiContracts";
  import RelationshipUserCard from "./RelationshipUserCard.svelte";
  import { applyRelationshipRoutes } from "./relationshipRouting";
  import {
    createRelationshipViewport,
    type RelationshipCardPosition,
  } from "./relationshipViewport";
  import { relationshipSubset } from "./relationshipFilters";
  import {
    normalizeRelationshipFilter,
    updateUserRelationshipsRoute,
    type RelationshipFilter,
  } from "$lib/admin/userRelationships";

  type Graph = GetResponse<"/api/admin/users/relationships">;
  type Edge = Graph["edges"][number];
  const cardWidth = 360;
  const cardHeight = 112;
  let {
    at,
    focus = "",
    filter = "all",
    onBack,
    onOpenUserCard,
    resolvedAvatarUrl,
    userDisplayName,
    userInitials,
  }: {
    at: TranslateFn;
    focus?: string;
    filter?: RelationshipFilter;
    onBack: () => void;
    onOpenUserCard: (id: unknown) => void;
    resolvedAvatarUrl: (user: AdminUser) => string;
    userDisplayName: (user: AdminUser) => string;
    userInitials: (user: AdminUser) => string;
  } = $props();

  const api = getAdminApi();
  let container: HTMLDivElement;
  let nodeLayer: HTMLDivElement;
  let cy: Core | undefined;
  let viewport: ReturnType<typeof createRelationshipViewport> | undefined;
  let appliedFilter: RelationshipFilter = "all";
  let loading = $state(true);
  let failed = $state(false);
  let layoutBusy = $state(false);
  let users = $state<AdminUser[]>([]);
  let edges = $state<Edge[]>([]);
  let positioned = $state<RelationshipCardPosition[]>([]);
  let query = $state("");
  let userListOpen = $state(false);
  let selectedId = $state("");
  let missingFocus = $state(false);
  let disposed = false;
  let loadVersion = 0;
  let cancelLayout: (() => void) | undefined;

  const subset = $derived(relationshipSubset(users, edges, filter));
  const selected = $derived(subset.users.find((user) => String(user.user_id) === selectedId));
  const byId = $derived(new Map(users.map((user) => [String(user.user_id), user])));
  const selectedEdges = $derived(
    subset.edges.filter(
      (edge) => String(edge.source) === selectedId || String(edge.target) === selectedId
    )
  );
  const matches = $derived.by(() => {
    const value = query.trim().toLocaleLowerCase();
    return subset.users.filter(
      (user) =>
        !value ||
        [
          userDisplayName(user),
          user.minishop_id,
          user.telegram_id,
          user.username,
          user.email,
          user.user_id,
        ].some((item) =>
          String(item ?? "")
            .toLocaleLowerCase()
            .includes(value)
        )
    );
  });

  function scheduleCards(): void {
    viewport?.sync();
  }

  function frameUser(graph: Core, id: string): void {
    graph.resize();
    graph.zoom(Math.min(1, Math.max(0.65, (container.clientWidth - 24) / cardWidth)));
    graph.center(graph.getElementById(id));
    scheduleCards();
  }

  function selectUser(id: string, center = true): void {
    if (!cy) return;
    const node = cy.getElementById(id);
    if (node.empty() || node.hasClass("filtered")) {
      missingFocus = true;
      return;
    }
    missingFocus = false;
    selectedId = id;
    cy.elements().removeClass("related");
    cy.nodes().unselect();
    node.select();
    node.closedNeighborhood().addClass("related");
    if (center) {
      const graph = cy;
      void tick().then(() => {
        if (disposed || graph.destroyed() || graph !== cy || selectedId !== id) return;
        frameUser(graph, id);
      });
    }
    updateUserRelationshipsRoute({ focus: id });
    scheduleCards();
  }

  function fit(): void {
    cy?.resize();
    cy?.fit(cy.elements(":visible"), 40);
    scheduleCards();
  }
  function clearSelection(): void {
    const previous = selectedId;
    selectedId = "";
    cy?.elements().unselect().removeClass("related");
    updateUserRelationshipsRoute({ focus: "" });
    void tick().then(() => {
      if (!cy || disposed) return;
      cy.resize();
      if (previous) cy.center(cy.getElementById(previous));
      scheduleCards();
    });
  }
  function changeZoom(factor: number): void {
    if (!cy) return;
    cy.zoom({
      level: Math.max(cy.minZoom(), Math.min(cy.maxZoom(), cy.zoom() * factor)),
      renderedPosition: { x: container.clientWidth / 2, y: container.clientHeight / 2 },
    });
  }

  function applyFilter(kind: RelationshipFilter, ids: Set<string>): void {
    if (!cy) return;
    cy.batch(() => {
      cy!.nodes().forEach((node) => {
        node.toggleClass("filtered", !ids.has(node.id()));
      });
      cy!.edges().forEach((edge) => {
        edge.toggleClass("filtered", kind !== "all" && edge.data("kind") !== kind);
      });
    });
    viewport?.setVisibleIds(ids);
    appliedFilter = kind;
  }

  function changeFilter(value: string): void {
    const next = normalizeRelationshipFilter(value);
    const ids = relationshipSubset(users, edges, next).ids;
    updateUserRelationshipsRoute(
      { filter: next, focus: ids.has(selectedId) ? selectedId : "" },
      true
    );
  }

  function layoutGraph(): Promise<Extract<RelationshipLayoutResult, { ok: true }>> {
    return new Promise((resolve, reject) => {
      const worker = new RelationshipsLayoutWorker();
      const clean = () => {
        clearTimeout(timeout);
        worker.terminate();
        cancelLayout = undefined;
      };
      const fail = (message = "relationship_layout_failed") => {
        clean();
        reject(new Error(message));
      };
      const timeout = window.setTimeout(fail, 60_000);
      cancelLayout = fail;
      worker.onerror = (event) => {
        event.preventDefault();
        fail(event.message);
      };
      worker.onmessage = (event: MessageEvent<RelationshipLayoutResult>) => {
        if (!event.data.ok) {
          fail(event.data.error);
          return;
        }
        clean();
        resolve(event.data);
      };
      worker.postMessage({
        nodes: users.map((user) => String(user.user_id)),
        edges: edges.map((edge) => ({ source: String(edge.source), target: String(edge.target) })),
        cardWidth,
        cardHeight,
        aspectRatio: Math.max(0.8, Math.min(2, container.clientWidth / container.clientHeight)),
      } satisfies RelationshipLayoutRequest);
    });
  }

  async function load(): Promise<void> {
    const version = ++loadVersion;
    loading = true;
    failed = false;
    missingFocus = false;
    layoutBusy = false;
    cancelLayout?.();
    viewport?.destroy();
    viewport = undefined;
    cy?.destroy();
    cy = undefined;
    positioned = [];
    users = [];
    edges = [];
    selectedId = "";
    try {
      const [response, { default: cytoscape }] = await Promise.all([
        api(buildAdminUserRelationshipsPath()),
        import("cytoscape"),
      ]);
      if (disposed || version !== loadVersion) return;
      const graph = unwrap(response);
      users = graph.nodes;
      edges = graph.edges;
      loading = false;
      if (!users.length) return;
      cy = cytoscape({
        container,
        elements: [
          ...users.map((user) => ({ data: { id: String(user.user_id) }, pannable: true })),
          ...edges.map((edge, index) => ({
            data: {
              id: `edge-${index}`,
              source: String(edge.source),
              target: String(edge.target),
              kind: edge.kind,
            },
          })),
        ],
        minZoom: 0.03,
        maxZoom: 1.8,
        autoungrabify: true,
        boxSelectionEnabled: false,
        style: [
          {
            selector: "node",
            style: {
              shape: "roundrectangle",
              width: cardWidth,
              height: cardHeight,
              "background-opacity": 0,
              "border-width": 0,
              label: "",
            },
          },
          {
            selector: "edge",
            style: {
              width: 2,
              "curve-style": "round-taxi",
              "taxi-direction": "vertical",
              "taxi-radius": 8,
              "target-arrow-shape": "triangle",
              "line-color": "#3b82f6",
              "target-arrow-color": "#3b82f6",
              "arrow-scale": 1.1,
            },
          },
          {
            selector: 'edge[kind="partner"]',
            style: {
              "line-color": "#d97706",
              "target-arrow-color": "#d97706",
              "line-style": "dashed",
            },
          },
          { selector: "edge.related", style: { width: 4 } },
          { selector: ".filtered", style: { display: "none" } },
        ],
        layout: { name: "preset" },
      });
      viewport = createRelationshipViewport(cy, nodeLayer, cardWidth, cardHeight, (cards) => {
        positioned = cards;
      });
      cy.on("tap", "node", (event) => selectUser(event.target.id(), false));
      cy.on("dbltap", "node", (event) => onOpenUserCard(Number(event.target.id())));
      layoutBusy = true;
      const layout = await layoutGraph();
      if (disposed || version !== loadVersion) return;
      const points = new Map(layout.positions.map((point) => [point.id, point]));
      cy.nodes().positions((node) => points.get(node.id()) || { x: 0, y: 0 });
      applyRelationshipRoutes(cy, layout.routes);
      viewport.setModel(users);
      applyFilter(filter, subset.ids);
      layoutBusy = false;
      fit();
      const requestedFocus = new URLSearchParams(window.location.search).get("focus") || focus;
      if (requestedFocus && subset.ids.has(requestedFocus)) selectUser(requestedFocus);
      else if (requestedFocus) {
        if (byId.has(requestedFocus)) updateUserRelationshipsRoute({ focus: "" });
        else missingFocus = true;
      } else if (subset.users.length) {
        // Start at a readable root; the complete graph remains a single fit away.
        const targets = new Set(subset.edges.map((edge) => String(edge.target)));
        const counts = new Map<string, number>();
        for (const edge of subset.edges)
          counts.set(String(edge.source), (counts.get(String(edge.source)) || 0) + 1);
        const roots = subset.users.filter((user) => !targets.has(String(user.user_id)));
        const candidates = roots.length ? roots : subset.users;
        const root = candidates.reduce((best, user) =>
          (counts.get(String(user.user_id)) || 0) > (counts.get(String(best.user_id)) || 0)
            ? user
            : best
        );
        cy.zoom(Math.min(1, Math.max(0.65, (container.clientWidth - 24) / cardWidth)));
        cy.center(cy.getElementById(String(root.user_id)));
        cy.panBy({ x: 0, y: -container.clientHeight * 0.22 });
      }
      scheduleCards();
    } catch {
      if (!disposed && version === loadVersion) {
        viewport?.destroy();
        viewport = undefined;
        cy?.destroy();
        cy = undefined;
        users = [];
        edges = [];
        positioned = [];
        selectedId = "";
        failed = true;
        loading = false;
        layoutBusy = false;
      }
    }
  }

  $effect(() => {
    const id = focus,
      kind = filter,
      visible = subset,
      busy = loading || layoutBusy;
    untrack(() => {
      if (!cy || busy) return;
      const changed = appliedFilter !== kind;
      if (changed) applyFilter(kind, visible.ids);
      if (id && visible.ids.has(id)) {
        if (id !== selectedId || changed) selectUser(id);
      } else {
        selectedId = "";
        cy.elements().unselect().removeClass("related");
        if (id && byId.has(id)) updateUserRelationshipsRoute({ focus: "" });
        missingFocus = Boolean(id && !byId.has(id));
        if (changed && visible.users.length) void tick().then(fit);
      }
    });
  });

  onMount(() => {
    void load();
    let previousWidth = container.clientWidth;
    const resize = new ResizeObserver(() => {
      const width = container.clientWidth;
      const changed = width !== previousWidth;
      previousWidth = width;
      const extent = cy?.extent();
      cy?.resize();
      if (changed && width > 0 && cy && !layoutBusy) {
        if (selectedId) frameUser(cy, selectedId);
        else if (extent)
          cy.pan({
            x: width / 2 - ((extent.x1 + extent.x2) / 2) * cy.zoom(),
            y: container.clientHeight / 2 - ((extent.y1 + extent.y2) / 2) * cy.zoom(),
          });
      }
      scheduleCards();
    });
    resize.observe(container);
    return () => {
      disposed = true;
      loadVersion++;
      resize.disconnect();
      viewport?.destroy();
      cancelLayout?.();
      cy?.destroy();
    };
  });
</script>

<section class="relationships" data-relationships-graph>
  <div class="relationships-heading">
    <AdminButton variant="ghost" onclick={onBack}
      ><ArrowLeft size={15} />{at("relationships_back", {}, "Back to users")}</AdminButton
    >
    <div>
      <h2>{at("relationships_title", {}, "Referral and partner graph")}</h2>
      <p>
        {at(
          "relationships_description",
          {},
          "All connected users. Arrows lead from the inviter or partner to the invited user."
        )}
      </p>
    </div>
  </div>
  <AdminListToolbar
    class="relationships-toolbar"
    columns={1}
    total={loading || failed ? undefined : subset.users.length}
    totalLabel={at("relationships_users", {}, "Connected users")}
    onsubmit={() => {
      if (matches[0]) selectUser(String(matches[0].user_id));
    }}
  >
    {#snippet search()}<Input
        class="input"
        type="search"
        bind:value={query}
        oninput={() => (userListOpen = true)}
        aria-label={at("relationships_search", {}, "Find by name, MS UUID, Telegram or email")}
        placeholder={at("relationships_search", {}, "Find by name, MS UUID, Telegram or email")}
      />{/snippet}
    {#snippet searchActions()}<AdminButton
        type="submit"
        disabled={!matches.length || loading || layoutBusy || failed}
        >{at("find", {}, "Find")}</AdminButton
      >{/snippet}
    {#snippet filters()}
      <AdminField label={at("relationships_filter", {}, "Connections")}>
        <AdminSelect
          value={filter}
          contentClass="relationships-filter-menu"
          ariaLabel={at("relationships_filter", {}, "Connections")}
          disabled={loading || layoutBusy || failed}
          items={[
            { value: "all", label: at("relationships_filter_all", {}, "All") },
            { value: "referral", label: at("relationships_legend_referrals", {}, "Referrals") },
            { value: "partner", label: at("relationships_legend_partners", {}, "Partners") },
          ]}
          onValueChange={changeFilter}
        />
      </AdminField>
    {/snippet}
    {#snippet actions()}
      <AdminButton
        size="icon"
        onclick={() => changeZoom(1.25)}
        disabled={loading || layoutBusy || !subset.users.length}
        title={at("relationships_zoom_in", {}, "Zoom in")}
        aria-label={at("relationships_zoom_in", {}, "Zoom in")}><Plus size={16} /></AdminButton
      >
      <AdminButton
        size="icon"
        onclick={() => changeZoom(0.8)}
        disabled={loading || layoutBusy || !subset.users.length}
        title={at("relationships_zoom_out", {}, "Zoom out")}
        aria-label={at("relationships_zoom_out", {}, "Zoom out")}><Minus size={16} /></AdminButton
      >
      <AdminButton onclick={fit} disabled={loading || layoutBusy || !subset.users.length}
        >{at("relationships_fit", {}, "Fit graph")}</AdminButton
      >
      <AdminButton
        class="relationships-refresh-button"
        onclick={() => load()}
        disabled={loading || layoutBusy}
        aria-label={at("refresh", {}, "Refresh")}
        title={at("refresh", {}, "Refresh")}
        ><RefreshCw size={15} /><span class="relationships-refresh-label"
          >{at("refresh", {}, "Refresh")}</span
        ></AdminButton
      >
    {/snippet}
    {#snippet metadata()}<div class="relationships-legend">
        <span><i class="referral"></i>{at("relationships_legend_referrals", {}, "Referrals")}</span
        ><span><i class="partner"></i>{at("relationships_legend_partners", {}, "Partners")}</span>
      </div>{/snippet}
  </AdminListToolbar>
  <p id="relationships-navigation-hint" class="relationships-hint">
    {at(
      "relationships_hint",
      {},
      "Drag to move. Zoom with the wheel or two fingers. Select a card for details."
    )}
  </p>
  {#if failed}<AdminEmptyState role="alert"
      >{at("relationships_error", {}, "Could not load the graph. Try refreshing.")}</AdminEmptyState
    >{/if}
  {#if !loading && !failed && !subset.users.length}<AdminEmptyState
      >{users.length
        ? at("relationships_filter_empty", {}, "No connections of this type.")
        : at("relationships_empty", {}, "No referral or partner connections yet.")}</AdminEmptyState
    >{/if}
  {#if missingFocus}<p role="status">
      {at("relationships_missing", {}, "This user has no connections in the graph.")}
    </p>{/if}
  <div
    class="relationships-workspace"
    class:has-selection={Boolean(selected)}
    style:display={failed || (!loading && !subset.users.length) ? "none" : undefined}
  >
    <div class="relationships-stage" aria-busy={loading || layoutBusy}>
      <div
        class="relationships-canvas"
        bind:this={container}
        role="application"
        aria-describedby="relationships-navigation-hint"
        aria-label={at(
          "relationships_canvas",
          {},
          "User connections. Use zoom controls, search or the user list to explore the graph."
        )}
      ></div>
      <div class="relationships-overlays">
        <div class="relationships-node-layer" bind:this={nodeLayer}>
          {#each positioned as item (item.user.user_id)}
            <button
              type="button"
              class="relationships-node"
              class:selected={selectedId === String(item.user.user_id)}
              style={`width:${cardWidth}px;height:${cardHeight}px;transform:translate(${item.x}px,${item.y}px)`}
              data-graph-user-id={item.user.user_id}
              aria-label={at(
                "relationships_select",
                { name: userDisplayName(item.user) },
                "Select {name}"
              )}
              onclick={() => selectUser(String(item.user.user_id), false)}
              onfocus={() => {
                if (cy) frameUser(cy, String(item.user.user_id));
              }}
              ondblclick={() => onOpenUserCard(item.user.user_id)}
            >
              <RelationshipUserCard
                user={item.user}
                {at}
                {resolvedAvatarUrl}
                {userDisplayName}
                {userInitials}
              />
            </button>
          {/each}
        </div>
      </div>
      {#if loading || layoutBusy}<div class="relationships-loading" role="status">
          {at("loading", {}, "Loading…")}
        </div>{/if}
    </div>
    {#if selected}
      <aside
        class="relationships-selection"
        aria-label={at("relationships_selected", {}, "Selected user")}
      >
        <div class="relationships-selection-head">
          <h3>{at("relationships_selected", {}, "Selected user")}</h3>
          <AdminButton
            size="icon"
            variant="icon"
            aria-label={at("relationships_clear_selection", {}, "Clear selection")}
            title={at("relationships_clear_selection", {}, "Clear selection")}
            onclick={clearSelection}><X size={16} /></AdminButton
          >
        </div>
        <RelationshipUserCard
          user={selected}
          {at}
          {resolvedAvatarUrl}
          {userDisplayName}
          {userInitials}
          expanded
        />
        <AdminButton onclick={() => onOpenUserCard(selected.user_id)}
          ><ExternalLink size={14} />{at("user_open_related", {}, "Open user card")}</AdminButton
        >
        <h3>{at("relationships_connections", {}, "Connections")}</h3>
        <ul>
          {#each selectedEdges as edge (`${edge.kind}-${edge.source}-${edge.target}`)}
            {@const otherId =
              String(edge.source) === selectedId ? String(edge.target) : String(edge.source)}
            {@const other = byId.get(otherId)}
            <li data-relationship-kind={edge.kind}>
              <span
                >{edge.kind === "partner"
                  ? at("relationships_partner", {}, "Partner")
                  : at("relationships_referral", {}, "Referral")} · {String(edge.source) ===
                selectedId
                  ? at("relationships_outgoing", {}, "Invited")
                  : at("relationships_incoming", {}, "Invited by")}</span
              ><AdminButton variant="ghost" size="sm" onclick={() => selectUser(otherId)}
                >{other ? userDisplayName(other) : otherId}</AdminButton
              >
            </li>
          {/each}
        </ul>
      </aside>
    {/if}
  </div>
  {#if !loading && !failed && subset.users.length}
    <details class="relationships-list" bind:open={userListOpen}>
      <summary>{at("relationships_list", { count: matches.length }, "User list · {count}")}</summary
      >
      {#if userListOpen}
        {#if !matches.length}<p>{at("relationships_no_results", {}, "No matching users.")}</p>{/if}
        <ul>
          {#each matches as user (user.user_id)}<li>
              <AdminButton variant="ghost" onclick={() => selectUser(String(user.user_id))}
                >{userDisplayName(user)} · {user.minishop_id || user.user_id}</AdminButton
              >
            </li>{/each}
        </ul>
      {/if}
    </details>
  {/if}
</section>

<style>
  .relationships {
    --admin-card-bg: var(--admin-surface);
    display: grid;
    gap: 14px;
    min-width: 0;
  }
  .relationships :global(.admin-btn),
  .relationships :global(.admin-btn:hover),
  .relationships :global(.admin-btn:focus-visible) {
    background-image: none;
  }
  .relationships :global(.relationships-toolbar .admin-list-toolbar-filters) {
    flex: 0 1 170px;
  }
  :global(.admin-select-content.relationships-filter-menu) {
    background: var(--admin-surface);
    background-image: none;
  }
  .relationships-heading {
    display: flex;
    gap: 18px;
    align-items: flex-start;
    flex-wrap: wrap;
  }
  h2 {
    margin: 0;
    font-size: 18px;
  }
  p {
    margin: 6px 0 0;
    color: var(--admin-muted);
    font-size: 12px;
  }
  .relationships-legend,
  .relationships-legend span {
    display: flex;
    gap: 8px;
    align-items: center;
  }
  .relationships-legend {
    flex-wrap: wrap;
    gap: 16px;
    color: var(--admin-muted);
    font-size: 12px;
  }
  .relationships-legend i {
    display: block;
    width: 24px;
    border-top: 3px solid #3b82f6;
  }
  .relationships-legend .partner {
    border-top-color: #d97706;
    border-top-style: dashed;
  }
  .relationships-workspace {
    display: grid;
    min-width: 0;
    gap: 12px;
  }
  .relationships-workspace.has-selection {
    grid-template-columns: minmax(0, 1fr) 300px;
  }
  .relationships-stage {
    position: relative;
    height: clamp(420px, 66vh, 820px);
    min-width: 0;
    overflow: clip;
    border: 1px solid var(--admin-border);
    border-radius: 12px;
    background: var(--admin-card-bg);
  }
  .relationships-canvas,
  .relationships-overlays {
    position: absolute;
    inset: 0;
  }
  .relationships-overlays {
    pointer-events: none;
    overflow: clip;
  }
  .relationships-node-layer {
    position: absolute;
    top: 0;
    left: 0;
    transform-origin: top left;
    will-change: transform;
  }
  .relationships-node {
    position: absolute;
    top: 0;
    left: 0;
    transform-origin: top left;
    pointer-events: none;
    padding: 12px;
    border-radius: 10px;
    border: 1px solid var(--admin-border);
    background: var(--admin-card-bg);
    color: var(--admin-text);
    box-shadow: var(--admin-card-shadow);
  }
  .relationships-node.selected {
    border: 2px solid var(--admin-accent, #3b82f6);
  }
  .relationships-node:focus-visible {
    outline: 3px solid var(--admin-accent, #3b82f6);
    outline-offset: 3px;
  }
  .relationships-loading {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    background: var(--admin-card-bg);
  }
  .relationships-selection {
    display: grid;
    align-content: start;
    gap: 14px;
    border: 1px solid var(--admin-border);
    border-radius: 12px;
    padding: 16px;
    min-width: 0;
    background: var(--admin-card-bg);
  }
  h3 {
    font-size: 13px;
    margin: 0;
  }
  .relationships-selection-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .relationships-selection ul {
    list-style: none;
    padding: 0;
    margin: 0;
    display: grid;
    gap: 8px;
    max-height: 330px;
    overflow: auto;
  }
  .relationships-selection li {
    display: grid;
    justify-items: start;
    min-width: 0;
    border-top: 1px solid var(--admin-border);
    padding-top: 8px;
  }
  .relationships-selection li > span {
    color: var(--admin-muted);
    font-size: 11px;
  }
  .relationships-selection :global(.admin-btn) {
    max-width: 100%;
    white-space: normal;
    overflow-wrap: anywhere;
  }
  .relationships-list {
    border: 1px solid var(--admin-border);
    border-radius: 12px;
    padding: 12px;
  }
  summary {
    cursor: pointer;
    font-size: 13px;
  }
  .relationships-list ul {
    list-style: none;
    padding: 0;
    margin: 10px 0 0;
    max-height: 240px;
    overflow: auto;
  }
  .relationships-list :global(.admin-btn) {
    max-width: 100%;
    white-space: normal;
    text-align: left;
    overflow-wrap: anywhere;
  }
  @media (max-width: 1000px) {
    .relationships-workspace.has-selection {
      grid-template-columns: minmax(0, 1fr);
    }
    .relationships-stage {
      height: 56vh;
      min-height: 380px;
    }
  }
  @media (max-width: 720px) {
    .relationships :global(.relationships-toolbar .admin-list-toolbar-filters) {
      flex-basis: 100%;
    }
  }
  @media (max-width: 360px) {
    .relationships :global(.relationships-toolbar .admin-list-toolbar-actions) {
      flex-wrap: nowrap;
      gap: 6px;
      width: 100%;
    }
    .relationships :global(.relationships-refresh-button) {
      width: 36px;
      min-width: 36px;
      padding-inline: 0;
    }
    .relationships-refresh-label {
      display: none;
    }
    .relationships-legend {
      gap: 12px;
    }
    .relationships-legend span {
      white-space: nowrap;
    }
    .relationships-legend i {
      width: 20px;
    }
  }
</style>
