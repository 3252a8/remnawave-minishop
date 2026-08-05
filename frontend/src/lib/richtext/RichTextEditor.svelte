<script lang="ts">
  import { Editor } from "@tiptap/core";
  import { onMount, tick } from "svelte";

  import { ScrollArea } from "$components/ui/index.js";

  import {
    applyLink,
    composerExtensions,
    insertLink,
    insertShortcode,
    insertText,
    toggleBlockquote,
    toggleCodeBlock,
    toggleMark,
    type MessageShortcodeInfo,
    type ToolbarMark,
  } from "./editorSchema.js";
  import { type Doc, docToTelegramHtml, telegramHtmlToDoc } from "./telegramHtml.js";
  import type { RichTextLabels, RichTextQuickInsert } from "./types.js";

  // Tiptap's JSON is structurally the subset we serialize; narrow it once here.
  const serialize = (editorInstance: Editor): string =>
    docToTelegramHtml(editorInstance.getJSON() as unknown as Doc);

  let {
    value,
    onInput,
    labels,
    placeholder = "",
    shortcodes = [],
    onRequestShortcodes,
    quickInserts = [],
    onRequestQuickInserts,
    showSource = false,
    autolink = false,
    disabled = false,
    minHeight = "140px",
    onSubmit,
    onTyping,
  }: {
    value: string;
    onInput: (value: string) => void;
    labels: RichTextLabels;
    placeholder?: string;
    /** Personalization tokens; an empty list hides the picker entirely. */
    shortcodes?: MessageShortcodeInfo[];
    onRequestShortcodes?: () => void;
    /** Host-defined one-tap inserts (a link to the customer's subscription…). */
    quickInserts?: RichTextQuickInsert[];
    onRequestQuickInserts?: () => void;
    /** The raw-markup toggle: useful to an admin, noise to a customer. */
    showSource?: boolean;
    autolink?: boolean;
    disabled?: boolean;
    minHeight?: string;
    /** Ctrl/Cmd+Enter, when the host has something to submit to. */
    onSubmit?: () => void;
    onTyping?: (typing: boolean) => void;
  } = $props();

  let host = $state<HTMLDivElement | null>(null);
  let editor = $state<Editor | null>(null);
  let sourceMode = $state(false);
  let sourceText = $state("");
  let sourceArea = $state<HTMLTextAreaElement | null>(null);
  let shortcodesOpen = $state(false);
  let insertsOpen = $state(false);
  let linkOpen = $state(false);
  let linkHref = $state("");
  let selectionTick = $state(0);
  let editorMounted = false;
  let lastEditorSyncValue = "";

  const hasShortcodes = $derived(Boolean(onRequestShortcodes));
  const hasQuickInserts = $derived(quickInserts.length > 0 || Boolean(onRequestQuickInserts));

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
      extensions: composerExtensions(placeholder, { autolink }),
      content: telegramHtmlToDoc(value),
      editable: !disabled,
      onUpdate: ({ editor: current }) => {
        const next = serialize(current);
        lastEditorSyncValue = next;
        onInput(next);
        onTyping?.(Boolean(current.getText().trim()));
      },
      onSelectionUpdate: () => {
        selectionTick += 1;
      },
      onTransaction: () => {
        selectionTick += 1;
      },
    });
    editor = instance;
    // Bound on the editable element rather than on its wrapper: the wrapper is
    // presentational, and a keydown handler there would need an interactive
    // role it must not have.
    instance.view.dom.addEventListener("keydown", handleKeydown);
    return () => {
      editorMounted = false;
      if (editor === instance) editor = null;
      instance.view.dom.removeEventListener("keydown", handleKeydown);
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

  // Tiptap emits an `update` from `setEditable` unless told not to, and that
  // update reports the untouched document as freshly edited — which writes the
  // value back to the host, re-enters this flush, and loops.
  $effect(() => {
    const current = editor;
    if (!current || current.isDestroyed) return;
    const editable = !disabled;
    if (current.isEditable === editable) return;
    current.setEditable(editable, false);
  });

  $effect(() => {
    if (shortcodesOpen) onRequestShortcodes?.();
  });

  $effect(() => {
    if (insertsOpen) onRequestQuickInserts?.();
  });

  $effect(() => {
    if (!shortcodesOpen && !insertsOpen) return;
    const close = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest(".rt-menu")) return;
      shortcodesOpen = false;
      insertsOpen = false;
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
    insertsOpen = false;
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
    lastEditorSyncValue = sourceText;
    onInput(sourceText);
    onTyping?.(Boolean(sourceText.trim()));
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (!onSubmit) return;
    if (!(event.ctrlKey || event.metaKey) || event.key !== "Enter") return;
    event.preventDefault();
    onSubmit();
  }

  /** Insert `token` at the caret while the raw-markup textarea has focus. */
  async function insertIntoSource(token: string): Promise<void> {
    const area = sourceArea;
    if (!area) {
      sourceText = `${sourceText}${token}`;
      lastEditorSyncValue = sourceText;
      onInput(sourceText);
      return;
    }
    const start = area.selectionStart ?? sourceText.length;
    const end = area.selectionEnd ?? sourceText.length;
    sourceText = sourceText.slice(0, start) + token + sourceText.slice(end);
    lastEditorSyncValue = sourceText;
    onInput(sourceText);
    await tick();
    area.focus();
    const caret = start + token.length;
    area.setSelectionRange(caret, caret);
  }

  function pickShortcode(name: string): void {
    shortcodesOpen = false;
    if (sourceMode) {
      void insertIntoSource(`{${name}}`);
      return;
    }
    withEditor((instance) => insertShortcode(instance, name));
  }

  function pickQuickInsert(item: RichTextQuickInsert): void {
    if (item.disabled) return;
    insertsOpen = false;
    if (item.content.kind === "link") {
      const { href, text } = item.content;
      if (sourceMode) {
        void insertIntoSource(`<a href="${href}">${text}</a> `);
        return;
      }
      withEditor((instance) => insertLink(instance, href, text));
      return;
    }
    if (item.content.kind === "shortcode") {
      pickShortcode(item.content.name);
      return;
    }
    const { text } = item.content;
    if (sourceMode) {
      void insertIntoSource(text);
      return;
    }
    withEditor((instance) => insertText(instance, text));
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
    lastEditorSyncValue = sourceText;
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
    { mark: "bold", label: labels.bold, icon: "B" },
    { mark: "italic", label: labels.italic, icon: "I" },
    { mark: "underline", label: labels.underline, icon: "U" },
    { mark: "strike", label: labels.strike, icon: "S" },
    { mark: "code", label: labels.code, icon: "</>" },
  ]);
</script>

<div class="rt-editor">
  <div class="rt-toolbar" role="toolbar" aria-label={labels.toolbar}>
    {#each markButtons as button (button.mark)}
      <button
        type="button"
        class="rt-tool"
        class:is-active={!sourceMode && active[button.mark]}
        title={button.label}
        aria-label={button.label}
        aria-pressed={!sourceMode && active[button.mark]}
        data-rt-format={button.mark}
        {disabled}
        onclick={() => handleMarkButton(button.mark)}
      >
        {button.icon}
      </button>
    {/each}
    <button
      type="button"
      class="rt-tool"
      class:is-active={!sourceMode && active.codeBlock}
      title={labels.pre}
      aria-label={labels.pre}
      data-rt-format="pre"
      {disabled}
      onclick={handlePreButton}
    >
      ⌗
    </button>
    <button
      type="button"
      class="rt-tool"
      class:is-active={!sourceMode && active.blockquote}
      title={labels.quote}
      aria-label={labels.quote}
      data-rt-format="blockquote"
      {disabled}
      onclick={handleQuoteButton}
    >
      ❝
    </button>
    <button
      type="button"
      class="rt-tool"
      class:is-active={!sourceMode && active.link}
      title={labels.link}
      aria-label={labels.link}
      data-rt-format="link"
      {disabled}
      onclick={handleLinkButton}
    >
      🔗
    </button>

    {#if hasQuickInserts}
      <div class="rt-menu">
        <button
          type="button"
          class="rt-tool rt-tool-wide"
          aria-haspopup="listbox"
          aria-expanded={insertsOpen}
          data-rt-inserts-toggle
          {disabled}
          onclick={() => (insertsOpen = !insertsOpen)}
        >
          {labels.insert}
        </button>
        {#if insertsOpen}
          <div class="rt-menu-list" role="listbox">
            <ScrollArea class="rt-menu-scroll" maxHeight="min(320px, 48vh)" type="auto">
              {#if quickInserts.length}
                <div class="rt-menu-items">
                  {#each quickInserts as item (item.id)}
                    <button
                      type="button"
                      class="rt-menu-item"
                      role="option"
                      aria-selected="false"
                      aria-disabled={item.disabled}
                      class:is-disabled={item.disabled}
                      onclick={() => pickQuickInsert(item)}
                    >
                      <span class="rt-menu-item-title">
                        {item.label}
                        {#if item.badge}<em class="rt-menu-badge">{item.badge}</em>{/if}
                      </span>
                      {#if item.description}
                        <span class="rt-menu-item-desc">{item.description}</span>
                      {/if}
                    </button>
                  {/each}
                </div>
              {:else}
                <div class="rt-menu-empty">{labels.insertEmpty}</div>
              {/if}
            </ScrollArea>
          </div>
        {/if}
      </div>
    {/if}

    {#if hasShortcodes}
      <div class="rt-menu">
        <button
          type="button"
          class="rt-tool rt-tool-wide"
          aria-haspopup="listbox"
          aria-expanded={shortcodesOpen}
          data-rt-shortcodes-toggle
          {disabled}
          onclick={() => (shortcodesOpen = !shortcodesOpen)}
        >
          {labels.shortcodes}
        </button>
        {#if shortcodesOpen}
          <div class="rt-menu-list" role="listbox">
            <ScrollArea class="rt-menu-scroll" maxHeight="min(320px, 48vh)" type="auto">
              {#if shortcodes.length}
                <div class="rt-menu-items">
                  {#each shortcodes as item (item.name)}
                    <button
                      type="button"
                      class="rt-menu-item"
                      role="option"
                      aria-selected="false"
                      onclick={() => pickShortcode(item.name)}
                    >
                      <span class="rt-menu-token">{`{${item.name}}`}</span>
                      <span class="rt-menu-item-desc">{item.description || item.name}</span>
                      {#if item.cost === "panel"}
                        <span class="rt-menu-cost">{labels.shortcodePanelBadge}</span>
                      {/if}
                    </button>
                  {/each}
                </div>
              {:else}
                <div class="rt-menu-empty">{labels.shortcodesLoading}</div>
              {/if}
            </ScrollArea>
          </div>
        {/if}
      </div>
    {/if}

    {#if showSource}
      <button
        type="button"
        class="rt-tool rt-tool-wide"
        class:is-active={sourceMode}
        data-rt-source-toggle
        {disabled}
        onclick={() => void (sourceMode ? exitSourceMode() : enterSourceMode())}
      >
        {sourceMode ? labels.sourceOff : labels.sourceOn}
      </button>
    {/if}
  </div>

  {#if linkOpen}
    <div class="rt-link-row">
      <input
        class="input rt-link-input"
        type="url"
        placeholder={labels.linkPlaceholder}
        bind:value={linkHref}
        onkeydown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            confirmLink();
          }
        }}
      />
      <button type="button" class="rt-tool" onclick={confirmLink}>
        {labels.linkApply}
      </button>
    </div>
  {/if}

  {#if sourceMode}
    <textarea
      bind:this={sourceArea}
      class="admin-textarea rt-source"
      rows="6"
      {disabled}
      value={sourceText}
      oninput={onSourceInput}
      onkeydown={handleKeydown}></textarea>
  {/if}
  <div
    bind:this={host}
    class="rt-surface"
    class:is-hidden={sourceMode}
    class:is-disabled={disabled}
    style={`--rt-min-height: ${minHeight}`}
    aria-hidden={sourceMode}
  ></div>
</div>

<style>
  .rt-editor {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .rt-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    align-items: center;
  }

  .rt-tool {
    min-width: 30px;
    height: 30px;
    padding: 0 8px;
    border: 1px solid var(--rt-border, var(--admin-border, #2a2f3a));
    border-radius: 8px;
    background: var(--rt-surface, var(--admin-surface-2, #161a22));
    color: var(--rt-text, var(--admin-text, #e6e9ef));
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    line-height: 1;
  }

  .rt-tool:hover:not(:disabled) {
    border-color: var(--rt-accent, var(--accent));
  }

  .rt-tool:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .rt-tool.is-active {
    border-color: var(--rt-accent, var(--accent));
    color: var(--rt-accent, var(--accent));
  }

  .rt-menu {
    position: relative;
    display: inline-flex;
  }

  .rt-menu-list {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    z-index: 120;
    width: min(440px, calc(100vw - 32px));
    min-width: min(300px, calc(100vw - 32px));
    padding: 6px;
    border: 1px solid var(--rt-border, var(--admin-border, #2a2f3a));
    border-radius: 10px;
    background: var(--rt-menu-bg, var(--admin-surface, #0e1116));
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.4);
  }

  .rt-menu-items {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding-right: 4px;
  }

  .rt-menu-item {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    width: 100%;
    padding: 6px 8px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: var(--rt-text, var(--admin-text, #e6e9ef));
    text-align: left;
    cursor: pointer;
  }

  .rt-menu-item:hover {
    background: var(--rt-surface, var(--admin-surface-2, #161a22));
  }

  .rt-menu-item.is-disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .rt-menu-item-title {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
  }

  .rt-menu-badge {
    font-size: 10px;
    font-style: normal;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--rt-accent, var(--accent));
  }

  .rt-menu-token {
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 12px;
    color: var(--rt-accent, var(--accent));
  }

  .rt-menu-item-desc {
    font-size: 12px;
    color: var(--rt-text-muted, var(--admin-text-muted, #9aa3b2));
  }

  .rt-menu-cost {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #f4b740;
  }

  .rt-menu-empty {
    padding: 8px;
    font-size: 12px;
    color: var(--rt-text-muted, var(--admin-text-muted, #9aa3b2));
  }

  .rt-link-row {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  .rt-link-input {
    flex: 1;
  }

  .rt-surface {
    min-height: var(--rt-min-height, 140px);
    padding: 10px 12px;
    border: 1px solid var(--rt-border, var(--admin-border, #2a2f3a));
    border-radius: 10px;
    background: var(--rt-surface-bg, var(--admin-surface-2, #10141b));
  }

  .rt-surface.is-hidden {
    display: none;
  }

  .rt-surface.is-disabled {
    opacity: 0.6;
  }

  .rt-surface :global(.ProseMirror) {
    min-height: calc(var(--rt-min-height, 140px) - 20px);
    outline: none;
    font-size: 14px;
    line-height: 1.55;
    white-space: pre-wrap;
  }

  .rt-surface :global(.ProseMirror p) {
    margin: 0 0 8px 0;
  }

  .rt-surface :global(.ProseMirror p.is-editor-empty:first-child::before) {
    content: attr(data-placeholder);
    float: left;
    height: 0;
    pointer-events: none;
    color: var(--rt-text-dim, var(--admin-text-dim, #5d6573));
  }

  .rt-surface :global(.ProseMirror pre) {
    padding: 8px 10px;
    border-radius: 8px;
    background: var(--rt-menu-bg, var(--admin-surface, #0b0e14));
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 13px;
  }

  .rt-surface :global(.ProseMirror blockquote) {
    margin: 0 0 8px 0;
    padding-left: 10px;
    border-left: 3px solid var(--rt-border, var(--admin-border, #2a2f3a));
    color: var(--rt-text-muted, var(--admin-text-muted, #9aa3b2));
  }

  .rt-surface :global(.rt-chip) {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 6px;
    background: color-mix(in srgb, var(--rt-accent, var(--accent)) 18%, transparent);
    color: var(--rt-accent, var(--accent));
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 12px;
    white-space: nowrap;
  }

  .rt-source {
    width: 100%;
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 13px;
  }
</style>
