import { describe, expect, it } from "vitest";
import { createApiClient } from "$lib/webapp/publicApi";
import { createMessageTargets } from "./messageTargets.svelte";

describe("active plugin message targets", () => {
  it("clears previously active choices on a failed reload and supports retry", async () => {
    let failed = false;
    const client = createApiClient({
      mockApi: async () => {
        if (failed) throw Error("unavailable");
        return {
          ok: true,
          sections: [{ id: "/extensions/sample/services", label: "Services", owner: "sample" }],
        };
      },
    });
    const targets = createMessageTargets(client.api);
    await targets.load();
    expect(targets.sections).toHaveLength(1);
    failed = true;
    await targets.load();
    expect(targets.sections).toEqual([]);
    expect(targets.failed).toBe(true);
    failed = false;
    await targets.load();
    expect(targets.sections).toHaveLength(1);
    expect(targets.failed).toBe(false);
  });
});
