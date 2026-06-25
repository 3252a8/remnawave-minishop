<script lang="ts">
  import { Input, Sortable } from "$components/ui/index.js";
  import { Tabs, Switch, Label } from "$components/ui/primitives.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { Plus, Save, Trash2, X } from "$components/ui/icons.js";
  import { AdminButton, AdminSelect } from "$components/patterns/admin/index.js";
  import { getContext } from "svelte";
  import { normalizeCurrencyKey, normalizeUuidList } from "../../lib/admin/tariffDraft.js";
  import type {
    DraftRowsField,
    DraftSquadField,
    PanelSquad,
    Tariff,
    TariffDraft,
    TariffsCatalog,
    TariffsStore,
  } from "$lib/admin/stores/tariffsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type SelectOption = { value: string; label: string };
  type ComponentCallback = (...args: never[]) => void;
  type DraftRow = Record<string, string | number | undefined>;

  export let at: TranslateFn;
  const tariffsStore = getContext<TariffsStore>("tariffsStore");

  let tariffEditorOpen = false;
  let tariffEditingKey = "";
  let tariffDraft: TariffDraft;
  let tariffsSaving = false;
  let tariffDeleteOpen = false;
  let tariffDeleteTarget: Tariff | null = null;
  let panelSquadsLoading = false;
  let panelSquads: PanelSquad[] = [];
  let tariffsCatalog: TariffsCatalog;
  let billingModelOptions: SelectOption[] = [];
  let panelSquadOptions: SelectOption[] = [];
  let defaultCurrencyKey = "rub";
  let defaultCurrencyCode = "RUB";
  let currencyPriceColumnLabel = "";
  let currencyPriceAriaLabel = "";
  let conversionCurrencyLabel = "";

  $: ({
    tariffEditorOpen,
    tariffEditingKey,
    tariffDraft,
    tariffsSaving,
    tariffDeleteOpen,
    tariffDeleteTarget,
    panelSquadsLoading,
    panelSquads,
    tariffsCatalog,
  } = $tariffsStore);

  $: billingModelOptions = [
    { value: "period", label: at("tariff_model_period_label", {}, "Период") },
    { value: "traffic", label: at("tariff_model_traffic_label", {}, "Трафик") },
  ];
  $: panelSquadOptions = (panelSquads || []).map((squad) => ({
    value: squad.uuid,
    label: squad.name,
  }));
  $: defaultCurrencyKey = normalizeCurrencyKey(tariffsCatalog?.default_currency || "rub") as string;
  $: defaultCurrencyCode = defaultCurrencyKey.toUpperCase();
  $: currencyPriceColumnLabel = at(
    "tariff_col_price_currency",
    { currency: defaultCurrencyCode },
    `Цена, ${defaultCurrencyCode}`
  );
  $: currencyPriceAriaLabel = at(
    "tariff_label_price_currency",
    { currency: defaultCurrencyCode },
    `Цена в ${defaultCurrencyCode}`
  );
  $: conversionCurrencyLabel = at(
    "tariff_label_conversion_currency",
    { currency: defaultCurrencyCode },
    `Курс конвертации, ${defaultCurrencyCode} за 1 GB`
  );
  function addDraftSquad(field: DraftSquadField, value: string): void {
    tariffsStore.addSquadToDraft(field, value);
    tariffsStore.update((state) => ({
      ...state,
      selectedBaseSquad: field === "squadUuids" ? "" : state.selectedBaseSquad,
      selectedPremiumSquad: field === "premiumSquadUuids" ? "" : state.selectedPremiumSquad,
    }));
  }

  const addBaseSquad = ((value: string) => addDraftSquad("squadUuids", value)) as ComponentCallback;
  const addPremiumSquad = ((value: string) =>
    addDraftSquad("premiumSquadUuids", value)) as ComponentCallback;

  function moveDraftRow(field: DraftRowsField, from: number, to: number): void {
    tariffsStore.moveDraftRow(field, from, to);
  }

  function addPackageRow(field: DraftRowsField, row: DraftRow): void {
    tariffsStore.addDraftRow(field, row);
  }

  const movePremiumTopupRow = ((from: number, to: number) =>
    moveDraftRow("premiumTopupRows", from, to)) as ComponentCallback;
  const movePeriodRow = ((from: number, to: number) =>
    moveDraftRow("periodRows", from, to)) as ComponentCallback;
  const moveTrafficRow = ((from: number, to: number) =>
    moveDraftRow("trafficRows", from, to)) as ComponentCallback;
  const moveTopupRow = ((from: number, to: number) =>
    moveDraftRow("topupRows", from, to)) as ComponentCallback;
  const moveHwidRow = ((from: number, to: number) =>
    moveDraftRow("hwidRows", from, to)) as ComponentCallback;
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
  <Tabs.Root bind:value={$tariffsStore.tariffEditorTab} class="admin-tabs-root">
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
            bind:value={$tariffsStore.tariffDraft.key}
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
            bind:value={$tariffsStore.tariffDraft.billing_model}
            items={billingModelOptions}
            ariaLabel={at("tariff_label_model", {}, "Модель")}
          />
        </div>
      </div>

      <div class="admin-action-row admin-action-row-bordered">
        <Switch.Root
          checked={tariffDraft.enabled}
          onCheckedChange={(v) => (tariffDraft.enabled = v)}
          class="admin-switch-root"
        >
          <Switch.Thumb class="admin-switch-thumb" />
        </Switch.Root>
        <Label.Root class="admin-action-label">
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
            bind:value={$tariffsStore.tariffDraft.nameRu}
          />
        </Label.Root>
        <Label.Root class="admin-field-label">
          <span>{at("tariff_label_name_en", {}, "Название · EN")}</span>
          <Input
            class="input"
            type="text"
            placeholder={at("tariff_placeholder_name_en", {}, "Standard")}
            bind:value={$tariffsStore.tariffDraft.nameEn}
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
            bind:value={$tariffsStore.tariffDraft.descriptionRu}
          />
        </Label.Root>
        <Label.Root class="admin-field-label">
          <span>{at("tariff_label_desc_en", {}, "Описание · EN")}</span>
          <Input
            class="input"
            type="text"
            placeholder={at("tariff_placeholder_desc_en", {}, "Base server pool")}
            bind:value={$tariffsStore.tariffDraft.descriptionEn}
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
          bind:value={$tariffsStore.selectedBaseSquad}
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
              on:click={() => tariffsStore.removeSquadFromDraft("squadUuids", uuid)}
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
            bind:value={$tariffsStore.tariffDraft.hwid_device_limit}
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
              bind:value={$tariffsStore.tariffDraft.monthly_gb}
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
              bind:value={$tariffsStore.tariffDraft.conversion_rate_rub_per_gb}
            />
          </Label.Root>
        {/if}
      </div>
    </Tabs.Content>

    <Tabs.Content value="premium" class="admin-tabs-content">
      <section class="admin-editor-section">
        <header class="admin-editor-section-head">
          <div class="admin-editor-section-title">
            <strong
              >{at("tariff_premium_head", {}, "Premium-доступ и отдельный счётчик трафика")}</strong
            >
            <small
              >{at(
                "tariff_premium_subhead",
                {},
                "Premium-сквады дают пользователю доступ к более быстрым/премиальным нодам; их трафик считается отдельно от основного, чтобы можно было ограничить или продавать дополнительно"
              )}</small
            >
          </div>
        </header>
        <div class="admin-form-row admin-form-row-2">
          <Label.Root class="admin-field-label">
            <span>{at("tariff_label_premium_name_ru", {}, "Название premium-раздела, RU")}</span>
            <small
              >{at(
                "tariff_hint_premium_name_ru",
                {},
                "Эта строка заменит «Premium-серверы» в кабинете, докупках и карточках лимитов."
              )}</small
            >
            <Input
              class="input"
              type="text"
              placeholder={at("tariff_placeholder_premium_name_ru", {}, "Premium-серверы")}
              bind:value={$tariffsStore.tariffDraft.premiumNameRu}
            />
          </Label.Root>
          <Label.Root class="admin-field-label">
            <span>{at("tariff_label_premium_name_en", {}, "Название premium-раздела, EN")}</span>
            <small
              >{at(
                "tariff_hint_premium_name_en",
                {},
                "Опционально для английского интерфейса."
              )}</small
            >
            <Input
              class="input"
              type="text"
              placeholder={at("tariff_placeholder_premium_name_en", {}, "Premium servers")}
              bind:value={$tariffsStore.tariffDraft.premiumNameEn}
            />
          </Label.Root>
        </div>
        <div class="admin-form-row admin-form-row-2">
          <div class="admin-field-label">
            <span>{at("tariff_label_premium_squads", {}, "Premium Internal Squads")}</span>
            <small
              >{at(
                "tariff_hint_premium_squads",
                {},
                "Сквады из Remnawave, доступные только владельцам этого тарифа. Трафик считается по их accessible nodes"
              )}</small
            >
            <AdminSelect
              bind:value={$tariffsStore.selectedPremiumSquad}
              items={panelSquadOptions}
              placeholder={at("btn_add_premium_squad", {}, "Добавить premium-сквад")}
              ariaLabel={at("btn_add_premium_squad", {}, "Добавить premium-сквад")}
              onValueChange={addPremiumSquad}
            />
            <div class="admin-chip-list">
              {#each normalizeUuidList(tariffDraft.premiumSquadUuids) as uuid}
                <button
                  type="button"
                  class="admin-chip"
                  on:click={() => tariffsStore.removeSquadFromDraft("premiumSquadUuids", uuid)}
                >
                  {tariffsStore.squadLabel(uuid)}
                  <X size={12} />
                </button>
              {/each}
            </div>
          </div>
          <Label.Root class="admin-field-label">
            <span
              >{at(
                "tariff_label_premium_traffic_limit",
                {},
                "Месячный лимит premium-трафика, GB"
              )}</span
            >
            <small
              >{at(
                "tariff_hint_premium_traffic_limit",
                {},
                "Сколько GB через premium-сквады включено в тариф каждый месяц. 0 или пусто — отдельного premium-лимита нет (premium-нодами можно пользоваться без ограничения)"
              )}</small
            >
            <Input
              class="input"
              type="number"
              min="0"
              step="0.1"
              placeholder="50"
              bind:value={$tariffsStore.tariffDraft.premium_monthly_gb}
            />
          </Label.Root>
        </div>
      </section>

      <section class="admin-editor-section">
        <header class="admin-editor-section-head">
          <div class="admin-editor-section-title">
            <strong>{at("tariff_premium_topup_title", {}, "Докупка premium-трафика")}</strong>
            <small
              >{at(
                "tariff_premium_topup_subtitle",
                {},
                "Пакеты для расширения месячного premium-лимита, когда пользователь его исчерпал"
              )}</small
            >
          </div>
          <div class="admin-editor-section-actions">
            <AdminButton
              size="sm"
              onclick={() => addPackageRow("premiumTopupRows", { gb: 10, price: "", stars: "" })}
              ><Plus size={12} /> {at("tariff_btn_package", {}, "Пакет")}</AdminButton
            >
          </div>
        </header>
        {#if tariffDraft.premiumTopupRows.length}
          <div class="admin-row-editor">
            <div class="admin-row-editor-line admin-row-editor-drag admin-row-editor-header">
              <span></span>
              <span>{at("tariff_col_volume_gb", {}, "Объём, GB")}</span>
              <span>{currencyPriceColumnLabel}</span>
              <span>{at("tariff_col_price_stars_full", {}, "Цена, ⭐ Stars")}</span>
              <span></span>
            </div>
            <Sortable
              items={tariffDraft.premiumTopupRows}
              class="admin-row-editor-line admin-row-editor-drag"
              handleLabel={at("tariff_package_reorder", {}, "Перетащите, чтобы изменить порядок")}
              onReorder={movePremiumTopupRow}
            >
              {#snippet children(row: DraftRow, index: number)}
                <Input
                  class="input"
                  type="number"
                  min="0.1"
                  step="0.1"
                  placeholder="10"
                  bind:value={row.gb}
                  aria-label={at("tariff_col_volume_gb", {}, "Объём premium-пакета в GB")}
                />
                <Input
                  class="input"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="199"
                  bind:value={row.price}
                  aria-label={currencyPriceAriaLabel}
                />
                <Input
                  class="input"
                  type="number"
                  min="0"
                  step="1"
                  placeholder="100"
                  bind:value={row.stars}
                  aria-label={at(
                    "tariff_label_price_stars",
                    {},
                    "Цена premium-пакета в Telegram Stars"
                  )}
                />
                <AdminButton
                  size="sm"
                  variant="danger"
                  onclick={() => tariffsStore.removeDraftRow("premiumTopupRows", index)}
                  aria-label={at("btn_delete", {}, "Удалить")}><Trash2 size={13} /></AdminButton
                >
              {/snippet}
            </Sortable>
          </div>
        {/if}
      </section>
    </Tabs.Content>

    <Tabs.Content value="pricing" class="admin-tabs-content">
      {#if tariffDraft.billing_model === "period"}
        <section class="admin-editor-section">
          <header class="admin-editor-section-head">
            <div class="admin-editor-section-title">
              <strong>{at("tariff_pricing_period_title", {}, "Периоды подписки и цены")}</strong>
              <small
                >{at(
                  "tariff_pricing_period_subtitle",
                  {},
                  "Каждая строка — отдельный вариант на витрине: за сколько месяцев пользователь платит и сколько это стоит"
                )}</small
              >
            </div>
            <AdminButton
              size="sm"
              onclick={() =>
                addPackageRow("periodRows", {
                  months: 1,
                  rub: "",
                  stars: "",
                  referral_inviter: "",
                  referral_referee: "",
                })}
            >
              <Plus size={13} />
              {at("tariff_btn_period", {}, "Период")}
            </AdminButton>
          </header>
          {#if !tariffDraft.periodRows.length}
            <p class="admin-muted">
              {at(
                "tariff_pricing_empty",
                {},
                "Добавьте хотя бы один период — без него тариф не появится на витрине."
              )}
            </p>
          {:else}
            <div class="admin-row-editor">
              <div class="admin-row-editor-line admin-row-editor-period admin-row-editor-header">
                <span></span>
                <span>{at("tariff_col_period_months", {}, "Срок, мес.")}</span>
                <span>{currencyPriceColumnLabel}</span>
                <span>{at("tariff_col_price_stars_full", {}, "Цена, ⭐ Stars")}</span>
                <span>{at("tariff_col_ref_inviter", {}, "Бонус приглашающему")}</span>
                <span>{at("tariff_col_ref_referee", {}, "Бонус приглашённому")}</span>
                <span></span>
              </div>
              <Sortable
                items={tariffDraft.periodRows}
                class="admin-row-editor-line admin-row-editor-period"
                handleLabel={at("tariff_period_reorder", {}, "Перетащите, чтобы изменить порядок")}
                onReorder={movePeriodRow}
              >
                {#snippet children(row: DraftRow, index: number)}
                  <Input
                    class="input"
                    type="number"
                    min="1"
                    placeholder="1"
                    bind:value={row.months}
                    aria-label={at("tariff_col_period_months", {}, "Срок (месяцы)")}
                  />
                  <Input
                    class="input"
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="299"
                    bind:value={row.rub}
                    aria-label={currencyPriceAriaLabel}
                  />
                  <Input
                    class="input"
                    type="number"
                    min="0"
                    step="1"
                    placeholder="150"
                    bind:value={row.stars}
                    aria-label={at("tariff_label_price_stars", {}, "Цена в Telegram Stars")}
                  />
                  <Input
                    class="input"
                    type="number"
                    min="0"
                    step="1"
                    placeholder="3"
                    bind:value={row.referral_inviter}
                    aria-label={at("tariff_label_ref_inviter", {}, "Бонус приглашающему")}
                  />
                  <Input
                    class="input"
                    type="number"
                    min="0"
                    step="1"
                    placeholder="1"
                    bind:value={row.referral_referee}
                    aria-label={at("tariff_label_ref_referee", {}, "Бонус приглашённому")}
                  />
                  <AdminButton
                    size="sm"
                    variant="danger"
                    onclick={() => tariffsStore.removeDraftRow("periodRows", index)}
                    aria-label={at("btn_delete", {}, "Удалить")}
                  >
                    <Trash2 size={13} />
                  </AdminButton>
                {/snippet}
              </Sortable>
            </div>
          {/if}
        </section>
      {:else}
        <section class="admin-editor-section">
          <header class="admin-editor-section-head">
            <div class="admin-editor-section-title">
              <strong>{at("tariff_pricing_traffic_title", {}, "Пакеты трафика")}</strong>
              <small
                >{at(
                  "tariff_pricing_traffic_subtitle",
                  {},
                  "Базовая витрина для трафиковой модели. Каждая строка — пакет «N гигабайт за N единиц валюты»"
                )}</small
              >
            </div>
            <div class="admin-editor-section-actions">
              <AdminButton
                size="sm"
                onclick={() => addPackageRow("trafficRows", { gb: 10, price: "", stars: "" })}
                ><Plus size={12} /> {at("tariff_btn_package", {}, "Пакет")}</AdminButton
              >
            </div>
          </header>
          {#if tariffDraft.trafficRows.length}
            <div class="admin-row-editor">
              <div class="admin-row-editor-line admin-row-editor-drag admin-row-editor-header">
                <span></span>
                <span>{at("tariff_col_volume_gb", {}, "Объём, GB")}</span>
                <span>{currencyPriceColumnLabel}</span>
                <span>{at("tariff_col_price_stars_full", {}, "Цена, ⭐ Stars")}</span>
                <span></span>
              </div>
              <Sortable
                items={tariffDraft.trafficRows}
                class="admin-row-editor-line admin-row-editor-drag"
                handleLabel={at("tariff_package_reorder", {}, "Перетащите, чтобы изменить порядок")}
                onReorder={moveTrafficRow}
              >
                {#snippet children(row: DraftRow, index: number)}
                  <Input
                    class="input"
                    type="number"
                    min="0.1"
                    step="0.1"
                    placeholder="50"
                    bind:value={row.gb}
                    aria-label={at("tariff_col_volume_gb", {}, "Объём пакета в GB")}
                  />
                  <Input
                    class="input"
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="299"
                    bind:value={row.price}
                    aria-label={currencyPriceAriaLabel}
                  />
                  <Input
                    class="input"
                    type="number"
                    min="0"
                    step="1"
                    placeholder="150"
                    bind:value={row.stars}
                    aria-label={at("tariff_label_price_stars", {}, "Цена пакета в Telegram Stars")}
                  />
                  <AdminButton
                    size="sm"
                    variant="danger"
                    onclick={() => tariffsStore.removeDraftRow("trafficRows", index)}
                    aria-label={at("btn_delete", {}, "Удалить")}><Trash2 size={13} /></AdminButton
                  >
                {/snippet}
              </Sortable>
            </div>
          {/if}
        </section>
      {/if}
    </Tabs.Content>

    <Tabs.Content value="topup" class="admin-tabs-content">
      {#if tariffDraft.billing_model === "period"}
        <section class="admin-editor-section">
          <header class="admin-editor-section-head">
            <div class="admin-editor-section-title">
              <strong
                >{at("tariff_topup_title", {}, "Докупка трафика поверх месячного лимита")}</strong
              >
              <small
                >{at(
                  "tariff_topup_subtitle",
                  {},
                  "Когда у пользователя кончился месячный лимит, ему предложат купить дополнительный пакет, не меняя срок подписки"
                )}</small
              >
            </div>
            <div class="admin-editor-section-actions">
              <AdminButton
                size="sm"
                onclick={() => addPackageRow("topupRows", { gb: 10, price: "", stars: "" })}
                ><Plus size={12} /> {at("tariff_btn_package", {}, "Пакет")}</AdminButton
              >
            </div>
          </header>
          {#if tariffDraft.topupRows.length}
            <div class="admin-row-editor">
              <div class="admin-row-editor-line admin-row-editor-drag admin-row-editor-header">
                <span></span>
                <span>{at("tariff_col_volume_gb", {}, "Объём, GB")}</span>
                <span>{currencyPriceColumnLabel}</span>
                <span>{at("tariff_col_price_stars_full", {}, "Цена, ⭐ Stars")}</span>
                <span></span>
              </div>
              <Sortable
                items={tariffDraft.topupRows}
                class="admin-row-editor-line admin-row-editor-drag"
                handleLabel={at("tariff_package_reorder", {}, "Перетащите, чтобы изменить порядок")}
                onReorder={moveTopupRow}
              >
                {#snippet children(row: DraftRow, index: number)}
                  <Input
                    class="input"
                    type="number"
                    min="0.1"
                    step="0.1"
                    placeholder="20"
                    bind:value={row.gb}
                    aria-label={at("tariff_col_volume_gb", {}, "Объём пакета в GB")}
                  />
                  <Input
                    class="input"
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="149"
                    bind:value={row.price}
                    aria-label={currencyPriceAriaLabel}
                  />
                  <Input
                    class="input"
                    type="number"
                    min="0"
                    step="1"
                    placeholder="75"
                    bind:value={row.stars}
                    aria-label={at("tariff_label_price_stars", {}, "Цена пакета в Telegram Stars")}
                  />
                  <AdminButton
                    size="sm"
                    variant="danger"
                    onclick={() => tariffsStore.removeDraftRow("topupRows", index)}
                    aria-label={at("btn_delete", {}, "Удалить")}><Trash2 size={13} /></AdminButton
                  >
                {/snippet}
              </Sortable>
            </div>
          {/if}
        </section>
      {:else}
        <p class="admin-muted">
          {at(
            "tariff_topup_traffic_hint",
            {},
            "Для трафиковой модели отдельные «докупки» не нужны — пакеты, которые вы настроили на вкладке «Цены», и являются докупками: пользователь покупает их повторно по мере исчерпания."
          )}
        </p>
      {/if}
    </Tabs.Content>

    <Tabs.Content value="hwid" class="admin-tabs-content">
      <section class="admin-editor-section">
        <header class="admin-editor-section-head">
          <div class="admin-editor-section-title">
            <strong
              >{at(
                "tariff_hwid_packages_title",
                {},
                "Пакеты дополнительных устройств (HWID)"
              )}</strong
            >
            <small
              >{at(
                "tariff_hwid_packages_subtitle",
                {},
                "Расширяет лимит, указанный во вкладке «Основное». Каждая строка — пакет «+N устройств за N единиц валюты»"
              )}</small
            >
          </div>
          <div class="admin-editor-section-actions">
            <AdminButton
              size="sm"
              onclick={() => addPackageRow("hwidRows", { count: 1, price: "", stars: "" })}
              ><Plus size={12} /> {at("tariff_btn_package", {}, "Пакет")}</AdminButton
            >
          </div>
        </header>
        {#if tariffDraft.hwidRows.length}
          <div class="admin-row-editor">
            <div class="admin-row-editor-line admin-row-editor-drag admin-row-editor-header">
              <span></span>
              <span>{at("tariff_col_hwid_count", {}, "+ устройств")}</span>
              <span>{currencyPriceColumnLabel}</span>
              <span>{at("tariff_col_price_stars_full", {}, "Цена, ⭐ Stars")}</span>
              <span></span>
            </div>
            <Sortable
              items={tariffDraft.hwidRows}
              class="admin-row-editor-line admin-row-editor-drag"
              handleLabel={at("tariff_package_reorder", {}, "Перетащите, чтобы изменить порядок")}
              onReorder={moveHwidRow}
            >
              {#snippet children(row: DraftRow, index: number)}
                <Input
                  class="input"
                  type="number"
                  min="1"
                  step="1"
                  placeholder="1"
                  bind:value={row.count}
                  aria-label={at(
                    "tariff_label_hwid_count_full",
                    {},
                    "Сколько устройств добавляет пакет"
                  )}
                />
                <Input
                  class="input"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="99"
                  bind:value={row.price}
                  aria-label={currencyPriceAriaLabel}
                />
                <Input
                  class="input"
                  type="number"
                  min="0"
                  step="1"
                  placeholder="50"
                  bind:value={row.stars}
                  aria-label={at("tariff_label_price_stars", {}, "Цена пакета в Telegram Stars")}
                />
                <AdminButton
                  size="sm"
                  variant="danger"
                  onclick={() => tariffsStore.removeDraftRow("hwidRows", index)}
                  aria-label={at("btn_delete", {}, "Удалить")}><Trash2 size={13} /></AdminButton
                >
              {/snippet}
            </Sortable>
          </div>
        {/if}
      </section>
    </Tabs.Content>
  </Tabs.Root>

  <div class="admin-dialog-actions">
    <AdminButton onclick={() => tariffsStore.updateState({ tariffEditorOpen: false })}
      >{at("btn_cancel", {}, "Отмена")}</AdminButton
    >
    <AdminButton
      variant="primary"
      onclick={tariffsStore.saveTariffDraft}
      disabled={tariffsSaving || !tariffDraft.key.trim()}
    >
      <Save size={14} />
      {tariffsSaving
        ? at("btn_saving", {}, "Сохранение...")
        : at("btn_save_tariff", {}, "Сохранить тариф")}
    </AdminButton>
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
  class="admin-dialog"
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
