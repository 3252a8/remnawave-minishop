<script lang="ts">
  import { onMount, tick } from "svelte";
  import { AdminButton, AdminField } from "$components/patterns/admin/index.js";
  import { Textarea } from "$components/ui/index.js";
  import { FileText, Pencil, RefreshCw } from "$components/ui/icons.js";
  import { getAdminApi } from "$lib/admin/context";
  import { adminErrorMessage } from "$lib/admin/errors";
  import { buildAdminUserNotePath } from "$lib/webapp/adminUserPanelPaths";
  import { unwrap } from "$lib/webapp/publicApi";
  import type { TranslateFn } from "./userDetailTypes";

  let { at, userId }: { at: TranslateFn; userId: string | number } = $props();
  const api = getAdminApi();
  const reads = new AbortController();
  let section: HTMLElement | undefined;
  let editing = $state(false);
  let saved = $state<string | null>(null);
  let draft = $state("");
  let busy = $state(false);
  let conflict = $state<"none" | "stale" | "review">("none");
  let error = $state("");
  let unavailable = $state("");
  let savedMessage = $state(false);
  const dirty = $derived(saved !== null && draft !== saved);

  async function readNote() {
    const response = await api(buildAdminUserNotePath(userId), { signal: reads.signal });
    if (!response?.ok) throw response;
    saved = unwrap(response).note;
    if (conflict === "none") draft = saved;
    else conflict = "review";
  }

  async function load() {
    if (busy || (dirty && conflict === "none")) return;
    busy = true;
    error = "";
    unavailable = "";
    savedMessage = false;
    try {
      await readNote();
    } catch (cause) {
      const message = adminErrorMessage(
        cause,
        at,
        at("user_note_load_failed", {}, "Could not load the note.")
      );
      if (
        conflict === "none" &&
        cause &&
        typeof cause === "object" &&
        "error" in cause &&
        (cause.error === "no_panel_user" || cause.error === "panel_user_not_found")
      ) {
        saved = null;
        draft = "";
        unavailable = message;
      } else {
        error = message;
      }
    } finally {
      busy = false;
    }
  }

  async function startEditing() {
    if (busy || saved === null) return;
    draft = saved ?? "";
    savedMessage = false;
    editing = true;
    await tick();
    section?.querySelector("textarea")?.focus({ preventScroll: true });
  }

  async function finishEditing() {
    draft = saved ?? "";
    conflict = "none";
    error = "";
    editing = false;
    await tick();
    section?.querySelector<HTMLButtonElement>("[data-edit-note]")?.focus({ preventScroll: true });
  }

  async function save() {
    if (busy || !dirty || saved === null || conflict === "stale") return;
    busy = true;
    error = "";
    savedMessage = false;
    try {
      const response = await api(buildAdminUserNotePath(userId), {
        method: "PUT",
        body: JSON.stringify({ note: draft, previous_note: saved }),
      });
      if (!response?.ok) {
        if (response && "error" in response && response.error === "note_conflict") {
          conflict = "stale";
          await readNote();
          return;
        }
        throw response;
      }
      saved = unwrap(response).note;
      savedMessage = true;
      busy = false;
      await finishEditing();
    } catch (cause) {
      error = adminErrorMessage(
        cause,
        at,
        at("user_note_save_failed", {}, "Could not save the note.")
      );
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    void load();
    return () => reads.abort();
  });
</script>

<section
  class="profile-note"
  bind:this={section}
  aria-label={at("user_note_label", {}, "Note in Remnawave")}
>
  <div class="note-header">
    <h3><FileText size={15} />{at("user_note_label", {}, "Note in Remnawave")}</h3>
    {#if !editing && saved !== null}
      <div class="note-tools">
        <AdminButton
          size="icon"
          variant="ghost"
          aria-label={at("user_note_refresh", {}, "Refresh note")}
          title={at("user_note_refresh", {}, "Refresh note")}
          disabled={busy}
          onclick={load}><RefreshCw size={14} /></AdminButton
        >
        <AdminButton
          data-edit-note
          size="sm"
          variant="ghost"
          disabled={busy}
          onclick={startEditing}
        >
          <Pencil size={14} />{saved
            ? at("btn_edit", {}, "Edit")
            : at("user_note_add", {}, "Add note")}
        </AdminButton>
      </div>
    {:else if !editing && (error || unavailable)}
      <AdminButton size="sm" variant="ghost" onclick={load} disabled={busy}>
        <RefreshCw size={14} />{at("refresh", {}, "Refresh")}
      </AdminButton>
    {/if}
  </div>
  {#if editing}
    <AdminField hint={at("user_note_hint", {}, "Changes appear in this user's Remnawave card.")}>
      <Textarea
        ariaLabel={at("user_note_label", {}, "Note in Remnawave")}
        bind:value={draft}
        rows={3}
        disabled={busy}
      />
    </AdminField>
    {#if conflict !== "none"}
      <p role="alert"
        >{at(
          "user_note_conflict",
          {},
          "The panel note changed while you were editing. Compare the latest version with your draft before saving."
        )}</p
      >
      {#if conflict === "review"}
        <AdminField label={at("user_note_latest", {}, "Latest panel version")}>
          <Textarea value={saved ?? ""} rows={3} readonly />
        </AdminField>
      {/if}
    {/if}
    <div class="note-actions">
      <AdminButton
        variant="primary"
        size="sm"
        disabled={busy || !dirty || conflict === "stale"}
        onclick={save}
      >
        {conflict === "review"
          ? at("user_note_save_draft", {}, "Save my version")
          : at("save", {}, "Save")}
      </AdminButton>
      {#if conflict === "stale"}
        <AdminButton size="sm" disabled={busy} onclick={load}
          ><RefreshCw size={14} />{at("refresh", {}, "Refresh")}</AdminButton
        >
      {/if}
      <AdminButton size="sm" variant="ghost" disabled={busy} onclick={finishEditing}>
        {conflict === "review"
          ? at("user_note_use_panel", {}, "Use panel version")
          : at("btn_cancel", {}, "Cancel")}
      </AdminButton>
    </div>
  {:else if saved}
    <p class="note-text">{saved}</p>
  {:else if unavailable}
    <span class="note-status">{unavailable}</span>
  {:else if busy}
    <span class="note-status" role="status">{at("loading", {}, "Loading…")}</span>
  {/if}
  {#if error}<p class="admin-field-error" role="alert">{error}</p>{/if}
  {#if savedMessage}<span class="note-status" role="status"
      >{at("user_note_saved", {}, "Note saved in Remnawave.")}</span
    >{/if}
</section>

<style>
  .profile-note {
    display: grid;
    gap: 8px;
    min-width: 0;
  }
  .note-header,
  .note-header h3,
  .note-tools {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .note-header {
    justify-content: space-between;
    flex-wrap: wrap;
  }
  .note-tools {
    gap: 2px;
  }
  .note-header h3 {
    margin: 0;
    color: var(--admin-muted);
    font-size: 13px;
    font-weight: 600;
  }
  .note-text {
    margin: 0;
    color: var(--admin-text);
    font-size: 14px;
    line-height: 1.5;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    max-height: 10em;
    overflow: auto;
  }
  .note-status {
    color: var(--admin-muted);
    font-size: 13px;
  }
  .note-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
</style>
