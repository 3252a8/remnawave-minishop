<script lang="ts">
  import { Checkbox, Input, Tabs } from "$components/ui/index.js";
  import { FileText, Sliders, Trash2 } from "$components/ui/icons.js";
  import { getContext, onMount } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminField,
    AdminPagination,
    AdminSelect,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import { TableHandler } from "@vincjo/datatables";
  import PromoActivationsPanel from "./promos/PromoActivationsPanel.svelte";
  import PromoEffectSelector from "./promos/PromoEffectSelector.svelte";
  import type { PromosStore } from "../../lib/admin/stores/promosStore";
  import type { components } from "../../lib/api/openapi.generated";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Promo = components["schemas"]["PromoOut"];
  type PromoDraft = Omit<components["schemas"]["PromoCreateBody"], "valid_days"> & {
    valid_days: number;
  };
  type PromoPatch = components["schemas"]["PromoUpdateBody"];
  type PromoActivation = components["schemas"]["PromoActivationOut"];
  type CreateNumberField =
    | "bonus_days"
    | "discount_percent"
    | "duration_multiplier"
    | "traffic_multiplier"
    | "min_subscription_months"
    | "min_traffic_gb"
    | "max_activations"
    | "valid_days";
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
  type EffectLike = {
    bonus_days?: number | null;
    discount_percent?: number | null;
    duration_multiplier?: number | null;
    traffic_multiplier?: number | null;
    bonus_requires_payment?: boolean | null;
    effect_summary?: string | null;
  };

  const BASIC_EDIT_FIELDS: readonly PromoEditField[] = [
    "is_active",
    "applies_to",
    "max_activations",
    "valid_until",
  ];
  const EFFECT_EDIT_FIELDS: readonly PromoEditField[] = [
    "bonus_days",
    "bonus_requires_payment",
    "discount_percent",
    "duration_multiplier",
    "traffic_multiplier",
  ];
  const ELIGIBILITY_EDIT_FIELDS: readonly PromoEditField[] = [
    "min_subscription_months",
    "min_traffic_gb",
  ];

  let {
    at,
    fmtDateShort,
    fmtDate = (value) => String(value || ""),
    fmtMoney = (value, currency) => `${value} ${currency || ""}`.trim(),
    paymentStatusVariant = () => "muted",
    onOpenUserCard = () => {},
  }: {
    at: TranslateFn;
    fmtDateShort: (value: string) => string;
    fmtDate?: (value: string | null | undefined) => string;
    fmtMoney?: (value: number, currency?: string | null) => string;
    paymentStatusVariant?: (status: string | null | undefined) => string;
    onOpenUserCard?: (userId: number) => void;
  } = $props();

  const promosStore = getContext<PromosStore>("promosStore");
  const promosTable = new TableHandler<Promo>();

  const promos = $derived(promosStore.promos as Promo[]);
  const promosTotal = $derived(Number(promosStore.promosTotal || 0));
  const promosPage = $derived(Number(promosStore.promosPage || 0));
  const promosLoading = $derived(Boolean(promosStore.promosLoading));
  const promoCreateOpen = $derived(Boolean(promosStore.promoCreateOpen));
  const promoEditOpen = $derived(Boolean(promosStore.promoEditOpen));
  const promoEditing = $derived(promosStore.promoEditing as Promo | null);
  const promoEditDraft = $derived((promosStore.promoEditDraft || {}) as PromoPatch);
  const activationsPromo = $derived(promosStore.promoActivationsPromo as Promo | null);
  const activations = $derived(promosStore.promoActivations as PromoActivation[]);
  const activationsLoading = $derived(Boolean(promosStore.promoActivationsLoading));
  const activationsTotal = $derived(Number(promosStore.promoActivationsTotal || 0));
  const activationsPage = $derived(Number(promosStore.promoActivationsPage || 0));
  const promoDraft = $derived(
    (promosStore.promoDraft || {
      code: "",
      bonus_days: 7,
      discount_percent: null,
      duration_multiplier: null,
      traffic_multiplier: null,
      bonus_requires_payment: false,
      applies_to: "all",
      min_subscription_months: null,
      min_traffic_gb: null,
      max_activations: 1,
      valid_days: 30,
      origin: "admin",
    }) as PromoDraft
  );
  const promoRows = $derived(promosTable.rows as Promo[]);
  const editActivationRows = $derived(activationsPromo?.id === promoEditing?.id ? activations : []);
  const promoBasicsDirtyCount = $derived(editDirtyCount(BASIC_EDIT_FIELDS));
  const promoEffectDirtyCount = $derived(editDirtyCount(EFFECT_EDIT_FIELDS));
  const promoEligibilityDirtyCount = $derived(editDirtyCount(ELIGIBILITY_EDIT_FIELDS));
  const promoSettingsDirtyCount = $derived(
    promoBasicsDirtyCount + promoEffectDirtyCount + promoEligibilityDirtyCount
  );
  const promoEffectDirtyFields = $derived({
    bonus_days: editFieldDirty("bonus_days") || editFieldDirty("bonus_requires_payment"),
    discount_percent: editFieldDirty("discount_percent"),
    duration_multiplier: editFieldDirty("duration_multiplier"),
    traffic_multiplier: editFieldDirty("traffic_multiplier"),
  } satisfies Partial<Record<PromoEffectKind, boolean>>);
  let promoCreateEffectKind = $state<PromoEffectKind>("bonus_days");
  let promoEditEffectKind = $state<PromoEffectKind>("bonus_days");
  let promoEditTab = $state<PromoEditTab>("settings");
  let previousCreateOpen = $state(false);
  let previousEditPromoId = $state<number | null>(null);
  const promoCreateUsesCheckout = $derived(
    promoCreateEffectKind !== "bonus_days" || Boolean(promoDraft.bonus_requires_payment)
  );
  const promoEditUsesCheckout = $derived(
    promoEditEffectKind !== "bonus_days" || Boolean(promoEditDraft.bonus_requires_payment)
  );

  $effect(() => promosTable.setRows(promos));
  $effect(() => {
    if (promoCreateOpen && !previousCreateOpen) {
      promoCreateEffectKind = effectKind(promoDraft);
    } else if (!promoCreateOpen) {
      promoCreateEffectKind = "bonus_days";
    }
    previousCreateOpen = promoCreateOpen;
  });
  $effect(() => {
    const editPromoId = promoEditing?.id ?? null;
    if (promoEditOpen && editPromoId !== previousEditPromoId) {
      promoEditEffectKind = effectKind(promoEditDraft);
      previousEditPromoId = editPromoId;
    } else if (!promoEditOpen) {
      promoEditEffectKind = "bonus_days";
      promoEditTab = "settings";
      previousEditPromoId = null;
    }
  });

  const promosPageCount = $derived(
    Math.max(1, Math.ceil(Number(promosTotal || 0) / promosStore.PROMOS_PAGE_SIZE))
  );
  const activationsPageCount = $derived(
    Math.max(1, Math.ceil(Number(activationsTotal || 0) / promosStore.ACTIVATIONS_PAGE_SIZE))
  );
  const promoHeaders = $derived([
    at("promo_csv_code", {}, "Code"),
    at("promo_col_type", {}, "Type"),
    at("promo_col_effect", {}, "Effect"),
    at("promo_col_scope", {}, "Scope"),
    at("promo_col_eligibility", {}, "Eligibility"),
    at("promo_col_activations", {}, "Uses"),
    at("promo_col_status", {}, "Status"),
    at("promo_col_valid_until", {}, "Valid until"),
    at("actions", {}, "Actions"),
  ]);
  const scopeItems = $derived([
    { value: "all", label: at("promo_scope_all", {}, "All") },
    { value: "subscription", label: at("promo_scope_subscription", {}, "Subscription") },
    { value: "traffic", label: at("promo_scope_traffic", {}, "Traffic package") },
    { value: "traffic_topup", label: at("promo_scope_traffic_topup", {}, "Traffic top-up") },
    { value: "hwid", label: at("promo_scope_hwid", {}, "HWID") },
  ]);
  onMount(() => {
    promosStore.loadPromos();
  });

  function nullableNumber(value: string): number | null {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function numberText(value: number | string | null | undefined): string {
    if (value == null || value === "") return "-";
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return "-";
    return Math.abs(parsed - Math.round(parsed)) < 1e-9
      ? String(Math.round(parsed))
      : String(Math.round(parsed * 100) / 100);
  }

  function multiplierText(value: number | null | undefined): string | null {
    if (value == null || Number(value) === 1) return null;
    return `x${numberText(value)}`;
  }

  function positiveNumber(
    value: number | string | null | undefined,
    fallback: number,
    minimum = 0
  ): number {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed > minimum ? parsed : fallback;
  }

  function effectKind(promo: EffectLike): PromoEffectKind {
    if (Number(promo.bonus_days || 0) > 0) return "bonus_days";
    if (Number(promo.discount_percent || 0) > 0) return "discount_percent";
    if (Number(promo.duration_multiplier || 1) > 1) return "duration_multiplier";
    if (Number(promo.traffic_multiplier || 1) > 1) return "traffic_multiplier";
    return "bonus_days";
  }

  function comparableNumber(value: number | string | null | undefined): number | null {
    if (value == null || value === "") return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function validUntilDirty(): boolean {
    if (!promoEditing) return false;
    if (promoEditDraft.clear_valid_until) {
      return promoEditing.valid_until != null && promoEditing.valid_until !== "";
    }
    return (
      validUntilInputValue(promoEditDraft.valid_until) !==
      validUntilInputValue(promoEditing.valid_until)
    );
  }

  function editFieldDirty(field: PromoEditField): boolean {
    if (!promoEditing) return false;
    if (field === "is_active") {
      return Boolean(promoEditDraft.is_active) !== Boolean(promoEditing.is_active);
    }
    if (field === "applies_to") {
      return (
        String(promoEditDraft.applies_to || "all") !== String(promoEditing.applies_to || "all")
      );
    }
    if (field === "valid_until") {
      return validUntilDirty();
    }
    if (field === "bonus_requires_payment") {
      return (
        Boolean(promoEditDraft.bonus_requires_payment) !==
        Boolean(promoEditing.bonus_requires_payment)
      );
    }
    return comparableNumber(promoEditDraft[field]) !== comparableNumber(promoEditing[field]);
  }

  function editDirtyCount(fields: readonly PromoEditField[]): number {
    return fields.filter((field) => editFieldDirty(field)).length;
  }

  function singleEffectPatch(kind: PromoEffectKind, source: EffectLike): Partial<PromoDraft> {
    return {
      bonus_days:
        kind === "bonus_days" ? Math.max(1, Math.trunc(positiveNumber(source.bonus_days, 7))) : 0,
      discount_percent:
        kind === "discount_percent" ? positiveNumber(source.discount_percent, 10) : null,
      duration_multiplier:
        kind === "duration_multiplier" ? positiveNumber(source.duration_multiplier, 2, 1) : null,
      traffic_multiplier:
        kind === "traffic_multiplier" ? positiveNumber(source.traffic_multiplier, 2, 1) : null,
      bonus_requires_payment:
        kind === "bonus_days" ? Boolean(source.bonus_requires_payment) : false,
    };
  }

  function selectCreateEffect(value: string): void {
    const kind = value as PromoEffectKind;
    promoCreateEffectKind = kind;
    const patch = singleEffectPatch(kind, promoDraft);
    if (kind === "bonus_days" && !patch.bonus_requires_payment) {
      patch.min_subscription_months = null;
      patch.min_traffic_gb = null;
    }
    promosStore.updateDraft(patch);
  }

  function selectEditEffect(value: string): void {
    const kind = value as PromoEffectKind;
    promoEditEffectKind = kind;
    const patch = singleEffectPatch(kind, promoEditDraft);
    if (kind === "bonus_days" && !patch.bonus_requires_payment) {
      patch.min_subscription_months = null;
      patch.min_traffic_gb = null;
    }
    promosStore.updateEditDraft(patch);
  }

  function setCreateBonusRequiresPayment(checked: boolean): void {
    promosStore.updateDraft({
      bonus_requires_payment: checked,
      min_subscription_months: checked ? promoDraft.min_subscription_months : null,
      min_traffic_gb: checked ? promoDraft.min_traffic_gb : null,
    });
  }

  function setEditBonusRequiresPayment(checked: boolean): void {
    promosStore.updateEditDraft({
      bonus_requires_payment: checked,
      min_subscription_months: checked ? promoEditDraft.min_subscription_months : null,
      min_traffic_gb: checked ? promoEditDraft.min_traffic_gb : null,
    } as Partial<PromoPatch>);
  }

  function openPromoSettings(promo: Promo): void {
    promoEditTab = "settings";
    promosStore.openEditPromo(promo);
  }

  function openPromoActivations(promo: Promo): void {
    promoEditTab = "activations";
    promosStore.openEditPromo(promo);
    void promosStore.openActivations(promo);
  }

  function selectPromoEditTab(value: string): void {
    promoEditTab = value as PromoEditTab;
    if (promoEditTab === "activations" && promoEditing) {
      void promosStore.openActivations(promoEditing);
    }
  }

  function closePromoEditor(): void {
    promosStore.closeActivations();
    promosStore.closeEditPromo();
    promoEditTab = "settings";
  }

  function scopeLabel(scope: string | null | undefined): string {
    const value = String(scope || "all");
    return scopeItems.find((item) => item.value === value)?.label || value;
  }

  function thresholdText(promo: Promo | PromoPatch): string {
    const parts: string[] = [];
    if (promo.min_subscription_months) {
      parts.push(
        at(
          "promo_threshold_months",
          { months: promo.min_subscription_months },
          `from ${promo.min_subscription_months} mo`
        )
      );
    }
    if (promo.min_traffic_gb) {
      parts.push(
        at(
          "promo_threshold_gb",
          { gb: numberText(promo.min_traffic_gb) },
          `from ${numberText(promo.min_traffic_gb)} GB`
        )
      );
    }
    return parts.join(", ") || "-";
  }

  function promoType(promo: Promo | PromoPatch): string {
    const hasBonus = Number(promo.bonus_days || 0) > 0;
    const hasDiscount = Number(promo.discount_percent || 0) > 0;
    const hasDuration = Number(promo.duration_multiplier || 1) > 1;
    const hasTraffic = Number(promo.traffic_multiplier || 1) > 1;
    const count = [hasBonus, hasDiscount, hasDuration, hasTraffic].filter(Boolean).length;
    if (count > 1) return at("promo_type_mixed", {}, "Mixed");
    if (hasDiscount) return at("promo_type_discount", {}, "Discount");
    if (hasDuration || hasTraffic) return at("promo_type_multiplier", {}, "Multiplier");
    return at("promo_type_bonus", {}, "Bonus");
  }

  function effectPieces(promo: EffectLike): string[] {
    const parts: string[] = [];
    if (Number(promo.bonus_days || 0) > 0) {
      parts.push(`+${promo.bonus_days} ${at("days_short", {}, "d")}`);
    }
    if (Number(promo.discount_percent || 0) > 0) {
      parts.push(`-${numberText(promo.discount_percent)}%`);
    }
    const duration = multiplierText(promo.duration_multiplier);
    if (duration) parts.push(`${duration} ${at("promo_effect_duration", {}, "duration")}`);
    const traffic = multiplierText(promo.traffic_multiplier);
    if (traffic) parts.push(`${traffic} ${at("promo_effect_traffic", {}, "traffic")}`);
    return parts;
  }

  function effectText(promo: EffectLike): string {
    const parts = effectPieces(promo);
    const text = promo.effect_summary || (parts.length ? parts.join(" + ") : "-");
    if (Number(promo.bonus_days || 0) <= 0) return text;
    const mode = promo.bonus_requires_payment
      ? at("promo_bonus_mode_payment_short", {}, "after payment")
      : at("promo_bonus_mode_instant_short", {}, "instant");
    return `${text} · ${mode}`;
  }

  function promoStatus(promo: Promo): { label: string; variant: "success" | "warning" | "muted" } {
    if (!promo.is_active) return { label: at("status_disabled", {}, "Disabled"), variant: "muted" };
    if (promo.valid_until && new Date(promo.valid_until).getTime() <= Date.now()) {
      return { label: at("status_expired", {}, "Expired"), variant: "warning" };
    }
    if (Number(promo.current_activations || 0) >= Number(promo.max_activations || 0)) {
      return { label: at("promo_status_used_up", {}, "Used up"), variant: "warning" };
    }
    return { label: at("badge_active", {}, "Active"), variant: "success" };
  }

  function validUntilInputValue(value: string | null | undefined): string {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const offsetMs = date.getTimezoneOffset() * 60_000;
    return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
  }

  function localDateTimeToIso(value: string): string | null {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const date = new Date(trimmed);
    if (Number.isNaN(date.getTime())) return null;
    return date.toISOString();
  }

  function updateEditValidUntil(value: string): void {
    const iso = localDateTimeToIso(value);
    promosStore.updateEditDraft({
      valid_until: iso,
      clear_valid_until: iso ? false : true,
    } as Partial<PromoPatch>);
  }

  function inputValue(event: Event): string {
    return (event.currentTarget as HTMLInputElement).value;
  }

  function updateCreateNumber(field: CreateNumberField, value: string): void {
    const parsed = nullableNumber(value);
    if (field === "bonus_days") {
      promosStore.updateDraft({ bonus_days: Number(parsed || 0) });
    } else if (field === "discount_percent") {
      promosStore.updateDraft({ discount_percent: parsed });
    } else if (field === "duration_multiplier") {
      promosStore.updateDraft({ duration_multiplier: parsed });
    } else if (field === "traffic_multiplier") {
      promosStore.updateDraft({ traffic_multiplier: parsed });
    } else if (field === "min_subscription_months") {
      promosStore.updateDraft({ min_subscription_months: parsed });
    } else if (field === "min_traffic_gb") {
      promosStore.updateDraft({ min_traffic_gb: parsed });
    } else if (field === "max_activations") {
      promosStore.updateDraft({ max_activations: Number(parsed || 1) });
    } else {
      promosStore.updateDraft({ valid_days: Number(parsed || 0) });
    }
  }

  function updateEditNumber(field: keyof PromoPatch, value: string): void {
    promosStore.updateEditDraft({ [field]: nullableNumber(value) } as Partial<PromoPatch>);
  }
</script>

<div class="admin-table-wrap admin-promos-table-wrap">
  {#if promosLoading}
    <AdminTableSkeleton
      headers={promoHeaders}
      rows={6}
      actionColumn
      widths={["92px", "86px", "132px", "96px", "104px", "78px", "78px", "96px", "132px"]}
    />
  {:else if !promos.length}
    <AdminEmptyState tone="card">
      <span class="admin-muted">{at("promos_empty", {}, "No codes")}</span>
    </AdminEmptyState>
  {:else}
    <AdminTable class="admin-promos-table">
      <thead>
        <tr>
          <th>{at("promo_csv_code", {}, "Code")}</th>
          <th>{at("promo_col_type", {}, "Type")}</th>
          <th>{at("promo_col_effect", {}, "Effect")}</th>
          <th>{at("promo_col_scope", {}, "Scope")}</th>
          <th>{at("promo_col_eligibility", {}, "Eligibility")}</th>
          <th>{at("promo_col_activations", {}, "Uses")}</th>
          <th>{at("promo_col_status", {}, "Status")}</th>
          <th>{at("promo_col_valid_until", {}, "Valid until")}</th>
          <th class="admin-cell-actions">{at("actions", {}, "Actions")}</th>
        </tr>
      </thead>
      <tbody>
        {#each promoRows as p (p.id)}
          {@const status = promoStatus(p)}
          <tr>
            <td class="admin-cell-mono" data-label={at("promo_csv_code", {}, "Code")}>{p.code}</td>
            <td data-label={at("promo_col_type", {}, "Type")}>
              <AdminBadge variant="muted">{promoType(p)}</AdminBadge>
            </td>
            <td class="admin-cell-wrap" data-label={at("promo_col_effect", {}, "Effect")}>
              {effectText(p)}
            </td>
            <td data-label={at("promo_col_scope", {}, "Scope")}>{scopeLabel(p.applies_to)}</td>
            <td data-label={at("promo_col_eligibility", {}, "Eligibility")}>
              {thresholdText(p)}
            </td>
            <td data-label={at("promo_col_activations", {}, "Uses")}>
              <AdminButton
                class="admin-promo-activations-btn"
                variant="ghost"
                size="sm"
                title={at("promo_activations_open", {}, "Open activations")}
                aria-label={at("promo_activations_open", {}, "Open activations")}
                onclick={() => openPromoActivations(p)}
              >
                {p.current_activations}/{p.max_activations}
              </AdminButton>
            </td>
            <td data-label={at("promo_col_status", {}, "Status")}>
              <AdminBadge variant={status.variant}>{status.label}</AdminBadge>
            </td>
            <td data-label={at("promo_col_valid_until", {}, "Valid until")}>
              {p.valid_until ? fmtDateShort(p.valid_until) : at("unlimited", {}, "Unlimited")}
            </td>
            <td class="admin-cell-actions" data-label={at("actions", {}, "Actions")}>
              <div class="admin-promo-actions">
                <AdminButton
                  size="icon"
                  variant="ghost"
                  title={at("btn_edit", {}, "Edit")}
                  aria-label={at("btn_edit", {}, "Edit")}
                  onclick={() => openPromoSettings(p)}
                >
                  <Sliders size={14} />
                </AdminButton>
                <AdminButton
                  size="icon"
                  variant="ghost"
                  title={at("promo_activations_open", {}, "Open activations")}
                  aria-label={at("promo_activations_open", {}, "Open activations")}
                  onclick={() => openPromoActivations(p)}
                >
                  <FileText size={14} />
                </AdminButton>
                <AdminButton
                  class="admin-promo-toggle-btn"
                  size="sm"
                  onclick={() => promosStore.togglePromo(p)}
                >
                  {p.is_active ? at("btn_disable", {}, "Off") : at("btn_enable", {}, "On")}
                </AdminButton>
                <AdminButton
                  size="icon"
                  variant="danger"
                  title={at("btn_delete", {}, "Delete")}
                  aria-label={at("btn_delete", {}, "Delete")}
                  onclick={() => promosStore.deletePromo(p)}
                >
                  <Trash2 size={14} />
                </AdminButton>
              </div>
            </td>
          </tr>
        {/each}
      </tbody>
    </AdminTable>
  {/if}
</div>

<AdminPagination
  page={promosPage}
  pageCount={promosPageCount}
  total={promosTotal}
  pageLabel={at("page_short", {}, "Page")}
  ofLabel={at("pagination_of", {}, "of")}
  totalLabel={at("total", {}, "Total")}
  jumpLabel={at("page_short", {}, "Page")}
  jumpAriaLabel={at("pagination_jump_aria", {}, "Go to page")}
  goLabel={at("pagination_go", {}, "Go")}
  prevLabel={at("back", {}, "Back")}
  nextLabel={at("next", {}, "Next")}
  onPageChange={(page) => promosStore.setPage(page)}
/>

<Dialog
  open={promoCreateOpen}
  title={at("promo_create_title", {}, "Create code")}
  closeLabel={at("close", {}, "Close")}
  onclose={() => promosStore.setCreateOpen(false)}
  class="admin-dialog admin-dialog-compact admin-promo-dialog"
>
  <div class="admin-form" data-dialog-content>
    <div class="admin-dialog-form-section">
      <div class="admin-form-row-2">
        <AdminField label={at("promo_label_code", {}, "Code")}>
          <Input
            type="text"
            class="input"
            value={promoDraft.code || ""}
            oninput={(e) =>
              promosStore.updateDraft({ code: (e.currentTarget as HTMLInputElement).value })}
            placeholder="AUTO"
          />
        </AdminField>
        <AdminField label={at("promo_label_scope", {}, "Scope")}>
          <AdminSelect
            value={promoDraft.applies_to || "all"}
            items={scopeItems}
            placeholder={at("promo_label_scope", {}, "Scope")}
            onValueChange={(value: string) => promosStore.updateDraft({ applies_to: value })}
          />
        </AdminField>
      </div>
      <div class="admin-promo-config-block">
        <div class="admin-promo-block-head">
          <div class="admin-promo-block-title">
            <strong>{at("promo_col_effect", {}, "Effect")}</strong>
            <small
              >{at(
                "promo_effect_single_hint",
                {},
                "Choose one effect; values do not stack."
              )}</small
            >
          </div>
        </div>
        <PromoEffectSelector
          {at}
          value={promoCreateEffectKind}
          values={promoDraft}
          onValueChange={selectCreateEffect}
          onNumberInput={updateCreateNumber}
        />
        {#if promoCreateEffectKind === "bonus_days"}
          <div class="admin-promo-field-shell admin-promo-bonus-mode">
            <AdminField label={at("promo_bonus_mode_label", {}, "Grant mode")}>
              <label class="admin-promo-check-row">
                <Checkbox
                  checked={Boolean(promoDraft.bonus_requires_payment)}
                  ariaLabel={at("promo_bonus_mode_payment", {}, "Grant after payment")}
                  onCheckedChange={setCreateBonusRequiresPayment}
                />
                <span>{at("promo_bonus_mode_payment", {}, "Grant after payment")}</span>
              </label>
            </AdminField>
            <small>
              {promoDraft.bonus_requires_payment
                ? at(
                    "promo_bonus_mode_payment_hint",
                    {},
                    "The user is sent to checkout; days are added only after a paid subscription purchase."
                  )
                : at(
                    "promo_bonus_mode_instant_hint",
                    {},
                    "The user receives the days immediately when the code is activated."
                  )}
            </small>
          </div>
        {/if}
      </div>
      <div class="admin-promo-config-block">
        <div class="admin-promo-block-head">
          <div class="admin-promo-block-title">
            <strong>{at("promo_col_eligibility", {}, "Eligibility")}</strong>
            <small>
              {promoCreateUsesCheckout
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
        </div>
        <div class="admin-form-row-2">
          <AdminField label={at("promo_label_min_months", {}, "Min months")}>
            <Input
              type="number"
              class="input"
              min="1"
              disabled={!promoCreateUsesCheckout}
              value={promoDraft.min_subscription_months == null
                ? ""
                : String(promoDraft.min_subscription_months)}
              oninput={(e) => updateCreateNumber("min_subscription_months", inputValue(e))}
            />
          </AdminField>
          <AdminField label={at("promo_label_min_gb", {}, "Min GB")}>
            <Input
              type="number"
              class="input"
              min="0"
              step="0.01"
              disabled={!promoCreateUsesCheckout}
              value={promoDraft.min_traffic_gb == null ? "" : String(promoDraft.min_traffic_gb)}
              oninput={(e) => updateCreateNumber("min_traffic_gb", inputValue(e))}
            />
          </AdminField>
        </div>
      </div>
      <div class="admin-form-row-2">
        <AdminField label={at("promo_label_max_activations", {}, "Max uses")}>
          <Input
            type="number"
            class="input"
            min="1"
            value={String(promoDraft.max_activations)}
            oninput={(e) => updateCreateNumber("max_activations", inputValue(e))}
          />
        </AdminField>
        <AdminField label={at("promo_label_valid_days", {}, "Valid days")}>
          <Input
            type="number"
            class="input"
            min="0"
            value={promoDraft.valid_days ? String(promoDraft.valid_days) : ""}
            oninput={(e) => updateCreateNumber("valid_days", inputValue(e))}
          />
        </AdminField>
      </div>
    </div>
    <div class="admin-dialog-actions">
      <AdminButton onclick={() => promosStore.setCreateOpen(false)}>
        {at("btn_cancel", {}, "Cancel")}
      </AdminButton>
      <AdminButton variant="primary" onclick={promosStore.createPromo}>
        {at("btn_create", {}, "Create")}
      </AdminButton>
    </div>
  </div>
</Dialog>

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
          <section
            class="admin-editor-section admin-promo-editor-section"
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
            <div class="admin-form-row-2">
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
            </div>
            <div class="admin-form-row-2">
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
              <AdminField label={at("promo_col_activations", {}, "Uses")}>
                <Input
                  type="text"
                  class="input"
                  value={`${promoEditing.current_activations}/${promoEditing.max_activations}`}
                  disabled
                />
              </AdminField>
            </div>
            <div class="admin-form-row-2">
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
            class="admin-editor-section admin-promo-editor-section"
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
              onValueChange={selectEditEffect}
              onNumberInput={updateEditNumber}
            />
            {#if promoEditEffectKind === "bonus_days"}
              <div
                class="admin-promo-field-shell admin-promo-bonus-mode"
                class:is-dirty={editFieldDirty("bonus_requires_payment")}
              >
                <AdminField label={at("promo_bonus_mode_label", {}, "Grant mode")}>
                  <label class="admin-promo-check-row">
                    <Checkbox
                      checked={Boolean(promoEditDraft.bonus_requires_payment)}
                      ariaLabel={at("promo_bonus_mode_payment", {}, "Grant after payment")}
                      onCheckedChange={setEditBonusRequiresPayment}
                    />
                    <span>{at("promo_bonus_mode_payment", {}, "Grant after payment")}</span>
                  </label>
                </AdminField>
                <small>
                  {promoEditDraft.bonus_requires_payment
                    ? at(
                        "promo_bonus_mode_payment_hint",
                        {},
                        "The user is sent to checkout; days are added only after a paid subscription purchase."
                      )
                    : at(
                        "promo_bonus_mode_instant_hint",
                        {},
                        "The user receives the days immediately when the code is activated."
                      )}
                </small>
                {#if editFieldDirty("bonus_requires_payment")}
                  <AdminBadge variant="warning"
                    >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                  >
                {/if}
              </div>
            {/if}
          </section>

          <section
            class="admin-editor-section admin-promo-editor-section"
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
            <div class="admin-form-row-2">
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

<style>
  .admin-promos-table-wrap :global(.admin-promos-table) {
    min-width: 900px;
  }

  .admin-promo-actions {
    display: inline-flex;
    align-items: center;
    justify-content: flex-end;
    gap: 6px;
    min-height: 34px;
    vertical-align: middle;
  }

  .admin-promo-actions :global(.admin-btn) {
    flex: 0 0 auto;
    margin-left: 0;
  }

  .admin-promos-table-wrap :global(.admin-promo-activations-btn.admin-btn) {
    height: 28px;
    min-height: 28px;
    padding: 0 8px;
    font-family: var(--font-mono);
  }

  .admin-promos-table-wrap :global(.admin-promo-toggle-btn.admin-btn) {
    height: 34px;
    min-height: 34px;
    padding: 0 12px;
    border-radius: 8px;
  }

  :global(.dialog-card.admin-dialog.admin-promo-dialog) {
    width: min(1040px, calc(100vw - 32px));
    inline-size: min(1040px, calc(100vw - 32px));
    max-width: none;
    max-height: min(100%, 780px);
  }

  :global(.dialog-card.admin-dialog.admin-promo-edit-dialog) {
    width: min(1240px, calc(100vw - 32px));
    inline-size: min(1240px, calc(100vw - 32px));
  }

  :global(.admin-promo-dialog > .dialog-body-scroll),
  :global(.admin-promo-dialog .dialog-body-scroll > .scroll-area__viewport),
  :global(.admin-promo-dialog .dialog-body-scroll > .scroll-area__viewport > div) {
    box-sizing: border-box;
    width: 100% !important;
    min-width: 0 !important;
    max-width: 100% !important;
  }

  .admin-promo-config-block {
    display: grid;
    gap: 12px;
    min-width: 0;
  }

  .admin-promo-block-head,
  .admin-promo-block-title,
  .admin-editor-section-title {
    min-width: 0;
  }

  .admin-promo-block-title,
  .admin-editor-section-title {
    display: grid;
    gap: 3px;
  }

  .admin-promo-block-title small,
  .admin-editor-section-title small {
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.35;
  }

  .admin-promo-check-row {
    display: inline-flex;
    align-items: center;
    min-height: 38px;
    gap: 8px;
    color: var(--admin-text);
  }

  .admin-promo-edit-body {
    display: grid;
    gap: 12px;
    min-width: 0;
  }

  .admin-promo-edit-summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px;
    border: 1px solid var(--admin-border);
    border-radius: 8px;
    background: var(--admin-surface-2);
    min-width: 0;
  }

  .admin-promo-edit-summary-main {
    display: grid;
    gap: 2px;
    min-width: 0;
  }

  .admin-promo-edit-summary-main span,
  .admin-promo-edit-summary-uses {
    color: var(--admin-muted);
    font-size: 12px;
  }

  .admin-promo-edit-summary-main strong {
    color: var(--admin-text);
    font-family: var(--font-mono);
    font-size: 16px;
    font-weight: 750;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .admin-promo-edit-summary-meta {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    flex-wrap: wrap;
    gap: 8px;
    flex: 0 0 auto;
  }

  .admin-promo-tab-dirty-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 18px;
    height: 18px;
    padding: 0 5px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--warning, #f59e0b) 18%, transparent);
    color: color-mix(in srgb, var(--warning, #f59e0b) 72%, var(--admin-text));
    font-size: 11px;
    font-weight: 700;
    line-height: 1;
  }

  .admin-promo-editor-section {
    gap: 12px;
  }

  .admin-promo-editor-section.is-dirty {
    border-color: color-mix(in srgb, var(--warning, #f59e0b) 70%, var(--admin-border));
    background: color-mix(in srgb, var(--warning, #f59e0b) 6%, var(--admin-surface-2));
  }

  .admin-promo-editor-section .admin-editor-section-head {
    min-height: 20px;
  }

  .admin-promo-field-shell {
    display: grid;
    gap: 6px;
    min-width: 0;
    padding: 8px;
    border: 1px solid transparent;
    border-radius: 8px;
  }

  .admin-promo-field-shell.is-dirty {
    border-color: color-mix(in srgb, var(--warning, #f59e0b) 64%, var(--admin-border));
    background: color-mix(in srgb, var(--warning, #f59e0b) 7%, transparent);
  }

  .admin-promo-field-shell :global(.admin-badge) {
    justify-self: start;
  }

  .admin-promo-bonus-mode {
    background: color-mix(in srgb, var(--accent) 5%, transparent);
  }

  .admin-promo-bonus-mode small {
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.35;
  }

  .admin-promo-dialog-actions {
    align-items: center;
  }

  .admin-promo-dialog-actions .admin-unsaved-hint {
    margin-right: auto;
  }

  @media (max-width: 720px) {
    .admin-promos-table-wrap :global(.admin-promos-table) {
      min-width: 0;
    }

    :global(.dialog-card.admin-dialog.admin-promo-dialog),
    :global(.dialog-card.admin-dialog.admin-promo-edit-dialog) {
      width: min(100%, calc(100vw - 24px));
      inline-size: min(100%, calc(100vw - 24px));
      padding: 14px;
      border-radius: 18px;
    }

    .admin-promo-edit-summary {
      align-items: stretch;
      flex-direction: column;
    }

    .admin-promo-edit-summary-meta {
      justify-content: flex-start;
    }

    .admin-promo-dialog-actions .admin-unsaved-hint {
      width: 100%;
      margin-right: 0;
    }
  }
</style>
