<script>
  import { Tabs, Switch, Label } from "$components/ui/primitives.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { Plus, Save, Trash2, X } from "$components/ui/icons.js";
  import { AdminButton, AdminSelect } from "$components/patterns/admin/index.js";
  import { getContext } from "svelte";
  import { normalizeUuidList } from "../../lib/admin/tariffDraft.js";
  
  export let at;
  const tariffsStore = getContext("tariffsStore");
  
  $: ({
    tariffEditorOpen,
    tariffEditingKey,
    tariffDraft,
    tariffsSaving,
    tariffDeleteOpen,
    tariffDeleteTarget,
    selectedBaseSquad,
    selectedPremiumSquad,
    panelSquadsLoading,
    panelSquads,
    tariffEditorTab,
  } = $tariffsStore);

  $: billingModelOptions = [
    { value: "period", label: at("tariff_model_period_label", {}, "Период") },
    { value: "traffic", label: at("tariff_model_traffic_label", {}, "Трафик") },
  ];
  $: panelSquadOptions = (panelSquads || []).map((squad) => ({
    value: squad.uuid,
    label: squad.name,
  }));

</script>

<Dialog
  open={tariffEditorOpen}
  title={tariffEditingKey ? at("tariff_edit_title", {}, "Настройка тарифа") : at("tariff_create_title", {}, "Новый тариф")}
  description={tariffEditingKey || at("tariff_create_subtitle", {}, "Каталог будет сохранён в JSON после подтверждения")}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={() => tariffsStore.updateState({ tariffEditorOpen: false })}
  class="admin-dialog admin-tariff-dialog"
>
  <Tabs.Root bind:value={$tariffsStore.tariffEditorTab} class="admin-tabs-root">
    <Tabs.List class="admin-tabs-list">
      <Tabs.Trigger value="general" class="admin-tabs-trigger">{at("tariff_tab_general", {}, "Основное")}</Tabs.Trigger>
      <Tabs.Trigger value="pricing" class="admin-tabs-trigger">{at("tariff_tab_pricing", {}, "Цены")}</Tabs.Trigger>
      <Tabs.Trigger value="topup" class="admin-tabs-trigger">{at("tariff_tab_topup", {}, "Докупки")}</Tabs.Trigger>
      <Tabs.Trigger value="premium" class="admin-tabs-trigger">{at("tariff_tab_premium", {}, "Premium")}</Tabs.Trigger>
      <Tabs.Trigger value="hwid" class="admin-tabs-trigger">{at("tariff_tab_hwid", {}, "Устройства")}</Tabs.Trigger>
    </Tabs.List>

    <Tabs.Content value="general" class="admin-tabs-content">
      <div class="admin-form-row admin-form-row-2">
        <Label.Root class="admin-field-label">
          <span>{at("tariff_label_key", {}, "Ключ тарифа")}</span>
          <small>{at("tariff_hint_key", {}, "Латиницей, без пробелов. Используется в платежах и подписках, менять после публикации не рекомендуется")}</small>
          <input class="input" type="text" placeholder="standard" bind:value={$tariffsStore.tariffDraft.key} />
        </Label.Root>

        <div class="admin-field-label">
          <span>{at("tariff_label_model", {}, "Модель тарификации")}</span>
          <small><b>{at("tariff_model_period_label", {}, "Период")}</b> — {at("tariff_model_period_desc", {}, "пользователь покупает фиксированный срок (1/3/12 мес. и т.д.)")}. <b>{at("tariff_model_traffic_label", {}, "Трафик")}</b> — {at("tariff_model_traffic_desc", {}, "пользователь покупает пакеты гигабайт по фиксированной цене за GB")}</small>
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
          <strong>{tariffDraft.enabled ? at("tariff_visible", {}, "Тариф виден на витрине") : at("tariff_hidden", {}, "Тариф скрыт от пользователей")}</strong>
          <small>{at("tariff_enabled_hint", {}, "Выключенный тариф не показывается в боте/мини-аппе, но активные подписки на нём продолжают работать")}</small>
        </Label.Root>
      </div>

      <div class="admin-form-row admin-form-row-2">
        <Label.Root class="admin-field-label">
          <span>{at("tariff_label_name_ru", {}, "Название · RU")}</span>
          <input class="input" type="text" placeholder={at("tariff_placeholder_name_ru", {}, "Стандарт")} bind:value={$tariffsStore.tariffDraft.nameRu} />
        </Label.Root>
        <Label.Root class="admin-field-label">
          <span>{at("tariff_label_name_en", {}, "Название · EN")}</span>
          <input class="input" type="text" placeholder={at("tariff_placeholder_name_en", {}, "Standard")} bind:value={$tariffsStore.tariffDraft.nameEn} />
        </Label.Root>
      </div>

      <div class="admin-form-row admin-form-row-2">
        <Label.Root class="admin-field-label">
          <span>{at("tariff_label_desc_ru", {}, "Описание · RU")}</span>
          <input class="input" type="text" placeholder={at("tariff_placeholder_desc_ru", {}, "Базовый набор серверов")} bind:value={$tariffsStore.tariffDraft.descriptionRu} />
        </Label.Root>
        <Label.Root class="admin-field-label">
          <span>{at("tariff_label_desc_en", {}, "Описание · EN")}</span>
          <input class="input" type="text" placeholder={at("tariff_placeholder_desc_en", {}, "Base server pool")} bind:value={$tariffsStore.tariffDraft.descriptionEn} />
        </Label.Root>
      </div>

      <div class="admin-field-label">
        <span>{at("tariff_label_squads", {}, "Базовые Internal Squads")}</span>
        <small>{panelSquadsLoading ? at("loading_squads", {}, "Загружаю список из панели…") : at("tariff_hint_squads", {}, "Сквады Remnawave, к которым подключается пользователь по этому тарифу. Выберите один или несколько")}</small>
        <AdminSelect
          bind:value={$tariffsStore.selectedBaseSquad}
          items={panelSquadOptions}
          placeholder={at("btn_add_squad", {}, "Добавить сквад")}
          ariaLabel={at("btn_add_squad", {}, "Добавить основной сквад")}
          onValueChange={(value) => {
            tariffsStore.addSquadToDraft("squadUuids", value);
            selectedBaseSquad = "";
          }}
        />
        <div class="admin-chip-list">
          {#each normalizeUuidList(tariffDraft.squadUuids) as uuid}
            <button type="button" class="admin-chip" on:click={() => tariffsStore.removeSquadFromDraft("squadUuids", uuid)}>
              {tariffsStore.squadLabel(uuid)} <X size={12} />
            </button>
          {/each}
        </div>
      </div>

      <div class="admin-form-row admin-form-row-2">
        <Label.Root class="admin-field-label">
          <span>{at("tariff_label_hwid", {}, "Лимит устройств (HWID)")}</span>
          <small>{at("tariff_hint_hwid", {}, "Сколько устройств может одновременно использовать подписку. Пусто — взять значение из .env, 0 — без ограничений")}</small>
          <input class="input" type="number" min="0" placeholder="5" bind:value={$tariffsStore.tariffDraft.hwid_device_limit} />
        </Label.Root>
        {#if tariffDraft.billing_model === "period"}
          <Label.Root class="admin-field-label">
            <span>{at("tariff_label_traffic_limit", {}, "Месячный лимит трафика, GB")}</span>
            <small>{at("tariff_hint_traffic_limit", {}, "Сколько GB включено в тариф на каждый месяц. 0 — безлимитный трафика. Сверху можно докупать пакеты на вкладке «Докупки»")}</small>
            <input class="input" type="number" min="0" step="0.1" placeholder="100" bind:value={$tariffsStore.tariffDraft.monthly_gb} />
          </Label.Root>
        {:else}
          <Label.Root class="admin-field-label">
            <span>{at("tariff_label_conversion", {}, "Курс конвертации, ₽ за 1 GB")}</span>
            <small>{at("tariff_hint_conversion", {}, "По этому курсу остаток подписки пересчитывается в гигабайты при переходе пользователя с тарифа «Период» на «Трафик»")}</small>
            <input class="input" type="number" min="0" step="0.01" placeholder="20" bind:value={$tariffsStore.tariffDraft.conversion_rate_rub_per_gb} />
          </Label.Root>
        {/if}
      </div>
    </Tabs.Content>

    <Tabs.Content value="premium" class="admin-tabs-content">
      <section class="admin-editor-section">
        <header class="admin-editor-section-head">
          <div class="admin-editor-section-title">
            <strong>{at("tariff_premium_head", {}, "Premium-доступ и отдельный счётчик трафика")}</strong>
            <small>{at("tariff_premium_subhead", {}, "Premium-сквады дают пользователю доступ к более быстрым/премиальным нодам; их трафик считается отдельно от основного, чтобы можно было ограничить или продавать дополнительно")}</small>
          </div>
        </header>
        <div class="admin-form-row admin-form-row-2">
          <Label.Root class="admin-field-label">
            <span>{at("tariff_label_premium_name_ru", {}, "Название premium-раздела, RU")}</span>
            <small>{at("tariff_hint_premium_name_ru", {}, "Эта строка заменит «Premium-серверы» в кабинете, докупках и карточках лимитов.")}</small>
            <input class="input" type="text" placeholder={at("tariff_placeholder_premium_name_ru", {}, "Premium-серверы")} bind:value={$tariffsStore.tariffDraft.premiumNameRu} />
          </Label.Root>
          <Label.Root class="admin-field-label">
            <span>{at("tariff_label_premium_name_en", {}, "Название premium-раздела, EN")}</span>
            <small>{at("tariff_hint_premium_name_en", {}, "Опционально для английского интерфейса.")}</small>
            <input class="input" type="text" placeholder={at("tariff_placeholder_premium_name_en", {}, "Premium servers")} bind:value={$tariffsStore.tariffDraft.premiumNameEn} />
          </Label.Root>
        </div>
        <div class="admin-form-row admin-form-row-2">
          <div class="admin-field-label">
            <span>{at("tariff_label_premium_squads", {}, "Premium Internal Squads")}</span>
            <small>{at("tariff_hint_premium_squads", {}, "Сквады из Remnawave, доступные только владельцам этого тарифа. Трафик считается по их accessible nodes")}</small>
            <AdminSelect
              bind:value={$tariffsStore.selectedPremiumSquad}
              items={panelSquadOptions}
              placeholder={at("btn_add_premium_squad", {}, "Добавить premium-сквад")}
              ariaLabel={at("btn_add_premium_squad", {}, "Добавить premium-сквад")}
              onValueChange={(value) => {
                tariffsStore.addSquadToDraft("premiumSquadUuids", value);
                selectedPremiumSquad = "";
              }}
            />
            <div class="admin-chip-list">
              {#each normalizeUuidList(tariffDraft.premiumSquadUuids) as uuid}
                <button type="button" class="admin-chip" on:click={() => tariffsStore.removeSquadFromDraft("premiumSquadUuids", uuid)}>
                  {tariffsStore.squadLabel(uuid)} <X size={12} />
                </button>
              {/each}
            </div>
          </div>
          <Label.Root class="admin-field-label">
            <span>{at("tariff_label_premium_traffic_limit", {}, "Месячный лимит premium-трафика, GB")}</span>
            <small>{at("tariff_hint_premium_traffic_limit", {}, "Сколько GB через premium-сквады включено в тариф каждый месяц. 0 или пусто — отдельного premium-лимита нет (premium-нодами можно пользоваться без ограничения)")}</small>
            <input class="input" type="number" min="0" step="0.1" placeholder="50" bind:value={$tariffsStore.tariffDraft.premium_monthly_gb} />
          </Label.Root>
        </div>
      </section>

      <section class="admin-editor-section">
        <header class="admin-editor-section-head">
          <div class="admin-editor-section-title">
            <strong>{at("tariff_premium_topup_title", {}, "Докупка premium-трафика")}</strong>
            <small>{at("tariff_premium_topup_subtitle", {}, "Пакеты для расширения месячного premium-лимита, когда пользователь его исчерпал")}</small>
          </div>
          <div class="admin-editor-section-actions">
            <AdminButton size="sm" onclick={() => tariffsStore.addDraftRow("premiumTopupRubRows", { gb: 10, price: "" })}><Plus size={12} /> {at("tariff_btn_package_rub", {}, "Пакет ₽")}</AdminButton>
            <AdminButton size="sm" onclick={() => tariffsStore.addDraftRow("premiumTopupStarsRows", { gb: 10, price: "" })}><Plus size={12} /> {at("tariff_btn_package_stars", {}, "Пакет ⭐")}</AdminButton>
          </div>
        </header>
        <div class="admin-package-columns">
          <div class="admin-row-editor">
            <span class="admin-row-editor-caption">{at("payment_rub", {}, "Оплата рублями")}</span>
            {#if tariffDraft.premiumTopupRubRows.length}
              <div class="admin-row-editor-line admin-row-editor-header">
                <span>{at("tariff_col_volume_gb", {}, "Объём, GB")}</span>
                <span>{at("tariff_col_price_rub", {}, "Цена, ₽")}</span>
                <span></span>
              </div>
            {/if}
            {#each tariffDraft.premiumTopupRubRows as row, index}
              <div class="admin-row-editor-line">
                <input class="input" type="number" min="0.1" step="0.1" placeholder="10" bind:value={row.gb} aria-label={at("tariff_col_volume_gb", {}, "Объём premium-пакета в GB")} />
                <input class="input" type="number" min="0" step="0.01" placeholder="199" bind:value={row.price} aria-label={at("tariff_label_price_rub", {}, "Цена premium-пакета в рублях")} />
                <AdminButton size="sm" variant="danger" onclick={() => tariffsStore.removeDraftRow("premiumTopupRubRows", index)} aria-label={at("btn_delete", {}, "Удалить")}><Trash2 size={13} /></AdminButton>
              </div>
            {/each}
          </div>
          <div class="admin-row-editor">
            <span class="admin-row-editor-caption">{at("payment_stars", {}, "Оплата Telegram Stars")}</span>
            {#if tariffDraft.premiumTopupStarsRows.length}
              <div class="admin-row-editor-line admin-row-editor-header">
                <span>{at("tariff_col_volume_gb", {}, "Объём, GB")}</span>
                <span>{at("tariff_col_price_stars", {}, "Цена, ⭐")}</span>
                <span></span>
              </div>
            {/if}
            {#each tariffDraft.premiumTopupStarsRows as row, index}
              <div class="admin-row-editor-line">
                <input class="input" type="number" min="0.1" step="0.1" placeholder="10" bind:value={row.gb} aria-label={at("tariff_col_volume_gb", {}, "Объём premium-пакета в GB")} />
                <input class="input" type="number" min="0" step="1" placeholder="100" bind:value={row.price} aria-label={at("tariff_label_price_stars", {}, "Цена premium-пакета в Telegram Stars")} />
                <AdminButton size="sm" variant="danger" onclick={() => tariffsStore.removeDraftRow("premiumTopupStarsRows", index)} aria-label={at("btn_delete", {}, "Удалить")}><Trash2 size={13} /></AdminButton>
              </div>
            {/each}
          </div>
        </div>
      </section>
    </Tabs.Content>

    <Tabs.Content value="pricing" class="admin-tabs-content">
      {#if tariffDraft.billing_model === "period"}
        <section class="admin-editor-section">
          <header class="admin-editor-section-head">
            <div class="admin-editor-section-title">
              <strong>{at("tariff_pricing_period_title", {}, "Периоды подписки и цены")}</strong>
              <small>{at("tariff_pricing_period_subtitle", {}, "Каждая строка — отдельный вариант на витрине: за сколько месяцев пользователь платит и сколько это стоит")}</small>
            </div>
            <AdminButton size="sm" onclick={() => tariffsStore.addDraftRow("periodRows", { months: 1, rub: "", stars: "" })}>
              <Plus size={13} /> {at("tariff_btn_period", {}, "Период")}
            </AdminButton>
          </header>
          {#if !tariffDraft.periodRows.length}
            <p class="admin-muted">{at("tariff_pricing_empty", {}, "Добавьте хотя бы один период — без него тариф не появится на витрине.")}</p>
          {:else}
            <div class="admin-row-editor">
              <div class="admin-row-editor-line admin-row-editor-4 admin-row-editor-header">
                <span>{at("tariff_col_period_months", {}, "Срок, мес.")}</span>
                <span>{at("tariff_col_price_rub", {}, "Цена, ₽")}</span>
                <span>{at("tariff_col_price_stars_full", {}, "Цена, ⭐ Stars")}</span>
                <span></span>
              </div>
              {#each tariffDraft.periodRows as row, index}
                <div class="admin-row-editor-line admin-row-editor-4">
                  <input class="input" type="number" min="1" placeholder="1" bind:value={row.months} aria-label={at("tariff_col_period_months", {}, "Срок (месяцы)")} />
                  <input class="input" type="number" min="0" step="0.01" placeholder="299" bind:value={row.rub} aria-label={at("tariff_label_price_rub", {}, "Цена в рублях")} />
                  <input class="input" type="number" min="0" step="1" placeholder="150" bind:value={row.stars} aria-label={at("tariff_label_price_stars", {}, "Цена в Telegram Stars")} />
                  <AdminButton size="sm" variant="danger" onclick={() => tariffsStore.removeDraftRow("periodRows", index)} aria-label={at("btn_delete", {}, "Удалить")}>
                    <Trash2 size={13} />
                  </AdminButton>
                </div>
              {/each}
            </div>
          {/if}
        </section>
      {:else}
        <section class="admin-editor-section">
          <header class="admin-editor-section-head">
            <div class="admin-editor-section-title">
              <strong>{at("tariff_pricing_traffic_title", {}, "Пакеты трафика")}</strong>
              <small>{at("tariff_pricing_traffic_subtitle", {}, "Базовая витрина для трафиковой модели. Каждая строка — пакет «N гигабайт за N единиц валюты»")}</small>
            </div>
            <div class="admin-editor-section-actions">
              <AdminButton size="sm" onclick={() => tariffsStore.addDraftRow("trafficRubRows", { gb: 10, price: "" })}><Plus size={12} /> {at("tariff_btn_package_rub", {}, "Пакет ₽")}</AdminButton>
              <AdminButton size="sm" onclick={() => tariffsStore.addDraftRow("trafficStarsRows", { gb: 10, price: "" })}><Plus size={12} /> {at("tariff_btn_package_stars", {}, "Пакет ⭐")}</AdminButton>
            </div>
          </header>
          <div class="admin-package-columns">
            <div class="admin-row-editor">
              <span class="admin-row-editor-caption">{at("payment_rub", {}, "Оплата рублями")}</span>
              {#if tariffDraft.trafficRubRows.length}
                <div class="admin-row-editor-line admin-row-editor-header">
                  <span>{at("tariff_col_volume_gb", {}, "Объём, GB")}</span>
                  <span>{at("tariff_col_price_rub", {}, "Цена, ₽")}</span>
                  <span></span>
                </div>
              {/if}
              {#each tariffDraft.trafficRubRows as row, index}
                <div class="admin-row-editor-line">
                  <input class="input" type="number" min="0.1" step="0.1" placeholder="50" bind:value={row.gb} aria-label={at("tariff_col_volume_gb", {}, "Объём пакета в GB")} />
                  <input class="input" type="number" min="0" step="0.01" placeholder="299" bind:value={row.price} aria-label={at("tariff_label_price_rub", {}, "Цена пакета в рублях")} />
                  <AdminButton size="sm" variant="danger" onclick={() => tariffsStore.removeDraftRow("trafficRubRows", index)} aria-label={at("btn_delete", {}, "Удалить")}><Trash2 size={13} /></AdminButton>
                </div>
              {/each}
            </div>
            <div class="admin-row-editor">
              <span class="admin-row-editor-caption">{at("payment_stars", {}, "Оплата Telegram Stars")}</span>
              {#if tariffDraft.trafficStarsRows.length}
                <div class="admin-row-editor-line admin-row-editor-header">
                  <span>{at("tariff_col_volume_gb", {}, "Объём, GB")}</span>
                  <span>{at("tariff_col_price_stars", {}, "Цена, ⭐")}</span>
                  <span></span>
                </div>
              {/if}
              {#each tariffDraft.trafficStarsRows as row, index}
                <div class="admin-row-editor-line">
                  <input class="input" type="number" min="0.1" step="0.1" placeholder="50" bind:value={row.gb} aria-label={at("tariff_col_volume_gb", {}, "Объём пакета в GB")} />
                  <input class="input" type="number" min="0" step="1" placeholder="150" bind:value={row.price} aria-label={at("tariff_label_price_stars", {}, "Цена пакета в Telegram Stars")} />
                  <AdminButton size="sm" variant="danger" onclick={() => tariffsStore.removeDraftRow("trafficStarsRows", index)} aria-label={at("btn_delete", {}, "Удалить")}><Trash2 size={13} /></AdminButton>
                </div>
              {/each}
            </div>
          </div>
        </section>
      {/if}
    </Tabs.Content>

    <Tabs.Content value="topup" class="admin-tabs-content">
      {#if tariffDraft.billing_model === "period"}
        <section class="admin-editor-section">
          <header class="admin-editor-section-head">
            <div class="admin-editor-section-title">
              <strong>{at("tariff_topup_title", {}, "Докупка трафика поверх месячного лимита")}</strong>
              <small>{at("tariff_topup_subtitle", {}, "Когда у пользователя кончился месячный лимит, ему предложат купить дополнительный пакет, не меняя срок подписки")}</small>
            </div>
            <div class="admin-editor-section-actions">
              <AdminButton size="sm" onclick={() => tariffsStore.addDraftRow("topupRubRows", { gb: 10, price: "" })}><Plus size={12} /> {at("tariff_btn_package_rub", {}, "Пакет ₽")}</AdminButton>
              <AdminButton size="sm" onclick={() => tariffsStore.addDraftRow("topupStarsRows", { gb: 10, price: "" })}><Plus size={12} /> {at("tariff_btn_package_stars", {}, "Пакет ⭐")}</AdminButton>
            </div>
          </header>
          <div class="admin-package-columns">
            <div class="admin-row-editor">
              <span class="admin-row-editor-caption">{at("payment_rub", {}, "Оплата рублями")}</span>
              {#if tariffDraft.topupRubRows.length}
                <div class="admin-row-editor-line admin-row-editor-header">
                  <span>{at("tariff_col_volume_gb", {}, "Объём, GB")}</span>
                  <span>{at("tariff_col_price_rub", {}, "Цена, ₽")}</span>
                  <span></span>
                </div>
              {/if}
              {#each tariffDraft.topupRubRows as row, index}
                <div class="admin-row-editor-line">
                  <input class="input" type="number" min="0.1" step="0.1" placeholder="20" bind:value={row.gb} aria-label={at("tariff_col_volume_gb", {}, "Объём пакета в GB")} />
                  <input class="input" type="number" min="0" step="0.01" placeholder="149" bind:value={row.price} aria-label={at("tariff_label_price_rub", {}, "Цена пакета в рублях")} />
                  <AdminButton size="sm" variant="danger" onclick={() => tariffsStore.removeDraftRow("topupRubRows", index)} aria-label={at("btn_delete", {}, "Удалить")}><Trash2 size={13} /></AdminButton>
                </div>
              {/each}
            </div>
            <div class="admin-row-editor">
              <span class="admin-row-editor-caption">{at("payment_stars", {}, "Оплата Telegram Stars")}</span>
              {#if tariffDraft.topupStarsRows.length}
                <div class="admin-row-editor-line admin-row-editor-header">
                  <span>{at("tariff_col_volume_gb", {}, "Объём, GB")}</span>
                  <span>{at("tariff_col_price_stars", {}, "Цена, ⭐")}</span>
                  <span></span>
                </div>
              {/if}
              {#each tariffDraft.topupStarsRows as row, index}
                <div class="admin-row-editor-line">
                  <input class="input" type="number" min="0.1" step="0.1" placeholder="20" bind:value={row.gb} aria-label={at("tariff_col_volume_gb", {}, "Объём пакета в GB")} />
                  <input class="input" type="number" min="0" step="1" placeholder="75" bind:value={row.price} aria-label={at("tariff_label_price_stars", {}, "Цена пакета в Telegram Stars")} />
                  <AdminButton size="sm" variant="danger" onclick={() => tariffsStore.removeDraftRow("topupStarsRows", index)} aria-label={at("btn_delete", {}, "Удалить")}><Trash2 size={13} /></AdminButton>
                </div>
              {/each}
            </div>
          </div>
        </section>
      {:else}
        <p class="admin-muted">{at("tariff_topup_traffic_hint", {}, "Для трафиковой модели отдельные «докупки» не нужны — пакеты, которые вы настроили на вкладке «Цены», и являются докупками: пользователь покупает их повторно по мере исчерпания.")}</p>
      {/if}
    </Tabs.Content>

    <Tabs.Content value="hwid" class="admin-tabs-content">
      <section class="admin-editor-section">
        <header class="admin-editor-section-head">
          <div class="admin-editor-section-title">
            <strong>{at("tariff_hwid_packages_title", {}, "Пакеты дополнительных устройств (HWID)")}</strong>
            <small>{at("tariff_hwid_packages_subtitle", {}, "Расширяет лимит, указанный во вкладке «Основное». Каждая строка — пакет «+N устройств за N единиц валюты»")}</small>
          </div>
          <div class="admin-editor-section-actions">
            <AdminButton size="sm" onclick={() => tariffsStore.addDraftRow("hwidRubRows", { count: 1, price: "" })}><Plus size={12} /> {at("tariff_btn_package_rub", {}, "Пакет ₽")}</AdminButton>
            <AdminButton size="sm" onclick={() => tariffsStore.addDraftRow("hwidStarsRows", { count: 1, price: "" })}><Plus size={12} /> {at("tariff_btn_package_stars", {}, "Пакет ⭐")}</AdminButton>
          </div>
        </header>
        <div class="admin-package-columns">
          <div class="admin-row-editor">
            <span class="admin-row-editor-caption">{at("payment_rub", {}, "Оплата рублями")}</span>
            {#if tariffDraft.hwidRubRows.length}
              <div class="admin-row-editor-line admin-row-editor-header">
                <span>{at("tariff_col_hwid_count", {}, "+ устройств")}</span>
                <span>{at("tariff_col_price_rub", {}, "Цена, ₽")}</span>
                <span></span>
              </div>
            {/if}
            {#each tariffDraft.hwidRubRows as row, index}
              <div class="admin-row-editor-line">
                <input class="input" type="number" min="1" step="1" placeholder="1" bind:value={row.count} aria-label={at("tariff_label_hwid_count_full", {}, "Сколько устройств добавляет пакет")} />
                <input class="input" type="number" min="0" step="0.01" placeholder="99" bind:value={row.price} aria-label={at("tariff_label_price_rub", {}, "Цена пакета в рублях")} />
                <AdminButton size="sm" variant="danger" onclick={() => tariffsStore.removeDraftRow("hwidRubRows", index)} aria-label={at("btn_delete", {}, "Удалить")}><Trash2 size={13} /></AdminButton>
              </div>
            {/each}
          </div>
          <div class="admin-row-editor">
            <span class="admin-row-editor-caption">{at("payment_stars", {}, "Оплата Telegram Stars")}</span>
            {#if tariffDraft.hwidStarsRows.length}
              <div class="admin-row-editor-line admin-row-editor-header">
                <span>{at("tariff_col_hwid_count", {}, "+ устройств")}</span>
                <span>{at("tariff_col_price_stars", {}, "Цена, ⭐")}</span>
                <span></span>
              </div>
            {/if}
            {#each tariffDraft.hwidStarsRows as row, index}
              <div class="admin-row-editor-line">
                <input class="input" type="number" min="1" step="1" placeholder="1" bind:value={row.count} aria-label={at("tariff_label_hwid_count_full", {}, "Сколько устройств добавляет пакет")} />
                <input class="input" type="number" min="0" step="1" placeholder="50" bind:value={row.price} aria-label={at("tariff_label_price_stars", {}, "Цена пакета в Telegram Stars")} />
                <AdminButton size="sm" variant="danger" onclick={() => tariffsStore.removeDraftRow("hwidStarsRows", index)} aria-label={at("btn_delete", {}, "Удалить")}><Trash2 size={13} /></AdminButton>
              </div>
            {/each}
          </div>
        </div>
      </section>
    </Tabs.Content>
  </Tabs.Root>

  <div class="admin-dialog-actions">
    <AdminButton onclick={() => tariffsStore.updateState({ tariffEditorOpen: false })}>{at("btn_cancel", {}, "Отмена")}</AdminButton>
    <AdminButton variant="primary" onclick={tariffsStore.saveTariffDraft} disabled={tariffsSaving || !tariffDraft.key.trim()}>
      <Save size={14} /> {tariffsSaving ? at("btn_saving", {}, "Сохранение...") : at("btn_save_tariff", {}, "Сохранить тариф")}
    </AdminButton>
  </div>
</Dialog>

<Dialog
  open={tariffDeleteOpen}
  title={at("tariff_delete_title", {}, "Удалить тариф?")}
  description={tariffDeleteTarget ? at("tariff_delete_subtitle", { key: tariffDeleteTarget.key }, `Тариф ${tariffDeleteTarget.key} исчезнет из каталога продаж.`) : ""}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={() => tariffsStore.updateState({ tariffDeleteOpen: false })}
  class="admin-dialog"
>
  <div class="admin-form-row">
    <AdminButton onclick={() => tariffsStore.updateState({ tariffDeleteOpen: false })}>{at("btn_cancel", {}, "Отмена")}</AdminButton>
    <AdminButton variant="danger" onclick={tariffsStore.deleteTariff} disabled={tariffsSaving}>
      <Trash2 size={14} /> {at("btn_confirm_delete", {}, "Подтвердить удаление")}
    </AdminButton>
  </div>
</Dialog>
