<script lang="ts">
  import { onMount } from "svelte";
  import AdminButton from "$components/patterns/admin/AdminButton.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { builtApiPath } from "$lib/webapp/publicApi";
  import type { AdminApi } from "../adminStores";
  import { responseError } from "./pluginPackageErrors";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Inventory = {
    generation: number;
    installations: Record<string, { digest: string; enabled: boolean }>;
    observations?: Record<string, { generation: number; status: string }>;
    failed_generation?: number | null;
    operations?: Array<{
      id: string;
      action: string;
      plugin: string;
      digest?: string;
      status?: string;
    }>;
  };
  type ApplyKind = "install" | "update" | "enable" | "disable";
  type ApplyOperation = {
    kind: ApplyKind;
    id: string;
    name: string;
    generation: number;
    digest?: string;
    operationId?: string;
    enabled?: boolean;
    stage: "changing" | "restarting" | "complete" | "failed";
    confirmed: boolean;
    acknowledged: boolean;
    startedAt: number;
    errorCode?: string;
  };
  type InstallOperation = {
    id: string;
    name: string;
    digest: string;
    operationId: string;
    generation: number;
  };
  const storageKey = "minishop-plugin-apply";

  let {
    api,
    at,
    blocked,
    oninventory,
    onready,
    onbusy,
  }: {
    api: AdminApi;
    at: TranslateFn;
    blocked: boolean;
    oninventory: () => Promise<Inventory>;
    onready: (id: string) => void;
    onbusy: (busy: boolean) => void;
  } = $props();
  let operation = $state<ApplyOperation | null>(null);
  let applying = false;

  function persist(): void {
    try {
      if (operation) sessionStorage.setItem(storageKey, JSON.stringify(operation));
      else sessionStorage.removeItem(storageKey);
    } catch {
      // The dialog still tracks the operation if session storage is unavailable.
    }
  }

  function update(changes: Partial<ApplyOperation>): void {
    if (!operation) return;
    operation = { ...operation, ...changes };
    persist();
  }

  function close(): void {
    if (operation?.stage === "changing" || operation?.stage === "restarting") return;
    operation = null;
    persist();
  }

  function errorLabel(code: string): string {
    if (code === "generation_conflict")
      return at("plugins_generation_conflict", {}, "The installation changed. Refresh and retry.");
    if (code === "restart_failed")
      return at(
        "plugins_apply_restart_failed",
        {},
        "The change was saved, but the application did not start normally. Check diagnostics."
      );
    if (code === "not_confirmed")
      return at(
        "plugins_apply_not_confirmed",
        {},
        "The change was not confirmed. Refresh the plugin list before retrying."
      );
    if (code === "waiting")
      return at(
        "plugins_apply_waiting",
        {},
        "The restart is taking longer than expected. Refresh the list to check its status."
      );
    return at(
      "plugins_apply_failed",
      {},
      "The change could not be applied. Check the package and try again."
    );
  }

  function completeLabel(kind: ApplyKind): string {
    if (kind === "install")
      return at("plugins_install_complete", {}, "Plugin installed. The application is ready.");
    if (kind === "update")
      return at("plugins_update_complete", {}, "Plugin updated. The application is ready.");
    if (kind === "enable")
      return at("plugins_enable_complete", {}, "Plugin enabled. The application is ready.");
    return at("plugins_disable_complete", {}, "Plugin disabled. The application is ready.");
  }

  function confirmed(current: Inventory, pending: ApplyOperation): boolean {
    if (current.generation <= pending.generation) return false;
    const installation = current.installations[pending.id];
    if (!installation) return false;
    if (pending.kind === "install" || pending.kind === "update") {
      return (
        installation.digest === pending.digest &&
        current.operations?.some(
          (item) =>
            item.id === pending.operationId &&
            item.plugin === pending.id &&
            item.digest === pending.digest &&
            item.action === "install" &&
            item.status === "completed"
        ) === true
      );
    }
    return installation.enabled === pending.enabled;
  }

  async function waitForReady(): Promise<void> {
    for (let attempt = 0; operation && Date.now() - operation.startedAt < 360_000; attempt += 1) {
      try {
        const current = await oninventory();
        const pending = operation;
        if (!pending) return;
        if (confirmed(current, pending)) {
          update({ confirmed: true, stage: "restarting" });
          if (current.failed_generation === current.generation) {
            update({ stage: "failed", errorCode: "restart_failed" });
            return;
          }
          const ready = ["backend", "worker"].every(
            (role) =>
              current.observations?.[role]?.generation === current.generation &&
              current.observations?.[role]?.status === "active"
          );
          if (ready) {
            update({ stage: "complete" });
            onready(pending.id);
            return;
          }
        } else if (!pending.acknowledged && attempt >= 5) {
          update({ stage: "failed", errorCode: "not_confirmed" });
          return;
        }
      } catch {
        // Both processes can be unavailable while the launcher changes generations.
      }
      await new Promise((resolve) => setTimeout(resolve, attempt < 5 ? 1000 : 4000));
    }
    update({ stage: "failed", errorCode: "waiting" });
  }

  async function start(
    next: Omit<ApplyOperation, "stage" | "confirmed" | "acknowledged" | "startedAt">,
    request: () => Promise<{ ok?: boolean; error?: string } | null>
  ): Promise<void> {
    if (blocked || applying) return;
    applying = true;
    onbusy(true);
    operation = {
      ...next,
      stage: "changing",
      confirmed: false,
      acknowledged: false,
      startedAt: Date.now(),
    };
    persist();
    try {
      try {
        const result = await request();
        if (!result?.ok) {
          update({ stage: "failed", errorCode: responseError(result, "apply_failed") });
          return;
        }
        update({ acknowledged: true });
      } catch {
        // The mutation may have persisted even when the restart drops its response.
      }
      await waitForReady();
    } finally {
      applying = false;
      onbusy(false);
    }
  }

  export async function toggle(
    id: string,
    name: string,
    enabled: boolean,
    generation: number
  ): Promise<void> {
    const path = builtApiPath<"/api/admin/plugins/{plugin_id}/enabled">(
      `/admin/plugins/${encodeURIComponent(id)}/enabled`
    );
    await start({ kind: enabled ? "enable" : "disable", id, name, generation, enabled }, () =>
      api(path, { method: "POST", body: JSON.stringify({ enabled, generation }) })
    );
  }

  export function install(next: InstallOperation, updating: boolean): void {
    void start(
      {
        kind: updating ? "update" : "install",
        id: next.id,
        name: next.name,
        digest: next.digest,
        operationId: next.operationId,
        generation: next.generation,
      },
      () =>
        api("/admin/plugins/install", {
          method: "POST",
          body: JSON.stringify({
            operation_id: next.operationId,
            digest: next.digest,
            generation: next.generation,
          }),
        })
    );
  }

  onMount(() => {
    try {
      const stored = sessionStorage.getItem(storageKey);
      if (stored) {
        const parsed: ApplyOperation = JSON.parse(stored);
        if (
          parsed &&
          typeof parsed.id === "string" &&
          typeof parsed.generation === "number" &&
          typeof parsed.startedAt === "number" &&
          ["changing", "restarting", "complete", "failed"].includes(parsed.stage)
        ) {
          operation = parsed;
        }
      }
    } catch {
      // Storage can be disabled; the dialog still works for this page session.
    }
    if (operation?.stage === "changing" || operation?.stage === "restarting") {
      applying = true;
      onbusy(true);
      void waitForReady().finally(() => {
        applying = false;
        onbusy(false);
      });
    }
  });
</script>

<Dialog
  open={Boolean(operation)}
  title={at("plugins_apply_title", { name: operation?.name }, "Apply change to {name}")}
  closeLabel={at("close", {}, "Close")}
  onclose={close}
  showCloseButton={operation?.stage === "complete" || operation?.stage === "failed"}
  class="admin-dialog admin-dialog-compact plugin-apply-dialog"
>
  {#if operation}
    <div class="plugin-apply-content">
      <ol
        class="plugin-apply-steps"
        aria-label={at("plugins_apply_progress", {}, "Change progress")}
      >
        <li class:current={operation.stage === "changing"} class:done={operation.confirmed}>
          {at("plugins_apply_step_change", {}, "Save the plugin change")}
        </li>
        <li
          class:current={operation.stage === "restarting"}
          class:done={operation.stage === "complete"}
        >
          {at("plugins_remove_step_restart", {}, "Restart backend and worker")}
        </li>
        <li class:done={operation.stage === "complete"}>
          {at("plugins_remove_step_ready", {}, "Confirm the application is ready")}
        </li>
      </ol>
      {#if operation.stage === "changing" || operation.stage === "restarting"}
        <p role="status">
          {operation.stage === "changing"
            ? at("plugins_apply_working", {}, "Saving the plugin change…")
            : at("plugins_remove_restarting", {}, "Waiting for the application to restart…")}
        </p>
      {:else if operation.stage === "complete"}
        <p role="status">{completeLabel(operation.kind)}</p>
      {:else}
        <p class="admin-error" role="alert">{errorLabel(operation.errorCode || "")}</p>
      {/if}
      {#if operation.stage === "complete" || operation.stage === "failed"}
        <div class="admin-dialog-actions">
          <AdminButton onclick={close}>{at("close", {}, "Close")}</AdminButton>
        </div>
      {/if}
    </div>
  {/if}
</Dialog>

<style>
  .plugin-apply-content {
    display: grid;
    gap: 16px;
  }
  .plugin-apply-content p {
    margin: 0;
    color: var(--admin-muted);
    font-size: 13px;
    line-height: 1.6;
  }
  .plugin-apply-steps {
    display: grid;
    gap: 10px;
    margin: 0;
    padding-left: 22px;
    color: var(--admin-muted);
    font-size: 13px;
  }
  .plugin-apply-steps .current {
    color: var(--admin-text);
    font-weight: 650;
  }
  .plugin-apply-steps .done {
    color: var(--accent);
  }
</style>
