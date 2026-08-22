import { describe, expect, it } from "vitest";

import { messageRequestBody, supportMessageImageUrl } from "./messageImage";

describe("message image requests", () => {
  it("keeps the existing JSON transport when there is no image", () => {
    expect(messageRequestBody({ body: "hello", buttons: [] }, null)).toBe(
      JSON.stringify({ body: "hello", buttons: [] })
    );
  });

  it("encodes structured fields and one image as multipart", () => {
    const image = new File([new Uint8Array([1, 2, 3])], "proof.png", { type: "image/png" });
    const body = messageRequestBody(
      { text: "hello", channels: ["telegram", "email"], scheduled_at: null },
      image
    );

    expect(body).toBeInstanceOf(FormData);
    const form = body as FormData;
    expect(form.get("text")).toBe("hello");
    expect(form.get("channels")).toBe('["telegram","email"]');
    expect(form.get("scheduled_at")).toBe("null");
    const upload = form.get("image");
    expect(upload).toBeInstanceOf(File);
    expect((upload as File).name).toBe("proof.png");
    expect((upload as File).type).toBe("image/png");
    expect((upload as File).size).toBe(3);
  });

  it("builds separate private user and admin image URLs", () => {
    expect(supportMessageImageUrl("abc")).toBe("/api/support/images/abc");
    expect(supportMessageImageUrl("abc", true)).toBe("/api/admin/message-images/abc");
  });
});
