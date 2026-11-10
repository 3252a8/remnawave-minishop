import { buildApiUrl } from "$lib/webapp/publicApi";

export const MESSAGE_IMAGE_MAX_BYTES = 8 * 1024 * 1024;
export const SUPPORT_IMAGE_MAX_COUNT = 5;
export const SUPPORT_IMAGE_TOTAL_MAX_BYTES = 16 * 1024 * 1024;
export const MESSAGE_IMAGE_ACCEPT = ["image/*", "image/heic", "image/heif", ".heic", ".heif"].join(
  ","
);

const MESSAGE_IMAGE_MIME_TYPES = new Set([
  "image/heic",
  "image/heic-sequence",
  "image/heif",
  "image/heif-sequence",
  "image/jpeg",
  "image/jpg",
  "image/pjpeg",
  "image/png",
  "image/webp",
  "image/x-heic",
  "image/x-heif",
]);

export function isAcceptedMessageImage(file: Pick<File, "name" | "type">): boolean {
  const contentType = String(file.type || "").toLowerCase();
  if (contentType && MESSAGE_IMAGE_MIME_TYPES.has(contentType)) return true;
  return /\.(?:heic|heif|jpe?g|jfif|png|webp)$/i.test(String(file.name || ""));
}

export function messageRequestBody(
  payload: Record<string, unknown>,
  image: File | File[] | null | undefined
): BodyInit {
  const images = Array.isArray(image) ? image : image ? [image] : [];
  if (!images.length) return JSON.stringify(payload);
  const form = new FormData();
  for (const [key, value] of Object.entries(payload)) {
    if (value === undefined) continue;
    form.append(key, typeof value === "string" ? value : JSON.stringify(value));
  }
  for (const file of images) form.append("image", file, file.name);
  return form;
}

export function supportMessageImageUrls(
  message: { image_id?: string | null; image_ids?: string[] },
  admin = false
): string[] {
  const ids = message.image_ids?.length
    ? message.image_ids
    : message.image_id
      ? [message.image_id]
      : [];
  return ids.map((id) => supportMessageImageUrl(id, admin));
}

export function supportMessageImageUrl(imageId: string, admin = false): string {
  const id = encodeURIComponent(imageId);
  return buildApiUrl(admin ? `/admin/message-images/${id}` : `/support/images/${id}`);
}
