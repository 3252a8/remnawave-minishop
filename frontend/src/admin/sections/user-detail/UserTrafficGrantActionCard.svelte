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
      label: at("user_traffic_grant_kind_regular", {}, "Обычный"),
    },
    {
      value: "premium",
      label: at("user_traffic_grant_kind_premium", {}, "Премиум"),
    },
  ]);
</script>

<section class="admin-user-action-sheet admin-user-action-sheet--traffic-grant">
  <AdminSectionHeader
    title={at("user_traffic_grant_title", {}, "Выдать трафик")}
    description={at(
      "user_traffic_grant_hint",
      {},
      "Зачисление ГБ на баланс пользователя — как при докупке, но без оплаты. Лимит и сквады в панели обновятся сразу."
    )}
  />
  <div class="admin-user-action-sheet-body admin-user-grant-stack">
    <Label.Root class="admin-field-label admin-extend-field">
      <span>{at("user_traffic_grant_kind", {}, "Тип трафика")}</span>
      <AdminSelect
        class="admin-grant-kind-select"
        value={usersStore.grantTrafficKindDraft}
        items={grantTrafficKindItems}
        onValueChange={selectGrantTrafficKind}
        ariaLabel={at("user_traffic_grant_kind", {}, "Тип трафика")}
      />
    </Label.Root>
    <Label.Root class="admin-field-label admin-extend-field">
      <span>{at("user_traffic_grant_gb", {}, "ГБ к выдаче")}</span>
      <div class="admin-extend-control">
        <Input
          class="input"
          type="number"
          min="0"
          step="1"
          placeholder="0"
          aria-label={at("user_traffic_grant_gb", {}, "ГБ к выдаче")}
          bind:value={usersStore.grantTrafficGbDraft}
        />
        <AdminButton
          variant="primary"
          onclick={usersStore.grantTraffic}
          disabled={userActionBusy || !grantTrafficGbValid}
        >
          <Plus size={14} />
          {at("user_traffic_grant_submit", {}, "Выдать")}
        </AdminButton>
      </div>
    </Label.Root>
  </div>
</section>
