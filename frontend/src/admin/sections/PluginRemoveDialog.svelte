<script lang="ts">
  import AdminButton from "$components/patterns/admin/AdminButton.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { Trash2 } from "$components/ui/icons.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  let {
    at,
    open,
    name,
    stage,
    error,
    confirmed,
    onclose,
    onremove,
  }: {
    at: TranslateFn;
    open: boolean;
    name: string;
    stage: "confirm" | "removing" | "restarting" | "complete" | "failed";
    error: string;
    confirmed: boolean;
    onclose: () => void;
    onremove: () => void;
  } = $props();
</script>

<Dialog
  {open}
  title={at("plugins_remove_title", { name }, "Remove {name}?")}
  closeLabel={at("close", {}, "Close")}
  {onclose}
  showCloseButton={stage !== "removing" && stage !== "restarting"}
  class="admin-dialog admin-dialog-compact plugin-remove-dialog"
>
  <div class="plugin-remove-content">
    <p>
      {at(
        "plugins_remove_explanation",
        {},
        "The plugin will be removed from this installation. Its saved data and verified package remain available. The application may be briefly unavailable while its backend and worker restart."
      )}
    </p>
    <ol
      class="plugin-remove-steps"
      aria-label={at("plugins_remove_progress", {}, "Removal progress")}
    >
      <li class:current={stage === "removing"} class:done={confirmed}>
        {at("plugins_remove_step_package", {}, "Remove plugin from the installation")}
      </li>
      <li class:current={stage === "restarting"} class:done={stage === "complete"}>
        {at("plugins_remove_step_restart", {}, "Restart backend and worker")}
      </li>
      <li class:done={stage === "complete"}>
        {at("plugins_remove_step_ready", {}, "Confirm the application is ready")}
      </li>
    </ol>
    {#if stage === "removing" || stage === "restarting"}
      <p role="status">
        {stage === "removing"
          ? at("plugins_removing", {}, "Removing the package…")
          : at("plugins_remove_restarting", {}, "Waiting for the application to restart…")}
      </p>
    {:else if stage === "complete"}
      <p role="status">
        {at("plugins_remove_complete", {}, "Plugin removed. The application is ready.")}
      </p>
    {:else if stage === "failed"}
      <p class="admin-error" role="alert">{error}</p>
    {/if}
    <div class="admin-dialog-actions">
      {#if stage === "confirm"}
        <AdminButton onclick={onclose}>{at("cancel", {}, "Cancel")}</AdminButton>
        <AdminButton variant="danger" onclick={onremove}>
          <Trash2 size={14} />{at("plugins_remove", {}, "Remove package")}
        </AdminButton>
      {:else if stage === "complete" || stage === "failed"}
        <AdminButton onclick={onclose}>{at("close", {}, "Close")}</AdminButton>
      {/if}
    </div>
  </div>
</Dialog>

<style>
  .plugin-remove-content {
    display: grid;
    gap: 16px;
  }
  .plugin-remove-content p {
    margin: 0;
    color: var(--admin-muted);
    font-size: 13px;
    line-height: 1.6;
  }
  .plugin-remove-steps {
    display: grid;
    gap: 10px;
    margin: 0;
    padding-left: 22px;
    color: var(--admin-muted);
    font-size: 13px;
  }
  .plugin-remove-steps .current {
    color: var(--admin-text);
    font-weight: 650;
  }
  .plugin-remove-steps .done {
    color: var(--accent);
  }
</style>
