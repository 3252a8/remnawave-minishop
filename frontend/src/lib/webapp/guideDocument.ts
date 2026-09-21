import { recordOrNull, type WebappRecord } from "./domainTypes";

export type GuideDocument = WebappRecord & {
  schemaVersion: 1;
  platforms: Array<WebappRecord & { id: string }>;
};

const platformId = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/;

export function guideDocumentToConfig(value: unknown): WebappRecord | null {
  const document = recordOrNull(value);
  if (!document || document.schemaVersion !== 1 || !Array.isArray(document.platforms)) {
    return null;
  }
  const platforms: Record<string, WebappRecord> = {};
  for (const item of document.platforms) {
    const platform = recordOrNull(item);
    const id = typeof platform?.id === "string" ? platform.id : "";
    if (!platform || !platformId.test(id) || Object.hasOwn(platforms, id)) return null;
    const { id: _id, ...content } = platform;
    platforms[id] = content;
  }
  const {
    schemaVersion: _version,
    revision: _revision,
    source: _source,
    resources: _resources,
    platforms: _platforms,
    ...content
  } = document;
  return { version: "1", ...content, platforms };
}
