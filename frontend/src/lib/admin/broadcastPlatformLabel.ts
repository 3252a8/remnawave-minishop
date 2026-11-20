type TranslateFn = (key: string, vars?: Record<string, unknown>, fallback?: string) => string;

const platformNames: Record<string, string> = {
  android: "Android",
  ios: "iOS",
  ipados: "iPadOS",
  linux: "Linux",
  macos: "macOS",
  tvos: "tvOS",
  windows: "Windows",
};

// History and per-user exclusions can outlive platform discovery.
export function broadcastPlatformLabel(target: string, at: TranslateFn): string | null {
  if (!target.startsWith("platform:")) return null;
  const key = target.slice("platform:".length);
  if (/^id-[a-f0-9]{24}$/.test(key)) {
    return at("broadcast_platform_identifier", { id: key.slice(3, 11) }, "Device platform · {id}");
  }
  const fallback = Object.hasOwn(platformNames, key) ? platformNames[key] : key;
  return at(`broadcast_target_platform_${key}`, {}, fallback);
}
