<script lang="ts">
  import { getPromosStore } from "$lib/admin/context";
  import { FileText, RefreshCw, Sliders, Trash2, User } from "$components/ui/icons.js";
  import { onMount } from "svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminEntityLink,
    AdminListToolbar,
    AdminPagination,
    AdminSelect,
    AdminSortableHeader,
    AdminTable,
    AdminTableSkeleton,
    VirtualTableRows,
  } from "$components/patterns/admin/index.js";
  import Input from "$components/ui/input.svelte";
  import { Tabs } from "$components/ui/primitives.js";
  import { TableHandler } from "@vincjo/datatables";
  import PromoCreateDialog from "./promos/PromoCreateDialog.svelte";
  import PromoEditDialog from "./promos/PromoEditDialog.svelte";
  import type { components } from "../../lib/api/openapi.generated";
  import type {
    PromoKind,
    PromoScopeFilter,
    PromoStatusFilter,
  } from "$lib/admin/stores/promosStore.svelte";
  import type { AdminBadgeVariant } from "$components/patterns/admin/types";
  import type { AdminSortColumn } from "$lib/admin/tableSort.js";
  import {
    formatAdminPromoEffect,
    formatAdminPromoEligibility,
  } from "$lib/admin/promoEffectDisplay.js";
  import type { PromoEffectSource } from "$lib/admin/promoEffectDisplay.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Promo = components["schemas"]["PromoOut"];
  type PromoDraft = Omit<components["schemas"]["PromoCreateBody"], "valid_days"> & {
    valid_days: number;
  };
  type PromoPatch = components["schemas"]["PromoUpdateBody"];
  type PromoActivation = components["schemas"]["PromoActivationOut"];
  type CreateNumberField =
    | "bonus_days"
    | "regular_traffic_gb"
    | "premium_traffic_gb"
    | "discount_percent"
    | "duration_multiplier"
    | "traffic_multiplier"
    | "min_subscription_days"
    | "min_traffic_gb"
    | "max_activations"
    | "valid_days";
  type PromoEffectKind =
    | "bonus_days"
    | "regular_traffic_gb"
    | "premium_traffic_gb"
    | "discount_percent"
    | "duration_multiplier"
    | "traffic_multiplier";
  type PromoEditTab = "settings" | "activations";
  type PromoEditField =
    | "is_active"
    | "applies_to"
    | "max_activations"
    | "valid_until"
    | "bonus_days"
    | "regular_traffic_gb"
    | "premium_traffic_gb"
    | "bonus_requires_payment"
    | "discount_percent"
    | "duration_multiplier"
    | "traffic_multiplier"
    | "min_subscription_days"
    | "min_traffic_gb";
  const BASIC_EDIT_FIELDS: readonly PromoEditField[] = [
    "is_active",
    "applies_to",
    "max_activations",
    "valid_until",
  ];
  const EFFECT_EDIT_FIELDS: readonly PromoEditField[] = [
    "bonus_days",
    "regular_traffic_gb",
    "premium_traffic_gb",
    "bonus_requires_payment",
    "discount_percent",
    "duration_multiplier",
    "traffic_multiplier",
  ];
  const ELIGIBILITY_EDIT_FIELDS: readonly PromoEditField[] = [
    "min_subscription_days",
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
    paymentStatusVariant?: (status: string | null | undefined) => AdminBadgeVariant;
    onOpenUserCard?: (userId: number) => void;
  } = $props();

  const promosStore = getPromosStore();
  const promosTable = new TableHandler<Promo>();

  const promos = $derived(promosStore.promos as Promo[]);
  const promosTotal = $derived(Number(promosStore.promosTotal || 0));
  const promosPage = $derived(Number(promosStore.promosPage || 0));
  const promosSort = $derived(String(promosStore.promosSort || ""));
  const promosStatus = $derived(promosStore.promosStatus as PromoStatusFilter);
  const promosScope = $derived(promosStore.promosScope as PromoScopeFilter);
  const promosLoading = $derived(Boolean(promosStore.promosLoading));
  const promoKind = $derived(String(promosStore.promoKind || "shared"));
  // The split only means something once some code carries an owner, so an
  // install that never issues one keeps the plain single list.
  const promoKindTabsVisible = $derived(Number(promosStore.promoOwnedTotal || 0) > 0);
  const promoCreateOpen = $derived(Boolean(promosStore.promoCreateOpen));
  const promoEditOpen = $derived(Boolean(promosStore.promoEditOpen));
  const promoEditing = $derived(promosStore.promoEditing as Promo | null);
  const promoEditDraft = $derived((promosStore.promoEditDraft || {}) as PromoPatch);
  const activationsPromo = $derived(promosStore.promoActivationsPromo as Promo | null);
  const activations = $derived(promosStore.promoActivations as PromoActivation[]);
  const activationsLoading = $derived(Boolean(promosStore.promoActivationsLoading));
  const activationsTotal = $derived(Number(promosStore.promoActivationsTotal || 0));
  const activationsPage = $derived(Number(promosStore.promoActivationsPage || 0));
  const promoRevenueSummary = $derived(promosStore.promoRevenueSummary);
  const promoDraft = $derived(
    (promosStore.promoDraft || {
      code: "",
      bonus_days: 7,
      regular_traffic_gb: 0,
      premium_traffic_gb: 0,
      discount_percent: null,
      duration_multiplier: null,
      traffic_multiplier: null,
      bonus_requires_payment: false,
      applies_to: "all",
      min_subscription_days: null,
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
    regular_traffic_gb:
      editFieldDirty("regular_traffic_gb") || editFieldDirty("bonus_requires_payment"),
    premium_traffic_gb:
      editFieldDirty("premium_traffic_gb") || editFieldDirty("bonus_requires_payment"),
    discount_percent: editFieldDirty("discount_percent"),
    duration_multiplier: editFieldDirty("duration_multiplier"),
    traffic_multiplier: editFieldDirty("traffic_multiplier"),
  } satisfies Partial<Record<PromoEffectKind, boolean>>);
  let promoEditTab = $state<PromoEditTab>("settings");
  let previousEditPromoId = $state<number | null>(null);
  let promoSearchQuery = $state(promosStore.promosSearch);
  const promoCreateUsesCheckout = $derived(effectUsesCheckout(promoDraft));
  const promoEditUsesCheckout = $derived(effectUsesCheckout(promoEditDraft));

  $effect(() => promosTable.setRows(promos));
  $effect(() => {
    const editPromoId = promoEditing?.id ?? null;
    if (promoEditOpen && editPromoId !== previousEditPromoId) {
      previousEditPromoId = editPromoId;
    } else if (!promoEditOpen) {
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
  const promoSortColumns = [
    { asc: "code_asc", desc: "code_desc", defaultDirection: "asc" },
    { asc: "type_asc", desc: "type_desc", defaultDirection: "asc" },
    { asc: "effect_asc", desc: "effect_desc", defaultDirection: "desc" },
    { asc: "scope_asc", desc: "scope_desc", defaultDirection: "asc" },
    { asc: "eligibility_asc", desc: "eligibility_desc", defaultDirection: "asc" },
    { asc: "activations_asc", desc: "activations_desc", defaultDirection: "desc" },
    { asc: "status_asc", desc: "status_desc", defaultDirection: "desc" },
    { asc: "valid_until_asc", desc: "valid_until_desc", defaultDirection: "asc" },
  ] satisfies AdminSortColumn<never>[];
  const promoKindTabs = $derived([
    { value: "shared", label: at("promo_kind_shared", {}, "Shared") },
    { value: "personal", label: at("promo_kind_personal", {}, "Personal") },
    { value: "all", label: at("promo_kind_all", {}, "All") },
  ]);
  const scopeItems = $derived([
    { value: "all", label: at("promo_scope_all", {}, "All") },
    { value: "subscription", label: at("promo_scope_subscription", {}, "Subscription") },
    { value: "traffic", label: at("promo_scope_traffic", {}, "Traffic package") },
    { value: "traffic_topup", label: at("promo_scope_traffic_topup", {}, "Traffic top-up") },
    { value: "hwid", label: at("promo_scope_hwid", {}, "HWID") },
  ]);
  const promoStatusItems = $derived([
    { value: "", label: at("filter_all", {}, "All") },
    { value: "active", label: at("badge_active", {}, "Active") },
    { value: "disabled", label: at("status_disabled", {}, "Disabled") },
    { value: "expired", label: at("status_expired", {}, "Expired") },
    { value: "used_up", label: at("promo_status_used_up", {}, "Used up") },
  ]);
  const promoScopeItems = $derived([
    { value: "", label: at("filter_all", {}, "All") },
    ...scopeItems,
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

  function positiveNumber(
    value: number | string | null | undefined,
    fallback: number,
    minimum = 0
  ): number {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed > minimum ? parsed : fallback;
  }

  function hasFixedGrant(promo: PromoEffectSource): boolean {
    return (
      Number(promo.bonus_days || 0) > 0 ||
      Number(promo.regular_traffic_gb || 0) > 0 ||
      Number(promo.premium_traffic_gb || 0) > 0
    );
  }

  function effectUsesCheckout(promo: PromoEffectSource): boolean {
    return (
      Boolean(promo.bonus_requires_payment) ||
      Number(promo.discount_percent || 0) > 0 ||
      Number(promo.duration_multiplier || 1) > 1 ||
      Number(promo.traffic_multiplier || 1) > 1
    );
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

  function toggledEffectPatch(
    kind: PromoEffectKind,
    checked: boolean,
    source: PromoEffectSource
  ): Partial<PromoDraft> {
    const values: Record<PromoEffectKind, number | null> = {
      bonus_days: checked ? Math.max(1, Math.trunc(positiveNumber(source.bonus_days, 7))) : 0,
      regular_traffic_gb: checked ? positiveNumber(source.regular_traffic_gb, 50) : 0,
      premium_traffic_gb: checked ? positiveNumber(source.premium_traffic_gb, 20) : 0,
      discount_percent: checked ? positiveNumber(source.discount_percent, 10) : null,
      duration_multiplier: checked ? positiveNumber(source.duration_multiplier, 2, 1) : null,
      traffic_multiplier: checked ? positiveNumber(source.traffic_multiplier, 2, 1) : null,
    };
    return { [kind]: values[kind] } as Partial<PromoDraft>;
  }

  function toggleCreateEffect(kind: PromoEffectKind, checked: boolean): void {
    const patch = toggledEffectPatch(kind, checked, promoDraft);
    const next = { ...promoDraft, ...patch };
    if (hasFixedGrant(next) && effectUsesCheckout(next)) patch.applies_to = "subscription";
    if (hasFixedGrant(next)) patch.min_traffic_gb = null;
    if (!effectUsesCheckout(next)) {
      patch.min_subscription_days = null;
      patch.min_traffic_gb = null;
    }
    promosStore.updateDraft(patch);
  }

  function toggleEditEffect(kind: PromoEffectKind, checked: boolean): void {
    const patch = toggledEffectPatch(kind, checked, promoEditDraft);
    const next = { ...promoEditDraft, ...patch };
    if (hasFixedGrant(next) && effectUsesCheckout(next)) patch.applies_to = "subscription";
    if (hasFixedGrant(next)) patch.min_traffic_gb = null;
    if (!effectUsesCheckout(next)) {
      patch.min_subscription_days = null;
      patch.min_traffic_gb = null;
    }
    promosStore.updateEditDraft(patch as Partial<PromoPatch>);
  }

  function setCreateBonusRequiresPayment(checked: boolean): void {
    const fixedPatch = hasFixedGrant(promoDraft) ? {} : { bonus_days: 7 };
    promosStore.updateDraft({
      ...fixedPatch,
      bonus_requires_payment: checked,
      applies_to: checked ? "subscription" : promoDraft.applies_to,
      min_subscription_days: checked ? promoDraft.min_subscription_days : null,
      min_traffic_gb: checked ? promoDraft.min_traffic_gb : null,
    });
  }

  function setEditBonusRequiresPayment(checked: boolean): void {
    const fixedPatch = hasFixedGrant(promoEditDraft) ? {} : { bonus_days: 7 };
    promosStore.updateEditDraft({
      ...fixedPatch,
      bonus_requires_payment: checked,
      applies_to: checked ? "subscription" : promoEditDraft.applies_to,
      min_subscription_days: checked ? promoEditDraft.min_subscription_days : null,
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
    return formatAdminPromoEligibility(promo, at);
  }

  /** Who a personal code was issued for, in whatever form the profile has. */
  function promoOwnerLabel(promo: Promo): string {
    if (promo.user_username) return `@${promo.user_username}`;
    if (promo.user_name) return promo.user_name;
    return at("promo_owner_id", { id: promo.user_id }, "ID {id}");
  }

  function promoType(promo: Promo | PromoPatch): string {
    const hasBonus = Number(promo.bonus_days || 0) > 0;
    const hasRegularTraffic = Number(promo.regular_traffic_gb || 0) > 0;
    const hasPremiumTraffic = Number(promo.premium_traffic_gb || 0) > 0;
    const hasDiscount = Number(promo.discount_percent || 0) > 0;
    const hasDuration = Number(promo.duration_multiplier || 1) > 1;
    const hasTraffic = Number(promo.traffic_multiplier || 1) > 1;
    const count = [
      hasBonus,
      hasRegularTraffic,
      hasPremiumTraffic,
      hasDiscount,
      hasDuration,
      hasTraffic,
    ].filter(Boolean).length;
    if (count > 1) return at("promo_type_mixed", {}, "Mixed");
    if (hasDiscount) return at("promo_type_discount", {}, "Discount");
    if (hasDuration || hasTraffic) return at("promo_type_multiplier", {}, "Multiplier");
    return at("promo_type_bonus", {}, "Bonus");
  }

  function effectText(promo: PromoEffectSource): string {
    return formatAdminPromoEffect(promo, at, { includeGrantMode: true });
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
    } else if (field === "regular_traffic_gb") {
      promosStore.updateDraft({ regular_traffic_gb: Number(parsed || 0) });
    } else if (field === "premium_traffic_gb") {
      promosStore.updateDraft({ premium_traffic_gb: Number(parsed || 0) });
    } else if (field === "discount_percent") {
      promosStore.updateDraft({ discount_percent: parsed });
    } else if (field === "duration_multiplier") {
      promosStore.updateDraft({ duration_multiplier: parsed });
    } else if (field === "traffic_multiplier") {
      promosStore.updateDraft({ traffic_multiplier: parsed });
    } else if (field === "min_subscription_days") {
      promosStore.updateDraft({ min_subscription_days: parsed });
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

  function openPromoLink(link: string | null | undefined): void {
    const target = String(link || "").trim();
    if (!target || typeof window === "undefined") return;
    window.open(target, "_blank", "noopener,noreferrer");
  }
</script>

{#if promoKindTabsVisible}
  <Tabs.Root
    value={promoKind}
    onValueChange={(value) => promosStore.setPromoKind(value as PromoKind)}
    class="admin-tabs-root admin-promo-kind-tabs"
  >
    <Tabs.List class="admin-tabs-list">
      {#each promoKindTabs as tab (tab.value)}
        <Tabs.Trigger value={tab.value} class="admin-tabs-trigger">{tab.label}</Tabs.Trigger>
      {/each}
    </Tabs.List>
  </Tabs.Root>
{/if}

<AdminListToolbar
  total={promosTotal}
  totalLabel={at("total", {}, "Total")}
  columns={2}
  onsubmit={() => promosStore.setSearch(promoSearchQuery)}
  class="admin-promos-toolbar"
>
  {#snippet search()}
    <Input
      type="search"
      class="input"
      bind:value={promoSearchQuery}
      aria-label={at("promos_search_placeholder", {}, "Search by code")}
      placeholder={at("promos_search_placeholder", {}, "Search by code")}
    />
  {/snippet}
  {#snippet searchActions()}
    <AdminButton type="submit" variant="primary" disabled={promosLoading}>
      {at("find", {}, "Find")}
    </AdminButton>
  {/snippet}
  {#snippet filters()}
    <div class="admin-toolbar-field">
      <span class="admin-toolbar-field-label">{at("status", {}, "Status")}</span>
      <AdminSelect
        value={promosStatus}
        items={promoStatusItems}
        class="admin-toolbar-select"
        ariaLabel={at("status", {}, "Status")}
        onValueChange={(value) => promosStore.setStatus(value as PromoStatusFilter)}
      />
    </div>
    <div class="admin-toolbar-field">
      <span class="admin-toolbar-field-label">{at("promo_label_scope", {}, "Scope")}</span>
      <AdminSelect
        value={promosScope}
        items={promoScopeItems}
        class="admin-toolbar-select"
        ariaLabel={at("promo_label_scope", {}, "Scope")}
        onValueChange={(value) => promosStore.setScope(value as PromoScopeFilter)}
      />
    </div>
  {/snippet}
  {#snippet actions()}
    <AdminButton
      variant="ghost"
      disabled={promosLoading}
      onclick={() => promosStore.loadPromos({ refresh: true })}
    >
      <RefreshCw size={15} />{at("refresh", {}, "Refresh")}
    </AdminButton>
  {/snippet}
</AdminListToolbar>

<div class="admin-table-wrap admin-promos-table-wrap">
  {#if promosLoading}
    <AdminTableSkeleton
      headers={promoHeaders}
      rows={6}
      rowHeight={70}
      actionColumn
      class="admin-promos-table"
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
          <AdminSortableHeader
            label={at("promo_csv_code", {}, "Code")}
            column={promoSortColumns[0]}
            currentSort={promosSort}
            {at}
            onSort={promosStore.setSort}
          />
          <AdminSortableHeader
            label={at("promo_col_type", {}, "Type")}
            column={promoSortColumns[1]}
            currentSort={promosSort}
            {at}
            onSort={promosStore.setSort}
          />
          <AdminSortableHeader
            label={at("promo_col_effect", {}, "Effect")}
            column={promoSortColumns[2]}
            currentSort={promosSort}
            {at}
            onSort={promosStore.setSort}
          />
          <AdminSortableHeader
            label={at("promo_col_scope", {}, "Scope")}
            column={promoSortColumns[3]}
            currentSort={promosSort}
            {at}
            onSort={promosStore.setSort}
          />
          <AdminSortableHeader
            label={at("promo_col_eligibility", {}, "Eligibility")}
            column={promoSortColumns[4]}
            currentSort={promosSort}
            {at}
            onSort={promosStore.setSort}
          />
          <AdminSortableHeader
            label={at("promo_col_activations", {}, "Uses")}
            column={promoSortColumns[5]}
            currentSort={promosSort}
            {at}
            onSort={promosStore.setSort}
          />
          <AdminSortableHeader
            label={at("promo_col_status", {}, "Status")}
            column={promoSortColumns[6]}
            currentSort={promosSort}
            {at}
            onSort={promosStore.setSort}
          />
          <AdminSortableHeader
            label={at("promo_col_valid_until", {}, "Valid until")}
            column={promoSortColumns[7]}
            currentSort={promosSort}
            {at}
            onSort={promosStore.setSort}
          />
          <th class="admin-cell-actions">{at("actions", {}, "Actions")}</th>
        </tr>
      </thead>
      <VirtualTableRows rows={promoRows} colspan={9} rowHeight={70} getKey={(p) => p.id}>
        {#snippet children(p)}
          {@const status = promoStatus(p)}
          <tr data-admin-code-id={p.id}>
            <td class="admin-cell-primary" data-label={at("promo_csv_code", {}, "Code")}>
              <AdminEntityLink
                kind="code"
                label={p.code}
                idText={`#${p.id}`}
                title={at("promo_info_open", {}, "Open code details")}
                onclick={() => openPromoSettings(p)}
              />
              {#if p.user_id}
                <button
                  type="button"
                  class="admin-promo-owner"
                  title={at("promo_owner_hint", {}, "Issued for this customer")}
                  onclick={() => onOpenUserCard?.(Number(p.user_id))}
                >
                  <User size={12} />
                  {promoOwnerLabel(p)}
                </button>
              {/if}
            </td>
            <td data-label={at("promo_col_type", {}, "Type")}>
              <div class="admin-promo-type">
                <AdminBadge variant="muted">{promoType(p)}</AdminBadge>
                {#if p.user_id}
                  <AdminBadge
                    variant="warning"
                    title={at(
                      "promo_reach_personal_hint",
                      {},
                      "Issued for one customer — do not send it to an audience."
                    )}
                  >
                    {at("promo_reach_personal", {}, "Personal")}
                  </AdminBadge>
                {/if}
              </div>
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
                data-admin-action="open-code-activations"
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
                  data-admin-action="open-code-settings"
                  size="icon"
                  variant="ghost"
                  title={at("btn_edit", {}, "Edit")}
                  aria-label={at("btn_edit", {}, "Edit")}
                  onclick={() => openPromoSettings(p)}
                >
                  <Sliders size={14} />
                </AdminButton>
                <AdminButton
                  data-admin-action="open-code-activations"
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
                  data-admin-action="toggle-code"
                  size="sm"
                  onclick={() => promosStore.togglePromo(p)}
                >
                  {p.is_active ? at("btn_disable", {}, "Off") : at("btn_enable", {}, "On")}
                </AdminButton>
                <AdminButton
                  data-admin-action="delete-code"
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
        {/snippet}
      </VirtualTableRows>
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

<PromoCreateDialog
  {at}
  open={promoCreateOpen}
  draft={promoDraft}
  usesCheckout={promoCreateUsesCheckout}
  {scopeItems}
  onClose={() => promosStore.setCreateOpen(false)}
  onCreate={promosStore.createPromo}
  onCodeInput={(code) => promosStore.updateDraft({ code })}
  onScopeChange={(applies_to) => promosStore.updateDraft({ applies_to })}
  onEffectEnabledChange={toggleCreateEffect}
  onNumberInput={updateCreateNumber}
  onBonusRequiresPaymentChange={setCreateBonusRequiresPayment}
/>
<PromoEditDialog
  {at}
  {activationsLoading}
  {activationsPage}
  {activationsPageCount}
  {activationsTotal}
  {promoRevenueSummary}
  {closePromoEditor}
  {editActivationRows}
  {editFieldDirty}
  {fmtDate}
  {fmtMoney}
  {inputValue}
  {onOpenUserCard}
  {openPromoLink}
  {paymentStatusVariant}
  {promoBasicsDirtyCount}
  {promoEditDraft}
  {promoEditOpen}
  {promoEditTab}
  {promoEditUsesCheckout}
  {promoEditing}
  {promoEffectDirtyCount}
  {promoEffectDirtyFields}
  {promoEligibilityDirtyCount}
  {promoSettingsDirtyCount}
  {promoStatus}
  {promosStore}
  {scopeItems}
  onEffectEnabledChange={toggleEditEffect}
  {selectPromoEditTab}
  {setEditBonusRequiresPayment}
  {updateEditNumber}
  {updateEditValidUntil}
  {validUntilInputValue}
/>
