<script lang="ts">
  import { Editor } from "@tiptap/core";
  import { onMount, tick } from "svelte";

  import { ScrollArea } from "$components/ui/index.js";

  import {
    applyLink,
    broadcastExtensions,
    insertShortcode,
    toggleBlockquote,
    toggleCodeBlock,
    toggleMark,
    type ToolbarMark,
  } from "../broadcastEditor";
  import type { BroadcastShortcodeInfo } from "../stores/broadcastStore.svelte";
  import { type Doc, docToTelegramHtml, telegramHtmlToDoc } from "../telegramHtml";

  // Tiptap's JSON is structurally the subset we serialize; narrow it once here.
  const serialize = (editorInstance: Editor): string =>
    docToTelegramHtml(editorInstance.getJSON() as unknown as Doc);

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
    shortcodes: BroadcastShortcodeInfo[];
    onRequestShortcodes: () => void;
    at: TranslateFn;
    placeholder?: string;
  } = $props();

  let host = $state<HTMLDivElement | null>(null);
  let editor = $state<Editor | null>(null);
  let sourceMode = $state(false);
  let sourceText = $state("");
  let sourceArea = $state<HTMLTextAreaElement | null>(null);
  let shortcodesOpen = $state(false);
  let linkOpen = $state(false);
  let linkHref = $state("");
  let selectionTick = $state(0);
  let editorMounted = false;
  let lastEditorSyncValue = "";

  const active = $derived.by(() => {
    selectionTick;
    if (!editor) {
      return {
        bold: false,
        italic: false,
        underline: false,
        strike: false,
        code: false,
        codeBlock: false,
        blockquote: false,
        link: false,
      };
    }
    return {
      bold: editor.isActive("bold"),
      italic: editor.isActive("italic"),
      underline: editor.isActive("underline"),
      strike: editor.isActive("strike"),
      code: editor.isActive("code"),
      codeBlock: editor.isActive("codeBlock"),
      blockquote: editor.isActive("blockquote"),
      link: editor.isActive("link"),
    };
  });

  onMount(() => {
    if (!host) return;
    editorMounted = true;
    const instance = new Editor({
      element: host,
      extensions: broadcastExtensions(placeholder),
      content: telegramHtmlToDoc(value),
      onUpdate: ({ editor: current }) => {
        onInput(serialize(current));
      },
      onSelectionUpdate: () => {
        selectionTick += 1;
      },
      onTransaction: () => {
        selectionTick += 1;
      },
    });
    editor = instance;
    return () => {
      editorMounted = false;
      if (editor === instance) editor = null;
      instance.destroy();
    };
  });

  // Keep the editor in sync when the value changes from outside (e.g. after a
  // successful send resets the draft). Skip in source mode and avoid feedback
  // loops by comparing the serialized form.
  $effect(() => {
    const current = editor;
    if (!current || current.isDestroyed || sourceMode) return;
    if (serialize(current) === value) {
      lastEditorSyncValue = value;
      return;
    }
    if (lastEditorSyncValue === value) return;
    lastEditorSyncValue = value;
    current.commands.setContent(telegramHtmlToDoc(value), { emitUpdate: false });
  });

  $effect(() => {
    if (shortcodesOpen) onRequestShortcodes();
  });

  $effect(() => {
    if (!shortcodesOpen) return;
    const close = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest(".broadcast-shortcode-menu")) return;
      shortcodesOpen = false;
    };
    window.addEventListener("pointerdown", close);
    return () => window.removeEventListener("pointerdown", close);
  });

  function withEditor(action: (instance: Editor) => void): void {
    if (editor && !editor.isDestroyed) action(editor);
  }

  async function enterSourceMode(): Promise<void> {
    sourceText = editor ? serialize(editor) : value;
    sourceMode = true;
    await tick();
    sourceArea?.focus();
  }

  async function exitSourceMode(): Promise<void> {
    shortcodesOpen = false;
    linkOpen = false;
    const current = editor;
    if (current && !current.isDestroyed) {
      current.commands.setContent(telegramHtmlToDoc(sourceText), { emitUpdate: false });
      sourceText = serialize(current);
    }
    lastEditorSyncValue = sourceText;
    onInput(sourceText);
    sourceMode = false;
    await tick();
    if (!editorMounted || editor !== current || current?.isDestroyed) return;
    current?.commands.focus("end");
  }

  function onSourceInput(event: Event): void {
    sourceText = (event.currentTarget as HTMLTextAreaElement).value;
    onInput(sourceText);
  }

  function toggleShortcodes(): void {
    shortcodesOpen = !shortcodesOpen;
  }

  function pickShortcode(name: string): void {
    shortcodesOpen = false;
    if (sourceMode) {
      const area = sourceArea;
      const token = `{${name}}`;
      if (area) {
        const start = area.selectionStart ?? sourceText.length;
        const end = area.selectionEnd ?? sourceText.length;
        sourceText = sourceText.slice(0, start) + token + sourceText.slice(end);
        onInput(sourceText);
        void tick().then(() => {
          area.focus();
          const caret = start + token.length;
          area.setSelectionRange(caret, caret);
        });
      } else {
        sourceText = `${sourceText}${token}`;
        onInput(sourceText);
      }
      return;
    }
    withEditor((instance) => insertShortcode(instance, name));
  }

  async function wrapSourceSelection(
    openTag: string,
    closeTag: string,
    options: { fallbackText?: string; selectHref?: boolean } = {}
  ): Promise<void> {
    const area = sourceArea;
    const start = area?.selectionStart ?? sourceText.length;
    const end = area?.selectionEnd ?? sourceText.length;
    const selected = sourceText.slice(start, end);
    const innerText = selected || options.fallbackText || "";
    sourceText = `${sourceText.slice(0, start)}${openTag}${innerText}${closeTag}${sourceText.slice(end)}`;
    onInput(sourceText);
    await tick();
    const currentArea = sourceArea;
    if (!currentArea) return;
    currentArea.focus();
    if (options.selectHref) {
      const hrefStart = openTag.indexOf("https://");
      if (hrefStart >= 0) {
        const selectionStart = start + hrefStart;
        currentArea.setSelectionRange(selectionStart, selectionStart + "https://".length);
        return;
      }
    }
    const caret = innerText
      ? start + openTag.length + innerText.length + closeTag.length
      : start + openTag.length;
    currentArea.setSelectionRange(caret, caret);
  }

  function sourceTagForMark(mark: ToolbarMark): string {
    if (mark === "bold") return "b";
    if (mark === "italic") return "i";
    if (mark === "underline") return "u";
    if (mark === "strike") return "s";
    return "code";
  }

  function handleMarkButton(mark: ToolbarMark): void {
    if (sourceMode) {
      const tag = sourceTagForMark(mark);
      void wrapSourceSelection(`<${tag}>`, `</${tag}>`);
      return;
    }
    withEditor((instance) => toggleMark(instance, mark));
  }

  function handlePreButton(): void {
    if (sourceMode) {
      void wrapSourceSelection("<pre>", "</pre>");
      return;
    }
    withEditor(toggleCodeBlock);
  }

  function handleQuoteButton(): void {
    if (sourceMode) {
      void wrapSourceSelection("<blockquote>", "</blockquote>");
      return;
    }
    withEditor(toggleBlockquote);
  }

  function handleLinkButton(): void {
    if (sourceMode) {
      void wrapSourceSelection('<a href="https://">', "</a>", {
        fallbackText: "https://",
        selectHref: true,
      });
      return;
    }
    openLink();
  }

  function openLink(): void {
    linkHref = editor?.getAttributes("link").href || "";
    linkOpen = true;
  }

  function confirmLink(): void {
    withEditor((instance) => applyLink(instance, linkHref));
    linkOpen = false;
    linkHref = "";
  }

  const markButtons: { mark: ToolbarMark; label: string; icon: string }[] = $derived([
    { mark: "bold", label: at("broadcast_format_bold", {}, "Жирный"), icon: "B" },
    { mark: "italic", label: at("broadcast_format_italic", {}, "Курсив"), icon: "I" },
    { mark: "underline", label: at("broadcast_format_underline", {}, "Подчёркнутый"), icon: "U" },
    { mark: "strike", label: at("broadcast_format_strike", {}, "Зачёркнутый"), icon: "S" },
    { mark: "code", label: at("broadcast_format_code", {}, "Моноширинный"), icon: "</>" },
  ]);
</script>

<div class="broadcast-editor">
  <div
    class="broadcast-toolbar"
    role="toolbar"
    aria-label={at("broadcast_toolbar", {}, "Форматирование")}
  >
    {#each markButtons as button (button.mark)}
      <button
        type="button"
        class="broadcast-tool"
        class:is-active={!sourceMode && active[button.mark]}
        title={button.label}
        aria-label={button.label}
        aria-pressed={!sourceMode && active[button.mark]}
        data-broadcast-format={button.mark}
        onclick={() => handleMarkButton(button.mark)}
      >
        {button.icon}
      </button>
    {/each}
    <button
      type="button"
      class="broadcast-tool"
      class:is-active={!sourceMode && active.codeBlock}
      title={at("broadcast_format_pre", {}, "Блок кода")}
      aria-label={at("broadcast_format_pre", {}, "Блок кода")}
      data-broadcast-format="pre"
      onclick={handlePreButton}
    >
      ⌗
    </button>
    <button
      type="button"
      class="broadcast-tool"
      class:is-active={!sourceMode && active.blockquote}
      title={at("broadcast_format_quote", {}, "Цитата")}
      aria-label={at("broadcast_format_quote", {}, "Цитата")}
      data-broadcast-format="blockquote"
      onclick={handleQuoteButton}
    >
      ❝
    </button>
    <button
      type="button"
      class="broadcast-tool"
      class:is-active={!sourceMode && active.link}
      title={at("broadcast_format_link", {}, "Ссылка")}
      aria-label={at("broadcast_format_link", {}, "Ссылка")}
      data-broadcast-format="link"
      onclick={handleLinkButton}
    >
      🔗
    </button>

    <div class="broadcast-shortcode-menu">
      <button
        type="button"
        class="broadcast-tool broadcast-tool-shortcode"
        aria-haspopup="listbox"
        aria-expanded={shortcodesOpen}
        onclick={toggleShortcodes}
      >
        {at("broadcast_insert_shortcode", {}, "{ } Шорткод")}
      </button>
      {#if shortcodesOpen}
        <div class="broadcast-shortcode-list" role="listbox">
          <ScrollArea class="broadcast-shortcode-scroll" maxHeight="min(320px, 48vh)" type="auto">
            {#if shortcodes.length}
              <div class="broadcast-shortcode-items">
                {#each shortcodes as item (item.name)}
                  <button
                    type="button"
                    class="broadcast-shortcode-item"
                    role="option"
                    aria-selected="false"
                    onclick={() => pickShortcode(item.name)}
                  >
                    <span class="broadcast-shortcode-token">{`{${item.name}}`}</span>
                    <span class="broadcast-shortcode-desc">{item.description || item.name}</span>
                    {#if item.cost === "panel"}
                      <span class="broadcast-shortcode-badge"
                        >{at("broadcast_shortcode_panel_badge", {}, "панель")}</span
                      >
                    {/if}
                  </button>
                {/each}
              </div>
            {:else}
              <div class="broadcast-shortcode-empty">
                {at("broadcast_shortcodes_loading", {}, "Загрузка...")}
              </div>
            {/if}
          </ScrollArea>
        </div>
      {/if}
    </div>

    <button
      type="button"
      class="broadcast-tool broadcast-tool-source"
      class:is-active={sourceMode}
      data-broadcast-source-toggle
      onclick={() => void (sourceMode ? exitSourceMode() : enterSourceMode())}
    >
      {sourceMode
        ? at("broadcast_source_mode_off", {}, "Редактор")
        : at("broadcast_source_mode_on", {}, "HTML")}
    </button>
  </div>

  {#if linkOpen}
    <div class="broadcast-link-row">
      <input
        class="input broadcast-link-input"
        type="url"
        placeholder="https://..."
        bind:value={linkHref}
        onkeydown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            confirmLink();
          }
        }}
      />
      <button type="button" class="broadcast-tool" onclick={confirmLink}>
        {at("broadcast_link_apply", {}, "OK")}
      </button>
    </div>
  {/if}

  {#if sourceMode}
    <textarea
      bind:this={sourceArea}
      class="admin-textarea broadcast-source"
      rows="6"
      value={sourceText}
      oninput={onSourceInput}></textarea>
  {/if}
  <div
    bind:this={host}
    class="broadcast-surface"
    class:is-hidden={sourceMode}
    aria-hidden={sourceMode}
  ></div>
</div>

<style>
  .broadcast-editor {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .broadcast-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    align-items: center;
  }

  .broadcast-tool {
    min-width: 30px;
    height: 30px;
    padding: 0 8px;
    border: 1px solid var(--admin-border, #2a2f3a);
    border-radius: 8px;
    background: var(--admin-surface-2, #161a22);
    color: var(--admin-text, #e6e9ef);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    line-height: 1;
  }

  .broadcast-tool:hover {
    border-color: var(--admin-accent, #00fe7a);
  }

  .broadcast-tool.is-active {
    border-color: var(--admin-accent, #00fe7a);
    color: var(--admin-accent, #00fe7a);
  }

  .broadcast-shortcode-menu {
    position: relative;
    display: inline-flex;
  }

  .broadcast-shortcode-list {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    z-index: 120;
    width: min(440px, calc(100vw - 32px));
    min-width: min(300px, calc(100vw - 32px));
    padding: 6px;
    border: 1px solid var(--admin-border, #2a2f3a);
    border-radius: 10px;
    background: var(--admin-surface, #0e1116);
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.4);
  }

  .broadcast-shortcode-items {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding-right: 4px;
  }

  .broadcast-shortcode-item {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    width: 100%;
    padding: 6px 8px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: var(--admin-text, #e6e9ef);
    text-align: left;
    cursor: pointer;
  }

  .broadcast-shortcode-item:hover {
    background: var(--admin-surface-2, #161a22);
  }

  .broadcast-shortcode-token {
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 12px;
    color: var(--admin-accent, #00fe7a);
  }

  .broadcast-shortcode-desc {
    font-size: 12px;
    color: var(--admin-text-muted, #9aa3b2);
  }

  .broadcast-shortcode-badge {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #f4b740;
  }

  .broadcast-shortcode-empty {
    padding: 8px;
    font-size: 12px;
    color: var(--admin-text-muted, #9aa3b2);
  }

  .broadcast-link-row {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  .broadcast-link-input {
    flex: 1;
  }

  .broadcast-surface {
    min-height: 140px;
    padding: 10px 12px;
    border: 1px solid var(--admin-border, #2a2f3a);
    border-radius: 10px;
    background: var(--admin-surface-2, #10141b);
  }

  .broadcast-surface.is-hidden {
    display: none;
  }

  .broadcast-surface :global(.ProseMirror) {
    min-height: 120px;
    outline: none;
    font-size: 14px;
    line-height: 1.55;
    white-space: pre-wrap;
  }

  .broadcast-surface :global(.ProseMirror p) {
    margin: 0 0 8px 0;
  }

  .broadcast-surface :global(.ProseMirror p.is-editor-empty:first-child::before) {
    content: attr(data-placeholder);
    float: left;
    height: 0;
    pointer-events: none;
    color: var(--admin-text-dim, #5d6573);
  }

  .broadcast-surface :global(.ProseMirror pre) {
    padding: 8px 10px;
    border-radius: 8px;
    background: var(--admin-surface, #0b0e14);
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 13px;
  }

  .broadcast-surface :global(.ProseMirror blockquote) {
    margin: 0 0 8px 0;
    padding-left: 10px;
    border-left: 3px solid var(--admin-border, #2a2f3a);
    color: var(--admin-text-muted, #9aa3b2);
  }

  .broadcast-surface :global(.broadcast-chip) {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 6px;
    background: color-mix(in srgb, var(--admin-accent, #00fe7a) 18%, transparent);
    color: var(--admin-accent, #00fe7a);
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 12px;
    white-space: nowrap;
  }

  .broadcast-source {
    width: 100%;
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 13px;
  }
</style>
