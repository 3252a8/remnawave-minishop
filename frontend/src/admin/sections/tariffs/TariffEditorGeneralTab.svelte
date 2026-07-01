<script lang="ts">
  import { getTariffsStore } from "$lib/admin/context";
  import { Input } from "$components/ui/index.js";
  import { Tabs, Switch, Label } from "$components/ui/primitives.js";
  import { AdminSelect } from "$components/patterns/admin/index.js";
  import { X } from "$components/ui/icons.js";
  import { normalizeUuidList } from "$lib/admin/tariffDraft.js";
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
    { value: "period", label: at("tariff_model_period_label", {}, "Период") },
    { value: "traffic", label: at("tariff_model_traffic_label", {}, "Трафик") },
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
      <span>{at("tariff_label_key", {}, "Ключ тарифа")}</span>
      <small
        >{at(
          "tariff_hint_key",
          {},
          "Латиницей, без пробелов. Используется в платежах и подписках, менять после публикации не рекомендуется"
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
      <span>{at("tariff_label_model", {}, "Модель тарификации")}</span>
      <small
        ><b>{at("tariff_model_period_label", {}, "Период")}</b> — {at(
          "tariff_model_period_desc",
          {},
          "пользователь покупает фиксированный срок (1/3/12 мес. и т.д.)"
        )}. <b>{at("tariff_model_traffic_label", {}, "Трафик")}</b> — {at(
          "tariff_model_traffic_desc",
          {},
          "пользователь покупает пакеты гигабайт по фиксированной цене за GB"
        )}</small
      >
      <AdminSelect
        value={String(tariffDraft.billing_model || "period")}
        items={billingModelOptions}
        ariaLabel={at("tariff_label_model", {}, "Модель")}
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
          ? at("tariff_visible", {}, "Тариф виден на витрине")
          : at("tariff_hidden", {}, "Тариф скрыт от пользователей")}</strong
      >
      <small
        >{at(
          "tariff_enabled_hint",
          {},
          "Выключенный тариф не показывается в боте/мини-аппе, но активные подписки на нём продолжают работать"
        )}</small
      >
    </Label.Root>
  </div>

  <div class="admin-form-row admin-form-row-2">
    <Label.Root class="admin-field-label">
      <span>{at("tariff_label_name_ru", {}, "Название · RU")}</span>
      <Input
        class="input"
        type="text"
        placeholder={at("tariff_placeholder_name_ru", {}, "Стандарт")}
        value={tariffDraft.nameRu}
        oninput={draftInputHandler(tariffsStore, "nameRu")}
      />
    </Label.Root>
    <Label.Root class="admin-field-label">
      <span>{at("tariff_label_name_en", {}, "Название · EN")}</span>
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
      <span>{at("tariff_label_desc_ru", {}, "Описание · RU")}</span>
      <Input
        class="input"
        type="text"
        placeholder={at("tariff_placeholder_desc_ru", {}, "Базовый набор серверов")}
        value={tariffDraft.descriptionRu}
        oninput={draftInputHandler(tariffsStore, "descriptionRu")}
      />
    </Label.Root>
    <Label.Root class="admin-field-label">
      <span>{at("tariff_label_desc_en", {}, "Описание · EN")}</span>
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
    <span>{at("tariff_label_squads", {}, "Базовые Internal Squads")}</span>
    <small
      >{panelSquadsLoading
        ? at("loading_squads", {}, "Загружаю список из панели…")
        : at(
            "tariff_hint_squads",
            {},
            "Сквады Remnawave, к которым подключается пользователь по этому тарифу. Выберите один или несколько"
          )}</small
    >
    <AdminSelect
      bind:value={tariffsStore.selectedBaseSquad}
      items={panelSquadOptions}
      placeholder={at("btn_add_squad", {}, "Добавить сквад")}
      ariaLabel={at("btn_add_squad", {}, "Добавить основной сквад")}
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
      <span>{at("tariff_label_hwid", {}, "Лимит устройств (HWID)")}</span>
      <small
        >{at(
          "tariff_hint_hwid",
          {},
          "Сколько устройств может одновременно использовать подписку. Пусто — взять значение из .env, 0 — без ограничений"
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
        <span>{at("tariff_label_traffic_limit", {}, "Месячный лимит трафика, GB")}</span>
        <small
          >{at(
            "tariff_hint_traffic_limit",
            {},
            "Сколько GB включено в тариф на каждый месяц. 0 — безлимитный трафика. Сверху можно докупать пакеты на вкладке «Докупки»"
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
            "По этому курсу остаток подписки пересчитывается в гигабайты при переходе пользователя с тарифа «Период» на «Трафик»"
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
