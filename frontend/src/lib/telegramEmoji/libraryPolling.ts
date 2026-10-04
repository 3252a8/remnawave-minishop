import { getEmojiLibrary, type TelegramEmojiApi } from "./api";
import type { EmojiLibrary } from "./types";

export function emojiLibraryIsWarming(library: EmojiLibrary | null): boolean {
  return Boolean(library?.sets.some((pack) => pack.state === "warming"));
}

/** The mounted owner starts this only while active/warming; completion stops it. */
export function pollEmojiLibrary(
  api: TelegramEmojiApi,
  onLibrary: (library: EmojiLibrary) => void,
  onError: (failure: unknown) => void,
  delay = 2000
): () => void {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let failures = 0;
  const schedule = (wait = delay) => {
    if (!controller.signal.aborted) timer = setTimeout(() => void poll(), wait);
  };
  const poll = async () => {
    try {
      const result = await getEmojiLibrary(api, controller.signal);
      if (controller.signal.aborted) return;
      failures = 0;
      onLibrary(result);
      if (emojiLibraryIsWarming(result)) schedule();
    } catch (failure) {
      if (controller.signal.aborted) return;
      onError(failure);
      failures = Math.min(failures + 1, 5);
      schedule(Math.min(delay * 2 ** failures, 30000));
    }
  };
  schedule();
  return () => {
    controller.abort();
    if (timer !== undefined) clearTimeout(timer);
  };
}
