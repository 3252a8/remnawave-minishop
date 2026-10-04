import { onDestroy } from "svelte";

import type { CustomEmoji } from "$lib/richtext/customEmoji";
import type { EmojiItem } from "$lib/telegramEmoji/types";
import type { CustomEmojiMediaLoader } from "$lib/richtext/types";
import { buildTelegramEmojiMediaPath } from "$lib/telegramEmoji/paths";
import { getAdminApiBlob } from "./context";

/** Adapt the admin palette's events to the shared editor's cancellable selection. */
export function createAdminEmojiPicker() {
  const mediaApi = getAdminApiBlob();
  const loadMedia: CustomEmojiMediaLoader = (id, signal) =>
    mediaApi(buildTelegramEmojiMediaPath(id), { signal });
  let open = $state(false);
  let resolveSelection: ((emoji: CustomEmoji | null) => void) | null = null;

  function finish(emoji: CustomEmoji | null): void {
    const resolve = resolveSelection;
    resolveSelection = null;
    open = false;
    resolve?.(emoji);
  }

  function select(): Promise<CustomEmoji | null> {
    finish(null);
    return new Promise((resolve) => {
      resolveSelection = resolve;
      open = true;
    });
  }

  onDestroy(() => finish(null));

  return {
    get open() {
      return open;
    },
    select,
    loadMedia,
    onOpenChange: (next: boolean) => {
      if (!next) finish(null);
    },
    onSelect: (item: EmojiItem) => finish({ id: item.id, fallback: item.fallback }),
  };
}
