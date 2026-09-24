import { afterEach, describe, expect, it, vi } from "vitest";
import { createExtensionHost, extensionPath, extensionRequestPath } from "./extensionHost";
import { createApiClient } from "./publicApi";
import { sectionFromPath, syncSectionPath } from "./routes";

afterEach(() => vi.unstubAllGlobals());

describe("customer extension host", () => {
  it("keeps direct page links and route prefixes", () => {
    const path = extensionPath("sample", "devices", "/prefix");
    expect(path).toBe("/prefix/extensions/sample/devices");
    expect(sectionFromPath(path, "/prefix")).toBe("extensions");
    const replaceState = vi.fn();
    vi.stubGlobal("window", {
      location: { pathname: path, protocol: "https:" },
      history: { replaceState },
    });
    syncSectionPath("extensions", true, null, null, "/prefix");
    expect(window.location.pathname).toBe(path);
    expect(replaceState).not.toHaveBeenCalled();
  });

  it.each(["/../other", "/%2e%2e/admin", "/%2fadmin", "/\\admin", "https://elsewhere/path"])(
    "rejects escaping the plugin API namespace: %s",
    (path) => {
      expect(() => extensionRequestPath("sample", path)).toThrow();
    }
  );

  it("keeps ordinary path and query parameters", () => {
    expect(extensionRequestPath("sample", "/devices?cursor=1")).toBe(
      "/api/plugins/sample/devices?cursor=1"
    );
  });

  it("uses authenticated Core requests and its own product identity", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ ok: true, order: { id: "one" } }), {
          headers: { "Content-Type": "application/json" },
        })
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient({ getAuthToken: () => "token" });
    const host = createExtensionHost(client, "sample", (key) => key);
    expect(await host.createOrder("router", {}, "unique-spin")).toEqual({ id: "one" });
    const [, options] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(options.body))).toEqual({
      product: "sample:router",
      options: {},
      idempotency_key: "unique-spin",
    });
    expect((options.headers as Headers).get("Authorization")).toBe("Bearer token");
  });

  it("delegates confirmation and notices to the host UI", async () => {
    const notify = vi.fn();
    const confirm = vi.fn(async () => true);
    const host = createExtensionHost(createApiClient(), "sample", (key) => key, "", {
      notify,
      confirm,
    });
    host.notify("Ready");
    expect(await host.confirm("Proceed?")).toBe(true);
    expect(notify).toHaveBeenCalledWith("Ready");
  });
});
