<script lang="ts">
  import { getTariffsStore } from "$lib/admin/context";
  import { Input } from "$components/ui/index.js";
  import { Tabs, Switch, Label } from "$components/ui/primitives.js";
  import { AdminSelect } from "$components/patterns/admin/index.js";
  import { X } from "$components/ui/icons.js";
  import { normalizeUuidList } from "$lib/admin/tariffDraft";
  import type { PanelSquad, TariffDraft, TariffsCatalog } from "$lib/admin/stores/tariffsStore";
  import {
    addDraftSquad,
    conversionCurrencyLabel as formatConversionCurrencyLabel,
    defaultCurrencyCode as getDefaultCurrencyCode,
    draftInputHandler,
    panelSquadOptions as toPanelSquadOptions,
    type SelectOption,
    type TranslateFn,
  } from "./tariffEditorTabUtils.js";

  let { at }: { at: TranslateFn } = $props();

  const tariffsStore = getTariffsStore();
  const tariffsState = $derived(tariffsStore);
  const tariffDraft: TariffDraft = $derived(tariffsState.tariffDraft);
  const panelSquadsLoading = $derived(Boolean(tariffsState.panelSquadsLoading));
  const panelSquads: PanelSquad[] = $derived(tariffsState.panelSquads || []);
  const tariffsCatalog: TariffsCatalog = $derived(tariffsState.tariffsCatalog);
  const billingModelOptions: SelectOption[] = $derived([
    { value: "period", label: at("tariff_model_period_label", {}, "Period") },
    { value: "traffic", label: at("tariff_model_traffic_label", {}, "Traffic") },
  ]);
  const panelSquadOptions: SelectOption[] = $derived(toPanelSquadOptions(panelSquads));
  const defaultCurrencyCode = $derived(getDefaultCurrencyCode(tariffsCatalog));
  const conversionCurrencyLabel = $derived(formatConversionCurrencyLabel(at, defaultCurrencyCode));

  function setDraftField(field: string, value: unknown): void {
    tariffsStore.updateDraftField(field, value);
  }

  function setBillingModel(value: string): void {
    setDraftField("billing_model", value);
  }

  function addBaseSquad(value: string): void {
    addDraftSquad(tariffsStore, "squadUuids", value);
  }
</script>

<Tabs.Content value="general" class="admin-tabs-content">
  <div class="admin-form-row admin-form-row-2">
    <Label.Root class="admin-field-label">
      <span>{at("tariff_label_key", {}, "Tariff key")}</span>
      <small
        >{at(
          "tariff_hint_key",
          {},
          "Latin characters, no spaces. Used in payments and subscriptions; changing it after publication is not recommended"
        )}</small
      >
      <Input
        class="input"
        type="text"
        placeholder="standard"
        value={tariffDraft.key}
        oninput={draftInputHandler(tariffsStore, "key")}
      />
    </Label.Root>

    <div class="admin-field-label">
      <span>{at("tariff_label_model", {}, "Billing model")}</span>
      <small
        ><b>{at("tariff_model_period_label", {}, "Period")}</b> — {at(
          "tariff_model_period_desc",
          {},
          "the user buys a fixed period (1/3/12 months, etc.)"
        )}. <b>{at("tariff_model_traffic_label", {}, "Traffic")}</b> — {at(
          "tariff_model_traffic_desc",
          {},
          "the user buys gigabyte packages at a fixed price per GB"
        )}</small
      >
      <AdminSelect
        value={String(tariffDraft.billing_model || "period")}
        items={billingModelOptions}
        ariaLabel={at("tariff_label_model", {}, "Billing model")}
        onValueChange={setBillingModel}
      />
    </div>
  </div>

  <div class="admin-action-row admin-action-row-bordered">
    <Switch.Root
      aria-labelledby="tariff-enabled-toggle-label"
      checked={tariffDraft.enabled}
      onCheckedChange={(value) => setDraftField("enabled", value)}
      class="admin-switch-root"
    >
      <Switch.Thumb class="admin-switch-thumb" />
    </Switch.Root>
    <Label.Root id="tariff-enabled-toggle-label" class="admin-action-label">
      <strong
        >{tariffDraft.enabled
          ? at("tariff_visible", {}, "Tariff is visible in the storefront")
          : at("tariff_hidden", {}, "Tariff is hidden from users")}</strong
      >
      <small
        >{at(
          "tariff_enabled_hint",
          {},
          "A disabled tariff is hidden from the bot/Mini App, but active subscriptions on it keep working"
        )}</small
      >
    </Label.Root>
  </div>

  <div class="admin-form-row admin-form-row-2">
    <Label.Root class="admin-field-label">
      <span>{at("tariff_label_name_ru", {}, "Name - RU")}</span>
      <Input
        class="input"
        type="text"
        placeholder={at("tariff_placeholder_name_ru", {}, "Standard")}
        value={tariffDraft.nameRu}
        oninput={draftInputHandler(tariffsStore, "nameRu")}
      />
    </Label.Root>
    <Label.Root class="admin-field-label">
      <span>{at("tariff_label_name_en", {}, "Name - EN")}</span>
      <Input
        class="input"
        type="text"
        placeholder={at("tariff_placeholder_name_en", {}, "Standard")}
        value={tariffDraft.nameEn}
        oninput={draftInputHandler(tariffsStore, "nameEn")}
      />
    </Label.Root>
  </div>

  <div class="admin-form-row admin-form-row-2">
    <Label.Root class="admin-field-label">
      <span>{at("tariff_label_desc_ru", {}, "Description - RU")}</span>
      <Input
        class="input"
        type="text"
        placeholder={at("tariff_placeholder_desc_ru", {}, "Base server pool")}
        value={tariffDraft.descriptionRu}
        oninput={draftInputHandler(tariffsStore, "descriptionRu")}
      />
    </Label.Root>
    <Label.Root class="admin-field-label">
      <span>{at("tariff_label_desc_en", {}, "Description - EN")}</span>
      <Input
        class="input"
        type="text"
        placeholder={at("tariff_placeholder_desc_en", {}, "Base server pool")}
        value={tariffDraft.descriptionEn}
        oninput={draftInputHandler(tariffsStore, "descriptionEn")}
      />
    </Label.Root>
  </div>

  <div class="admin-field-label">
    <span>{at("tariff_label_squads", {}, "Base Internal Squads")}</span>
    <small
      >{panelSquadsLoading
        ? at("loading_squads", {}, "Loading list from panel...")
        : at(
            "tariff_hint_squads",
            {},
            "Remnawave squads this tariff connects the user to. Select one or more"
          )}</small
    >
    <AdminSelect
      bind:value={tariffsStore.selectedBaseSquad}
      items={panelSquadOptions}
      placeholder={at("btn_add_squad", {}, "Add squad")}
      ariaLabel={at("btn_add_squad", {}, "Add squad")}
      onValueChange={addBaseSquad}
    />
    <div class="admin-chip-list">
      {#each normalizeUuidList(tariffDraft.squadUuids) as uuid}
        <button
          type="button"
          class="admin-chip"
          onclick={() => tariffsStore.removeSquadFromDraft("squadUuids", uuid)}
        >
          {tariffsStore.squadLabel(uuid)}
          <X size={12} />
        </button>
      {/each}
    </div>
  </div>

  <div class="admin-form-row admin-form-row-2">
    <Label.Root class="admin-field-label">
      <span>{at("tariff_label_hwid", {}, "Device limit (HWID)")}</span>
      <small
        >{at(
          "tariff_hint_hwid",
          {},
          "How many devices can use the subscription at the same time. Empty means use the .env value; 0 means unlimited"
        )}</small
      >
      <Input
        class="input"
        type="number"
        min="0"
        placeholder="5"
        value={tariffDraft.hwid_device_limit}
        oninput={draftInputHandler(tariffsStore, "hwid_device_limit")}
      />
    </Label.Root>
    {#if tariffDraft.billing_model === "period"}
      <Label.Root class="admin-field-label">
        <span>{at("tariff_label_traffic_limit", {}, "Monthly traffic limit, GB")}</span>
        <small
          >{at(
            "tariff_hint_traffic_limit",
            {},
            "How many GB are included every month. 0 means unlimited traffic. Extra packages can be sold on the Top-ups tab"
          )}</small
        >
        <Input
          class="input"
          type="number"
          min="0"
          step="0.1"
          placeholder="100"
          value={tariffDraft.monthly_gb}
          oninput={draftInputHandler(tariffsStore, "monthly_gb")}
        />
      </Label.Root>
    {:else}
      <Label.Root class="admin-field-label">
        <span>{conversionCurrencyLabel}</span>
        <small
          >{at(
            "tariff_hint_conversion",
            {},
            "This rate converts the remaining subscription period to gigabytes when a user switches from Period to Traffic"
          )}</small
        >
        <Input
          class="input"
          type="number"
          min="0"
          step="0.01"
          placeholder="20"
          value={tariffDraft.conversion_rate_rub_per_gb}
          oninput={draftInputHandler(tariffsStore, "conversion_rate_rub_per_gb")}
        />
      </Label.Root>
    {/if}
  </div>
</Tabs.Content>
