<script>
  import { onDestroy, onMount } from "svelte";

  import { cn } from "../utils.js";
  import { animatedEmojiAssetUrls, normalizeBrand } from "./browser.js";

  const LOGO_LOAD_TIMEOUT_MS = 10000;

  const EMOJI_FONT_OPTIONS = {
    "noto-color": {
      cssFamily: "Noto Color Emoji",
      stylesheet: (text) =>
        `https://fonts.googleapis.com/css2?family=Noto+Color+Emoji&display=swap&text=${encodeURIComponent(text)}`,
    },
    "noto-emoji": {
      cssFamily: "Noto Emoji",
      stylesheet: (text) =>
        `https://fonts.googleapis.com/css2?family=Noto+Emoji:wght@700&display=swap&text=${encodeURIComponent(text)}`,
    },
    twemoji: {
      cssFamily: "Twemoji Mozilla",
      stylesheet: () => "https://cdn.jsdelivr.net/npm/twemoji-colr-font@15.0.3/twemoji.css",
    },
    openmoji: {
      cssFamily: "OpenMoji Color",
      stylesheet: () => "https://cdn.jsdelivr.net/npm/@openmoji/font@15.1.0/css/openmoji-color.css",
    },
  };

  export let brand = {};
  export let logoUrl = "";
  export let emoji = "";
  export let emojiFont = "";
  export let size = "sm";
  export let animate = false;
  let className = "";
  export { className as class };

  const SIZE_CLASSES = {
    sm: "",
    md: "brand-mark-lg",
    lg: "brand-mark-xl",
    xl: "brand-mark-xl",
  };

  let loaded = false;
  let failed = false;
  let lastLogoUrl = "";
  let logoLoadTimer = null;
  let logoLoadTimerUrl = "";
  let fontLoaded = false;
  let loadedFontKey = "";
  let animatedEmojiError = false;
  let animatedEmojiStaticFallback = false;
  let lastAnimatedEmoji = "";

  $: normalizedBrand = normalizeBrand({
    ...brand,
    logoUrl: logoUrl || brand?.logoUrl,
    emoji: emoji || brand?.emoji || brand?.logoEmoji,
    emojiFont: emojiFont || brand?.emojiFont || brand?.logoEmojiFont,
  });
  $: normalizedLogoUrl = normalizedBrand.logoUrl;
  $: normalizedEmoji = normalizedBrand.emoji;
  $: normalizedEmojiFont = normalizedBrand.emojiFont;
  $: sizeClass = SIZE_CLASSES[size] || "";
  $: animatedEmojiAssets = animatedEmojiAssetUrls(normalizedEmoji);
  $: animatedEmojiSrc = animatedEmojiAssets.gif;
  $: animatedEmojiFallbackSrc = animatedEmojiAssets.webp;
  $: useAnimatedEmoji =
    !normalizedLogoUrl &&
    normalizedEmojiFont === "noto-color-animated" &&
    animatedEmojiSrc &&
    !animatedEmojiError;

  $: if (normalizedLogoUrl !== lastLogoUrl) {
    lastLogoUrl = normalizedLogoUrl;
    loaded = false;
    failed = false;
  }
  $: if (normalizedLogoUrl && !loaded && !failed) armLogoLoadTimeout();
  $: if (!normalizedLogoUrl || loaded || failed) clearLogoLoadTimeout();
  $: if (`${normalizedEmojiFont}:${normalizedEmoji}` !== lastAnimatedEmoji) {
    lastAnimatedEmoji = `${normalizedEmojiFont}:${normalizedEmoji}`;
    animatedEmojiError = false;
    animatedEmojiStaticFallback = false;
  }

  onDestroy(() => {
    clearLogoLoadTimeout();
  });

  onMount(() => {
    loadEmojiFont(normalizedEmojiFont, normalizedEmoji);
  });

  $: if (normalizedEmojiFont && normalizedEmoji) {
    loadEmojiFont(normalizedEmojiFont, normalizedEmoji);
  }

  function loadEmojiFont(font, text) {
    if (typeof document === "undefined") return;
    if (font === "system" || font === "noto-color-animated" || !font) {
      fontLoaded = true;
      loadedFontKey = "system";
      return;
    }

    const fontOption = EMOJI_FONT_OPTIONS[font];
    if (!fontOption) {
      fontLoaded = true;
      loadedFontKey = font;
      return;
    }

    const fontUrl = fontOption.stylesheet(text);
    const fontKey = `${font}:${text}`;
    if (loadedFontKey === fontKey) return;

    fontLoaded = false;
    loadedFontKey = fontKey;

    const existing = document.querySelector(`link[data-brand-emoji-font="${fontKey}"]`);
    if (existing) {
      fontLoaded = true;
      return;
    }

    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = fontUrl;
    link.dataset.brandEmojiFont = fontKey;
    link.onload = () => {
      fontLoaded = true;
      if (document.fonts && fontOption.cssFamily) {
        document.fonts.load(`1em "${fontOption.cssFamily}"`, text).finally(() => {
          fontLoaded = true;
        });
      }
    };
    link.onerror = () => {
      fontLoaded = true;
    };

    document.head.appendChild(link);
  }

  function getEmojiFontClass(font) {
    if (font === "noto-color") return "emoji-font-noto-color";
    if (font === "noto-emoji") return "emoji-font-noto-emoji";
    if (font === "twemoji") return "emoji-font-twemoji";
    if (font === "openmoji") return "emoji-font-openmoji";
    if (font === "apple") return "emoji-font-apple";
    if (font === "segoe") return "emoji-font-segoe";
    if (font === "noto-local") return "emoji-font-noto-local";
    return "";
  }

  function clearLogoLoadTimeout() {
    if (logoLoadTimer) {
      window.clearTimeout(logoLoadTimer);
      logoLoadTimer = null;
    }
    logoLoadTimerUrl = "";
  }

  function armLogoLoadTimeout() {
    if (typeof window === "undefined") return;
    if (logoLoadTimer && logoLoadTimerUrl === normalizedLogoUrl) return;
    clearLogoLoadTimeout();
    logoLoadTimerUrl = normalizedLogoUrl;
    logoLoadTimer = window.setTimeout(() => {
      if (logoLoadTimerUrl === normalizedLogoUrl && !loaded) failed = true;
    }, LOGO_LOAD_TIMEOUT_MS);
  }
</script>

<div
  class={cn(
    "brand-mark",
    sizeClass,
    animate && "brand-mark-animate",
    normalizedLogoUrl && !failed && !loaded && "brand-mark-loading",
    normalizedLogoUrl && !failed && loaded && "brand-mark-loaded",
    className
  )}
  aria-busy={normalizedLogoUrl && !failed && !loaded ? "true" : undefined}
>
  {#if normalizedLogoUrl && !failed}
    {#if !loaded}
      <span class="brand-mark-spinner" aria-hidden="true"></span>
    {/if}
    <img
      class:loaded
      src={normalizedLogoUrl}
      alt=""
      loading="eager"
      decoding="async"
      fetchpriority="high"
      on:load={() => {
        loaded = true;
        clearLogoLoadTimeout();
      }}
      on:error={() => {
        failed = true;
        clearLogoLoadTimeout();
      }}
    />
  {:else if useAnimatedEmoji}
    <img
      class="brand-mark-animated-emoji loaded"
      src={animatedEmojiStaticFallback ? animatedEmojiFallbackSrc : animatedEmojiSrc}
      alt=""
      loading="eager"
      decoding="async"
      fetchpriority="high"
      on:error={() => {
        if (!animatedEmojiStaticFallback && animatedEmojiFallbackSrc) {
          animatedEmojiStaticFallback = true;
        } else {
          animatedEmojiError = true;
        }
      }}
    />
  {:else}
    <span
      class={cn("brand-mark-emoji", getEmojiFontClass(normalizedEmojiFont))}
      style="opacity: {fontLoaded ? 1 : 0}; transition: opacity 0.2s ease;"
    >
      {normalizedEmoji}
    </span>
  {/if}
</div>

<style>
  .brand-mark {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2rem;
    height: 2rem;
    flex-shrink: 0;
    overflow: visible;
    font-size: 1.625rem;
  }

  .brand-mark img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  .brand-mark img.loaded {
    opacity: 1;
  }

  .brand-mark.brand-mark-lg {
    width: 4.125rem;
    height: 4.125rem;
    font-size: 2.875rem;
  }

  .brand-mark.brand-mark-xl {
    width: 6rem;
    height: 6rem;
    font-size: 4.375rem;
  }

  .brand-mark img.brand-mark-animated-emoji {
    object-fit: contain;
    transform: scale(1.08);
  }

  .brand-mark.brand-mark-animate {
    animation: brand-mark-pulse 2s ease-in-out infinite;
  }

  .brand-mark-spinner {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .brand-mark-spinner::after {
    content: "";
    width: 1rem;
    height: 1rem;
    border: 2px solid currentColor;
    border-bottom-color: transparent;
    border-radius: 50%;
    animation: brand-mark-spin 0.8s linear infinite;
    opacity: 0.5;
  }

  @keyframes brand-mark-spin {
    0% {
      transform: rotate(0deg);
    }
    100% {
      transform: rotate(360deg);
    }
  }

  @keyframes brand-mark-pulse {
    0%,
    100% {
      transform: scale(1);
    }
    50% {
      transform: scale(1.05);
    }
  }

  .brand-mark-emoji {
    color: inherit;
    font-size: 1em;
    line-height: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    transform: translateY(0.02em);
    transform-origin: center;
  }

  .brand-mark-xl .brand-mark-emoji {
    font-size: 1em;
  }

  .brand-mark-lg .brand-mark-emoji {
    font-size: 1em;
  }

  .emoji-font-noto-color {
    font-family: "Noto Color Emoji", sans-serif;
  }

  .emoji-font-noto-emoji {
    color: var(--accent);
    font-family: "Noto Emoji", sans-serif;
    font-weight: 700;
  }

  .emoji-font-twemoji {
    font-family: "Twemoji Mozilla", sans-serif;
  }

  .emoji-font-openmoji {
    font-family: "OpenMoji Color", sans-serif;
  }

  .emoji-font-apple {
    font-family: "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif;
  }

  .emoji-font-segoe {
    font-family: "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji", sans-serif;
  }

  .emoji-font-noto-local {
    font-family: "Noto Color Emoji", "Noto Emoji", sans-serif;
  }
</style>
