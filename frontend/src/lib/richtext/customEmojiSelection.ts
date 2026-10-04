import type { Editor } from "@tiptap/core";
import type { Mark } from "@tiptap/pm/model";
import type { SelectionBookmark, Transaction } from "@tiptap/pm/state";

import type { CustomEmoji } from "./customEmoji.js";
import { insertCustomEmoji } from "./editorSchema.js";

/** A bookmark survives focus changes and maps through edits while the picker loads. */
export class CustomEmojiSelection {
  private request = 0;
  private pending: { editor: Editor; bookmark: SelectionBookmark; marks: readonly Mark[] } | null =
    null;

  cancel(): void {
    this.request += 1;
    this.pending = null;
  }

  map(editor: Editor, transaction: Transaction): void {
    if (this.pending?.editor === editor && transaction.docChanged)
      this.pending.bookmark = this.pending.bookmark.map(transaction.mapping);
  }

  async select(
    editor: Editor,
    picker: () => Promise<CustomEmoji | null>,
    canInsert: () => boolean
  ): Promise<void> {
    const request = ++this.request;
    this.pending = {
      editor,
      bookmark: editor.state.selection.getBookmark(),
      marks: editor.state.storedMarks || editor.state.selection.$from.marks(),
    };
    try {
      const emoji = await picker();
      const saved = this.pending;
      if (request !== this.request || !saved || !emoji || editor.isDestroyed || !canInsert())
        return;
      editor.commands.command(({ tr }) => {
        tr.setSelection(saved.bookmark.resolve(tr.doc));
        tr.setStoredMarks(saved.marks);
        return true;
      });
      insertCustomEmoji(editor, emoji);
    } finally {
      if (request === this.request) this.pending = null;
    }
  }
}
