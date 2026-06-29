<script lang="ts">
  import { Checkbox, Input, ScrollArea } from "$components/ui/index.js";
  import { FileText, Sliders, Trash2, User } from "$components/ui/icons.js";
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
  import type { PromosStore } from "../../lib/admin/stores/promosStore";
  import type { components } from "../../lib/api/openapi.generated";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Promo = components["schemas"]["PromoOut"];
  type PromoDraft = components["schemas"]["PromoCreateBody"];
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
  type EffectLike = {
    bonus_days?: number | null;
    discount_percent?: number | null;
    duration_multiplier?: number | null;
    traffic_multiplier?: number | null;
    effect_summary?: string | null;
  };

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
  const activationsTable = new TableHandler<PromoActivation>();

  const promos = $derived(promosStore.promos as Promo[]);
  const promosTotal = $derived(Number(promosStore.promosTotal || 0));
  const promosPage = $derived(Number(promosStore.promosPage || 0));
  const promosLoading = $derived(Boolean(promosStore.promosLoading));
  const promoCreateOpen = $derived(Boolean(promosStore.promoCreateOpen));
  const promoEditOpen = $derived(Boolean(promosStore.promoEditOpen));
  const promoEditing = $derived(promosStore.promoEditing as Promo | null);
  const promoEditDraft = $derived((promosStore.promoEditDraft || {}) as PromoPatch);
  const activationsOpen = $derived(Boolean(promosStore.promoActivationsOpen));
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
      applies_to: "all",
      min_subscription_months: null,
      min_traffic_gb: null,
      max_activations: 1,
      valid_days: 30,
      origin: "admin",
    }) as PromoDraft
  );
  const promoRows = $derived(promosTable.rows as Promo[]);
  const activationRows = $derived(activationsTable.rows as PromoActivation[]);

  $effect(() => promosTable.setRows(promos));
  $effect(() => activationsTable.setRows(activations));

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
    at("promo_col_origin", {}, "Origin"),
    at("actions", {}, "Actions"),
  ]);
  const activationHeaders = $derived([
    at("user", {}, "User"),
    at("date", {}, "Date"),
    at("payment_detail_payment_section", {}, "Payment"),
    at("amount", {}, "Amount"),
    at("promo_col_base_amount", {}, "Base"),
    at("promo_col_discount_amount", {}, "Discount"),
    at("promo_col_grant", {}, "Grant"),
    at("promo_col_effect", {}, "Effect"),
    at("status", {}, "Status"),
    at("provider", {}, "Provider"),
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
    if (promo.effect_summary) return promo.effect_summary;
    const parts = effectPieces(promo);
    return parts.length ? parts.join(" + ") : "-";
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

  function activationEffectText(row: PromoActivation): string {
    if (row.effect_summary) return row.effect_summary;
    const parts = effectPieces(row);
    return parts.length ? parts.join(" + ") : "-";
  }

  function paymentLabel(row: PromoActivation): string {
    if (!row.payment_id) return at("promo_activation_standalone", {}, "Standalone");
    return `#${row.payment_id}`;
  }

  function amountLabel(row: PromoActivation): string {
    if (row.payment_amount == null) return "-";
    return fmtMoney(Number(row.payment_amount), row.payment_currency);
  }

  function baseAmountLabel(row: PromoActivation): string {
    if (row.base_amount == null) return "-";
    return fmtMoney(Number(row.base_amount), row.payment_currency);
  }

  function discountAmountLabel(row: PromoActivation): string {
    if (row.discount_amount == null || Number(row.discount_amount || 0) <= 0) return "-";
    return fmtMoney(Number(row.discount_amount), row.payment_currency);
  }

  function gbText(value: number | null | undefined): string {
    if (value == null) return "";
    return `${numberText(value)} GB`;
  }

  function grantLabel(row: PromoActivation): string {
    const parts: string[] = [];
    if (Number(row.granted_days || 0) > 0) {
      parts.push(`+${numberText(row.granted_days)} ${at("days_short", {}, "d")}`);
    }
    if (row.charged_gb != null && row.granted_gb != null) {
      parts.push(`${gbText(row.charged_gb)} -> ${gbText(row.granted_gb)}`);
    } else if (row.granted_gb != null) {
      parts.push(gbText(row.granted_gb));
    }
    if (row.charged_months != null && Number(row.granted_days || 0) > 0) {
      parts.push(`${numberText(row.charged_months)} mo`);
    }
    return parts.join(", ") || "-";
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
      widths={["92px", "86px", "132px", "96px", "104px", "78px", "78px", "96px", "76px", "132px"]}
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
          <th>{at("promo_col_origin", {}, "Origin")}</th>
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
                onclick={() => void promosStore.openActivations(p)}
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
            <td class="admin-cell-mono" data-label={at("promo_col_origin", {}, "Origin")}>
              {p.origin || "admin"}
            </td>
            <td class="admin-cell-actions" data-label={at("actions", {}, "Actions")}>
              <AdminButton
                size="icon"
                variant="ghost"
                title={at("btn_edit", {}, "Edit")}
                aria-label={at("btn_edit", {}, "Edit")}
                onclick={() => promosStore.openEditPromo(p)}
              >
                <Sliders size={14} />
              </AdminButton>
              <AdminButton
                size="icon"
                variant="ghost"
                title={at("promo_activations_open", {}, "Open activations")}
                aria-label={at("promo_activations_open", {}, "Open activations")}
                onclick={() => void promosStore.openActivations(p)}
              >
                <FileText size={14} />
              </AdminButton>
              <AdminButton size="sm" onclick={() => promosStore.togglePromo(p)}>
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
      <div class="admin-form-row-3">
        <AdminField label={at("promo_label_bonus_days", {}, "Bonus days")}>
          <Input
            type="number"
            class="input"
            min="0"
            value={String(promoDraft.bonus_days || 0)}
            oninput={(e) => updateCreateNumber("bonus_days", inputValue(e))}
          />
        </AdminField>
        <AdminField label={at("promo_label_discount", {}, "Discount %")}>
          <Input
            type="number"
            class="input"
            min="0"
            max="100"
            step="0.01"
            value={promoDraft.discount_percent == null ? "" : String(promoDraft.discount_percent)}
            oninput={(e) => updateCreateNumber("discount_percent", inputValue(e))}
          />
        </AdminField>
        <AdminField label={at("promo_label_duration_multiplier", {}, "Duration x")}>
          <Input
            type="number"
            class="input"
            min="1"
            step="0.001"
            value={promoDraft.duration_multiplier == null
              ? ""
              : String(promoDraft.duration_multiplier)}
            oninput={(e) => updateCreateNumber("duration_multiplier", inputValue(e))}
          />
        </AdminField>
      </div>
      <div class="admin-form-row-3">
        <AdminField label={at("promo_label_traffic_multiplier", {}, "Traffic x")}>
          <Input
            type="number"
            class="input"
            min="1"
            step="0.001"
            value={promoDraft.traffic_multiplier == null
              ? ""
              : String(promoDraft.traffic_multiplier)}
            oninput={(e) => updateCreateNumber("traffic_multiplier", inputValue(e))}
          />
        </AdminField>
        <AdminField label={at("promo_label_min_months", {}, "Min months")}>
          <Input
            type="number"
            class="input"
            min="1"
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
            value={promoDraft.min_traffic_gb == null ? "" : String(promoDraft.min_traffic_gb)}
            oninput={(e) => updateCreateNumber("min_traffic_gb", inputValue(e))}
          />
        </AdminField>
      </div>
      <div class="admin-form-row-3">
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
        <AdminField label={at("promo_col_origin", {}, "Origin")}>
          <Input
            type="text"
            class="input"
            value={promoDraft.origin || "admin"}
            oninput={(e) =>
              promosStore.updateDraft({ origin: (e.currentTarget as HTMLInputElement).value })}
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
  onclose={promosStore.closeEditPromo}
  class="admin-dialog admin-dialog-compact admin-promo-dialog"
>
  {#if promoEditing}
    <div class="admin-form" data-dialog-content>
      <div class="admin-dialog-form-section">
        <div class="admin-form-row-2">
          <AdminField label={at("promo_label_code", {}, "Code")}>
            <Input type="text" class="input" value={promoEditing.code} disabled />
          </AdminField>
          <AdminField label={at("promo_col_status", {}, "Status")}>
            <label class="admin-promo-check-row">
              <Checkbox
                checked={Boolean(promoEditDraft.is_active)}
                ariaLabel={at("status_active", {}, "Active")}
                onCheckedChange={(checked) => promosStore.updateEditDraft({ is_active: checked })}
              />
              <span>{at("badge_active", {}, "Active")}</span>
            </label>
          </AdminField>
        </div>
        <div class="admin-form-row-2">
          <AdminField label={at("promo_label_scope", {}, "Scope")}>
            <AdminSelect
              value={promoEditDraft.applies_to || "all"}
              items={scopeItems}
              placeholder={at("promo_label_scope", {}, "Scope")}
              onValueChange={(value: string) => promosStore.updateEditDraft({ applies_to: value })}
            />
          </AdminField>
          <AdminField label={at("promo_col_origin", {}, "Origin")}>
            <Input
              type="text"
              class="input"
              value={promoEditDraft.origin || "admin"}
              oninput={(e) =>
                promosStore.updateEditDraft({
                  origin: (e.currentTarget as HTMLInputElement).value,
                })}
            />
          </AdminField>
        </div>
        <div class="admin-form-row-3">
          <AdminField label={at("promo_label_bonus_days", {}, "Bonus days")}>
            <Input
              type="number"
              class="input"
              min="0"
              value={String(promoEditDraft.bonus_days || 0)}
              oninput={(e) => updateEditNumber("bonus_days", inputValue(e))}
            />
          </AdminField>
          <AdminField label={at("promo_label_discount", {}, "Discount %")}>
            <Input
              type="number"
              class="input"
              min="0"
              max="100"
              step="0.01"
              value={promoEditDraft.discount_percent == null
                ? ""
                : String(promoEditDraft.discount_percent)}
              oninput={(e) => updateEditNumber("discount_percent", inputValue(e))}
            />
          </AdminField>
          <AdminField label={at("promo_label_duration_multiplier", {}, "Duration x")}>
            <Input
              type="number"
              class="input"
              min="1"
              step="0.001"
              value={promoEditDraft.duration_multiplier == null
                ? ""
                : String(promoEditDraft.duration_multiplier)}
              oninput={(e) => updateEditNumber("duration_multiplier", inputValue(e))}
            />
          </AdminField>
        </div>
        <div class="admin-form-row-3">
          <AdminField label={at("promo_label_traffic_multiplier", {}, "Traffic x")}>
            <Input
              type="number"
              class="input"
              min="1"
              step="0.001"
              value={promoEditDraft.traffic_multiplier == null
                ? ""
                : String(promoEditDraft.traffic_multiplier)}
              oninput={(e) => updateEditNumber("traffic_multiplier", inputValue(e))}
            />
          </AdminField>
          <AdminField label={at("promo_label_min_months", {}, "Min months")}>
            <Input
              type="number"
              class="input"
              min="1"
              value={promoEditDraft.min_subscription_months == null
                ? ""
                : String(promoEditDraft.min_subscription_months)}
              oninput={(e) => updateEditNumber("min_subscription_months", inputValue(e))}
            />
          </AdminField>
          <AdminField label={at("promo_label_min_gb", {}, "Min GB")}>
            <Input
              type="number"
              class="input"
              min="0"
              step="0.01"
              value={promoEditDraft.min_traffic_gb == null
                ? ""
                : String(promoEditDraft.min_traffic_gb)}
              oninput={(e) => updateEditNumber("min_traffic_gb", inputValue(e))}
            />
          </AdminField>
        </div>
        <div class="admin-form-row-2">
          <AdminField label={at("promo_label_max_activations", {}, "Max uses")}>
            <Input
              type="number"
              class="input"
              min={String(promoEditing.current_activations || 1)}
              value={String(promoEditDraft.max_activations || promoEditing.max_activations)}
              oninput={(e) => updateEditNumber("max_activations", inputValue(e))}
            />
          </AdminField>
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
          <AdminField label={at("promo_col_valid_until", {}, "Valid until")}>
            <Input
              type="datetime-local"
              class="input"
              value={promoEditDraft.clear_valid_until
                ? ""
                : validUntilInputValue(promoEditDraft.valid_until || promoEditing.valid_until)}
              disabled={Boolean(promoEditDraft.clear_valid_until)}
              oninput={(e) => updateEditValidUntil(inputValue(e))}
            />
          </AdminField>
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
        </div>
      </div>
      <div class="admin-dialog-actions">
        <AdminButton onclick={promosStore.closeEditPromo}
          >{at("btn_cancel", {}, "Cancel")}</AdminButton
        >
        <AdminButton variant="primary" onclick={promosStore.savePromo}>
          {at("btn_save", {}, "Save")}
        </AdminButton>
      </div>
    </div>
  {/if}
</Dialog>

<Dialog
  open={activationsOpen}
  title={activationsPromo
    ? at(
        "promo_activations_title",
        { code: activationsPromo.code },
        `Activations ${activationsPromo.code}`
      )
    : at("promo_activations_title_empty", {}, "Activations")}
  closeLabel={at("close", {}, "Close")}
  onclose={promosStore.closeActivations}
  class="admin-dialog admin-promo-activations-dialog"
>
  <div class="admin-promo-activations-body" data-dialog-content>
    {#if activationsLoading}
      <AdminTableSkeleton
        headers={activationHeaders}
        rows={6}
        widths={[
          "160px",
          "104px",
          "72px",
          "86px",
          "86px",
          "86px",
          "120px",
          "120px",
          "86px",
          "90px",
        ]}
      />
    {:else if !activationRows.length}
      <AdminEmptyState tone="card">
        <span class="admin-muted">{at("promo_activations_empty", {}, "No activations")}</span>
      </AdminEmptyState>
    {:else}
      <ScrollArea class="admin-promo-activations-scroll" maxHeight="min(58vh, 520px)">
        <AdminTable class="admin-promo-activations-table">
          <thead>
            <tr>
              <th>{at("user", {}, "User")}</th>
              <th>{at("date", {}, "Date")}</th>
              <th>{at("payment_detail_payment_section", {}, "Payment")}</th>
              <th>{at("amount", {}, "Amount")}</th>
              <th>{at("promo_col_base_amount", {}, "Base")}</th>
              <th>{at("promo_col_discount_amount", {}, "Discount")}</th>
              <th>{at("promo_col_grant", {}, "Grant")}</th>
              <th>{at("promo_col_effect", {}, "Effect")}</th>
              <th>{at("status", {}, "Status")}</th>
              <th>{at("provider", {}, "Provider")}</th>
            </tr>
          </thead>
          <tbody>
            {#each activationRows as row (row.activation_id)}
              <tr>
                <td class="admin-cell-user-with-action" data-label={at("user", {}, "User")}>
                  <span class="admin-promos-user-cell">
                    <AdminButton
                      class="admin-promos-user-btn"
                      variant="ghost"
                      size="icon"
                      title={at("payments_open_user", {}, "Open user card")}
                      aria-label={at("payments_open_user", {}, "Open user card")}
                      onclick={() => onOpenUserCard(row.user_id)}
                    >
                      <User size={14} />
                    </AdminButton>
                    <span class="admin-promos-user-name">
                      {row.user_label || row.user_id}
                      <small>ID {row.user_id}</small>
                    </span>
                  </span>
                </td>
                <td data-label={at("date", {}, "Date")}>{fmtDate(row.activated_at)}</td>
                <td
                  class="admin-cell-mono"
                  data-label={at("payment_detail_payment_section", {}, "Payment")}
                >
                  {paymentLabel(row)}
                </td>
                <td data-label={at("amount", {}, "Amount")}>{amountLabel(row)}</td>
                <td data-label={at("promo_col_base_amount", {}, "Base")}>
                  {baseAmountLabel(row)}
                </td>
                <td data-label={at("promo_col_discount_amount", {}, "Discount")}>
                  {discountAmountLabel(row)}
                </td>
                <td class="admin-cell-wrap" data-label={at("promo_col_grant", {}, "Grant")}>
                  {grantLabel(row)}
                </td>
                <td class="admin-cell-wrap" data-label={at("promo_col_effect", {}, "Effect")}>
                  {activationEffectText(row)}
                </td>
                <td data-label={at("status", {}, "Status")}>
                  {#if row.payment_status}
                    <AdminBadge variant={paymentStatusVariant(row.payment_status)}>
                      {row.payment_status}
                    </AdminBadge>
                  {:else}
                    <AdminBadge variant="muted">
                      {at("promo_activation_standalone", {}, "Standalone")}
                    </AdminBadge>
                  {/if}
                </td>
                <td data-label={at("provider", {}, "Provider")}>
                  {row.payment_provider || "-"}
                </td>
              </tr>
            {/each}
          </tbody>
        </AdminTable>
      </ScrollArea>
    {/if}
    <AdminPagination
      page={activationsPage}
      pageCount={activationsPageCount}
      total={activationsTotal}
      pageLabel={at("page_short", {}, "Page")}
      ofLabel={at("pagination_of", {}, "of")}
      totalLabel={at("total", {}, "Total")}
      jumpLabel={at("page_short", {}, "Page")}
      jumpAriaLabel={at("pagination_jump_aria", {}, "Go to page")}
      goLabel={at("pagination_go", {}, "Go")}
      prevLabel={at("back", {}, "Back")}
      nextLabel={at("next", {}, "Next")}
      onPageChange={(page) => promosStore.setActivationsPage(page)}
    />
  </div>
</Dialog>

<style>
  .admin-promos-table-wrap :global(.admin-promos-table) {
    min-width: 980px;
  }

  .admin-promos-table-wrap :global(.admin-cell-actions) {
    gap: 6px;
  }

  .admin-promos-table-wrap :global(.admin-promo-activations-btn.admin-btn) {
    height: 28px;
    min-height: 28px;
    padding: 0 8px;
    font-family: var(--font-mono);
  }

  .admin-form-row-3 {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
  }

  .admin-promo-check-row {
    display: inline-flex;
    align-items: center;
    min-height: 38px;
    gap: 8px;
    color: var(--admin-text);
  }

  .admin-promo-activations-body {
    display: grid;
    gap: 12px;
  }

  :global(.admin-promo-activations-scroll) {
    width: 100%;
  }

  :global(.admin-promo-activations-table) {
    min-width: 1180px;
  }

  .admin-promos-user-cell {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  .admin-promos-user-name {
    display: grid;
    min-width: 0;
    gap: 2px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-promos-user-name small {
    color: var(--admin-muted);
    font-family: var(--font-mono);
    font-size: 11px;
  }

  .admin-cell-user-with-action :global(.admin-promos-user-btn.admin-btn) {
    width: 30px;
    height: 30px;
    min-width: 30px;
    min-height: 30px;
    flex-shrink: 0;
    padding: 0;
    border-radius: 7px;
  }

  @media (max-width: 720px) {
    .admin-form-row-3 {
      grid-template-columns: 1fr;
    }

    .admin-promos-table-wrap :global(.admin-promos-table),
    :global(.admin-promo-activations-table) {
      min-width: 0;
    }
  }
</style>
