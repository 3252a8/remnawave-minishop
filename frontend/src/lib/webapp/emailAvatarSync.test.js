import { describe, expect, it, vi } from "vitest";

import { createEmailAvatarSync } from "./emailAvatarSync.js";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

describe("createEmailAvatarSync", () => {
  it("normalizes emails before requesting an avatar", async () => {
    const buildAvatarUrl = vi.fn().mockResolvedValue("avatar-url");
    const onAvatarUrl = vi.fn();
    const sync = createEmailAvatarSync(buildAvatarUrl);

    sync.sync(" User@Example.COM ", onAvatarUrl);
    await Promise.resolve();

    expect(buildAvatarUrl).toHaveBeenCalledWith("user@example.com");
    expect(onAvatarUrl).toHaveBeenCalledWith("avatar-url");
  });

  it("does not request the same email twice", async () => {
    const buildAvatarUrl = vi.fn().mockResolvedValue("avatar-url");
    const sync = createEmailAvatarSync(buildAvatarUrl);

    sync.sync("user@example.test", vi.fn());
    sync.sync("USER@example.test", vi.fn());
    await Promise.resolve();

    expect(buildAvatarUrl).toHaveBeenCalledOnce();
  });

  it("clears the avatar when a previously active email disappears", async () => {
    const buildAvatarUrl = vi.fn().mockResolvedValue("avatar-url");
    const onAvatarUrl = vi.fn();
    const sync = createEmailAvatarSync(buildAvatarUrl);

    sync.sync("user@example.test", onAvatarUrl);
    sync.sync("", onAvatarUrl);
    await Promise.resolve();

    expect(onAvatarUrl).toHaveBeenCalledWith("");
    expect(onAvatarUrl).not.toHaveBeenCalledWith("avatar-url");
  });

  it("ignores stale avatar results after the email changes", async () => {
    const first = deferred();
    const second = deferred();
    const buildAvatarUrl = vi
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const onAvatarUrl = vi.fn();
    const sync = createEmailAvatarSync(buildAvatarUrl);

    sync.sync("first@example.test", onAvatarUrl);
    sync.sync("second@example.test", onAvatarUrl);
    first.resolve("first-avatar");
    second.resolve("second-avatar");
    await Promise.resolve();

    expect(onAvatarUrl).toHaveBeenCalledTimes(1);
    expect(onAvatarUrl).toHaveBeenCalledWith("second-avatar");
  });

  it("emits an empty avatar for current email load failures", async () => {
    const buildAvatarUrl = vi.fn().mockRejectedValue(new Error("failed"));
    const onAvatarUrl = vi.fn();
    const sync = createEmailAvatarSync(buildAvatarUrl);

    sync.sync("user@example.test", onAvatarUrl);
    await Promise.resolve();

    expect(onAvatarUrl).toHaveBeenCalledWith("");
  });
});
