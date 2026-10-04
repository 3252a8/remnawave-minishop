<script lang="ts">
  import { getAdminApi } from "$lib/admin/context";
  import { createAdminEmojiPicker } from "$lib/admin/emojiPicker.svelte";
  import RichTextEditor from "$lib/richtext/RichTextEditor.svelte";
  import type { MessageShortcodeInfo } from "$lib/richtext/editorSchema";
  import EmojiPicker from "$lib/telegramEmoji/EmojiPicker.svelte";

  import { adminRichTextLabels } from "../richTextLabels.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    value,
    onInput,
    shortcodes,
    onRequestShortcodes,
    at,
    placeholder = "",
  }: {
    value: string;
    onInput: (value: string) => void;
    shortcodes: MessageShortcodeInfo[];
    onRequestShortcodes: () => void;
    at: TranslateFn;
    placeholder?: string;
  } = $props();

  const labels = $derived(adminRichTextLabels(at));
  const api = getAdminApi();
  const emojiPicker = createAdminEmojiPicker();
</script>

<RichTextEditor
  {value}
  {onInput}
  {labels}
  {placeholder}
  {shortcodes}
  {onRequestShortcodes}
  selectCustomEmoji={emojiPicker.select}
  loadCustomEmojiMedia={emojiPicker.loadMedia}
  showSource
/>

<EmojiPicker
  open={emojiPicker.open}
  onOpenChange={emojiPicker.onOpenChange}
  onSelect={emojiPicker.onSelect}
  {at}
  {api}
/>
