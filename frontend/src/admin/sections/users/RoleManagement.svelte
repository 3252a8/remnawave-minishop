<script lang="ts">
  import { onMount } from "svelte";
  import { AdminButton, AdminSelect } from "$components/patterns/admin/index.js";
  import { Input } from "$components/ui/index.js";
  import { builtApiPath } from "$lib/webapp/publicApi";
  import type { AdminApi } from "../../adminStores";

  type Role = "owner" | "admin";
  type Assignment = { user_id: number; email: string | null; role: Role };
  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let { api, at }: { api: AdminApi; at: TranslateFn } = $props();
  let available = $state(false);
  let assignments = $state<Assignment[]>([]);
  let email = $state("");
  let role = $state<Role>("admin");
  let busy = $state(false);
  let error = $state("");

  async function load(): Promise<void> {
    const response = await api("/admin/roles");
    if (!response?.ok) return;
    available = true;
    assignments = (response.roles || []) as Assignment[];
  }

  onMount(() => {
    void load().catch(() => {
      // A regular admin cannot read or change account roles.
    });
  });

  async function grant(): Promise<void> {
    if (busy || !email.trim()) return;
    busy = true;
    error = "";
    try {
      const response = await api("/admin/roles", {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), role }),
      });
      if (!response?.ok) throw new Error("role_update_failed");
      email = "";
      await load();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      busy = false;
    }
  }

  async function revoke(assignment: Assignment): Promise<void> {
    if (busy) return;
    busy = true;
    error = "";
    try {
      const path = builtApiPath<"/api/admin/roles/{user_id}/{role}">(
        `/admin/roles/${encodeURIComponent(String(assignment.user_id))}/${assignment.role}`
      );
      const response = await api(path, { method: "DELETE" });
      if (!response?.ok) throw new Error("role_update_failed");
      await load();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      busy = false;
    }
  }
</script>

{#if available}
  <section class="role-management" aria-label={at("roles_title", {}, "Account access")}>
    <div class="role-heading">
      <h2>{at("roles_title", {}, "Account access")}</h2>
      <p>{at("roles_hint", {}, "Grant access to an account with a verified email address.")}</p>
    </div>
    <form
      class="role-form"
      onsubmit={(event) => {
        event.preventDefault();
        void grant();
      }}
    >
      <Input
        type="email"
        required
        bind:value={email}
        aria-label={at("roles_email", {}, "Verified email")}
        placeholder={at("roles_email", {}, "Verified email")}
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
      <AdminButton size="sm" variant="primary" type="submit" disabled={busy}>
        {at("roles_grant", {}, "Grant access")}
      </AdminButton>
    </form>
    {#if error}<p class="admin-error" role="alert">{error.replaceAll("_", " ")}</p>{/if}
    <div class="role-list">
      {#each assignments as assignment (`${assignment.user_id}:${assignment.role}`)}
        <div class="role-row">
          <span>{assignment.email || `#${assignment.user_id}`}</span>
          <strong
            >{assignment.role === "owner"
              ? at("roles_owner", {}, "Owner")
              : at("roles_admin", {}, "Administrator")}</strong
          >
          <AdminButton size="sm" disabled={busy} onclick={() => void revoke(assignment)}>
            {at("roles_revoke", {}, "Revoke")}
          </AdminButton>
        </div>
      {/each}
    </div>
  </section>
{/if}

<style>
  .role-management {
    display: grid;
    gap: 1rem;
    margin-bottom: 1.25rem;
    padding: 1.25rem;
    border: 1px solid var(--border, #d9e0ea);
    border-radius: 1rem;
  }
  .role-heading h2 {
    margin: 0;
    font-size: 1.15rem;
  }
  .role-heading p {
    margin: 0.35rem 0 0;
  }
  .role-form,
  .role-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }
  .role-form :global(input) {
    min-width: 16rem;
    flex: 1;
  }
  .role-list {
    display: grid;
    gap: 0.5rem;
  }
  .role-row {
    justify-content: space-between;
  }
  .role-row span {
    flex: 1;
    overflow-wrap: anywhere;
  }
</style>
