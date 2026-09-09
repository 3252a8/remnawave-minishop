import { describe, expect, it } from "vitest";

import { adminErrorMessage } from "./errors.js";

const messages: Record<string, string> = {
  error_image_dimensions: "Image dimensions are not supported",
  error_image_type: "Image type is not supported",
  error_invalid_audience:
    "The recipient was not found. Refresh or reopen the user card and try again.",
};

function at(key: string, vars: Record<string, unknown> = {}, fallback = ""): string {
  if (key === "error_with_details") return `${vars.message}: ${vars.details}`;
  return messages[key] || fallback || key;
}

describe("adminErrorMessage", () => {
  it("keeps known flat API errors readable", () => {
    expect(
      adminErrorMessage(
        { error: "unsupported_image", message: "image/tiff" },
        at,
        "Broadcast failed"
      )
    ).toBe("Image type is not supported: image/tiff");
  });

  it("explains an invalid direct-message audience", () => {
    expect(adminErrorMessage({ error: "invalid_audience" }, at, "Broadcast failed")).toBe(
      "The recipient was not found. Refresh or reopen the user card and try again."
    );
  });

  it("extracts a code and reason from nested error objects", () => {
    expect(
      adminErrorMessage(
        {
          error: {
            code: "image_dimensions",
            message: "12000×12000 exceeds the supported size",
          },
        },
        at,
        "Broadcast failed"
      )
    ).toBe("Image dimensions are not supported: 12000×12000 exceeds the supported size");
  });

  it("summarizes structured validation details", () => {
    expect(
      adminErrorMessage(
        { detail: [{ msg: "Image is empty" }, { message: "Choose another file" }] },
        at,
        "Broadcast failed"
      )
    ).toBe("Image is empty; Choose another file");
  });

  it("uses the requested fallback instead of stringifying unknown objects", () => {
    const message = adminErrorMessage({}, at, "Broadcast failed");

    expect(message).toBe("Broadcast failed");
    expect(message).not.toBe("[object Object]");
  });
});
