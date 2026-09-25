<script lang="ts">
  import { onMount } from "svelte";
  import { getRoleApi } from "$lib/admin/context";
  import { AdminButton, AdminCombobox, AdminSelect } from "$components/patterns/admin/index.js";
  import type { Role, RoleAssignment, RoleCandidate } from "$lib/admin/roleApi";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let { at }: { at: TranslateFn } = $props();
  const roleApi = getRoleApi();
  let available = $state(false);
  let assignments = $state<RoleAssignment[]>([]);
  let candidates = $state<RoleCandidate[]>([]);
  let selectedId = $state("");
  let role = $state<Role>("admin");
  let busy = $state(false);
  let searching = $state(false);
  let error = $state("");
  let searchRequest = 0;

  const candidateItems = $derived(
    candidates.map((user) => ({
      value: user.minishop_id,
      label: `${user.first_name || user.username || user.email || user.minishop_id} · ${user.minishop_id}`,
    }))
  );
  const selectedCandidate = $derived(candidates.find((user) => user.minishop_id === selectedId));

  async function load(): Promise<void> {
    try {
      const response = await roleApi.list();
      if (!response) return;
      available = true;
      assignments = response;
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    }
  }

  async function search(query: string): Promise<void> {
    const requestId = ++searchRequest;
    searching = true;
    try {
      const response = await roleApi.candidates(query);
      if (requestId === searchRequest) candidates = response;
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      if (requestId === searchRequest) searching = false;
    }
  }

  onMount(() => {
    void load().then(() => {
      if (available) void search("");
    });
  });

  async function grant(): Promise<void> {
    if (busy || !selectedCandidate) return;
    busy = true;
    error = "";
    try {
      await roleApi.grant(selectedCandidate.minishop_id, role);
      selectedId = "";
      await load();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      busy = false;
    }
  }

  async function revoke(assignment: RoleAssignment): Promise<void> {
    if (busy) return;
    if (
      typeof window !== "undefined" &&
      !window.confirm(at("roles_revoke_access_confirm", {}, "Revoke this account's access?"))
    )
      return;
    busy = true;
    error = "";
    try {
      await roleApi.revoke(assignment.user_id, assignment.role);
      await load();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      busy = false;
    }
  }
</script>

{#if available}
  <div class="role-management">
    <p class="admin-muted">{at("roles_hint", {}, "Choose an existing account to grant access.")}</p>
    <div class="role-form">
      <AdminCombobox
        value={selectedId}
        items={candidateItems}
        ariaLabel={at("roles_search", {}, "Find a user")}
        placeholder={at("roles_search", {}, "Find by name, email or ID")}
        loading={searching}
        emptyMessage={at("roles_no_matches", {}, "No users found")}
        onValueChange={(value) => (selectedId = value)}
        onInputChange={(value) => void search(value)}
      />
      <AdminSelect
        value={role}
        items={[
          { value: "admin", label: at("roles_admin", {}, "Administrator") },
          { value: "owner", label: at("roles_owner", {}, "Owner") },
        ]}
        ariaLabel={at("roles_role", {}, "Role")}
        onValueChange={(value) => (role = value as Role)}
      />
      <AdminButton
        size="sm"
        variant="primary"
        disabled={busy || !selectedCandidate}
        onclick={grant}
      >
        {at("roles_grant", {}, "Grant access")}
      </AdminButton>
    </div>
    {#if error}<p class="admin-error" role="alert">{error.replaceAll("_", " ")}</p>{/if}
    <div class="role-list">
      {#each assignments as assignment (`${assignment.user_id}:${assignment.role}`)}
        <div class="role-row">
          <span>{assignment.email || assignment.minishop_id || "—"}</span>
          <strong>
            {assignment.role === "owner"
              ? at("roles_owner", {}, "Owner")
              : at("roles_admin", {}, "Administrator")}
          </strong>
          <AdminButton size="sm" disabled={busy} onclick={() => void revoke(assignment)}>
            {at("roles_revoke", {}, "Revoke")}
          </AdminButton>
        </div>
      {/each}
    </div>
  </div>
{/if}

<style>
  .role-management,
  .role-list {
    display: grid;
    gap: 0.75rem;
  }
  .role-management {
    padding: 1rem;
  }
  .role-management p {
    margin: 0;
  }
  .role-form,
  .role-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }
  .role-form :global(.admin-combobox) {
    min-width: min(100%, 16rem);
    flex: 1;
  }
  .role-row span {
    flex: 1;
    overflow-wrap: anywhere;
  }
</style>
