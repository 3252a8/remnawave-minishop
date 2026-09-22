<script lang="ts">
  import { AdminButton, AdminField } from "$components/patterns/admin/index.js";
  import { FileInput, Input } from "$components/ui/index.js";
  import { Globe2, Upload } from "$components/ui/icons.js";

  type Labels = {
    archive: string;
    repository: string;
    drop: string;
    dropHint: string;
    chooseFile: string;
    oneFile: string;
    repositoryUrl: string;
    repositoryHint: string;
    revision: string;
    subdir?: string;
    find: string;
  };

  let {
    method = $bindable("archive"),
    repository = $bindable(""),
    revision = $bindable(""),
    subdir = $bindable(""),
    labels,
    busy = false,
    showSubdir = false,
    onarchive,
    onrepository,
    onerror,
  }: {
    method?: "archive" | "repository";
    repository?: string;
    revision?: string;
    subdir?: string;
    labels: Labels;
    busy?: boolean;
    showSubdir?: boolean;
    onarchive: (file: File) => void | Promise<void>;
    onrepository: () => void | Promise<void>;
    onerror: (message: string) => void;
  } = $props();

  let fileInput = $state<HTMLInputElement | null>(null);
  let dragging = $state(false);

  function accept(files: FileList | null | undefined): void {
    if (!files?.length || busy) return;
    if (files.length !== 1) {
      onerror(labels.oneFile);
      return;
    }
    void onarchive(files[0]);
  }
</script>

<div class="method-buttons">
  <AdminButton
    disabled={busy}
    variant={method === "archive" ? "primary" : "default"}
    aria-pressed={method === "archive"}
    onclick={() => (method = "archive")}><Upload size={15} />{labels.archive}</AdminButton
  >
  <AdminButton
    disabled={busy}
    variant={method === "repository" ? "primary" : "default"}
    aria-pressed={method === "repository"}
    onclick={() => (method = "repository")}><Globe2 size={15} />{labels.repository}</AdminButton
  >
</div>

{#if method === "archive"}
  <section
    class="import-drop"
    class:dragging
    aria-label={labels.drop}
    ondragover={(event) => {
      event.preventDefault();
      dragging = true;
    }}
    ondragleave={() => (dragging = false)}
    ondrop={(event) => {
      event.preventDefault();
      dragging = false;
      accept(event.dataTransfer?.files);
    }}
  >
    <span class="upload-symbol"><Upload size={26} /></span>
    <strong>{labels.drop}</strong>
    <p>{labels.dropHint}</p>
    <FileInput
      bind:element={fileInput}
      class="admin-import-file"
      accept=".zip,application/zip,application/x-zip-compressed"
      disabled={busy}
      onchange={(event) => {
        accept(event.currentTarget.files);
        event.currentTarget.value = "";
      }}
    />
    <AdminButton disabled={busy} onclick={() => fileInput?.click()}>{labels.chooseFile}</AdminButton
    >
  </section>
{:else}
  <AdminField label={labels.repositoryUrl} hint={labels.repositoryHint}>
    <Input
      type="url"
      class="input"
      bind:value={repository}
      placeholder="https://github.com/author/repository"
      disabled={busy}
    />
  </AdminField>
  <AdminField label={labels.revision}>
    <Input class="input" bind:value={revision} placeholder="v1.0.0" disabled={busy} />
  </AdminField>
  {#if showSubdir && labels.subdir}
    <AdminField label={labels.subdir}>
      <Input class="input" bind:value={subdir} placeholder="themes" disabled={busy} />
    </AdminField>
  {/if}
  <AdminButton variant="primary" disabled={busy || !repository.trim()} onclick={onrepository}
    ><Globe2 size={15} />{labels.find}</AdminButton
  >
{/if}

<style>
  :global(.admin-import-file) {
    display: none;
  }
  .method-buttons {
    display: flex;
    gap: 8px;
  }
  .method-buttons :global(button) {
    flex: 1;
  }
  .import-drop {
    display: grid;
    justify-items: center;
    gap: 13px;
    padding: 32px 16px;
    border: 1px dashed var(--admin-border-strong);
    border-radius: 12px;
    background: var(--admin-surface-2);
    text-align: center;
  }
  .dragging {
    border-color: var(--accent);
  }
  .upload-symbol {
    display: grid;
    place-items: center;
    width: 54px;
    height: 54px;
    border-radius: 15px;
    background: var(--admin-surface);
    color: var(--accent);
    border: 1px solid var(--admin-border);
  }
  p {
    margin: 0;
    font-size: 12px;
    line-height: 1.6;
    color: var(--admin-muted);
  }
  @media (max-width: 480px) {
    .import-drop {
      padding: 22px 12px;
    }
    .method-buttons :global(button) {
      padding-inline: 10px;
    }
  }
</style>
