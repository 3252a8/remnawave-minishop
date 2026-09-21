import { afterEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import { createWebappDataClient } from "./dataClient";

afterEach(() => vi.unstubAllGlobals());

describe("profile requests", () => {
  it("coalesces parallel loads and keeps a newer fresh response", async () => {
    let oldResolve!: (response: Response) => void;
    let newResolve!: (response: Response) => void;
    const fetch = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            oldResolve = resolve;
          })
      )
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            newResolve = resolve;
          })
      );
    vi.stubGlobal("fetch", fetch);
    const client = createWebappDataClient();
    const old = client.loadData();
    const duplicate = client.loadData();
    expect(fetch).toHaveBeenCalledTimes(1);
    const fresh = client.loadData({ fresh: true });
    newResolve(Response.json({ ok: true, revision: 2 }));
    const result = await fresh;
    oldResolve(Response.json({ ok: true, revision: 1 }));
    expect(await old).toEqual(result);
    expect(await duplicate).toEqual(result);
    expect(get(client.data)).toEqual(result);
  });

  it("does not replace state with an older response after a failed fresh request", async () => {
    let resolveOld!: (response: Response) => void;
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementationOnce(
          () =>
            new Promise<Response>((resolve) => {
              resolveOld = resolve;
            })
        )
        .mockResolvedValueOnce(Response.json({ ok: false }, { status: 503 }))
    );
    const client = createWebappDataClient();
    const old = client.loadData();
    await expect(client.loadData({ fresh: true })).rejects.toThrow("service_unavailable");
    resolveOld(Response.json({ ok: true }));
    await expect(old).rejects.toThrow("superseded_profile");
    expect(get(client.data)).toBeNull();
  });
});
