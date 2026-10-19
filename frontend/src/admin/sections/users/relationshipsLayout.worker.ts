import cytoscape from "cytoscape";
import elk from "cytoscape-elk";
import type { LayoutOptions } from "cytoscape";
import { relationshipRoutes, terminateRelationshipEngines } from "./relationshipElk";
import type { RelationshipEdgeRoute } from "./relationshipRouting";

export type RelationshipLayoutRequest = {
  nodes: string[];
  edges: { source: string; target: string }[];
  cardWidth: number;
  cardHeight: number;
  aspectRatio: number;
};
export type RelationshipLayoutResult =
  | { ok: true; positions: { id: string; x: number; y: number }[]; routes: RelationshipEdgeRoute[] }
  | { ok: false; error: string };

// cytoscape-elk does not expose rejection or cancellation. Isolate its
// asynchronous work so failures are observable and termination cancels layout.
self.addEventListener("unhandledrejection", (event) => {
  event.preventDefault();
  self.postMessage({ ok: false, error: String(event.reason) } satisfies RelationshipLayoutResult);
  terminateRelationshipEngines();
  self.close();
});

self.addEventListener("message", (event: MessageEvent<RelationshipLayoutRequest>) => {
  try {
    const input = event.data;
    cytoscape.use(elk);
    const cy = cytoscape({
      headless: true,
      styleEnabled: true,
      elements: [
        ...input.nodes.map((id) => ({ data: { id } })),
        ...input.edges.map((edge, index) => ({ data: { id: `edge-${index}`, ...edge } })),
      ],
      style: [{ selector: "node", style: { width: input.cardWidth, height: input.cardHeight } }],
      layout: { name: "preset" },
    });
    const options: LayoutOptions & { fit: boolean; animate: boolean; elk: Record<string, string> } =
      {
        name: "elk",
        fit: false,
        animate: false,
        elk: {
          algorithm: "layered",
          aspectRatio: String(input.aspectRatio),
          "elk.direction": "DOWN",
          "elk.edgeRouting": "ORTHOGONAL",
          "elk.spacing.nodeNode": "36",
          "elk.spacing.componentComponent": "96",
          "elk.layered.spacing.nodeNodeBetweenLayers": "80",
          "elk.spacing.edgeEdge": "12",
          "elk.layered.spacing.edgeNodeBetweenLayers": "24",
          // There are no compound nodes. INCLUDE_CHILDREN disables component
          // packing and stretches every independent tree into one wide strip.
          "elk.hierarchyHandling": "SEPARATE_CHILDREN",
          "elk.layered.compaction.connectedComponents": "true",
          // Stagger siblings into sublayers so wide families also use more rows.
          "elk.layered.layerUnzipping.strategy": "ALTERNATING",
        },
        stop: () => {
          const positions = cy.nodes().map((node) => ({ id: node.id(), ...node.position() }));
          self.postMessage({
            ok: true,
            positions,
            routes: relationshipRoutes(),
          } satisfies RelationshipLayoutResult);
          cy.destroy();
          terminateRelationshipEngines();
          self.close();
        },
      };
    cy.layout(options).run();
  } catch (error) {
    self.postMessage({ ok: false, error: String(error) } satisfies RelationshipLayoutResult);
    terminateRelationshipEngines();
    self.close();
  }
});
