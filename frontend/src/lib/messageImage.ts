import { buildApiUrl } from "$lib/webapp/publicApi";

export const MESSAGE_IMAGE_MAX_BYTES = 8 * 1024 * 1024;
export const MESSAGE_IMAGE_ACCEPT = [
  "image/heic",
  "image/heif",
  "image/jpeg",
  "image/png",
  "image/webp",
  ".heic",
  ".heif",
].join(",");

const MESSAGE_IMAGE_MIME_TYPES = new Set(
  MESSAGE_IMAGE_ACCEPT.split(",").filter((value) => value.startsWith("image/"))
);

export function isAcceptedMessageImage(file: Pick<File, "name" | "type">): boolean {
  const contentType = String(file.type || "").toLowerCase();
  if (contentType && MESSAGE_IMAGE_MIME_TYPES.has(contentType)) return true;
  return /\.(?:heic|heif|jpe?g|png|webp)$/i.test(String(file.name || ""));
}

export function messageRequestBody(
  payload: Record<string, unknown>,
  image: File | null | undefined
): BodyInit {
  if (!image) return JSON.stringify(payload);
  const form = new FormData();
  for (const [key, value] of Object.entries(payload)) {
    if (value === undefined) continue;
    form.append(key, typeof value === "string" ? value : JSON.stringify(value));
  }
  form.append("image", image, image.name);
  return form;
}

export function supportMessageImageUrl(imageId: string, admin = false): string {
  const id = encodeURIComponent(imageId);
  return buildApiUrl(admin ? `/admin/message-images/${id}` : `/support/images/${id}`);
}
