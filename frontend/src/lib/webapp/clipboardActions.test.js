import { describe, expect, it, vi } from "vitest";

import { createClipboardActions } from "./clipboardActions.js";

function makeActions(result = true) {
  const deps = {
    copyTextToClipboard: vi.fn(async () => result),
    showToast: vi.fn(),
    t: vi.fn((key) => key),
  };
  return { actions: createClipboardActions(deps), deps };
}

describe("createClipboardActions", () => {
  it("shows the default copied message after a successful copy", async () => {
    const { actions, deps } = makeActions(true);

    await actions.copyText("value");

    expect(deps.copyTextToClipboard).toHaveBeenCalledWith("value");
    expect(deps.showToast).toHaveBeenCalledWith("wa_copied");
  });

  it("shows a custom success message", async () => {
    const { actions, deps } = makeActions(true);

    await actions.copyText("value", "done");

    expect(deps.showToast).toHaveBeenCalledWith("done");
  });

  it("shows unavailable when copying fails", async () => {
    const { actions, deps } = makeActions(false);

    await actions.copyText("value");

    expect(deps.showToast).toHaveBeenCalledWith("wa_unavailable");
  });
});
