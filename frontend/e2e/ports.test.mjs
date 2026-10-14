import { EventEmitter } from "node:events";
import { createServer } from "node:net";
import { randomInt } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { browserPort, E2E_HOST, selectBrowserPort } from "./ports.mjs";

vi.mock("node:net", () => ({ createServer: vi.fn() }));
vi.mock("node:crypto", () => ({ randomInt: vi.fn() }));

class ProbeServer extends EventEmitter {
  constructor(errorCode, closeError) {
    super();
    this.errorCode = errorCode;
    this.closeError = closeError;
    this.listen = vi.fn((options, callback) => {
      queueMicrotask(() => {
        if (this.errorCode) {
          this.emit("error", Object.assign(new Error(this.errorCode), { code: this.errorCode }));
        } else {
          callback();
        }
      });
      return this;
    });
    this.close = vi.fn((callback) => callback(this.closeError));
  }
}

beforeEach(() => {
  vi.mocked(randomInt).mockReturnValue(50000);
  vi.mocked(createServer).mockImplementation(() => new ProbeServer());
});
afterEach(() => vi.resetAllMocks());

describe("browser test ports", () => {
  it.each([undefined, ""])("keeps the direct-launch default for %s", (value) => {
    expect(browserPort(value)).toBe(8091);
  });

  it.each(["8091", "14566", "49152", "65535", " 14566 "])(
    "accepts a valid explicit port %s",
    (value) => expect(browserPort(value)).toBe(Number(value))
  );

  it.each(["0", "65536", "-1", "1.5", "NaN", "Infinity", "1e4", "0x4000", "abc", " "])(
    "rejects malformed or out-of-range PORT=%s",
    (value) => expect(() => browserPort(value)).toThrow("PORT must be an integer")
  );

  it.each(["22", "1719", "6000", "6566", "6665", "6666", "6667", "6668", "6669", "6697", "10080"])(
    "rejects Chromium-blocked PORT=%s before opening a socket",
    async (value) => {
      await expect(selectBrowserPort(value)).rejects.toThrow("blocked by Chromium");
      expect(createServer).not.toHaveBeenCalled();
    }
  );

  it("chooses a high browser-safe port instead of asking the OS for port zero", async () => {
    const server = new ProbeServer();
    vi.mocked(createServer).mockReturnValue(server);
    expect(await selectBrowserPort()).toBe(50000);
    expect(randomInt).toHaveBeenCalledWith(49152, 65536);
    expect(server.listen).toHaveBeenCalledWith(
      { port: 50000, host: E2E_HOST, exclusive: true },
      expect.any(Function)
    );
    expect(server.close).toHaveBeenCalledOnce();
    expect(server.listenerCount("error")).toBe(0);
  });

  it.each(["EADDRINUSE", "EACCES"])("retries a busy or Windows-reserved port: %s", async (code) => {
    vi.mocked(randomInt).mockReturnValueOnce(50000).mockReturnValueOnce(60000);
    vi.mocked(createServer)
      .mockReturnValueOnce(new ProbeServer(code))
      .mockReturnValueOnce(new ProbeServer());
    expect(await selectBrowserPort()).toBe(60000);
    expect(createServer).toHaveBeenCalledTimes(2);
  });

  it("honours an available explicit port and closes the probe before handoff", async () => {
    const server = new ProbeServer();
    vi.mocked(createServer).mockReturnValue(server);
    expect(await selectBrowserPort("14566")).toBe(14566);
    expect(randomInt).not.toHaveBeenCalled();
    expect(server.close).toHaveBeenCalledOnce();
  });

  it("fails immediately for an occupied explicit port instead of silently changing it", async () => {
    vi.mocked(createServer).mockReturnValue(new ProbeServer("EADDRINUSE"));
    await expect(selectBrowserPort("14566")).rejects.toThrow("Cannot bind configured PORT=14566");
    expect(createServer).toHaveBeenCalledOnce();
    expect(randomInt).not.toHaveBeenCalled();
  });

  it("does not conceal unexpected socket errors", async () => {
    vi.mocked(createServer).mockReturnValue(new ProbeServer("EMFILE"));
    await expect(selectBrowserPort()).rejects.toThrow("EMFILE");
    expect(createServer).toHaveBeenCalledOnce();
  });

  it("does not hand off a probe that failed to close", async () => {
    vi.mocked(createServer).mockReturnValue(new ProbeServer(undefined, new Error("close failed")));
    await expect(selectBrowserPort()).rejects.toThrow("close failed");
  });

  it("bounds retries when every candidate is unavailable", async () => {
    vi.mocked(createServer).mockImplementation(() => new ProbeServer("EACCES"));
    await expect(selectBrowserPort()).rejects.toThrow("after 128 attempts");
    expect(createServer).toHaveBeenCalledTimes(128);
  });
});
