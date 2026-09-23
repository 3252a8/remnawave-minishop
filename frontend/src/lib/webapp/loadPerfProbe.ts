type LoadStage = "start" | "data" | "admin" | "section" | "paint";

let nextLoadId = 0;

export function createLoadPerfProbe(enabled: boolean, route: string) {
  const perf =
    enabled && typeof performance !== "undefined" && typeof performance.mark === "function"
      ? performance
      : null;
  const prefix = `webapp:load:${++nextLoadId}`;
  const times = new Map<LoadStage, number>();

  function mark(stage: LoadStage): void {
    if (!perf) return;
    perf.mark(`${prefix}:${stage}`);
    times.set(stage, perf.now());
  }

  mark("start");

  function finish(section: string): void {
    if (!perf) return;
    const report = () => {
      mark("paint");
      const start = times.get("start") || 0;
      const data = times.get("data") || start;
      const admin = times.get("admin") || data;
      const loaded = times.get("section") || admin;
      const painted = times.get("paint") || loaded;
      perf.measure(`${prefix}:total`, `${prefix}:start`, `${prefix}:paint`);
      console.info(
        "[webapp-perf]",
        JSON.stringify({
          route,
          section,
          dataMs: Math.round(data - start),
          adminMs: Math.round(admin - data),
          sectionMs: Math.round(loaded - admin),
          paintMs: Math.round(painted - loaded),
          totalMs: Math.round(painted - start),
        })
      );
    };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(report);
    else report();
  }

  return { mark, finish };
}
