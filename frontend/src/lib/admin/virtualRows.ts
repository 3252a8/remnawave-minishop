export type VirtualRange = {
  start: number;
  end: number;
};

export function calculateVirtualRange({
  rowCount,
  rowHeight,
  viewportHeight,
  offsetTop,
  overscan,
}: {
  rowCount: number;
  rowHeight: number;
  viewportHeight: number;
  offsetTop: number;
  overscan: number;
}): VirtualRange {
  const count = Math.max(0, Math.floor(Number(rowCount) || 0));
  const height = Math.max(1, Number(rowHeight) || 1);
  const viewHeight = Math.max(0, Number(viewportHeight) || 0);
  const beforeViewport = Math.max(0, -Number(offsetTop || 0));
  const extra = Math.max(0, Math.floor(Number(overscan) || 0));
  const start = Math.max(0, Math.floor(beforeViewport / height) - extra);
  const visibleCount = Math.ceil(viewHeight / height) + extra * 2;
  const end = Math.min(count, Math.max(start + 1, start + visibleCount));
  return { start, end };
}
