/** The Telegram entity ID is a decimal string, including values above 2^53. */
export type CustomEmoji = { id: string; fallback: string };

export function isCustomEmojiId(value: string): boolean {
  return /^[1-9][0-9]{0,19}$/.test(value);
}

const emojiGraphemes = new Intl.Segmenter(undefined, { granularity: "grapheme" });

/** Keep a complete emoji sequence, including its variation selectors and ZWJ. */
export function isCustomEmojiFallback(value: string): boolean {
  if (!value || [...value].length > 64 || /[<>\s]/u.test(value)) return false;
  if ([...emojiGraphemes.segment(value)].length !== 1) return false;
  if (/\p{Regional_Indicator}/u.test(value)) return /^\p{Regional_Indicator}{2}$/u.test(value);
  if (value.includes("\u20e3")) return /^[#*0-9]\ufe0f?\u20e3$/u.test(value);
  if (/[\u{e0020}-\u{e007f}]/u.test(value))
    return /^\u{1f3f4}[\u{e0030}-\u{e0039}\u{e0061}-\u{e007a}]+\u{e007f}$/u.test(value);
  return value
    .split("\u200d")
    .every((part) => /^\p{Extended_Pictographic}[\ufe0e\ufe0f]?\p{Emoji_Modifier}?$/u.test(part));
}

export function isCustomEmoji(value: CustomEmoji): boolean {
  return isCustomEmojiId(value.id) && isCustomEmojiFallback(value.fallback);
}
