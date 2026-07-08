<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import { Input } from "$components/ui/index.js";
  import {
    AdminButton,
    AdminSectionHeader,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { Plus, RefreshCw, Save, Trash2 } from "$components/ui/icons.js";
  import type { AdminPanelSquadOverrides } from "$lib/admin/stores/usersStoreState";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type SelectOption = { value: string; label: string };

  let {
    at,
    panelSquadOverrides = null,
    userActionBusy = false,
    panelSquadItems = [],
    squadLabel,
    userSquadOverrideDraft = "",
    selectUserSquadOverride,
    userExternalSquadModeDraft = "inherit",
    selectUserExternalSquadMode,
    userExternalSquadUuidDraft = "",
    updateUserExternalSquadUuid,
  }: {
    at: TranslateFn;
    panelSquadOverrides?: AdminPanelSquadOverrides | null;
    userActionBusy?: boolean;
    panelSquadItems?: SelectOption[];
    squadLabel: (uuid: string) => string;
    userSquadOverrideDraft?: string;
    selectUserSquadOverride: (value: string) => void;
    userExternalSquadModeDraft?: "inherit" | "set" | "cleared";
    selectUserExternalSquadMode: (value: string) => void;
    userExternalSquadUuidDraft?: string;
    updateUserExternalSquadUuid: (value: string) => void;
  } = $props();

  const usersStore = getUsersStore();
  const managedInternalSquads = $derived(panelSquadOverrides?.managed_internal_squads || []);
  const manualInternalSquads = $derived(panelSquadOverrides?.manual_internal_squads || []);
  const effectiveInternalSquads = $derived(
    panelSquadOverrides?.effective_internal_squad_uuids || []
  );
  const externalSquad = $derived(panelSquadOverrides?.external || null);
  const externalModeItems = $derived([
    { value: "inherit", label: at("user_external_squad_mode_inherit", {}, "Use default setting") },
    { value: "set", label: at("user_external_squad_mode_set", {}, "Assign manually") },
    {
      value: "cleared",
      label: at("user_external_squad_mode_cleared", {}, "Do not assign external squad"),
    },
  ]);
  const userSquadOverrideCanAdd = $derived(
    Boolean(String(userSquadOverrideDraft || "").trim()) && !userActionBusy
  );

  function squadDisplayLabel(uuid: unknown): string {
    const value = String(uuid || "");
    return value ? squadLabel(value) : "—";
  }

  function squadSourceLabel(source: unknown): string {
    const value = String(source || "");
    if (value === "admin") return at("user_squad_source_admin", {}, "admin");
    if (value === "panel") return at("user_squad_source_panel", {}, "panel");
    if (value === "trial") return at("user_squad_source_trial", {}, "trial");
    if (value === "tariff") return at("user_squad_source_tariff", {}, "tariff");
    if (value === "settings") return at("user_squad_source_settings", {}, "settings");
    return value || "—";
  }
</script>

{#if panelSquadOverrides}
  <section class="admin-user-action-sheet admin-user-action-sheet--squad-overrides">
    <AdminSectionHeader
      title={at("user_squad_overrides_title", {}, "Panel squads")}
      description={at(
        "user_squad_overrides_hint",
        {},
        "Controls which Remnawave squads will be kept for this user when bot actions update the panel."
      )}
    />
    <div class="admin-user-action-sheet-body admin-squad-overrides-body">
      <section class="admin-squad-section">
        <header class="admin-squad-section-head">
          <strong>{at("user_squad_managed_title", {}, "From tariff")}</strong>
          <small>
            {at(
              "user_squad_managed_hint",
              {},
              "Calculated by the bot from the current tariff, trial, or default settings."
            )}
          </small>
        </header>
        {#if managedInternalSquads.length}
          <div class="admin-squad-list">
            {#each managedInternalSquads as squad}
              <div class="admin-squad-row">
                <span class="admin-squad-row-main">{squadDisplayLabel(squad.uuid)}</span>
                <small>{squadSourceLabel(squad.source)}</small>
              </div>
            {/each}
          </div>
        {:else}
          <p class="admin-muted">{at("user_squad_empty", {}, "No squads")}</p>
        {/if}
      </section>

      <section class="admin-squad-section">
        <header class="admin-squad-section-head">
          <strong>{at("user_squad_manual_title", {}, "Manual additions")}</strong>
          <small>
            {at(
              "user_squad_manual_hint",
              {},
              "These internal squads are preserved in addition to tariff squads and are synced back to Remnawave."
            )}
          </small>
        </header>
        {#if manualInternalSquads.length}
          <div class="admin-squad-list">
            {#each manualInternalSquads as squad}
              <div class="admin-squad-row admin-squad-row--removable">
                <span class="admin-squad-row-main">{squadDisplayLabel(squad.uuid)}</span>
                <small>{squadSourceLabel(squad.source)}</small>
                <AdminButton
                  size="icon"
                  variant="icon"
                  title={at("user_squad_remove", {}, "Remove")}
                  aria-label={at("user_squad_remove", {}, "Remove")}
                  disabled={userActionBusy}
                  onclick={() =>
                    usersStore.removeUserInternalSquadOverride(String(squad.uuid || ""))}
                >
                  <Trash2 size={14} />
                </AdminButton>
              </div>
            {/each}
          </div>
        {:else}
          <p class="admin-muted">{at("user_squad_no_manual", {}, "No manual squads")}</p>
        {/if}
      </section>

      <section class="admin-squad-section">
        <header class="admin-squad-section-head">
          <strong>{at("user_squad_add_section_title", {}, "Add internal squad")}</strong>
          <small>
            {at(
              "user_squad_add_hint",
              {},
              "Choose a panel squad or enter its UUID to pin it as a manual addition."
            )}
          </small>
        </header>
        <div class="admin-squad-control-row">
          {#if panelSquadItems.length}
            <AdminSelect
              class="admin-squad-select"
              value={userSquadOverrideDraft}
              items={panelSquadItems}
              placeholder={at("user_squad_add_placeholder", {}, "Internal squad")}
              ariaLabel={at("user_squad_add_placeholder", {}, "Internal squad")}
              disabled={userActionBusy}
              onValueChange={selectUserSquadOverride}
            />
          {:else}
            <Input
              class="input admin-squad-uuid-input"
              value={userSquadOverrideDraft}
              placeholder={at("user_squad_uuid_placeholder", {}, "Internal squad UUID")}
              aria-label={at("user_squad_uuid_placeholder", {}, "Internal squad UUID")}
              disabled={userActionBusy}
              oninput={(event) => selectUserSquadOverride(event.currentTarget.value)}
            />
          {/if}
          <AdminButton
            variant="primary"
            disabled={!userSquadOverrideCanAdd}
            onclick={usersStore.addUserInternalSquadOverride}
          >
            <Plus size={14} />
            {at("user_squad_add", {}, "Add")}
          </AdminButton>
          <AdminButton
            variant="ghost"
            disabled={userActionBusy}
            onclick={usersStore.refreshUserSquadOverrides}
          >
            <RefreshCw size={14} />
            {at("user_squad_refresh", {}, "Refresh from panel")}
          </AdminButton>
        </div>
      </section>

      <section class="admin-squad-section">
        <header class="admin-squad-section-head">
          <strong>{at("user_external_squad_section_title", {}, "External squad")}</strong>
          <small>
            {at(
              "user_external_squad_hint",
              {},
              "Controls the optional external Remnawave squad: inherit the global setting, assign a specific UUID, or keep it empty."
            )}
          </small>
        </header>
        <div class="admin-squad-control-row">
          <AdminSelect
            class="admin-squad-external-mode"
            value={userExternalSquadModeDraft}
            items={externalModeItems}
            placeholder={at("user_external_squad_mode", {}, "External behavior")}
            ariaLabel={at("user_external_squad_mode", {}, "External behavior")}
            disabled={userActionBusy}
            onValueChange={selectUserExternalSquadMode}
          />
          {#if userExternalSquadModeDraft === "set"}
            <Input
              class="input admin-squad-uuid-input"
              value={userExternalSquadUuidDraft}
              placeholder={at("user_external_squad_uuid", {}, "External squad UUID")}
              aria-label={at("user_external_squad_uuid", {}, "External squad UUID")}
              disabled={userActionBusy}
              oninput={(event) => updateUserExternalSquadUuid(event.currentTarget.value)}
            />
          {/if}
          <AdminButton
            variant="primary"
            disabled={userActionBusy ||
              (userExternalSquadModeDraft === "set" &&
                !String(userExternalSquadUuidDraft || "").trim())}
            onclick={usersStore.saveUserExternalSquadOverride}
          >
            <Save size={14} />
            {at("user_external_squad_save", {}, "Save")}
          </AdminButton>
        </div>
      </section>

      <section class="admin-squad-section admin-squad-section--effective">
        <header class="admin-squad-section-head">
          <strong>{at("user_squad_effective_title", {}, "Result sent to panel")}</strong>
          <small>
            {at(
              "user_squad_effective_hint",
              {},
              "Internal squads are tariff squads plus manual additions; external squad follows the selected behavior above."
            )}
          </small>
        </header>
        <div class="admin-squad-effective-grid">
          <span>
            <small>{at("user_squad_effective_internal", {}, "Internal squads")}</small>
            <strong>{effectiveInternalSquads.length}</strong>
          </span>
          <span>
            <small>{at("user_external_squad_effective", {}, "External squad")}</small>
            <strong>{externalSquad?.effective_uuid || "—"}</strong>
          </span>
        </div>
      </section>
    </div>
  </section>
{/if}
