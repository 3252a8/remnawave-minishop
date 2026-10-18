import type { Core } from "cytoscape";

/** Add distance only to native mouse / single-touch drags, never pan or pinch. */
export function accelerateRelationshipDrag(graph: Core): () => void {
  const gain = 1.5;
  // pan() returns Cytoscape's mutable object: retain independent snapshots.
  let current = { ...graph.pan() };
  let before = current;
  const capture = () => {
    before = current;
    current = { ...graph.pan() };
  };
  const accelerate = () => {
    const x = (current.x - before.x) * (gain - 1);
    const y = (current.y - before.y) * (gain - 1);
    // Native dragpan follows its panBy and precedes pointer re-projection.
    // This correction emits pan/viewport, not dragpan, so it cannot recurse.
    if (x || y) graph.panBy({ x, y });
  };
  graph.on("pan", capture);
  graph.on("dragpan", accelerate);
  return () => {
    graph.off("pan", capture);
    graph.off("dragpan", accelerate);
  };
}
