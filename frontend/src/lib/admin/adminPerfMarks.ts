import { tick } from "svelte";

let perfSpanSeq = 0;

function getPerformance(): Performance | null {
  return typeof performance !== "undefined" &&
    typeof performance.mark === "function" &&
    typeof performance.measure === "function"
    ? performance
    : null;
}

function markName(scope: string, id: number, stage: string): string {
  return `admin:${scope}:${id}:${stage}`;
}

export function createAdminPerfSpan(scope: "users" | "logs" | "payments") {
  const perf = getPerformance();
  const id = ++perfSpanSeq;
  const start = markName(scope, id, "start");
  const apiResponse = markName(scope, id, "api-response");
  const stateAssign = markName(scope, id, "state-assign");
  const renderSettled = markName(scope, id, "render-settled");

  if (perf) perf.mark(start);

  return {
    apiResponse(): void {
      perf?.mark(apiResponse);
    },
    stateAssign(): void {
      perf?.mark(stateAssign);
    },
    async renderSettled(): Promise<void> {
      if (!perf) return;
      await tick();
      perf.mark(renderSettled);
      perf.measure(`admin:${scope}:api`, start, apiResponse);
      perf.measure(`admin:${scope}:assign`, apiResponse, stateAssign);
      perf.measure(`admin:${scope}:render`, stateAssign, renderSettled);
      perf.measure(`admin:${scope}:total`, start, renderSettled);
    },
  };
}
