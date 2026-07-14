<script lang="ts">
  import { Checkbox, Input, Tabs } from "$components/ui/index.js";
  import { Copy, ExternalLink } from "$components/ui/icons.js";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminField,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import PromoActivationsPanel from "./PromoActivationsPanel.svelte";
  import PromoEffectSelector from "./PromoEffectSelector.svelte";
  import type { components } from "$lib/api/openapi.generated";
  import type { AdminBadgeVariant } from "$components/patterns/admin/types";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Promo = components["schemas"]["PromoOut"];
  type PromoPatch = components["schemas"]["PromoUpdateBody"];
  type PromoActivation = components["schemas"]["PromoActivationOut"];
  type PromoEffectKind =
    "bonus_days" | "discount_percent" | "duration_multiplier" | "traffic_multiplier";
  type PromoEditTab = "settings" | "activations";
  type PromoEditField =
    | "is_active"
    | "applies_to"
    | "max_activations"
    | "valid_until"
    | "bonus_days"
    | "bonus_requires_payment"
    | "discount_percent"
    | "duration_multiplier"
    | "traffic_multiplier"
    | "min_subscription_months"
    | "min_traffic_gb";
  type PromoStatus = { label: string; variant: "success" | "warning" | "muted" };
  type PromosStoreBridge = {
    updateEditDraft: (patch: Partial<PromoPatch>) => void;
    copyToClipboard: (value: string | null | undefined, message?: string) => void;
    savePromo: () => void | Promise<void>;
    setActivationsPage: (page: number) => void;
  };

  let {
    at,
    activationsLoading,
    activationsPage,
    activationsPageCount,
    activationsTotal,
    closePromoEditor,
    editActivationRows,
    editFieldDirty,
    fmtDate,
    fmtMoney,
    inputValue,
    onOpenUserCard,
    openPromoLink,
    paymentStatusVariant,
    promoBasicsDirtyCount,
    promoEditDraft,
    promoEditEffectKind,
    promoEditOpen,
    promoEditTab,
    promoEditUsesCheckout,
    promoEditing,
    promoEffectDirtyCount,
    promoEffectDirtyFields,
    promoEligibilityDirtyCount,
    promoSettingsDirtyCount,
    promoStatus,
    promosStore,
    scopeItems,
    selectEditEffect,
    selectPromoEditTab,
    setEditBonusRequiresPayment,
    updateEditNumber,
    updateEditValidUntil,
    validUntilInputValue,
  }: {
    at: TranslateFn;
    activationsLoading: boolean;
    activationsPage: number;
    activationsPageCount: number;
    activationsTotal: number;
    closePromoEditor: () => void;
    editActivationRows: PromoActivation[];
    editFieldDirty: (field: PromoEditField) => boolean;
    fmtDate: (value: string | null | undefined) => string;
    fmtMoney: (value: number, currency?: string | null) => string;
    inputValue: (event: Event) => string;
    onOpenUserCard: (userId: number) => void;
    openPromoLink: (link: string | null | undefined) => void;
    paymentStatusVariant: (status: string | null | undefined) => AdminBadgeVariant;
    promoBasicsDirtyCount: number;
    promoEditDraft: PromoPatch;
    promoEditEffectKind: PromoEffectKind;
    promoEditOpen: boolean;
    promoEditTab: PromoEditTab;
    promoEditUsesCheckout: boolean;
    promoEditing: Promo | null;
    promoEffectDirtyCount: number;
    promoEffectDirtyFields: Partial<Record<PromoEffectKind, boolean>>;
    promoEligibilityDirtyCount: number;
    promoSettingsDirtyCount: number;
    promoStatus: (promo: Promo) => PromoStatus;
    promosStore: PromosStoreBridge;
    scopeItems: Array<{ value: string; label: string }>;
    selectEditEffect: (value: string) => void;
    selectPromoEditTab: (value: string) => void;
    setEditBonusRequiresPayment: (checked: boolean) => void;
    updateEditNumber: (field: keyof PromoPatch, value: string) => void;
    updateEditValidUntil: (value: string) => void;
    validUntilInputValue: (value: string | null | undefined) => string;
  } = $props();
</script>

<Dialog
  open={promoEditOpen}
  title={promoEditing
    ? at("promo_edit_title", { code: promoEditing.code }, `Edit ${promoEditing.code}`)
    : at("promo_edit_title_empty", {}, "Edit code")}
  closeLabel={at("close", {}, "Close")}
  onclose={closePromoEditor}
  class="admin-dialog admin-promo-dialog admin-promo-edit-dialog"
>
  {#if promoEditing}
    {@const editStatus = promoStatus(promoEditing)}
    <div class="admin-promo-edit-body" data-dialog-content>
      <div class="admin-promo-edit-summary">
        <div class="admin-promo-edit-summary-main">
          <span>{at("promo_label_code", {}, "Code")}</span>
          <strong>{promoEditing.code}</strong>
        </div>
        <div class="admin-promo-edit-summary-meta">
          {#if promoSettingsDirtyCount}
            <AdminBadge variant="warning">
              {at(
                "settings_dirty_count",
                { count: promoSettingsDirtyCount },
                `Changes: ${promoSettingsDirtyCount}`
              )}
            </AdminBadge>
          {/if}
          <AdminBadge variant={editStatus.variant}>{editStatus.label}</AdminBadge>
          <span class="admin-promo-edit-summary-uses">
            {promoEditing.current_activations}/{promoEditing.max_activations}
          </span>
        </div>
      </div>

      <Tabs.Root
        value={promoEditTab}
        onValueChange={selectPromoEditTab}
        class="admin-tabs-root admin-promo-tabs-root"
      >
        <Tabs.List class="admin-tabs-list">
          <Tabs.Trigger value="settings" class="admin-tabs-trigger">
            {at("promo_tab_settings", {}, "Settings")}
            {#if promoSettingsDirtyCount}
              <span class="admin-promo-tab-dirty-count">{promoSettingsDirtyCount}</span>
            {/if}
          </Tabs.Trigger>
          <Tabs.Trigger value="activations" class="admin-tabs-trigger">
            {at("promo_tab_activations", {}, "Activations")}
          </Tabs.Trigger>
        </Tabs.List>

        <Tabs.Content value="settings" class="admin-tabs-content admin-promo-settings-tab">
          <div class="admin-promo-settings-grid">
            <section
              class="admin-editor-section admin-promo-editor-section admin-promo-basics-section"
              class:is-dirty={promoBasicsDirtyCount}
            >
              <header class="admin-editor-section-head">
                <div class="admin-editor-section-title">
                  <strong>{at("promo_section_basics", {}, "Basics")}</strong>
                </div>
                {#if promoBasicsDirtyCount}
                  <AdminBadge variant="warning">
                    {at(
                      "settings_dirty_count",
                      { count: promoBasicsDirtyCount },
                      `Changes: ${promoBasicsDirtyCount}`
                    )}
                  </AdminBadge>
                {/if}
              </header>
              <div class="admin-promo-fields-grid admin-promo-basics-grid">
                <div class="admin-promo-field-shell" class:is-dirty={editFieldDirty("is_active")}>
                  <AdminField label={at("promo_col_status", {}, "Status")}>
                    <label class="admin-promo-check-row">
                      <Checkbox
                        checked={Boolean(promoEditDraft.is_active)}
                        ariaLabel={at("status_active", {}, "Active")}
                        onCheckedChange={(checked) =>
                          promosStore.updateEditDraft({ is_active: checked })}
                      />
                      <span>{at("badge_active", {}, "Active")}</span>
                    </label>
                  </AdminField>
                  {#if editFieldDirty("is_active")}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                    >
                  {/if}
                </div>
                <div class="admin-promo-field-shell" class:is-dirty={editFieldDirty("applies_to")}>
                  <AdminField label={at("promo_label_scope", {}, "Scope")}>
                    <AdminSelect
                      value={promoEditDraft.applies_to || "all"}
                      items={scopeItems}
                      placeholder={at("promo_label_scope", {}, "Scope")}
                      onValueChange={(value: string) =>
                        promosStore.updateEditDraft({ applies_to: value })}
                    />
                  </AdminField>
                  {#if editFieldDirty("applies_to")}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                    >
                  {/if}
                </div>
                <div
                  class="admin-promo-field-shell"
                  class:is-dirty={editFieldDirty("max_activations")}
                >
                  <AdminField label={at("promo_label_max_activations", {}, "Max uses")}>
                    <Input
                      type="number"
                      class="input"
                      min={String(promoEditing.current_activations || 1)}
                      value={promoEditDraft.max_activations == null
                        ? ""
                        : String(promoEditDraft.max_activations)}
                      oninput={(e) => updateEditNumber("max_activations", inputValue(e))}
                    />
                  </AdminField>
                  {#if editFieldDirty("max_activations")}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                    >
                  {/if}
                </div>
                <div class="admin-promo-field-shell admin-promo-field-shell-static">
                  <AdminField label={at("promo_col_activations", {}, "Uses")}>
                    <Input
                      type="text"
                      class="input"
                      value={`${promoEditing.current_activations}/${promoEditing.max_activations}`}
                      disabled
                    />
                  </AdminField>
                </div>
                <div class="admin-promo-field-shell" class:is-dirty={editFieldDirty("valid_until")}>
                  <AdminField label={at("promo_col_valid_until", {}, "Valid until")}>
                    <Input
                      type="datetime-local"
                      class="input"
                      value={promoEditDraft.clear_valid_until
                        ? ""
                        : validUntilInputValue(
                            promoEditDraft.valid_until || promoEditing.valid_until
                          )}
                      disabled={Boolean(promoEditDraft.clear_valid_until)}
                      oninput={(e) => updateEditValidUntil(inputValue(e))}
                    />
                  </AdminField>
                  {#if editFieldDirty("valid_until")}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                    >
                  {/if}
                </div>
                <div class="admin-promo-field-shell" class:is-dirty={editFieldDirty("valid_until")}>
                  <AdminField label={at("unlimited", {}, "Unlimited")}>
                    <label class="admin-promo-check-row">
                      <Checkbox
                        checked={Boolean(promoEditDraft.clear_valid_until)}
                        ariaLabel={at("unlimited", {}, "Unlimited")}
                        onCheckedChange={(checked) =>
                          promosStore.updateEditDraft({
                            clear_valid_until: checked,
                            valid_until: checked ? null : promoEditing.valid_until,
                          } as Partial<PromoPatch>)}
                      />
                      <span>{at("unlimited", {}, "Unlimited")}</span>
                    </label>
                  </AdminField>
                  {#if editFieldDirty("valid_until")}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                    >
                  {/if}
                </div>
              </div>
            </section>

            <section
              class="admin-editor-section admin-promo-editor-section admin-promo-effect-section"
              class:is-dirty={promoEffectDirtyCount}
            >
              <header class="admin-editor-section-head">
                <div class="admin-editor-section-title">
                  <strong>{at("promo_col_effect", {}, "Effect")}</strong>
                  <small>
                    {at("promo_effect_single_hint", {}, "Choose one effect; values do not stack.")}
                  </small>
                </div>
                {#if promoEffectDirtyCount}
                  <AdminBadge variant="warning">
                    {at(
                      "settings_dirty_count",
                      { count: promoEffectDirtyCount },
                      `Changes: ${promoEffectDirtyCount}`
                    )}
                  </AdminBadge>
                {/if}
              </header>
              <PromoEffectSelector
                {at}
                value={promoEditEffectKind}
                values={promoEditDraft}
                dirtyFields={promoEffectDirtyFields}
                bonusRequiresPayment={Boolean(promoEditDraft.bonus_requires_payment)}
                bonusModeDirty={editFieldDirty("bonus_requires_payment")}
                onValueChange={selectEditEffect}
                onNumberInput={updateEditNumber}
                onBonusRequiresPaymentChange={setEditBonusRequiresPayment}
              />
            </section>

            <section
              class="admin-editor-section admin-promo-editor-section admin-promo-eligibility-section"
              class:is-dirty={promoEligibilityDirtyCount}
            >
              <header class="admin-editor-section-head">
                <div class="admin-editor-section-title">
                  <strong>{at("promo_col_eligibility", {}, "Eligibility")}</strong>
                  <small>
                    {promoEditUsesCheckout
                      ? at(
                          "promo_conditions_hint",
                          {},
                          "Optional minimum purchase requirements checked before the code can be applied."
                        )
                      : at(
                          "promo_conditions_disabled_for_instant_bonus",
                          {},
                          "Instant bonus-day grants do not use purchase requirements."
                        )}
                  </small>
                </div>
                {#if promoEligibilityDirtyCount}
                  <AdminBadge variant="warning">
                    {at(
                      "settings_dirty_count",
                      { count: promoEligibilityDirtyCount },
                      `Changes: ${promoEligibilityDirtyCount}`
                    )}
                  </AdminBadge>
                {/if}
              </header>
              <div class="admin-promo-fields-grid admin-promo-eligibility-grid">
                <div
                  class="admin-promo-field-shell"
                  class:is-dirty={editFieldDirty("min_subscription_months")}
                >
                  <AdminField label={at("promo_label_min_months", {}, "Min months")}>
                    <Input
                      type="number"
                      class="input"
                      min="1"
                      disabled={!promoEditUsesCheckout}
                      value={promoEditDraft.min_subscription_months == null
                        ? ""
                        : String(promoEditDraft.min_subscription_months)}
                      oninput={(e) => updateEditNumber("min_subscription_months", inputValue(e))}
                    />
                  </AdminField>
                  {#if editFieldDirty("min_subscription_months")}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                    >
                  {/if}
                </div>
                <div
                  class="admin-promo-field-shell"
                  class:is-dirty={editFieldDirty("min_traffic_gb")}
                >
                  <AdminField label={at("promo_label_min_gb", {}, "Min GB")}>
                    <Input
                      type="number"
                      class="input"
                      min="0"
                      step="0.01"
                      disabled={!promoEditUsesCheckout}
                      value={promoEditDraft.min_traffic_gb == null
                        ? ""
                        : String(promoEditDraft.min_traffic_gb)}
                      oninput={(e) => updateEditNumber("min_traffic_gb", inputValue(e))}
                    />
                  </AdminField>
                  {#if editFieldDirty("min_traffic_gb")}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                    >
                  {/if}
                </div>
              </div>
            </section>

            <section
              class="admin-editor-section admin-promo-editor-section admin-promo-links-section"
            >
              <header class="admin-editor-section-head">
                <div class="admin-editor-section-title">
                  <strong>{at("promo_section_links", {}, "Links")}</strong>
                </div>
              </header>
              <div class="admin-link-list admin-promo-link-list">
                <div class="admin-link-row">
                  <div class="admin-link-row-meta">
                    <span class="admin-link-row-label">
                      {at("promo_link_bot", {}, "Telegram bot")}
                    </span>
                    {#if promoEditing.bot_link}
                      <a
                        class="admin-link-row-url"
                        href={promoEditing.bot_link}
                        target="_blank"
                        rel="noopener"
                      >
                        {promoEditing.bot_link}
                      </a>
                    {:else}
                      <span class="admin-link-row-url admin-link-row-url-muted">
                        {at("promo_link_unavailable", {}, "Unavailable")}
                      </span>
                    {/if}
                  </div>
                  <div class="admin-promo-link-actions">
                    <AdminButton
                      size="icon"
                      variant="icon"
                      title={at("open", {}, "Open")}
                      aria-label={at("open", {}, "Open")}
                      disabled={!promoEditing.bot_link}
                      onclick={() => openPromoLink(promoEditing.bot_link)}
                    >
                      <ExternalLink size={14} />
                    </AdminButton>
                    <AdminButton
                      size="icon"
                      variant="icon"
                      title={at("copy", {}, "Copy")}
                      aria-label={at("copy", {}, "Copy")}
                      disabled={!promoEditing.bot_link}
                      onclick={() =>
                        promosStore.copyToClipboard(
                          promoEditing.bot_link,
                          at("promo_link_copied", {}, "Link copied")
                        )}
                    >
                      <Copy size={14} />
                    </AdminButton>
                  </div>
                </div>

                <div class="admin-link-row">
                  <div class="admin-link-row-meta">
                    <span class="admin-link-row-label">
                      {at("promo_link_webapp", {}, "Web app")}
                    </span>
                    {#if promoEditing.webapp_link}
                      <a
                        class="admin-link-row-url"
                        href={promoEditing.webapp_link}
                        target="_blank"
                        rel="noopener"
                      >
                        {promoEditing.webapp_link}
                      </a>
                    {:else}
                      <span class="admin-link-row-url admin-link-row-url-muted">
                        {at("promo_link_unavailable", {}, "Unavailable")}
                      </span>
                    {/if}
                  </div>
                  <div class="admin-promo-link-actions">
                    <AdminButton
                      size="icon"
                      variant="icon"
                      title={at("open", {}, "Open")}
                      aria-label={at("open", {}, "Open")}
                      disabled={!promoEditing.webapp_link}
                      onclick={() => openPromoLink(promoEditing.webapp_link)}
                    >
                      <ExternalLink size={14} />
                    </AdminButton>
                    <AdminButton
                      size="icon"
                      variant="icon"
                      title={at("copy", {}, "Copy")}
                      aria-label={at("copy", {}, "Copy")}
                      disabled={!promoEditing.webapp_link}
                      onclick={() =>
                        promosStore.copyToClipboard(
                          promoEditing.webapp_link,
                          at("promo_link_copied", {}, "Link copied")
                        )}
                    >
                      <Copy size={14} />
                    </AdminButton>
                  </div>
                </div>
              </div>
            </section>
          </div>

          <div class="admin-dialog-actions admin-promo-dialog-actions">
            {#if promoSettingsDirtyCount}
              <span class="admin-unsaved-hint">
                {at("promo_unsaved_hint", {}, "There are unsaved changes.")}
              </span>
            {/if}
            <AdminButton onclick={closePromoEditor}>{at("btn_cancel", {}, "Cancel")}</AdminButton>
            <AdminButton variant="primary" onclick={promosStore.savePromo}>
              {at("btn_save", {}, "Save")}
            </AdminButton>
          </div>
        </Tabs.Content>

        <Tabs.Content value="activations" class="admin-tabs-content admin-promo-activations-tab">
          <PromoActivationsPanel
            rows={editActivationRows}
            loading={activationsLoading}
            page={activationsPage}
            pageCount={activationsPageCount}
            total={activationsTotal}
            {at}
            {fmtDate}
            {fmtMoney}
            {paymentStatusVariant}
            {onOpenUserCard}
            onPageChange={(page) => promosStore.setActivationsPage(page)}
          />
        </Tabs.Content>
      </Tabs.Root>
    </div>
  {/if}
</Dialog>
