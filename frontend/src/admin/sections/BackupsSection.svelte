<script>
  import { getContext, onMount } from "svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminPagination,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import { Checkbox, FileInput, RadioGroup, RadioGroupItem } from "$components/ui/index.js";
  import {
    CheckCircle2,
    Database,
    Plus,
    RefreshCw,
    Server,
    TriangleAlert,
    Upload,
  } from "$components/ui/icons.js";
  import { Tooltip } from "$components/ui/primitives.js";

  export let at = (key) => key;
  export let fmtDate = (value) => value;

  const BACKUPS_PAGE_SIZE = 10;
  const backupsStore = getContext("backupsStore");

  let selectedName = "";
  let restoreDatabase = true;
  let restoreCompose = false;
  let backupsPage = 0;
  let fileInput = null;

  $: ({
    archives,
    backupDir,
    backupsCreating,
    backupsLoading,
    backupsUploading,
    backupsRestoring,
    lastRestore,
  } = $backupsStore);
  $: totalArchives = archives?.length || 0;
  $: backupsPageCount = Math.max(1, Math.ceil(totalArchives / BACKUPS_PAGE_SIZE));
  $: if (backupsPage > backupsPageCount - 1) backupsPage = backupsPageCount - 1;
  $: backupsPageStart = backupsPage * BACKUPS_PAGE_SIZE;
  $: pagedArchives = (archives || []).slice(backupsPageStart, backupsPageStart + BACKUPS_PAGE_SIZE);
  $: if (!selectedName && archives?.length) {
    selectedName = archives[0].name;
    backupsPage = 0;
  }
  $: if (selectedName && archives?.length && !archives.some((item) => item.name === selectedName)) {
    selectedName = archives[0].name;
    backupsPage = 0;
  }
  $: selectedArchive = (archives || []).find((item) => item.name === selectedName) || null;
  $: if (selectedArchive && restoreDatabase && !selectedArchive.has_database)
    restoreDatabase = false;
  $: if (selectedArchive && restoreCompose && !selectedArchive.has_compose) restoreCompose = false;
  $: if (selectedArchive && !restoreDatabase && !restoreCompose) {
    if (selectedArchive.has_database) restoreDatabase = true;
    else if (selectedArchive.has_compose) restoreCompose = true;
  }
  $: canRestore = Boolean(
    selectedArchive && (restoreDatabase || restoreCompose) && !backupsRestoring && !backupsCreating
  );
  $: backupHeaders = [
    "",
    at("backups_col_archive", {}, "Архив"),
    at("backups_col_created", {}, "Создан"),
    at("backups_col_size", {}, "Размер"),
    at("backups_col_contents", {}, "Состав"),
    at("backups_col_warnings", {}, "Предупреждения"),
  ];

  function formatSize(sizeBytes) {
    const units = ["B", "KB", "MB", "GB"];
    let value = Number(sizeBytes || 0);
    let unit = units[0];
    for (unit of units) {
      if (value < 1024 || unit === "GB") break;
      value /= 1024;
    }
    return unit === "B" ? `${Math.round(value)} ${unit}` : `${value.toFixed(1)} ${unit}`;
  }

  function archiveDate(archive) {
    return archive?.created_at_local || archive?.created_at || archive?.modified_at || "";
  }

  function selectedComponentsText() {
    const parts = [];
    if (restoreDatabase) parts.push(at("backups_target_database", {}, "БД"));
    if (restoreCompose) parts.push(at("backups_target_compose", {}, "compose-папку"));
    return parts.join(" + ");
  }

  function selectArchive(name) {
    selectedName = name;
  }

  function focusArchivePage(name) {
    const index = (archives || []).findIndex((item) => item.name === name);
    if (index >= 0) backupsPage = Math.floor(index / BACKUPS_PAGE_SIZE);
  }

  function setBackupsPage(page) {
    backupsPage = Math.min(Math.max(0, Number(page) || 0), backupsPageCount - 1);
  }

  function warningsText(warnings) {
    return (warnings || []).filter(Boolean).join("\n");
  }

  function paginationMeta() {
    const end = Math.min(backupsPageStart + pagedArchives.length, totalArchives);
    return at(
      "backups_pagination_meta",
      { from: backupsPageStart + 1, to: end, total: totalArchives },
      `${backupsPageStart + 1}-${end} / ${totalArchives}`
    );
  }

  async function uploadSelectedFile(event) {
    const file = event?.currentTarget?.files?.[0];
    if (!file) return;
    const archive = await backupsStore.uploadArchive(file);
    if (archive?.name) {
      selectedName = archive.name;
      focusArchivePage(archive.name);
    }
    event.currentTarget.value = "";
  }

  async function createManualBackup() {
    const archive = await backupsStore.createBackup();
    if (archive?.name) {
      selectedName = archive.name;
      focusArchivePage(archive.name);
    }
  }

  async function restoreSelected() {
    if (!canRestore) return;
    const confirmText = at(
      "backups_restore_confirm",
      { name: selectedName, components: selectedComponentsText() },
      `Запустить восстановление из ${selectedName}?`
    );
    if (typeof window !== "undefined" && !window.confirm(confirmText)) return;

    const ok = await backupsStore.restoreArchive({
      archiveName: selectedName,
      restoreDatabase,
      restoreCompose,
    });
    if (ok) await backupsStore.loadArchives();
  }

  onMount(() => {
    backupsStore.loadArchives();
  });
</script>

<div class="backups-layout">
  <div class="admin-toolbar admin-toolbar-card backups-toolbar">
    <div class="backups-toolbar-main">
      <AdminButton onclick={() => backupsStore.loadArchives()} disabled={backupsLoading}>
        <RefreshCw size={14} />
        {at("btn_refresh", {}, "Обновить")}
      </AdminButton>
      <AdminButton onclick={createManualBackup} disabled={backupsCreating || backupsRestoring}>
        <Plus size={14} />
        {backupsCreating
          ? at("backups_creating", {}, "Создание...")
          : at("backups_create", {}, "Создать бэкап")}
      </AdminButton>
      <AdminButton onclick={() => fileInput?.click()} disabled={backupsUploading}>
        <Upload size={14} />
        {backupsUploading
          ? at("backups_uploading", {}, "Загрузка...")
          : at("backups_upload", {}, "Загрузить архив")}
      </AdminButton>
      <FileInput
        bind:element={fileInput}
        class="backups-file-input"
        accept=".zip,application/zip"
        on:change={uploadSelectedFile}
      />
    </div>
    <div class="admin-toolbar-summary">
      <span class="admin-toolbar-field-label">{at("backups_dir", {}, "Каталог")}</span>
      <strong class="backups-dir">{backupDir || "data/backups"}</strong>
    </div>
  </div>

  <article class="admin-card backups-restore-card">
    <header class="admin-card-head">
      <div>
        <h3>{at("backups_restore_title", {}, "Восстановление")}</h3>
        {#if selectedArchive}
          <small class="backups-selected-name">{selectedArchive.name}</small>
        {/if}
      </div>
      {#if lastRestore}
        <AdminBadge variant="success">
          <CheckCircle2 size={12} />
          {at("backups_last_restore_done", {}, "Готово")}
        </AdminBadge>
      {/if}
    </header>
    <div class="admin-card-body backups-restore-body">
      <label class="backups-check" class:is-disabled={!selectedArchive?.has_database}>
        <Checkbox
          bind:checked={restoreDatabase}
          disabled={!selectedArchive?.has_database || backupsRestoring}
          ariaLabel={at("backups_target_database", {}, "БД")}
        />
        <Database size={16} />
        <span>{at("backups_target_database", {}, "БД")}</span>
      </label>
      <label class="backups-check" class:is-disabled={!selectedArchive?.has_compose}>
        <Checkbox
          bind:checked={restoreCompose}
          disabled={!selectedArchive?.has_compose || backupsRestoring}
          ariaLabel={at("backups_target_compose", {}, "compose-папка")}
        />
        <Server size={16} />
        <span>{at("backups_target_compose", {}, "compose-папка")}</span>
      </label>
      <AdminButton variant="danger" onclick={restoreSelected} disabled={!canRestore}>
        <RefreshCw size={14} />
        {backupsRestoring
          ? at("backups_restoring", {}, "Восстановление...")
          : at("backups_restore_run", {}, "Запустить")}
      </AdminButton>
    </div>
    {#if lastRestore?.compose_pre_restore_archive}
      <div class="backups-restore-note">
        {at(
          "backups_pre_restore_snapshot",
          { path: lastRestore.compose_pre_restore_archive },
          "Текущая compose-папка сохранена перед заменой."
        )}
      </div>
    {/if}
  </article>

  <div class="admin-table-wrap">
    {#if backupsLoading}
      <AdminTableSkeleton
        headers={backupHeaders}
        rows={6}
        widths={["36px", "minmax(220px, 1fr)", "150px", "80px", "150px", "120px"]}
      />
    {:else if !archives?.length}
      <AdminEmptyState tone="card">
        <span class="admin-muted">{at("backups_empty", {}, "Архивов пока нет")}</span>
      </AdminEmptyState>
    {:else}
      <RadioGroup
        class="backups-archive-radio-group"
        name="backup-archive"
        value={selectedName}
        onValueChange={selectArchive}
      >
        <AdminTable class="backups-table">
          <thead>
            <tr>
              <th aria-label={at("select", {}, "Выбрать")}></th>
              <th>{at("backups_col_archive", {}, "Архив")}</th>
              <th>{at("backups_col_created", {}, "Создан")}</th>
              <th>{at("backups_col_size", {}, "Размер")}</th>
              <th>{at("backups_col_contents", {}, "Состав")}</th>
              <th>{at("backups_col_warnings", {}, "Предупреждения")}</th>
            </tr>
          </thead>
          <tbody>
            {#each pagedArchives as archive (archive.name)}
              <tr class:is-selected={archive.name === selectedName}>
                <td data-label={at("select", {}, "Выбрать")}>
                  <RadioGroupItem
                    value={archive.name}
                    ariaLabel={archive.name}
                    class="backups-radio"
                  />
                </td>
                <td
                  class="admin-cell-wrap backups-name"
                  data-label={at("backups_col_archive", {}, "Архив")}
                >
                  {archive.name}
                </td>
                <td data-label={at("backups_col_created", {}, "Создан")}
                  >{fmtDate(archiveDate(archive))}</td
                >
                <td data-label={at("backups_col_size", {}, "Размер")}
                  >{formatSize(archive.size_bytes)}</td
                >
                <td data-label={at("backups_col_contents", {}, "Состав")}>
                  <span class="backups-badges">
                    {#if archive.has_database}
                      <AdminBadge variant="success">{at("backups_badge_db", {}, "БД")}</AdminBadge>
                    {/if}
                    {#if archive.has_compose}
                      <AdminBadge variant="muted">
                        {at("backups_badge_compose", {}, "Compose")}
                      </AdminBadge>
                    {/if}
                  </span>
                </td>
                <td data-label={at("backups_col_warnings", {}, "Предупреждения")}>
                  {#if archive.warnings?.length}
                    <Tooltip.Root>
                      <Tooltip.Trigger
                        class="backups-warning-trigger"
                        aria-label={warningsText(archive.warnings)}
                      >
                        <TriangleAlert size={12} />
                        {archive.warnings.length}
                      </Tooltip.Trigger>
                      <Tooltip.Portal>
                        <Tooltip.Content class="backups-warning-tooltip" side="top" align="end">
                          {#each archive.warnings as warning, index}
                            <p>{index + 1}. {warning}</p>
                          {/each}
                        </Tooltip.Content>
                      </Tooltip.Portal>
                    </Tooltip.Root>
                  {:else}
                    <span class="admin-muted">-</span>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </AdminTable>
      </RadioGroup>
      {#if totalArchives > BACKUPS_PAGE_SIZE}
        <AdminPagination
          meta={paginationMeta()}
          page={backupsPage}
          pageCount={backupsPageCount}
          pageLabel={at("page_short", {}, "Стр.")}
          ofLabel={at("pagination_of", {}, "из")}
          jumpLabel={at("page_short", {}, "Стр.")}
          jumpAriaLabel={at("pagination_jump_aria", {}, "Перейти к странице")}
          goLabel={at("pagination_go", {}, "Перейти")}
          prevLabel={at("pagination_prev", {}, "Назад")}
          nextLabel={at("pagination_next", {}, "Далее")}
          onPageChange={setBackupsPage}
        />
      {/if}
    {/if}
  </div>
</div>

<style>
  .backups-layout {
    display: grid;
    gap: 12px;
  }

  .backups-toolbar-main {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }

  :global(.backups-file-input) {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }

  .backups-dir,
  .backups-selected-name,
  .backups-name {
    font-family: var(--font-mono);
    word-break: break-word;
  }

  .backups-dir {
    max-width: min(420px, 70vw);
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .backups-restore-body {
    display: grid;
    grid-template-columns: repeat(2, minmax(160px, 1fr)) auto;
    gap: 10px;
    align-items: center;
  }

  .backups-check {
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 38px;
    padding: 8px 10px;
    border: 1px solid var(--admin-border);
    border-radius: 8px;
    background: var(--admin-surface-2);
    color: var(--admin-text);
    font-size: 13px;
  }

  .backups-check.is-disabled {
    opacity: 0.55;
  }

  .backups-restore-note {
    border-top: 1px solid var(--admin-border);
    padding: 10px 14px;
    color: var(--admin-muted);
    font-size: 12px;
  }

  :global(.backups-table tbody tr.is-selected) {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
  }

  .backups-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  :global(.backups-archive-radio-group.ui-radio-group) {
    display: block;
  }

  :global(.backups-radio.ui-radio-item) {
    margin-inline: auto;
  }

  :global(.backups-warning-trigger) {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    min-height: 24px;
    padding: 2px 7px;
    border: 1px solid var(--warning-border);
    border-radius: 999px;
    background: var(--warning-soft);
    color: var(--warning-text);
    font: inherit;
    font-size: 11px;
    font-weight: 600;
    cursor: help;
    outline: none;
  }

  :global(.backups-warning-trigger:focus-visible) {
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--warning) 22%, transparent);
  }

  :global(.backups-warning-tooltip) {
    z-index: 120;
    display: grid;
    gap: 6px;
    max-width: min(440px, calc(100vw - 32px));
    padding: 10px 12px;
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    background: var(--admin-surface);
    color: var(--admin-text);
    box-shadow: var(--shadow-popover);
    font-size: 12px;
    line-height: 1.4;
  }

  :global(.backups-warning-tooltip) p {
    margin: 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  @media (max-width: 760px) {
    .backups-restore-body {
      grid-template-columns: minmax(0, 1fr);
    }

    :global(.backups-restore-body .admin-btn) {
      width: 100%;
    }
  }
</style>
