<script lang="ts">
  import { AdminBadge } from "$components/patterns/admin/index.js";
  import type { RequiredChannelDiagnostics } from "$lib/admin/stores/settingsStore";

  let {
    at,
    currentLang = "ru",
    diagnostics,
    changed = false,
  }: {
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
    currentLang?: string;
    diagnostics: RequiredChannelDiagnostics | null;
    changed?: boolean;
  } = $props();

  const status = $derived(diagnostics?.status);
  const checkedAt = $derived(diagnostics?.checked_at ? new Date(diagnostics.checked_at) : null);
  const checkedTime = $derived(
    checkedAt && Number.isFinite(checkedAt.getTime()) ? checkedAt.toLocaleString(currentLang) : null
  );
  const variant = $derived(
    status === "available"
      ? "success"
      : status === "missing_rights"
        ? "warning"
        : status === "unavailable"
          ? "danger"
          : "muted"
  );
</script>

{#if changed || diagnostics}
  <div class="required-channel-diagnostic" role="status">
    {#if changed}
      <small>
        {at(
          "required_channel_save_to_check",
          {},
          "Save the channel setting to check the bot's access."
        )}
      </small>
    {:else}
      <AdminBadge {variant} wrap>
        {#if status === "available"}
          {at("required_channel_available", {}, "Membership checks are available")}
        {:else if status === "missing_rights"}
          {at("required_channel_missing_rights", {}, "Bot administrator rights are required")}
        {:else if status === "unavailable"}
          {at("required_channel_unavailable", {}, "Channel is unavailable")}
        {:else}
          {at("required_channel_disabled", {}, "Required channel is not configured")}
        {/if}
      </AdminBadge>
      <small>
        {#if checkedTime && diagnostics?.checked_at}
          {at("required_channel_last_check", {}, "Last checked:")}
          <time datetime={diagnostics.checked_at}>{checkedTime}</time>
        {:else}
          {at("required_channel_not_checked", {}, "Not checked yet")}
        {/if}
      </small>
    {/if}
  </div>
{/if}

<style>
  .required-channel-diagnostic {
    display: grid;
    justify-items: start;
    gap: 6px;
    min-width: 0;
  }
</style>
