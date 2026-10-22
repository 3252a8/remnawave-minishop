import type { Core, Position } from "cytoscape";

export type RelationshipEdgeRoute = { id: string; points: Position[] };

/** Preserve ELK's orthogonal lanes and vertical ports in Cytoscape's renderer. */
export function applyRelationshipRoutes(cy: Core, routes: RelationshipEdgeRoute[]): void {
  cy.batch(() => {
    for (const route of routes) {
      const edge = cy.getElementById(route.id);
      const start = route.points[0];
      const end = route.points.at(-1);
      if (edge.empty() || !start || !end) continue;
      const source = edge.source().position();
      const target = edge.target().position();
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const squareLength = dx * dx + dy * dy;
      if (!squareLength) continue;
      const length = Math.sqrt(squareLength);
      const bends =
        route.points.length > 2
          ? route.points.slice(1, -1)
          : [{ x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 }];
      edge.style({
        "curve-style": "round-segments",
        "edge-distances": "node-position",
        "source-endpoint": `${start.x - source.x}px ${start.y - source.y}px`,
        "target-endpoint": `${end.x - target.x}px ${end.y - target.y}px`,
        "segment-weights": bends.map(
          (point) => ((point.x - source.x) * dx + (point.y - source.y) * dy) / squareLength
        ),
        "segment-distances": bends.map(
          (point) => (dx * (point.y - source.y) - dy * (point.x - source.x)) / length
        ),
        "segment-radii": [8],
      });
    }
  });
}
