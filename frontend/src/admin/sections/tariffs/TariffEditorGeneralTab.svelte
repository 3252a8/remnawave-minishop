<script lang="ts">
  import { getTariffsStore } from "$lib/admin/context";
  import { Input } from "$components/ui/index.js";
  import { Tabs, Switch } from "$components/ui/primitives.js";
  import {
    AdminButton,
    AdminSelect,
    AdminSettingCard,
    AdminSettingsGroup,
  } from "$components/patterns/admin/index.js";
  import { Copy, X } from "$components/ui/icons.js";
  import { normalizeUuidList } from "$lib/admin/tariffDraft";
  import { buildCheckoutUrl } from "$lib/webapp/deeplinks.js";
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

  let { at, routePrefix = "" }: { at: TranslateFn; routePrefix?: string } = $props();

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
  const checkoutLink = $derived(
    typeof window === "undefined"
      ? ""
      : buildCheckoutUrl({
          origin: window.location.origin,
          plan: String(tariffDraft.key || ""),
          routePrefix,
        })
  );
  const legacyKeysText = $derived(
    Array.isArray(tariffDraft.legacyKeys)
      ? tariffDraft.legacyKeys.join(", ")
      : String(tariffDraft.legacyKeys || "")
  );
  const billingModelDescription = $derived(
    `${at("tariff_model_period_label", {}, "Period")} — ${at(
      "tariff_model_period_desc",
      {},
      "the user buys a fixed period (1/3/12 months, etc.)"
    )}. ${at("tariff_model_traffic_label", {}, "Traffic")} — ${at(
      "tariff_model_traffic_desc",
      {},
      "the user buys gigabyte packages at a fixed price per GB"
    )}.`
  );

  function setDraftField(field: string, value: unknown): void {
    tariffsStore.updateDraftField(field, value);
  }

  function setBillingModel(value: string): void {
    if (
      value === "period" &&
      tariffDraft.billing_model !== "period" &&
      !tariffDraft.traffic_limit_strategy
    ) {
      setDraftField("traffic_limit_strategy", "MONTH");
    }
    setDraftField("billing_model", value);
  }

  function addBaseSquad(value: string): void {
    addDraftSquad(tariffsStore, "squadUuids", value);
  }
</script>

<Tabs.Content value="general" class="admin-tabs-content">
  <AdminSettingsGroup
    title={at("tariff_group_identity", {}, "Tariff identity and state")}
    description={at(
      "tariff_group_identity_hint",
      {},
      "Stable identifiers and the sales model used by billing and existing subscriptions."
    )}
  >
    <AdminSettingCard
      title={at("tariff_label_key", {}, "Tariff key")}
      description={at(
        "tariff_hint_key",
        {},
        "Latin characters, no spaces. Used in payments and subscriptions; changing it after publication is not recommended"
      )}
    >
      <Input
        class="input"
        type="text"
        placeholder="standard"
        value={tariffDraft.key}
        oninput={draftInputHandler(tariffsStore, "key")}
      />
    </AdminSettingCard>

    <AdminSettingCard
      title={at("tariff_label_model", {}, "Billing model")}
      description={billingModelDescription}
    >
      <AdminSelect
        value={String(tariffDraft.billing_model || "period")}
        items={billingModelOptions}
        ariaLabel={at("tariff_label_model", {}, "Billing model")}
        onValueChange={setBillingModel}
      />
    </AdminSettingCard>

    <AdminSettingCard
      title={at("tariff_checkout_link_title", {}, "Tariff checkout link")}
      description={at(
        "tariff_checkout_link_hint",
        {},
        "Opens this tariff in the public checkout flow before sign-in or registration."
      )}
    >
      <div class="tariff-checkout-link-control">
        <Input
          class="input"
          type="text"
          readonly
          value={checkoutLink}
          placeholder={at(
            "tariff_checkout_link_placeholder",
            {},
            "Enter a tariff key to create the link"
          )}
          aria-label={at("tariff_checkout_link_title", {}, "Tariff checkout link")}
        />
        <AdminButton
          size="icon"
          variant="icon"
          title={at("tariff_checkout_link_copy", {}, "Copy checkout link")}
          aria-label={at("tariff_checkout_link_copy", {}, "Copy checkout link")}
          disabled={!checkoutLink}
          onclick={() =>
            tariffsStore.copyToClipboard(
              checkoutLink,
              at("tariff_checkout_link_copied", {}, "Checkout link copied")
            )}
        >
          <Copy size={14} />
        </AdminButton>
      </div>
    </AdminSettingCard>

    <AdminSettingCard
      title={at("tariff_label_legacy_keys", {}, "Previous tariff keys")}
      description={at(
        "tariff_hint_legacy_keys",
        {},
        "Old keys kept for pending payments and existing subscriptions. Separate multiple keys with commas"
      )}
    >
      <Input
        class="input"
        type="text"
        placeholder={at("tariff_placeholder_legacy_keys", {}, "old-key, legacy")}
        value={legacyKeysText}
        oninput={draftInputHandler(tariffsStore, "legacyKeys")}
      />
    </AdminSettingCard>

    <AdminSettingCard
      title={tariffDraft.enabled
        ? at("tariff_visible", {}, "Tariff is visible in the storefront")
        : at("tariff_hidden", {}, "Tariff is hidden from users")}
      description={at(
        "tariff_enabled_hint",
        {},
        "A disabled tariff is hidden from the bot/Mini App, but active subscriptions on it keep working"
      )}
    >
      <div class="admin-setting-switch">
        <Switch.Root
          aria-label={at("tariff_enabled", {}, "Tariff enabled")}
          checked={tariffDraft.enabled}
          onCheckedChange={(value) => setDraftField("enabled", value)}
          class="admin-switch-root"
        >
          <Switch.Thumb class="admin-switch-thumb" />
        </Switch.Root>
        <span>
          {tariffDraft.enabled ? at("enabled", {}, "Enabled") : at("disabled", {}, "Disabled")}
        </span>
      </div>
    </AdminSettingCard>

    {#if tariffDraft.billing_model === "traffic"}
      <AdminSettingCard
        title={conversionCurrencyLabel}
        description={at(
          "tariff_hint_conversion",
          {},
          "This rate converts the remaining subscription period to gigabytes when a user switches from Period to Traffic"
        )}
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
      </AdminSettingCard>
    {/if}
  </AdminSettingsGroup>

  <AdminSettingsGroup
    title={at("tariff_group_presentation", {}, "Names and descriptions")}
    description={at(
      "tariff_group_presentation_hint",
      {},
      "Localized storefront copy shown to customers."
    )}
  >
    <AdminSettingCard title={at("tariff_label_name_ru", {}, "Name - RU")}>
      <Input
        class="input"
        type="text"
        placeholder={at("tariff_placeholder_name_ru", {}, "Standard")}
        value={tariffDraft.nameRu}
        oninput={draftInputHandler(tariffsStore, "nameRu")}
      />
    </AdminSettingCard>
    <AdminSettingCard title={at("tariff_label_name_en", {}, "Name - EN")}>
      <Input
        class="input"
        type="text"
        placeholder={at("tariff_placeholder_name_en", {}, "Standard")}
        value={tariffDraft.nameEn}
        oninput={draftInputHandler(tariffsStore, "nameEn")}
      />
    </AdminSettingCard>

    <AdminSettingCard title={at("tariff_label_desc_ru", {}, "Description - RU")}>
      <Input
        class="input"
        type="text"
        placeholder={at("tariff_placeholder_desc_ru", {}, "Base server pool")}
        value={tariffDraft.descriptionRu}
        oninput={draftInputHandler(tariffsStore, "descriptionRu")}
      />
    </AdminSettingCard>
    <AdminSettingCard title={at("tariff_label_desc_en", {}, "Description - EN")}>
      <Input
        class="input"
        type="text"
        placeholder={at("tariff_placeholder_desc_en", {}, "Base server pool")}
        value={tariffDraft.descriptionEn}
        oninput={draftInputHandler(tariffsStore, "descriptionEn")}
      />
    </AdminSettingCard>
  </AdminSettingsGroup>

  <AdminSettingsGroup
    title={at("tariff_group_access", {}, "Base access")}
    description={at(
      "tariff_group_access_hint",
      {},
      "Remnawave resources assigned to every subscription on this tariff."
    )}
  >
    <AdminSettingCard
      title={at("tariff_label_squads", {}, "Base Internal Squads")}
      description={panelSquadsLoading
        ? at("loading_squads", {}, "Loading list from panel...")
        : at(
            "tariff_hint_squads",
            {},
            "Remnawave squads this tariff connects the user to. Select one or more"
          )}
      alignStart
    >
      <div class="tariff-setting-control-stack">
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
    </AdminSettingCard>
  </AdminSettingsGroup>
</Tabs.Content>

<style>
  .tariff-setting-control-stack {
    display: grid;
    gap: 8px;
    width: 100%;
    min-width: 0;
  }

  .tariff-checkout-link-control {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: 8px;
    width: 100%;
    min-width: 0;
  }
</style>
