import { normalizedEmail } from "./formatters.js";
import { buildGravatarUrl } from "./gravatar.js";

type BuildAvatarUrl = (email: string) => Promise<string>;
type AvatarUrlSink = (url: string) => void;

export function createEmailAvatarSync(buildAvatarUrl: BuildAvatarUrl = buildGravatarUrl) {
  let activeEmailKey = "";

  function sync(email: unknown, onAvatarUrl: AvatarUrlSink) {
    const emailKey = normalizedEmail(email);
    if (!emailKey) {
      if (activeEmailKey) {
        activeEmailKey = "";
        onAvatarUrl("");
      }
      return;
    }
    if (activeEmailKey === emailKey) return;
    activeEmailKey = emailKey;
    buildAvatarUrl(emailKey).then(
      (url) => {
        if (activeEmailKey === emailKey) onAvatarUrl(url);
      },
      () => {
        if (activeEmailKey === emailKey) onAvatarUrl("");
      }
    );
  }

  return { sync };
}
