<script lang="ts">
  import { previewHtmlFromWire } from "$lib/richtext/telegramHtml";
  import { ExternalLink, MousePointerClick } from "$components/ui/icons";
  import EmojiGlyph from "$lib/telegramEmoji/EmojiGlyph.svelte";
  import type { MenuPreview, TranslateFn } from "$lib/telegramEmoji/types";

  let {
    at,
    preview,
    loading,
    error = "",
    theme,
    selectedId,
    onSelect,
  }: {
    at: TranslateFn;
    preview: MenuPreview | null;
    loading: boolean;
    error?: string;
    theme: "light" | "dark";
    selectedId: string;
    onSelect: (id: string) => void;
  } = $props();
  const messageHtml = $derived(previewHtmlFromWire(preview?.text || ""));
</script>

<section
  class="telegram-preview"
  data-theme={theme}
  aria-label={at("telegram_menu_preview")}
  aria-busy={loading}
>
  <header>
    <div class="bot-avatar">🤖</div>
    <div>
      <strong>{at("telegram_menu_preview_bot")}</strong><span>{at("telegram_menu_preview")}</span>
    </div>
  </header>
  <div class="telegram-chat">
    {#if error}<p class="preview-message" role="alert">
        {at(error, {}, at("telegram_menu_preview_failed"))}
      </p>
    {:else if !preview}<p class="preview-message" role="status">{at("loading")}</p>
    {:else if !preview.available}<p class="preview-message">{at("telegram_menu_unavailable")}</p>
    {:else}
      <div class="telegram-message">{@html messageHtml}</div>
      <div class="telegram-keyboard" class:updating={loading}>
        {#each preview.rows as row, rowIndex (rowIndex)}
          <div class="telegram-row" style={`--columns: ${row.length}`}>
            {#each row as button (button.id)}
              <button
                type="button"
                class="telegram-key"
                data-style={button.style}
                aria-pressed={selectedId === button.id}
                title={at("telegram_menu_select_preview", { label: button.label })}
                onclick={() => onSelect(button.id)}
              >
                {#if button.icon_custom_emoji_id}<EmojiGlyph
                    fallback={button.emoji_fallback}
                    url={button.thumbnail_url}
                    size={19}
                  />{/if}
                <span>{button.label}</span>
                {#if button.kind === "url" || button.kind === "webapp"}<ExternalLink
                    size={10}
                    aria-hidden="true"
                  />{/if}
              </button>
            {/each}
          </div>
        {/each}
      </div>
    {/if}
  </div>
  <footer><MousePointerClick size={14} /><span>{at("telegram_menu_preview_hint")}</span></footer>
</section>

<style>
  .telegram-preview {
    --tg-bg: #e6ebee;
    --tg-head: #fff;
    --tg-message: #fff;
    --tg-text: #17212b;
    --tg-muted: #708499;
    --tg-button: #dce8f0;
    --tg-primary: #3589d2;
    --tg-success: #2b9460;
    --tg-danger: #cc4c53;
    display: grid;
    border: 1px solid var(--admin-border);
    border-radius: 16px;
    overflow: hidden;
    min-width: 0;
    color: var(--tg-text);
    background: var(--tg-bg);
  }
  .telegram-preview[data-theme="dark"] {
    --tg-bg: #0e1621;
    --tg-head: #17212b;
    --tg-message: #182533;
    --tg-text: #eaf2f7;
    --tg-muted: #8a9dad;
    --tg-button: #25374a;
    --tg-primary: #246cae;
    --tg-success: #217a50;
    --tg-danger: #a9424d;
  }
  header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 13px 16px;
    background: var(--tg-head);
  }
  header > div:last-child {
    display: grid;
    gap: 2px;
  }
  header strong {
    font-size: 13px;
  }
  header span {
    font-size: 11px;
    color: var(--tg-muted);
  }
  .bot-avatar {
    display: grid;
    place-items: center;
    height: 34px;
    width: 34px;
    border-radius: 50%;
    background: var(--tg-primary);
    font-size: 19px;
  }
  .telegram-chat {
    display: grid;
    align-content: start;
    gap: 7px;
    padding: 18px 14px;
    min-height: 220px;
    background-image: radial-gradient(
      color-mix(in srgb, var(--tg-muted) 12%, transparent) 1px,
      transparent 1px
    );
    background-size: 16px 16px;
  }
  .telegram-message {
    background: var(--tg-message);
    padding: 12px 14px;
    border-radius: 12px 12px 12px 3px;
    font-size: 13px;
    line-height: 1.55;
    overflow-wrap: anywhere;
  }
  .telegram-message :global(a) {
    color: #3589d2;
  }
  .telegram-message :global(pre) {
    overflow: auto;
    white-space: pre-wrap;
  }
  .telegram-message :global(blockquote) {
    margin: 6px 0;
    border-left: 3px solid var(--tg-primary);
    padding-left: 8px;
  }
  .telegram-keyboard {
    display: grid;
    gap: 5px;
  }
  .telegram-row {
    display: grid;
    grid-template-columns: repeat(var(--columns), minmax(0, 1fr));
    gap: 5px;
  }
  .telegram-key {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    position: relative;
    min-height: 40px;
    padding: 8px;
    font: inherit;
    font-size: 12px;
    line-height: 1.35;
    border: 2px solid transparent;
    border-radius: 7px;
    background: var(--tg-button);
    color: var(--tg-text);
    cursor: pointer;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  .telegram-key[data-style="primary"] {
    background: var(--tg-primary);
    color: #fff;
  }
  .telegram-key[data-style="success"] {
    background: var(--tg-success);
    color: #fff;
  }
  .telegram-key[data-style="danger"] {
    background: var(--tg-danger);
    color: #fff;
  }
  .telegram-key[aria-pressed="true"] {
    border-color: var(--admin-accent);
    box-shadow: 0 0 0 1px var(--tg-bg);
  }
  .telegram-key:focus-visible {
    outline: 2px solid var(--admin-accent);
    outline-offset: 2px;
  }
  .telegram-key > :global(svg) {
    flex: 0 0 auto;
    opacity: 0.6;
  }
  .updating {
    opacity: 0.6;
  }
  .preview-message {
    margin: 0;
    padding: 16px;
    background: var(--tg-message);
    border-radius: 10px;
    color: var(--tg-muted);
    font-size: 12px;
    line-height: 1.5;
  }
  footer {
    display: flex;
    align-items: flex-start;
    gap: 6px;
    padding: 10px 14px;
    background: var(--tg-head);
    color: var(--tg-muted);
    font-size: 11px;
    line-height: 1.5;
  }
  footer > :global(svg) {
    margin-top: 2px;
    flex: 0 0 auto;
  }
</style>
