<script lang="ts">
  import { onMount } from "svelte";
  import {
    ArrowRight,
    CheckCircle2,
    Coins,
    CreditCard,
    FileText,
    History,
    Plus,
    RefreshCw,
    Settings,
    TrendingUp,
    TriangleAlert,
    UserPlus,
    UsersRound,
    WalletCards,
  } from "$components/ui/icons.js";
  import { Tabs } from "$components/ui/primitives.js";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { partnerSortColumns } from "$lib/admin/partnerProgramSort.js";
  import {
    createPartnerAdminPreviewState,
    emptyApplication,
    emptyPartner,
    emptyWithdrawal,
    initialPartnerAdminScenario as initialScenario,
    partnerAdminRouteState,
    type PartnerAdminView as View,
    type PartnerDialogKind as DialogKind,
  } from "$lib/admin/partnerAdminState.js";
  import {
    formatPartnerMoney,
    partnerActionIdempotencyKey,
    partnerStatusLabel,
    partnerStatusVariant,
    partnerTopListQuery,
    partnerWithdrawalTransitionMessage,
    type PartnerWithdrawalTransition,
  } from "$lib/admin/partnerProgramUi.js";
  import { sortAdminRows } from "$lib/admin/tableSort.js";
  import { withRoutePrefix } from "$lib/webapp/routes.js";
  import { getSettingsStore } from "$lib/admin/context.js";
  import {
    applications as previewApplications,
    partners as previewPartners,
    withdrawals as previewWithdrawals,
    type ApplicationRow,
    type PartnerAuditRow,
    type PartnerChartPoint,
    type PartnerClientRow,
    type PartnerCommissionRow,
    type PartnerLedgerRow,
    type PartnerRow,
    type WithdrawalRow,
  } from "$lib/admin/previewMock/partnerProgram.js";
  import type { AdminApi } from "../adminStores.js";
  import {
    DEFAULT_PARTNER_LIST_QUERY,
    loadPartnerDashboard,
    loadPartnerDetail,
    loadPartnerLists,
    loadPartnerPage,
    requirePartnerAdminResponse,
    type AdminPartnerListQuery,
    type AdminPartnerDashboard,
    type PartnerLinkRow,
  } from "$lib/admin/partnerProgramApi.js";
  import PartnerProgramCharts from "./partners/PartnerProgramCharts.svelte";
  import PartnerDashboardTables from "./partners/PartnerDashboardTables.svelte";
  import PartnerProgramSkeleton from "./partners/PartnerProgramSkeleton.svelte";
  import PartnerProgramTables from "./partners/PartnerProgramTables.svelte";
  import PartnerActionDialog from "./partners/PartnerActionDialog.svelte";
  import PartnerOperationDetails from "./partners/PartnerOperationDetails.svelte";
  import PartnerReferralImportBanner from "./partners/PartnerReferralImportBanner.svelte";
  import "./partnersSection.css";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type IconComponent = typeof UsersRound;

  let {
    api,
    at,
    currentLang = "en",
    routePrefix = "",
    onOpenSettingsPath = () => {},
    onOpenUserCard = () => {},
    onOpenPaymentCard = () => {},
  }: {
    api: AdminApi;
    at: TranslateFn;
    currentLang?: string;
    routePrefix?: string;
    onOpenSettingsPath?: (path?: unknown) => void;
    onOpenUserCard?: (userId: number) => void;
    onOpenPaymentCard?: (paymentId: number) => void;
  } = $props();

  const adminScenario = initialScenario();
  const previewMode = Boolean(adminScenario);
  const emptyChartsPreview = adminScenario === "empty_charts";
  const emptyListsPreview = adminScenario === "empty_lists";
  const settingsStore = getSettingsStore();
  const referralProgramEnabled = $derived.by(() => {
    const field = settingsStore.settingsSections
      .flatMap((section) => section.fields || [])
      .find((item) => item.key === "REFERRAL_PROGRAM_ENABLED");
    return field ? Boolean(field.value) : true;
  });
  let currency = $state("RUB");
  const previewState = createPartnerAdminPreviewState(
    previewMode,
    emptyChartsPreview,
    emptyListsPreview
  );
  let partners = $state<PartnerRow[]>(previewState.partners);
  let partnerTotal = $state(previewMode ? previewPartners.length : 0);
  let partnerQuery = $state<AdminPartnerListQuery>({ ...DEFAULT_PARTNER_LIST_QUERY });
  let topPartnerSort = $state("earned_desc");
  let topPartners = $state<PartnerRow[]>(previewState.topPartners);
  let partnerListRequestId = 0;
  let applications = $state<ApplicationRow[]>(previewState.applications);
  let withdrawals = $state<WithdrawalRow[]>(previewState.withdrawals);
  let partnerLinks = $state<PartnerLinkRow[]>(previewState.partnerLinks);
  let partnerClients = $state<PartnerClientRow[]>(previewState.partnerClients);
  let partnerCommissions = $state<PartnerCommissionRow[]>(previewState.partnerCommissions);
  let partnerLedger = $state<PartnerLedgerRow[]>(previewState.partnerLedger);
  let partnerAudit = $state<PartnerAuditRow[]>(previewState.partnerAudit);
  let partnerRevenueDaily = $state<PartnerChartPoint[]>(previewState.partnerRevenueDaily);
  let partnerPayoutsDaily = $state<PartnerChartPoint[]>(previewState.partnerPayoutsDaily);
  let dashboard = $state<AdminPartnerDashboard | null>(null);
  let loading = $state(!previewMode);
  let loadError = $state(false);

  const dashboardMetrics: Array<{
    key: string;
    value: string;
    icon: IconComponent;
    tone: string;
  }> = $derived([
    {
      key: "active",
      value:
        adminScenario === "empty"
          ? "0 / 0"
          : dashboard
            ? `${dashboard.active} / ${dashboard.paused}`
            : "18 / 2",
      icon: UsersRound,
      tone: "success",
    },
    {
      key: "clients",
      value: adminScenario === "empty" ? "0" : dashboard ? String(dashboard.clients) : "247",
      icon: UserPlus,
      tone: "info",
    },
    {
      key: "gross",
      value: money(adminScenario === "empty" ? 0 : (dashboard?.gross ?? 482700)),
      icon: TrendingUp,
      tone: "success",
    },
    {
      key: "commissions",
      value: money(adminScenario === "empty" ? 0 : (dashboard?.commissions ?? 144810)),
      icon: Coins,
      tone: "warning",
    },
    {
      key: "paid",
      value: money(adminScenario === "empty" ? 0 : (dashboard?.paid ?? 87300)),
      icon: WalletCards,
      tone: "muted",
    },
    {
      key: "available",
      value: money(adminScenario === "empty" ? 0 : (dashboard?.available ?? 42840)),
      icon: CreditCard,
      tone: "info",
    },
    {
      key: "requested",
      value: money(adminScenario === "empty" ? 0 : (dashboard?.requested ?? 11700)),
      icon: History,
      tone: "warning",
    },
    {
      key: "hold",
      value: money(adminScenario === "empty" ? 0 : (dashboard?.hold ?? 9340)),
      icon: FileText,
      tone: "muted",
    },
  ]);
  function initialRouteState(): { id: string; view: View } {
    return partnerAdminRouteState(routePrefix);
  }
  const initialRoute = initialRouteState();
  let view = $state<View>(initialRoute.view);
  let selectedPartner = $state<PartnerRow>(
    (previewMode
      ? previewPartners.find(
          (partner) => partner.id.toLowerCase() === initialRoute.id.toLowerCase()
        ) || previewPartners[0]
      : null) || emptyPartner
  );
  let selectedApplication = $state<ApplicationRow>(
    (previewMode
      ? previewApplications.find(
          (application) => application.id.toLowerCase() === initialRoute.id.toLowerCase()
        ) || previewApplications[0]
      : null) || emptyApplication
  );
  let selectedWithdrawal = $state<WithdrawalRow>(
    (previewMode
      ? previewWithdrawals.find(
          (withdrawal) => withdrawal.id.toLowerCase() === initialRoute.id.toLowerCase()
        ) || previewWithdrawals[0]
      : null) || emptyWithdrawal
  );
  // "Change status" said nothing about what it does. The label names the
  // transition the click performs, and flips with the partner's state.
  const partnerStatusActionLabel = $derived(
    selectedPartner.status === "paused"
      ? at("partners_action_resume", {}, "Resume partnership")
      : at("partners_action_pause", {}, "Pause partnership")
  );
  const pendingApplications = $derived(
    applications.filter((application) => application.status === "pending")
  );
  const pendingApplicationCount = $derived(pendingApplications.length);
  const openWithdrawalCount = $derived(
    withdrawals.filter(
      (withdrawal) => withdrawal.status === "requested" || withdrawal.status === "processing"
    ).length
  );
  let dialog = $state<DialogKind>("");
  let dialogReason = $state("");
  let dialogAmount = $state("");
  const balanceModes = ["add", "subtract", "set"] as const;
  let balanceMode = $state<(typeof balanceModes)[number]>("add");
  const balancePreviewValue = $derived.by(() => {
    const amount = Number(dialogAmount || 0);
    if (balanceMode === "set") return amount;
    if (balanceMode === "subtract") return selectedPartner.available - amount;
    return selectedPartner.available + amount;
  });
  let decisionOutcome = $state<"approved" | "rejected">("approved");
  let approvalRate = $state("30");
  let approvalWelcome = $state("");
  let rejectMessage = $state("");
  let actionStatus = $state("");
  let actionError = $state(false);
  let actionBusy = $state(false);
  let createUserId = $state("");
  let createRate = $state("30");
  let dialogRate = $state("30");
  let importOnCreate = $state(false);
  let importPreview = $state({ found: 0, new_clients: 0, existing: 0, conflicts: 0 });
  let revealedRequisites = $state("");
  let withdrawalExternalReference = $state("");
  let withdrawalSettlementAmount = $state("");
  let withdrawalSettlementError = $state("");
  let withdrawalRejectionReason = $state("");
  let withdrawalRejectionError = $state("");

  function syncRouteView(): void {
    actionStatus = "";
    actionError = false;
    const route = partnerAdminRouteState(routePrefix);
    const routeId = route.id.toLowerCase();
    if (route.view === "partner_detail") {
      selectedPartner =
        partners.find((partner) => partner.id.toLowerCase() === routeId) || selectedPartner;
    } else if (route.view === "application_detail") {
      selectedApplication =
        applications.find((application) => application.id.toLowerCase() === routeId) ||
        selectedApplication;
    } else if (route.view === "withdrawal_detail") {
      selectedWithdrawal =
        withdrawals.find((withdrawal) => withdrawal.id.toLowerCase() === routeId) ||
        selectedWithdrawal;
      withdrawalExternalReference = selectedWithdrawal.externalReference || "";
      withdrawalSettlementAmount = selectedWithdrawal.settlementAmount || "";
      withdrawalSettlementError = "";
    }
    view = route.view;
    if (!previewMode && route.view === "partner_detail" && route.id) {
      void loadSelectedPartnerDetail(route.id);
    }
  }

  function money(value: number): string {
    return formatPartnerMoney(value, currency);
  }

  type PartnerRequestOptions = {
    method?: string;
    headers?: Record<string, string>;
    body?: string;
  };

  async function request(
    path: string,
    options: PartnerRequestOptions = {}
  ): Promise<Record<string, unknown>> {
    const call = api as unknown as (
      path: string,
      options?: PartnerRequestOptions
    ) => Promise<Record<string, unknown>>;
    return requirePartnerAdminResponse(await call(path, options));
  }

  async function post(
    path: string,
    payload?: Record<string, unknown>
  ): Promise<Record<string, unknown>> {
    return request(path, {
      method: "POST",
      headers: payload ? { "Content-Type": "application/json" } : undefined,
      body: payload ? JSON.stringify(payload) : undefined,
    });
  }

  async function loadSelectedPartnerDetail(partnerId = selectedPartner.id): Promise<void> {
    if (previewMode || !partnerId) return;
    const path = `/admin/partners/${encodeURIComponent(partnerId)}?currency=${encodeURIComponent(currency)}`;
    const detail = await loadPartnerDetail(api, partnerId, currency, path);
    selectedPartner = detail.partner;
    partnerLinks = detail.links;
    partnerClients = detail.clients;
    partnerCommissions = detail.commissions;
    partnerLedger = detail.ledger;
    partnerAudit = detail.audit;
    const otherWithdrawals = withdrawals.filter((item) => item.partnerId !== partnerId);
    withdrawals = [...detail.withdrawals, ...otherWithdrawals];
  }

  async function refreshAll(): Promise<void> {
    if (previewMode) return;
    const partnerRequestId = ++partnerListRequestId;
    loading = true;
    loadError = false;
    try {
      const [nextDashboard, lists, topPartnerPage] = await Promise.all([
        loadPartnerDashboard(api, currency),
        loadPartnerLists(api, currency, partnerQuery),
        loadPartnerPage(api, currency, partnerTopListQuery(topPartnerSort)),
      ]);
      dashboard = nextDashboard;
      partnerRevenueDaily = nextDashboard.revenue;
      partnerPayoutsDaily = nextDashboard.payouts;
      topPartners = topPartnerPage.partners;
      if (partnerRequestId === partnerListRequestId) {
        partners = lists.partners;
        partnerTotal = lists.partnerTotal;
        selectedPartner =
          partners.find((item) => item.id === selectedPartner.id) || partners[0] || emptyPartner;
      }
      applications = lists.applications;
      withdrawals = lists.withdrawals;
      selectedApplication =
        applications.find((item) => item.id === selectedApplication.id) ||
        applications[0] ||
        emptyApplication;
      selectedWithdrawal =
        withdrawals.find((item) => item.id === selectedWithdrawal.id) ||
        withdrawals[0] ||
        emptyWithdrawal;
      if (view === "partner_detail" && selectedPartner.id) {
        await loadSelectedPartnerDetail(selectedPartner.id);
      }
    } catch {
      loadError = true;
    } finally {
      loading = false;
    }
  }

  async function updatePartnerQuery(next: AdminPartnerListQuery): Promise<void> {
    const query = { ...next };
    const requestId = ++partnerListRequestId;
    partnerQuery = query;
    if (previewMode) return;
    try {
      const page = await loadPartnerPage(api, currency, query);
      if (requestId !== partnerListRequestId) return;
      partners = page.partners;
      partnerTotal = page.total;
      selectedPartner =
        partners.find((item) => item.id === selectedPartner.id) || partners[0] || emptyPartner;
    } catch {
      loadError = true;
    }
  }

  async function updateTopPartnerSort(sort: string): Promise<void> {
    topPartnerSort = sort;
    if (previewMode) {
      topPartners = emptyListsPreview
        ? []
        : sortAdminRows(previewPartners, sort, partnerSortColumns).slice(0, 6);
      return;
    }
    try {
      const page = await loadPartnerPage(api, currency, partnerTopListQuery(topPartnerSort));
      if (sort !== topPartnerSort) return;
      topPartners = page.partners;
    } catch {
      loadError = true;
    }
  }

  async function changeCurrency(value: string): Promise<void> {
    currency = value;
    if (!previewMode) await refreshAll();
  }

  const statusLabel = (status: string): string => partnerStatusLabel(at, status);

  function navigate(next: View, id = ""): void {
    actionStatus = "";
    actionError = false;
    if (next !== "withdrawal_detail") revealedRequisites = "";
    view = next;
    if (typeof window === "undefined" || window.location.protocol === "file:") return;
    let suffix = "";
    if (next === "partner_detail")
      suffix = `/partner/${encodeURIComponent(id || selectedPartner.id)}`;
    else if (next === "application_detail")
      suffix = `/applications/${encodeURIComponent(id || selectedApplication.id)}`;
    else if (next === "withdrawal_detail")
      suffix = `/withdrawals/${encodeURIComponent(id || selectedWithdrawal.id)}`;
    else if (next === "partners" || next === "applications" || next === "withdrawals")
      suffix = `/${next}`;
    const target = withRoutePrefix(`/admin/partners${suffix}`, routePrefix);
    const query = new URLSearchParams(window.location.search);
    query.delete("partner_admin_view");
    const search = query.size ? `?${query.toString()}` : "";
    window.history.pushState(null, "", `${target}${search}${window.location.hash}`);
  }

  function openPartnerById(partnerId: string): void {
    const target = partners.find((partner) => partner.id === partnerId);
    if (target) openPartner(target);
  }

  function openPartner(partner: (typeof partners)[number]): void {
    selectedPartner = partner;
    navigate("partner_detail", partner.id);
    if (!previewMode) void loadSelectedPartnerDetail(partner.id);
  }

  function openApplication(application: (typeof applications)[number]): void {
    selectedApplication = application;
    navigate("application_detail", application.id);
  }

  function openWithdrawal(withdrawal: (typeof withdrawals)[number]): void {
    revealedRequisites = "";
    selectedWithdrawal = withdrawal;
    withdrawalExternalReference = withdrawal.externalReference || "";
    withdrawalSettlementAmount = withdrawal.settlementAmount || "";
    withdrawalSettlementError = "";
    withdrawalRejectionReason = "";
    withdrawalRejectionError = "";
    navigate("withdrawal_detail", withdrawal.id);
  }

  async function completeDialog(): Promise<void> {
    actionError = false;
    if (previewMode) {
      actionStatus = at("partners_action_saved", {}, "Changes saved in the prototype");
      dialog = "";
      dialogReason = "";
      dialogAmount = "";
      return;
    }
    if (actionBusy) return;
    actionBusy = true;
    try {
      if (dialog === "create") {
        const created = await post("/admin/partners", {
          user_id: Number(createUserId),
          commission_bps: Math.round(Number(createRate) * 100),
          welcome_message: null,
        });
        const createdProfile = created.partner as Record<string, unknown> | undefined;
        if (importOnCreate && createdProfile?.partner_id) {
          await post(`/admin/partners/${createdProfile.partner_id}/referral-import`, {
            confirm_without_retroactive_commission: true,
          });
        }
      } else if (dialog === "rate") {
        const commissionBps = Math.round(Number(dialogRate) * 100);
        const response = await post(`/admin/partners/${selectedPartner.id}/commission-rate`, {
          commission_bps: commissionBps,
          reason: dialogReason.trim(),
        });
        const savedProfile = (response.partner || {}) as Record<string, unknown>;
        if (Number(savedProfile.commission_bps) !== commissionBps) {
          throw new Error(
            at("partners_rate_save_mismatch", {}, "The server did not confirm the new rate")
          );
        }
        const savedRate = commissionBps / 100;
        selectedPartner = { ...selectedPartner, rate: savedRate };
        partners = partners.map((partner) =>
          partner.id === selectedPartner.id ? { ...partner, rate: savedRate } : partner
        );
      } else if (dialog === "balance") {
        const scale = selectedPartner.currencyScale ?? 2;
        await post(`/admin/partners/${selectedPartner.id}/balance-adjustments`, {
          currency,
          currency_scale: scale,
          mode: balanceMode,
          amount_minor: Math.round(Number(dialogAmount) * 10 ** scale),
          reason: dialogReason.trim() || null,
          idempotency_key: partnerActionIdempotencyKey("admin-balance"),
          allow_negative: false,
          internal_reference: null,
        });
      } else if (dialog === "import") {
        await post(`/admin/partners/${selectedPartner.id}/referral-import`, {
          confirm_without_retroactive_commission: true,
        });
      } else if (dialog === "status") {
        const transition = selectedPartner.status === "paused" ? "resume" : "pause";
        await post(`/admin/partners/${selectedPartner.id}/${transition}`, {
          reason: dialogReason.trim() || null,
        });
      } else if (dialog === "link") {
        await post(`/admin/partners/${selectedPartner.id}/link/rotate`);
      }
      dialog = "";
      dialogReason = "";
      dialogAmount = "";
      await refreshAll();
      actionStatus = at("partners_action_saved", {}, "Changes saved");
    } catch (error) {
      actionError = true;
      actionStatus =
        error instanceof Error ? error.message : at("partners_action_failed", {}, "Action failed");
    } finally {
      actionBusy = false;
    }
  }

  async function decideApplication(status: "approved" | "rejected"): Promise<void> {
    actionError = false;
    if (previewMode) {
      selectedApplication.status = status;
    } else {
      actionBusy = true;
      try {
        await post(
          `/admin/partner-applications/${selectedApplication.id}/${status === "approved" ? "approve" : "reject"}`,
          {
            decision_message: status === "rejected" ? rejectMessage.trim() || null : null,
            commission_bps: status === "approved" ? Math.round(Number(approvalRate) * 100) : null,
            welcome_message: status === "approved" ? approvalWelcome.trim() || null : null,
          }
        );
        await refreshAll();
      } catch (error) {
        actionError = true;
        actionStatus =
          error instanceof Error
            ? error.message
            : at("partners_action_failed", {}, "Action failed");
        return;
      } finally {
        actionBusy = false;
      }
    }
    actionStatus =
      status === "approved"
        ? at("partners_application_approved", {}, "Application approved")
        : at("partners_application_rejected", {}, "Application rejected");
  }

  async function transitionWithdrawal(status: PartnerWithdrawalTransition): Promise<void> {
    actionError = false;
    actionStatus = "";
    withdrawalSettlementError = "";
    withdrawalRejectionError = "";
    if (status === "reject" && !withdrawalRejectionReason.trim()) {
      withdrawalRejectionError = at("partners_reason_required", {}, "Reason (required)");
      actionStatus = withdrawalRejectionError;
      actionError = true;
      return;
    }
    if (
      status === "paid" &&
      selectedWithdrawal.method === "crypto" &&
      !withdrawalSettlementAmount.trim()
    ) {
      withdrawalSettlementError = at(
        "partners_settlement_amount_required",
        {},
        "Enter the actual crypto settlement amount before marking the withdrawal as paid."
      );
      actionStatus = withdrawalSettlementError;
      actionError = true;
      return;
    }
    if (previewMode) {
      selectedWithdrawal.status =
        status === "reject" ? "rejected" : status === "fail" ? "failed" : status;
      selectedWithdrawal.externalReference = withdrawalExternalReference.trim();
      selectedWithdrawal.settlementAmount = withdrawalSettlementAmount.trim();
      if (status === "reject") selectedWithdrawal.noteKey = withdrawalRejectionReason.trim();
      actionStatus = partnerWithdrawalTransitionMessage(at, status);
      return;
    }
    actionBusy = true;
    try {
      await post(`/admin/partner-withdrawals/${selectedWithdrawal.id}/${status}`, {
        status_version: selectedWithdrawal.statusVersion ?? 1,
        message:
          status === "reject" ? withdrawalRejectionReason.trim() : dialogReason.trim() || null,
        external_reference: withdrawalExternalReference.trim() || null,
        settlement_amount: withdrawalSettlementAmount.trim() || null,
      });
      await refreshAll();
      selectedWithdrawal =
        withdrawals.find((item) => item.id === selectedWithdrawal.id) || selectedWithdrawal;
      actionStatus = partnerWithdrawalTransitionMessage(at, status);
    } catch (error) {
      actionError = true;
      actionStatus =
        error instanceof Error && error.message === "withdrawal_rejection_reason_required"
          ? at("partners_reason_required", {}, "Reason (required)")
          : error instanceof Error
            ? error.message
            : at("partners_action_failed", {}, "Action failed");
    } finally {
      actionBusy = false;
    }
  }

  async function revealWithdrawalRequisites(): Promise<void> {
    actionError = false;
    if (previewMode) {
      revealedRequisites = selectedWithdrawal.masked;
      return;
    }
    try {
      const response = await post(`/admin/partner-withdrawals/${selectedWithdrawal.id}/reveal`);
      revealedRequisites = JSON.stringify(response.requisites || {}, null, 2);
    } catch (error) {
      actionError = true;
      actionStatus =
        error instanceof Error ? error.message : at("partners_action_failed", {}, "Action failed");
    }
  }

  async function loadImportPreview(): Promise<void> {
    if (previewMode || dialog !== "import" || !selectedPartner.id) return;
    try {
      const response = await request(`/admin/partners/${selectedPartner.id}/referral-import`);
      const value = (response.preview || {}) as Record<string, unknown>;
      importPreview = {
        found: Number(value.found || 0),
        new_clients: Number(value.importable || 0),
        existing: Number(value.already_this_partner || 0),
        conflicts: Number(value.other_partner || 0) + Number(value.self_conflict || 0),
      };
    } catch {
      importPreview = { found: 0, new_clients: 0, existing: 0, conflicts: 0 };
    }
  }

  $effect(() => {
    dialog;
    selectedPartner.id;
    if (dialog === "import") void loadImportPreview();
    if (dialog === "rate") dialogRate = String(selectedPartner.rate);
  });

  onMount(() => {
    if (!previewMode) void refreshAll();
    void settingsStore.loadSettings();
  });

  async function copyLink(url: string): Promise<void> {
    try {
      await navigator.clipboard?.writeText(url);
      actionStatus = at("partners_link_copied", {}, "Partner link copied");
    } catch {
      actionStatus = at("partners_link_copy_failed", {}, "Could not copy the partner link");
    }
  }
</script>

<svelte:window onpopstate={syncRouteView} />

<div class="partners-admin-page">
  <header class="partners-toolbar">
    <Tabs.Root
      class="admin-tabs-root partners-toolbar-tabs"
      value={view}
      onValueChange={(value) => navigate(value as View)}
    >
      <Tabs.List
        class="admin-tabs-list"
        aria-label={at("partners_navigation", {}, "Partner program navigation")}
      >
        {#each ["dashboard", "partners", "applications", "withdrawals"] as item}
          <Tabs.Trigger class="admin-tabs-trigger" value={item}>
            {at(`partners_tab_${item}`, {}, item)}
            {#if item === "applications" && pendingApplicationCount}
              <AdminBadge variant="danger">{pendingApplicationCount}</AdminBadge>
            {/if}
            {#if item === "withdrawals" && openWithdrawalCount}
              <AdminBadge variant="warning">{openWithdrawalCount}</AdminBadge>
            {/if}
          </Tabs.Trigger>
        {/each}
      </Tabs.List>
    </Tabs.Root>
    <div class="partners-toolbar-actions">
      <AdminSelect
        value={currency}
        items={["RUB", "USD", "EUR"].map((value) => ({ value, label: value }))}
        ariaLabel={at("partners_currency", {}, "Currency")}
        onValueChange={(value) => void changeCurrency(value)}
      />
      <AdminButton onclick={() => onOpenSettingsPath(["partner"])}>
        <Settings size={15} />{at("partners_configure", {}, "Configure program")}
      </AdminButton>
    </div>
  </header>

  {#if actionStatus}
    <div
      class="partners-success-banner"
      class:partners-error-banner={actionError}
      role={actionError ? "alert" : "status"}
    >
      {#if actionError}<TriangleAlert size={16} />{:else}<CheckCircle2 size={16} />{/if}
      {actionStatus}
    </div>
  {/if}

  {#if adminScenario === "loading" || loading}
    <PartnerProgramSkeleton {at} {view} />
  {:else if adminScenario === "error" || loadError}
    <AdminEmptyState class="partners-dashboard-state partners-dashboard-error">
      <TriangleAlert size={26} />
      <h2>{at("partners_load_error_title", {}, "Could not load partner dashboard")}</h2>
      <p>{at("partners_load_error_hint", {}, "Check the connection and try again.")}</p>
      <AdminButton onclick={() => void refreshAll()}>
        <RefreshCw size={15} />{at("partners_retry", {}, "Try again")}
      </AdminButton>
    </AdminEmptyState>
  {:else if view === "dashboard"}
    {#if !referralProgramEnabled}
      <PartnerReferralImportBanner {at} {api} {previewMode} onImported={refreshAll} />
    {/if}

    <section
      class="partners-kpi-grid"
      aria-label={at("partners_kpi_title", {}, "Partner program summary")}
    >
      {#each dashboardMetrics as metric}
        {@const MetricIcon = metric.icon}
        <article class="partners-kpi-card partners-tone-{metric.tone}">
          <span><MetricIcon size={18} /></span>
          <div>
            <small>{at(`partners_kpi_${metric.key}`, {}, metric.key)}</small><strong
              >{metric.value}</strong
            >
          </div>
        </article>
      {/each}
    </section>

    {#if adminScenario === "empty" || (!previewMode && !partners.length && !applications.length)}
      <AdminEmptyState class="partners-dashboard-state">
        <UsersRound size={27} />
        <h2>{at("partners_empty_title", {}, "No partner activity yet")}</h2>
        <p>
          {at(
            "partners_empty_hint",
            {},
            "Approve an application or add a partner to start collecting statistics."
          )}
        </p>
        <AdminButton variant="primary" onclick={() => (dialog = "create")}>
          <Plus size={15} />{at("partners_add", {}, "Add partner")}
        </AdminButton>
      </AdminEmptyState>
    {:else}
      <PartnerProgramCharts
        {at}
        {currentLang}
        {currency}
        {money}
        {partnerRevenueDaily}
        {partnerPayoutsDaily}
      />

      <section class="partners-preview-grid">
        <PartnerDashboardTables
          {at}
          partners={topPartners}
          {withdrawals}
          partnerSort={topPartnerSort}
          {money}
          {statusLabel}
          onPartnerSort={(sort) => void updateTopPartnerSort(sort)}
          onOpenPartner={openPartner}
          onOpenWithdrawal={openWithdrawal}
          onViewPartners={() => navigate("partners")}
          onViewWithdrawals={() => navigate("withdrawals")}
        />
        <article class="admin-card partners-preview-card partners-preview-wide">
          <header>
            <div>
              <FileText size={17} /><strong
                >{at("partners_pending_applications", {}, "Pending applications")}</strong
              >{#if pendingApplicationCount}<AdminBadge variant="danger"
                  >{pendingApplicationCount}</AdminBadge
                >{/if}
            </div>
            <button type="button" onclick={() => navigate("applications")}
              >{at("partners_view_all", {}, "View all")}<ArrowRight size={14} /></button
            >
          </header>
          {#each pendingApplications.slice(0, 3) as application (application.id)}<button
              type="button"
              class="partners-preview-row"
              onclick={() => openApplication(application)}
              ><span
                ><strong>{application.handle} — {application.user}</strong><small
                  >{application.submitted}</small
                ></span
              ><AdminBadge variant={partnerStatusVariant(application.status)}
                >{statusLabel(application.status)}</AdminBadge
              ></button
            >{/each}
        </article>
      </section>
    {/if}
  {:else if view === "partners" || view === "applications" || view === "withdrawals"}
    <PartnerProgramTables
      {at}
      {partners}
      {partnerTotal}
      {partnerQuery}
      {applications}
      {withdrawals}
      {view}
      {money}
      onAddPartner={() => (dialog = "create")}
      onOpenPartner={openPartner}
      onOpenApplication={openApplication}
      onOpenWithdrawal={openWithdrawal}
      onPartnerQueryChange={updatePartnerQuery}
      {onOpenUserCard}
    />
  {:else}
    <PartnerOperationDetails
      {at}
      {view}
      {selectedPartner}
      {selectedApplication}
      {selectedWithdrawal}
      {partnerLinks}
      {partnerClients}
      {partnerCommissions}
      {partnerLedger}
      {partnerAudit}
      {withdrawals}
      {money}
      {statusLabel}
      {partnerStatusActionLabel}
      {onOpenUserCard}
      {onOpenPaymentCard}
      onNavigate={navigate}
      onOpenWithdrawal={openWithdrawal}
      {openPartnerById}
      onCopyLink={copyLink}
      {decideApplication}
      {transitionWithdrawal}
      {revealWithdrawalRequisites}
      {revealedRequisites}
      bind:withdrawalExternalReference
      bind:withdrawalSettlementAmount
      bind:withdrawalSettlementError
      bind:withdrawalRejectionReason
      bind:withdrawalRejectionError
      bind:dialog
      bind:decisionOutcome
      bind:approvalRate
      bind:approvalWelcome
      bind:rejectMessage
    />
  {/if}
</div>

<PartnerActionDialog
  {at}
  {selectedPartner}
  {previewMode}
  {importPreview}
  {balanceModes}
  {balancePreviewValue}
  {money}
  {completeDialog}
  {actionBusy}
  bind:dialog
  bind:createUserId
  bind:createRate
  bind:importOnCreate
  bind:dialogRate
  bind:dialogReason
  bind:dialogAmount
  bind:balanceMode
/>
