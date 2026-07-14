<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import {
    AdminButton,
    AdminSectionHeader,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { Input } from "$components/ui/index.js";
  import { Label } from "$components/ui/primitives.js";
  import { Plus } from "$components/ui/icons.js";
  import type { TranslateFn } from "./userDetailTypes";

  let {
    at,
    userActionBusy = false,
    grantTrafficGbValid = false,
    selectGrantTrafficKind,
  }: {
    at: TranslateFn;
    userActionBusy?: boolean;
    grantTrafficGbValid?: boolean;
    selectGrantTrafficKind: (value: string) => void;
  } = $props();

  const usersStore = getUsersStore();
  const grantTrafficKindItems = $derived([
    {
      value: "regular",
      label: at("user_traffic_grant_kind_regular", {}, "Regular"),
    },
    {
      value: "premium",
      label: at("user_traffic_grant_kind_premium", {}, "Premium"),
    },
  ]);
</script>

<section class="admin-user-action-sheet admin-user-action-sheet--traffic-grant">
  <AdminSectionHeader
    title={at("user_traffic_grant_title", {}, "Grant traffic")}
    description={at(
      "user_traffic_grant_hint",
      {},
      "Adds GB to the user balance like a top-up, but without payment. The limit and squads update in the panel immediately."
    )}
  />
  <div class="admin-user-action-sheet-body admin-user-grant-stack">
    <Label.Root class="admin-field-label admin-extend-field">
      <span>{at("user_traffic_grant_kind", {}, "Traffic type")}</span>
      <AdminSelect
        class="admin-grant-kind-select"
        value={usersStore.grantTrafficKindDraft}
        items={grantTrafficKindItems}
        onValueChange={selectGrantTrafficKind}
        ariaLabel={at("user_traffic_grant_kind", {}, "Traffic type")}
      />
    </Label.Root>
    <Label.Root class="admin-field-label admin-extend-field">
      <span>{at("user_traffic_grant_gb", {}, "GB to grant")}</span>
      <div class="admin-extend-control">
        <Input
          class="input"
          type="number"
          min="0"
          step="1"
          placeholder="0"
          aria-label={at("user_traffic_grant_gb", {}, "GB to grant")}
          bind:value={usersStore.grantTrafficGbDraft}
        />
        <AdminButton
          variant="primary"
          onclick={usersStore.grantTraffic}
          disabled={userActionBusy || !grantTrafficGbValid}
        >
          <Plus size={14} />
          {at("user_traffic_grant_submit", {}, "Grant")}
        </AdminButton>
      </div>
    </Label.Root>
  </div>
</section>
