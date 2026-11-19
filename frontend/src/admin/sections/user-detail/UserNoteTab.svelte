<script lang="ts">
  import { onDestroy, untrack } from "svelte";
  import { AdminButton, AdminField } from "$components/patterns/admin/index.js";
  import { Textarea } from "$components/ui/index.js";
  import { RefreshCw } from "$components/ui/icons.js";
  import { getAdminApi } from "$lib/admin/context";
  import { adminErrorMessage } from "$lib/admin/errors";
  import { buildAdminUserNotePath } from "$lib/webapp/adminUserPanelPaths";
  import { unwrap } from "$lib/webapp/publicApi";
  import type { TranslateFn } from "./userDetailTypes";

  let { at, userId, active }: { at: TranslateFn; userId: string | number; active: boolean } =
    $props();
  const api = getAdminApi();
  const reads = new AbortController();
  let saved = $state<string | null>(null);
  let draft = $state("");
  let busy = $state(false);
  let conflict = $state<"none" | "stale" | "review">("none");
  let error = $state("");
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
    savedMessage = false;
    try {
      await readNote();
    } catch (cause) {
      error = adminErrorMessage(
        cause,
        at,
        at("user_note_load_failed", {}, "Could not load the note.")
      );
    } finally {
      busy = false;
    }
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
      draft = saved;
      savedMessage = true;
      conflict = "none";
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

  function usePanelNote() {
    draft = saved ?? "";
    conflict = "none";
    error = "";
    savedMessage = false;
  }

  $effect(() => {
    if (active)
      untrack(() => {
        if (!dirty && conflict === "none") void load();
      });
  });
  onDestroy(() => reads.abort());
</script>

<section class="admin-user-action-sheet" aria-label={at("user_tab_note", {}, "Note")}>
  <div class="admin-user-action-sheet-body admin-user-override-stack">
    {#if saved !== null}
      <AdminField
        label={at("user_note_label", {}, "Note in Remnawave")}
        hint={at("user_note_hint", {}, "Changes appear in this user's Remnawave card.")}
      >
        <Textarea
          bind:value={draft}
          rows={4}
          disabled={busy}
          oninput={() => (savedMessage = false)}
        />
      </AdminField>
    {/if}
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
    {#if error}<p class="admin-field-error" role="alert">{error}</p>{/if}
    {#if busy && saved === null}<span role="status">{at("loading", {}, "Loading…")}</span>{/if}
    {#if savedMessage}<span role="status"
        >{at("user_note_saved", {}, "Note saved in Remnawave.")}</span
      >{/if}
    <div class="note-actions">
      {#if saved !== null}
        <AdminButton
          variant="primary"
          disabled={busy || !dirty || conflict === "stale"}
          onclick={save}
        >
          {conflict === "review"
            ? at("user_note_save_draft", {}, "Save my version")
            : at("save", {}, "Save")}
        </AdminButton>
      {/if}
      {#if conflict === "review"}
        <AdminButton disabled={busy} onclick={usePanelNote}
          >{at("user_note_use_panel", {}, "Use panel version")}</AdminButton
        >
      {:else if dirty && conflict === "none"}
        <AdminButton disabled={busy} onclick={usePanelNote}
          >{at("btn_cancel", {}, "Cancel")}</AdminButton
        >
      {:else}
        <AdminButton disabled={busy} onclick={load}
          ><RefreshCw size={14} />{at("refresh", {}, "Refresh")}</AdminButton
        >
      {/if}
    </div>
  </div>
</section>

<style>
  .note-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
</style>
