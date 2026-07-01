<script lang="ts">
  import { getTariffsStore } from "$lib/admin/context";
  import { Tabs } from "$components/ui/primitives.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { Save, Trash2 } from "$components/ui/icons.js";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import TariffEditorGeneralTab from "./tariffs/TariffEditorGeneralTab.svelte";
  import TariffEditorHwidTab from "./tariffs/TariffEditorHwidTab.svelte";
  import TariffEditorPremiumTab from "./tariffs/TariffEditorPremiumTab.svelte";
  import TariffEditorPricingTab from "./tariffs/TariffEditorPricingTab.svelte";
  import TariffEditorTopupTab from "./tariffs/TariffEditorTopupTab.svelte";
  import type { Tariff } from "$lib/admin/stores/tariffsStore";
  import type { TranslateFn } from "./tariffs/tariffEditorTabUtils.js";

  let { at }: { at: TranslateFn } = $props();
  const tariffsStore = getTariffsStore();

  const tariffsState = $derived(tariffsStore);
  const tariffEditorOpen = $derived(Boolean(tariffsState.tariffEditorOpen));
  const tariffEditingKey = $derived(String(tariffsState.tariffEditingKey || ""));
  const tariffsSaving = $derived(Boolean(tariffsState.tariffsSaving));
  const tariffDeleteOpen = $derived(Boolean(tariffsState.tariffDeleteOpen));
  const tariffDeleteTarget: Tariff | null = $derived(tariffsState.tariffDeleteTarget);
</script>

<Dialog
  open={tariffEditorOpen}
  title={tariffEditingKey
    ? at("tariff_edit_title", {}, "Настройка тарифа")
    : at("tariff_create_title", {}, "Новый тариф")}
  description={tariffEditingKey ||
    at("tariff_create_subtitle", {}, "Каталог будет сохранён в JSON после подтверждения")}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={() => tariffsStore.updateState({ tariffEditorOpen: false })}
  class="admin-dialog admin-tariff-dialog"
>
  <div class="admin-tariff-dialog-stack">
    <Tabs.Root bind:value={tariffsStore.tariffEditorTab} class="admin-tabs-root">
      <Tabs.List class="admin-tabs-list">
        <Tabs.Trigger value="general" class="admin-tabs-trigger"
          >{at("tariff_tab_general", {}, "Основное")}</Tabs.Trigger
        >
        <Tabs.Trigger value="pricing" class="admin-tabs-trigger"
          >{at("tariff_tab_pricing", {}, "Цены")}</Tabs.Trigger
        >
        <Tabs.Trigger value="topup" class="admin-tabs-trigger"
          >{at("tariff_tab_topup", {}, "Докупки")}</Tabs.Trigger
        >
        <Tabs.Trigger value="premium" class="admin-tabs-trigger"
          >{at("tariff_tab_premium", {}, "Premium")}</Tabs.Trigger
        >
        <Tabs.Trigger value="hwid" class="admin-tabs-trigger"
          >{at("tariff_tab_hwid", {}, "Устройства")}</Tabs.Trigger
        >
      </Tabs.List>

      <TariffEditorGeneralTab {at} />
      <TariffEditorPremiumTab {at} />
      <TariffEditorPricingTab {at} />
      <TariffEditorTopupTab {at} />
      <TariffEditorHwidTab {at} />
    </Tabs.Root>

    <div class="admin-dialog-actions">
      <AdminButton onclick={() => tariffsStore.updateState({ tariffEditorOpen: false })}
        >{at("btn_cancel", {}, "Отмена")}</AdminButton
      >
      <AdminButton
        variant="primary"
        onclick={tariffsStore.saveTariffDraft}
        disabled={tariffsSaving}
      >
        <Save size={14} />
        {tariffsSaving
          ? at("btn_saving", {}, "Сохранение...")
          : at("btn_save_tariff", {}, "Сохранить тариф")}
      </AdminButton>
    </div>
  </div>
</Dialog>

<Dialog
  open={tariffDeleteOpen}
  title={at("tariff_delete_title", {}, "Удалить тариф?")}
  description={tariffDeleteTarget
    ? at(
        "tariff_delete_subtitle",
        { key: tariffDeleteTarget.key },
        `Тариф ${tariffDeleteTarget.key} исчезнет из каталога продаж.`
      )
    : ""}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={() => tariffsStore.updateState({ tariffDeleteOpen: false })}
  class="admin-dialog admin-tariff-delete-dialog"
>
  <div class="admin-form-row">
    <AdminButton onclick={() => tariffsStore.updateState({ tariffDeleteOpen: false })}
      >{at("btn_cancel", {}, "Отмена")}</AdminButton
    >
    <AdminButton variant="danger" onclick={tariffsStore.deleteTariff} disabled={tariffsSaving}>
      <Trash2 size={14} />
      {at("btn_confirm_delete", {}, "Подтвердить удаление")}
    </AdminButton>
  </div>
</Dialog>
