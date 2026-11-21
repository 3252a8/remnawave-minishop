<script lang="ts">
  import { onMount, untrack } from "svelte";
  import { AdminButton, AdminField } from "$components/patterns/admin/index.js";
  import { Dialog, Input, Switch } from "$components/ui/index.js";
  import { ArrowUp, Check, Copy, Download, RefreshCw } from "$components/ui/icons.js";
  import { getAdminApi } from "$lib/admin/context";
  import type { components } from "$lib/api/openapi.generated";
  import { unwrap } from "$lib/webapp/publicApi";
  import { copyTextToClipboard } from "$lib/webapp/clipboard.js";
  import { documentationBaseUrlForVersion } from "$lib/webapp/documentationUrl";

  type State = components["schemas"]["CoreUpdateState"];
  let {
    at,
    visible,
    open,
    onopen,
    onclose,
  }: {
    at: (key: string, params?: Record<string, unknown>) => string;
    visible: boolean;
    open: boolean;
    onopen: (event: MouseEvent) => void;
    onclose: () => void;
  } = $props();
  const api = getAdminApi();
  let status = $state<State | null>(null);
  let preview = $state<State | null>(null);
  let checkedTag = $state("");
  let tag = $state("");
  let busy = $state(false);
  let error = $state("");
  let reconnecting = $state(false);
  let awaitingJob = $state(false);
  let connectionChecked = $state(false);
  let copyResult = $state<"copied" | "failed" | null>(null);
  let requestSequence = 0;
  const installerRepository = "https://gitlab.com/3252a8/remnawave-minishop";
  const installerPath = "deploy/docker/install-updater.sh";
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
  const setupNeeded = $derived(status?.installable && !status.executor && !active);
  const guide = $derived(
    documentationBaseUrlForVersion(status?.current) + "troubleshooting/maintenance/#host-updater"
  );
  const installerChannel = $derived(status?.tag === "dev" ? "dev" : "latest");
  const installerRef = $derived(installerChannel === "dev" ? "dev" : "main");
  const installerCommand = $derived(
    `(set -e; installer=$(mktemp); trap 'rm -f -- "$installer"' EXIT; url='${installerRepository}/-/raw/${installerRef}/${installerPath}'; if command -v curl >/dev/null; then curl -fsSL --proto '=https' "$url" -o "$installer"; else wget -qO "$installer" "$url"; fi; sudo bash "$installer" --channel ${installerChannel})`
  );
  const valid = $derived(validImageTag(tag));

  function validImageTag(value: string): boolean {
    return /^(?:latest|dev|[0-9]+\.[0-9]+\.[0-9]+)$/.test(value) && value.length <= 64;
  }

  async function checkTag(imageTag: string): Promise<State> {
    return unwrap(
      await api("/admin/core-updates/check", {
        method: "POST",
        body: JSON.stringify({ tag: imageTag }),
      })
    ).state;
  }

  async function load(refresh = false) {
    const sequence = ++requestSequence;
    try {
      let next = (refresh && status) || unwrap(await api("/admin/core-updates")).state;
      if (refresh && next.official && validImageTag(next.tag)) next = await checkTag(next.tag);
      if (sequence !== requestSequence) return;
      if (awaitingJob && !next.phase) error = "core_update_expired";
      if (open && !status) tag = next.tag || "latest";
      status = next;
      reconnecting = false;
      awaitingJob = steps.slice(0, 4).includes(next.phase);
    } catch {
      if (sequence === requestSequence) reconnecting = true;
    }
  }
  onMount(() => {
    if (!open) void load();
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

  $effect(() => {
    if (open) untrack(refreshDialog);
  });

  function refreshDialog() {
    preview = null;
    checkedTag = "";
    tag = status?.tag || "";
    error = "";
    connectionChecked = false;
    copyResult = null;
    void load(true);
  }

  async function copyInstaller() {
    copyResult = (await copyTextToClipboard(installerCommand)) ? "copied" : "failed";
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
    requestSequence += 1;
    error = "";
    try {
      if (action === "check") {
        preview = await checkTag(tag);
        checkedTag = tag;
        if (tag === status?.tag) status = preview;
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
      reconnecting = false;
    } catch {
      error = "core_update_request_failed";
      if (action === "apply") await load();
    } finally {
      busy = false;
    }
  }
</script>

{#if visible && (status?.available || active)}
  <section class="update-banner" aria-label={at("core_update_title")}>
    <span class="update-icon"><Download size={20} aria-hidden="true" /></span>
    <div class="summary">
      <strong
        >{active
          ? at("core_update_in_progress")
          : at(status?.installable ? "core_update_available" : "core_update_base_available", {
              version: status?.release?.version,
            })}</strong
      >
      <span
        >{active ? at(phaseLabel) : at("core_update_installed", { version: currentVersion })}</span
      >
    </div>
    <AdminButton variant="primary" onclick={onopen}
      >{active
        ? at("core_update_progress")
        : at(status?.installable ? "core_update_open" : "core_update_title")}</AdminButton
    >
  </section>
{/if}

<Dialog
  {open}
  portal
  title={at("core_update_title")}
  closeLabel={at("close")}
  {onclose}
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
    {#if !status && !reconnecting}<p role="status">{at("loading")}</p>{/if}
    {#if !active && status}
      {#if candidate && !selected?.available}
        <div class="current-status" role="status">
          <Check size={18} aria-hidden="true" />
          <strong>{at("core_update_current_ok")}</strong>
        </div>
      {/if}
      {#if status}
        <div class="versions">
          <div
            ><small>{at("core_update_current")}</small><strong title={status.current}
              >{currentVersion}</strong
            ></div
          >
          {#if candidate && selected?.available}
            <div>
              <small
                >{at(status.installable ? "core_update_target" : "core_update_published")}</small
              >
              <strong>{candidate.version}</strong>
            </div>
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
      {/if}
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
        {#if status.official && !status.installable}
          <p>{at("core_update_base_only")}</p>
        {:else if setupNeeded}
          <section class="setup" aria-label={at("core_update_setup_title")}>
            <strong>{at("core_update_setup_title")}</strong>
            <p>{at("core_update_setup_location")}</p>
            <div class="installer-code">
              <div class="installer-actions">
                <AdminButton variant="ghost" size="sm" onclick={copyInstaller}>
                  {#if copyResult === "copied"}<Check size={14} aria-hidden="true" />{:else}<Copy
                      size={14}
                      aria-hidden="true"
                    />{/if}
                  {at("core_update_copy")}
                </AdminButton>
              </div>
              <pre><code>{installerCommand}</code></pre>
            </div>
            {#if copyResult}
              <p role="status">
                {at(
                  copyResult === "copied" ? "core_update_copy_copied" : "core_update_copy_failed"
                )}
              </p>
            {/if}
            <p>{at("core_update_setup_options")}</p>
            <div class="setup-links">
              <a
                href={`${installerRepository}/-/blob/${installerRef}/${installerPath}`}
                target="_blank"
                rel="noopener noreferrer">{at("core_update_setup_files")}</a
              >
              <a href={guide} target="_blank" rel="noopener noreferrer"
                >{at("core_update_setup_guide")}</a
              >
            </div>
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
      <AdminButton onclick={onclose}>{at("close")}</AdminButton>
      {#if !active && (setupNeeded || reconnecting)}
        <AdminButton variant="primary" disabled={busy} onclick={checkConnection}
          ><RefreshCw size={15} />{at("core_update_setup_recheck")}</AdminButton
        >
      {:else if !active && status?.installable}
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
  .setup-links {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
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
  .current-status {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px;
    color: var(--success-text);
    background: var(--success-soft);
    border: 1px solid var(--success-border);
    border-radius: var(--radius, 10px);
  }
  .current-status :global(svg) {
    flex: none;
  }
  .installer-code {
    min-width: 0;
    padding: 4px 10px 10px;
    border: 1px solid var(--admin-border);
    border-radius: var(--radius, 10px);
    background: var(--admin-elev);
  }
  .installer-actions {
    display: flex;
    justify-content: flex-end;
  }
  .installer-code pre {
    margin: 4px 0 0;
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
