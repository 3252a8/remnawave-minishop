import { buildApiUrl } from "$lib/webapp/publicApi";

export const MESSAGE_IMAGE_MAX_BYTES = 8 * 1024 * 1024;
export const MESSAGE_IMAGE_ACCEPT = "image/jpeg,image/png,image/webp";

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
