import type { Core } from "cytoscape";
import type { AdminUser } from "$lib/admin/stores/usersStoreState";
import { enhanceRelationshipNavigation } from "./relationshipNavigation";

export type RelationshipCardPosition = { user: AdminUser; x: number; y: number; order: number };
type Bounds = { x1: number; y1: number; x2: number; y2: number };

/** Keep card DOM in model space; viewport motion only composites one layer. */
export function createRelationshipViewport(
  graph: Core,
  layer: HTMLDivElement,
  cardWidth: number,
  cardHeight: number,
  onCards: (cards: RelationshipCardPosition[]) => void
) {
  const cell = cardWidth * 2;
  const buckets = new Map<string, RelationshipCardPosition[]>();
  let allowed = new Set<string>();
  let coverage: Bounds | undefined;
  let mounted: RelationshipCardPosition[] = [];
  let frame = 0;
  let force = true;
  let coverageZoom = 0;
  const stopNavigation = enhanceRelationshipNavigation(graph);

  function update(): void {
    frame = 0;
    if (graph.destroyed()) return;
    const scale = graph.zoom();
    const pan = graph.pan();
    layer.style.transform = `translate3d(${pan.x}px,${pan.y}px,0) scale(${scale})`;
    const extent = graph.extent();
    if (
      !force &&
      coverage &&
      scale / coverageZoom < 1.35 &&
      scale / coverageZoom > 0.75 &&
      extent.x1 >= coverage.x1 + cardWidth &&
      extent.y1 >= coverage.y1 + cardHeight &&
      extent.x2 <= coverage.x2 - cardWidth &&
      extent.y2 <= coverage.y2 - cardHeight
    )
      return;
    force = false;
    coverageZoom = scale;
    const margin = 280 / scale;
    coverage = {
      x1: extent.x1 - margin - cardWidth,
      y1: extent.y1 - margin - cardHeight,
      x2: extent.x2 + margin + cardWidth,
      y2: extent.y2 + margin + cardHeight,
    };
    const bounds = coverage;
    const next: RelationshipCardPosition[] = [];
    const addBucket = (cards: RelationshipCardPosition[]) => {
      for (const card of cards)
        if (
          allowed.has(String(card.user.user_id)) &&
          card.x <= bounds.x2 &&
          card.x + cardWidth >= bounds.x1 &&
          card.y <= bounds.y2 &&
          card.y + cardHeight >= bounds.y1
        )
          next.push(card);
    };
    const x1 = Math.floor((bounds.x1 - cardWidth) / cell),
      x2 = Math.floor(bounds.x2 / cell);
    const y1 = Math.floor((bounds.y1 - cardHeight) / cell),
      y2 = Math.floor(bounds.y2 / cell);
    if ((x2 - x1 + 1) * (y2 - y1 + 1) > buckets.size * 2) {
      for (const bucket of buckets.values()) addBucket(bucket);
    } else {
      for (let x = x1; x <= x2; x++)
        for (let y = y1; y <= y2; y++) {
          const bucket = buckets.get(`${x}:${y}`);
          if (bucket) addBucket(bucket);
        }
    }
    next.sort((a, b) => a.order - b.order);
    if (next.length !== mounted.length || next.some((card, index) => card !== mounted[index])) {
      mounted = next;
      onCards(next);
    }
  }

  function sync(): void {
    if (!frame) frame = requestAnimationFrame(update);
  }
  graph.on("pan zoom resize", sync);

  return {
    sync,
    setModel(users: AdminUser[]): void {
      buckets.clear();
      users.forEach((user, order) => {
        const point = graph.getElementById(String(user.user_id)).position();
        const card = { user, order, x: point.x - cardWidth / 2, y: point.y - cardHeight / 2 };
        const key = `${Math.floor(card.x / cell)}:${Math.floor(card.y / cell)}`;
        const bucket = buckets.get(key) || [];
        bucket.push(card);
        buckets.set(key, bucket);
      });
      force = true;
      sync();
    },
    setVisibleIds(ids: Set<string>): void {
      allowed = ids;
      force = true;
      sync();
    },
    destroy(): void {
      stopNavigation();
      graph.off("pan zoom resize", sync);
      cancelAnimationFrame(frame);
    },
  };
}
