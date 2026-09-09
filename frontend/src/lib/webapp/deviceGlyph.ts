// Pick a Lucide device silhouette from the panel's free-form model, platform and
// user-agent strings. Matching is word-bounded because short tokens like "ios",
// "tv" and "pc" otherwise appear inside unrelated words surprisingly often.

export type DeviceShape = "phone" | "tablet" | "laptop" | "desktop" | "tv";

interface DeviceGlyphSource {
  display_name?: unknown;
  platform?: unknown;
  platform_label?: unknown;
  os_version?: unknown;
  user_agent?: unknown;
}

function haystack(device: DeviceGlyphSource | null | undefined): string {
  return [
    device?.display_name,
    device?.platform,
    device?.platform_label,
    device?.os_version,
    device?.user_agent,
  ]
    .map((part) => String(part ?? ""))
    .join(" ")
    .toLowerCase();
}

function matcher(words: readonly string[]): RegExp {
  return new RegExp(`\\b(?:${words.join("|")})\\b`);
}

const TV = matcher(["tv", "tvos", "appletv", "shield", "firestick", "chromecast"]);
const TABLET = matcher(["ipad", "tablet", "tab", "pad", "surface"]);
const LAPTOP = matcher(["macbook", "laptop", "notebook", "thinkpad", "chromebook", "book"]);
const DESKTOP = matcher(["imac", "mac mini", "mac studio", "mac pro", "desktop", "pc"]);
const PHONE = matcher(["iphone", "phone", "pixel", "galaxy", "xiaomi", "redmi", "oneplus"]);
const APPLE_MOBILE = matcher(["ios", "ipados", "iphone", "ipad"]);
const ANDROID = matcher(["android", "harmonyos", "grapheneos"]);
const WINDOWS = matcher(["windows", "win32", "win64", "winnt", "microsoft"]);
const LINUX = matcher(["linux", "ubuntu", "debian", "fedora", "arch", "openwrt"]);
const MAC_COMPUTER = matcher(["macos", "mac os", "macintosh", "darwin"]);

export function resolveDeviceShape(device: DeviceGlyphSource | null | undefined): DeviceShape {
  const text = haystack(device);
  if (TV.test(text)) return "tv";
  if (TABLET.test(text)) return "tablet";
  if (LAPTOP.test(text)) return "laptop";
  if (DESKTOP.test(text)) return "desktop";
  if (PHONE.test(text)) return "phone";
  // Android user agents also contain "Linux", so mobile platforms come first.
  if (ANDROID.test(text) || APPLE_MOBILE.test(text)) return "phone";
  if (MAC_COMPUTER.test(text) || WINDOWS.test(text)) return "laptop";
  if (LINUX.test(text)) return "desktop";
  return "phone";
}
