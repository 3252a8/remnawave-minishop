<script lang="ts">
  import { onMount } from "svelte";
  import { AdminButton, AdminField } from "$components/patterns/admin/index.js";
  import { Dialog, Input, Switch } from "$components/ui/index.js";
  import { ArrowUp, Check, Download, RefreshCw } from "$components/ui/icons.js";
  import { getAdminApi } from "$lib/admin/context";
  import type { components } from "$lib/api/openapi.generated";
  import { unwrap } from "$lib/webapp/publicApi";
  import { documentationBaseUrlForVersion } from "$lib/webapp/documentationUrl";

  type State = components["schemas"]["CoreUpdateState"];
  let {
    at,
    visible,
  }: { at: (key: string, params?: Record<string, unknown>) => string; visible: boolean } = $props();
  const api = getAdminApi();
  let status = $state<State | null>(null);
  let preview = $state<State | null>(null);
  let checkedTag = $state("");
  let open = $state(false);
  let tag = $state("");
  let busy = $state(false);
  let error = $state("");
  let reconnecting = $state(false);
  let awaitingJob = $state(false);
  let connectionChecked = $state(false);
  const setupCommands = [
    "sudo install -m 0755 deploy/docker/core-updater.py /usr/local/sbin/minishop-updater",
    "sudo install -m 0644 deploy/docker/minishop-updater.service /etc/systemd/system/",
    "sudo python3 -I /usr/local/sbin/minishop-updater --enroll /opt/remnawave-minishop",
    "sudo systemctl daemon-reload",
    "sudo systemctl enable --now minishop-updater",
  ].join("\n");
  const steps = ["queued", "pulling", "migrating", "starting", "complete"];
  const phaseLabels: Record<string, string> = {
    queued: "core_update_phase_queued",
    pulling: "core_update_phase_pulling",
    migrating: "core_update_phase_migrating",
    starting: "core_update_phase_starting",
    complete: "core_update_phase_complete",
    failed: "core_update_phase_failed",
  };
  const stepLabels: Record<string, string> = {
    pulling: "core_update_step_pulling",
    migrating: "core_update_step_migrating",
    starting: "core_update_step_starting",
  };
  const phaseLabel = $derived(phaseLabels[status?.phase ?? ""] ?? "core_update_phase_failed");
  const active = $derived(!!status && steps.slice(0, 4).includes(status.phase));
  const selected = $derived(preview ?? status);
  const currentVersion = $derived(
    status?.current.replace(/(\+g[0-9a-f]{8})[0-9a-f]+$/, "$1") ?? ""
  );
  const candidate = $derived(selected?.release?.tag === tag ? selected.release : null);
  const canApply = $derived(
    candidate && (selected?.available || (status?.phase === "failed" && status.job_tag === tag))
  );
  const setupNeeded = $derived(status?.official && !status.executor && !active);
  const guide = $derived(
    documentationBaseUrlForVersion(status?.current) + "troubleshooting/maintenance/#host-updater"
  );
  const sourceRevision = $derived(status?.current.match(/\+g([0-9a-f]{7,40})$/)?.[1]);
  const valid = $derived(/^(?:latest|dev|[0-9]+\.[0-9]+\.[0-9]+)$/.test(tag) && tag.length <= 64);

  async function load() {
    try {
      const next = unwrap(await api("/admin/core-updates")).state;
      if (awaitingJob && !next.phase) error = "core_update_expired";
      status = next;
      reconnecting = false;
      awaitingJob = steps.slice(0, 4).includes(next.phase);
    } catch {
      reconnecting = true;
    }
  }
  onMount(() => {
    void load();
    const refreshOnFocus = () => {
      if (open && setupNeeded && !busy) void load();
    };
    window.addEventListener("focus", refreshOnFocus);
    let polling = false;
    const timer = window.setInterval(async () => {
      if (!(active || awaitingJob || (reconnecting && open)) || busy || polling) return;
      polling = true;
      try {
        await load();
      } finally {
        polling = false;
      }
    }, 2500);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refreshOnFocus);
    };
  });

  function show() {
    preview = null;
    checkedTag = "";
    tag = status?.tag || "latest";
    error = "";
    connectionChecked = false;
    open = true;
    void load();
  }
  async function checkConnection() {
    busy = true;
    try {
      await load();
      connectionChecked = true;
    } finally {
      busy = false;
    }
  }
  async function run(action: "check" | "apply" | "notify", enabled = false) {
    if (busy) return;
    busy = true;
    error = "";
    try {
      if (action === "check") {
        preview = unwrap(
          await api("/admin/core-updates/check", { method: "POST", body: JSON.stringify({ tag }) })
        ).state;
        checkedTag = tag;
        if (tag === preview.tag) status = preview;
      } else if (action === "notify") {
        status = unwrap(
          await api("/admin/core-updates/notifications", {
            method: "PUT",
            body: JSON.stringify({ enabled }),
          })
        ).state;
      } else if (candidate) {
        awaitingJob = true;
        status = unwrap(
          await api("/admin/core-updates/apply", {
            method: "POST",
            body: JSON.stringify({ tag, revision: candidate.revision }),
          })
        ).state;
        preview = null;
      }
    } catch {
      error = "core_update_request_failed";
      if (action === "apply") await load();
    } finally {
      busy = false;
    }
  }
</script>

{#if visible}
  {#if status?.available || active}
    <section class="update-banner" aria-label={at("core_update_title")}>
      <span class="update-icon"><Download size={20} aria-hidden="true" /></span>
      <div class="summary">
        <strong
          >{active
            ? at("core_update_in_progress")
            : at("core_update_available", { version: status?.release?.version })}</strong
        >
        <span
          >{active
            ? at(phaseLabel)
            : at("core_update_installed", { version: currentVersion })}</span
        >
      </div>
      <AdminButton variant="primary" onclick={show}
        >{active ? at("core_update_progress") : at("core_update_open")}</AdminButton
      >
    </section>
  {:else}
    <div class="update-link"
      ><AdminButton variant="ghost" size="sm" onclick={show}
        ><Download size={14} />{at("core_update_title")}</AdminButton
      ></div
    >
  {/if}
{/if}

<Dialog
  {open}
  portal
  title={at("core_update_title")}
  closeLabel={at("close")}
  onclose={() => (open = false)}
  class={setupNeeded ? "admin-dialog" : "admin-dialog admin-dialog-compact"}
>
  <div class="update-body">
    {#if active || status?.phase === "complete" || status?.phase === "failed"}
      <div role="status" class="progress-box">
        <strong>{at(phaseLabel)}</strong>
        {#if active}
          <ol>
            {#each steps.slice(1, 4) as step, idx (step)}
              <li
                class:current={step === status?.phase}
                class:done={steps.indexOf(status?.phase || "") > idx + 1}
              >
                <span class="step-marker"
                  >{#if steps.indexOf(status?.phase || "") > idx + 1}<Check
                      size={12}
                    />{:else}{idx + 1}{/if}</span
                >
                {at(stepLabels[step])}
              </li>
            {/each}
          </ol>
        {/if}
      </div>
    {/if}
    {#if reconnecting}<p role="status">{at("core_update_reconnecting")}</p>{/if}
    {#if !active}
      {#if status}
        <div class="versions">
          <div
            ><small>{at("core_update_current")}</small><strong title={status.current}
              >{currentVersion}</strong
            ></div
          >
          {#if candidate}
            <div><small>{at("core_update_target")}</small><strong>{candidate.version}</strong></div>
          {/if}
        </div>
      {/if}
      <div class="tag-row">
        <AdminField label={at("core_update_tag")}
          ><Input bind:value={tag} disabled={busy} maxlength={64} /></AdminField
        >
        <AdminButton disabled={busy || !valid} onclick={() => run("check")}
          ><RefreshCw size={14} />{at("core_update_check")}</AdminButton
        >
      </div>
      {#if !valid}<p role="status">{at("core_update_tag_hint")}</p>
      {:else if status && !status.official}<p>{at("core_update_custom")}</p>
      {:else if !candidate && (tag === checkedTag || (tag === status?.tag && !status.release))}<p
          role="status">{at("core_update_no_image")}</p
        >
      {:else if candidate && !selected?.available}<p role="status">{at("core_update_current_ok")}</p
        >{/if}
      {#if status}
        <label class="preference"
          ><span>{at("core_update_notify")}</span>
          <Switch.Root
            aria-label={at("core_update_notify")}
            checked={status.notifications}
            disabled={busy}
            onCheckedChange={(enabled) => run("notify", enabled)}
            class="admin-switch-root"><Switch.Thumb class="admin-switch-thumb" /></Switch.Root
          >
        </label>
        {#if setupNeeded}
          <section class="setup" aria-label={at("core_update_setup_title")}>
            <strong>{at("core_update_setup_title")}</strong>
            <p>{at("core_update_no_executor")}</p>
            <details>
              <summary>{at("core_update_setup_commands")}</summary>
              <p>{at("core_update_setup_location")}</p>
              {#if sourceRevision}
                <a
                  href={`https://gitlab.com/3252a8/remnawave-minishop/-/archive/${sourceRevision}/remnawave-minishop-${sourceRevision}.tar.gz`}
                  target="_blank"
                  rel="noopener noreferrer">{at("core_update_setup_files")}</a
                >
              {/if}
              <pre><code>{setupCommands}</code></pre>
              <p>{at("core_update_setup_diagnostics")}</p>
              <pre><code>sudo systemctl status minishop-updater</code></pre>
            </details>
            <a href={guide} target="_blank" rel="noopener noreferrer"
              >{at("core_update_setup_guide")}</a
            >
          </section>
          {#if connectionChecked && !reconnecting}<p role="status">{at("core_update_setup_wait")}</p
            >{/if}
        {:else if canApply}<p>{at("core_update_restarts")}</p>{/if}
      {/if}
    {/if}
    {#if error}<p class="admin-error" role="alert">{at(error)}</p>{/if}
  </div>
  {#snippet footer()}
    <div class="dialog-actions">
      <AdminButton onclick={() => (open = false)}>{at("close")}</AdminButton>
      {#if !active && (setupNeeded || reconnecting)}
        <AdminButton variant="primary" disabled={busy} onclick={checkConnection}
          ><RefreshCw size={15} />{at("core_update_setup_recheck")}</AdminButton
        >
      {:else if !active && status?.official}
        <AdminButton
          variant="primary"
          disabled={busy || !status.executor || !canApply}
          onclick={() => run("apply")}><ArrowUp size={15} />{at("core_update_start")}</AdminButton
        >
      {/if}
    </div>
  {/snippet}
</Dialog>

<style>
  .update-banner {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 16px;
    border: 1px solid color-mix(in srgb, var(--accent) 42%, transparent);
    border-radius: var(--radius, 10px);
    background: color-mix(in srgb, var(--accent) 7%, var(--admin-surface));
  }
  .update-icon {
    display: grid;
    place-items: center;
    flex: none;
    width: 36px;
    height: 36px;
    color: var(--accent);
    border-radius: 9px;
    background: color-mix(in srgb, var(--accent) 14%, transparent);
  }
  .summary {
    flex: 1;
    min-width: 0;
    display: grid;
    gap: 3px;
  }
  .summary strong {
    font-size: 15px;
  }
  .summary span,
  small,
  .update-body p {
    color: var(--admin-muted);
    font-size: 13px;
  }
  .setup {
    min-width: 0;
    display: grid;
    gap: 8px;
    padding: 12px;
    border: 1px solid var(--admin-border);
    border-radius: var(--radius, 10px);
    font-size: 13px;
  }
  .setup summary {
    cursor: pointer;
    font-weight: 600;
  }
  .setup details > :global(*) {
    margin-block: 8px 0;
  }
  .setup a {
    color: var(--accent);
    text-decoration: underline;
  }
  .setup pre {
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    user-select: all;
    line-height: 1.45;
  }
  .summary span,
  .versions strong {
    overflow-wrap: anywhere;
  }
  .update-link {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 8px;
  }
  .update-body {
    display: grid;
    gap: 16px;
  }
  .update-body p {
    margin: 0;
    line-height: 1.45;
  }
  .versions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
  }
  .versions div {
    display: grid;
    align-content: start;
    gap: 4px;
  }
  .versions strong {
    font-size: 14px;
  }
  .tag-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: end;
    gap: 8px;
  }
  .preference {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    font-size: 14px;
  }
  .progress-box ol {
    display: grid;
    gap: 10px;
    padding: 0;
    list-style: none;
    margin: 12px 0 0;
  }
  .progress-box li {
    display: flex;
    align-items: center;
    gap: 9px;
    color: var(--admin-muted);
  }
  .progress-box li.current,
  .progress-box li.done {
    color: var(--accent);
  }
  .step-marker {
    width: 20px;
    height: 20px;
    display: grid;
    place-items: center;
    border: 1px solid currentColor;
    border-radius: 50%;
    font-size: 11px;
  }
  .dialog-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 8px;
  }
  @media (max-width: 600px) {
    .update-banner {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 10px;
    }
    .update-banner :global(button) {
      grid-column: 1/-1;
    }
    .tag-row {
      align-items: end;
    }
    .versions {
      gap: 8px;
    }
  }
</style>
