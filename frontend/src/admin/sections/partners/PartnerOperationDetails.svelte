<script lang="ts">
  import {
    ArrowLeft,
    Coins,
    Copy,
    RefreshCw,
    Sliders,
    TriangleAlert,
    UserPlus,
    UserRound,
  } from "$components/ui/icons.js";
  import { Input, Textarea } from "$components/ui/index.js";
  import {
    AdminBadge,
    AdminButton,
    AdminCardActions,
    AdminEntityLink,
    AdminField,
  } from "$components/patterns/admin/index.js";
  import type { PartnerLinkRow } from "$lib/admin/partnerProgramApi.js";
  import { partnerStatusVariant } from "$lib/admin/partnerProgramUi.js";
  import type {
    ApplicationRow,
    PartnerAuditRow,
    PartnerClientRow,
    PartnerCommissionRow,
    PartnerLedgerRow,
    PartnerRow,
    WithdrawalRow,
  } from "$lib/admin/previewMock/partnerProgram.js";
  import PartnerDetailActivity from "./PartnerDetailActivity.svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type DetailView = "partner_detail" | "application_detail" | "withdrawal_detail";
  type DialogKind = "" | "create" | "rate" | "balance" | "import" | "status" | "link";

  let {
    at,
    view,
    selectedPartner,
    selectedApplication,
    selectedWithdrawal,
    partnerLinks,
    partnerClients,
    partnerCommissions,
    partnerLedger,
    partnerAudit,
    withdrawals,
    money,
    statusLabel,
    partnerStatusActionLabel,
    onOpenUserCard,
    onOpenPaymentCard,
    onNavigate,
    onOpenWithdrawal,
    openPartnerById,
    onCopyLink,
    decideApplication,
    transitionWithdrawal,
    revealWithdrawalRequisites,
    revealedRequisites,
    withdrawalExternalReference = $bindable(),
    withdrawalSettlementAmount = $bindable(),
    withdrawalSettlementError = $bindable(),
    withdrawalRejectionReason = $bindable(),
    withdrawalRejectionError = $bindable(),
    dialog = $bindable(),
    decisionOutcome = $bindable(),
    approvalRate = $bindable(),
    approvalWelcome = $bindable(),
    rejectMessage = $bindable(),
  }: {
    at: TranslateFn;
    view: DetailView;
    selectedPartner: PartnerRow;
    selectedApplication: ApplicationRow;
    selectedWithdrawal: WithdrawalRow;
    partnerLinks: PartnerLinkRow[];
    partnerClients: PartnerClientRow[];
    partnerCommissions: PartnerCommissionRow[];
    partnerLedger: PartnerLedgerRow[];
    partnerAudit: PartnerAuditRow[];
    withdrawals: WithdrawalRow[];
    money: (value: number) => string;
    statusLabel: (status: string) => string;
    partnerStatusActionLabel: string;
    onOpenUserCard: (userId: number) => void;
    onOpenPaymentCard: (paymentId: number) => void;
    onNavigate: (view: "partners" | "applications" | "withdrawals") => void;
    onOpenWithdrawal: (withdrawal: WithdrawalRow) => void;
    openPartnerById: (partnerId: string) => void;
    onCopyLink: (url: string) => Promise<void>;
    decideApplication: (status: "approved" | "rejected") => Promise<void>;
    transitionWithdrawal: (status: "processing" | "paid" | "reject" | "fail") => Promise<void>;
    revealWithdrawalRequisites: () => Promise<void>;
    revealedRequisites: string;
    withdrawalExternalReference: string;
    withdrawalSettlementAmount: string;
    withdrawalSettlementError: string;
    withdrawalRejectionReason: string;
    withdrawalRejectionError: string;
    dialog: DialogKind;
    decisionOutcome: "approved" | "rejected";
    approvalRate: string;
    approvalWelcome: string;
    rejectMessage: string;
  } = $props();

  const partnerActions = [
    { key: "rate" as const, icon: Sliders },
    { key: "balance" as const, icon: Coins },
    { key: "import" as const, icon: UserPlus },
    { key: "status" as const, icon: TriangleAlert },
  ];
</script>

{#if view === "partner_detail"}
  <section class="partners-detail-view">
    <button class="partners-back" type="button" onclick={() => onNavigate("partners")}>
      <ArrowLeft size={16} />{at("partners_back_to_list", {}, "Back to partners")}
    </button>
    <header class="admin-card partners-detail-head">
      <AdminEntityLink
        kind="partner"
        label={selectedPartner.name}
        secondary={selectedPartner.handle}
        idText={selectedPartner.id}
        title={at("partners_open_user_card", {}, "Open user card")}
        onclick={() => onOpenUserCard(selectedPartner.userId)}
      />
      <div class="partners-detail-head-meta">
        <AdminBadge variant={partnerStatusVariant(selectedPartner.status)}>
          {statusLabel(selectedPartner.status)}
        </AdminBadge>
        <AdminButton size="sm" onclick={() => onOpenUserCard(selectedPartner.userId)}>
          <UserRound size={14} />{at("partners_open_user_card", {}, "Open user card")}
        </AdminButton>
      </div>
    </header>
    <section class="partners-kpi-grid partners-kpi-detail">
      {#each [["rate", `${selectedPartner.rate}%`], ["clients", String(selectedPartner.clients)], ["payments", String(selectedPartner.payments)], ["gross", money(selectedPartner.gross)], ["earned", money(selectedPartner.earned)], ["available", money(selectedPartner.available)]] as metric (metric[0])}
        <article class="partners-kpi-card">
          <div>
            <small>{at(`partners_kpi_${metric[0]}`, {}, metric[0])}</small>
            <strong>{metric[1]}</strong>
          </div>
        </article>
      {/each}
    </section>
    <article class="admin-card partners-links-card">
      <header>
        <strong>{at("partners_personal_links", {}, "Partner links")}</strong>
        <AdminButton size="sm" onclick={() => (dialog = "link")}>
          <RefreshCw size={14} />{at("partners_rotate_link", {}, "Rotate")}
        </AdminButton>
      </header>
      <div>
        {#each partnerLinks as link (link.id)}
          <span>
            <AdminBadge variant="muted">{link.labelKey}</AdminBadge>
            <code>{link.url}</code>
            <AdminButton
              size="sm"
              variant="ghost"
              onclick={() => onCopyLink(link.url)}
              aria-label={at("partners_copy_link", {}, "Copy partner link")}
              title={at("partners_copy_link", {}, "Copy partner link")}
            >
              <Copy size={15} />
            </AdminButton>
          </span>
        {/each}
      </div>
    </article>
    <div class="partners-detail-actions">
      {#each partnerActions as action (action.key)}
        {@const ActionIcon = action.icon}
        <AdminButton
          variant={action.key === "status" && selectedPartner.status === "active"
            ? "dangerSoft"
            : "default"}
          onclick={() => (dialog = action.key)}
        >
          <ActionIcon size={15} />{action.key === "status"
            ? partnerStatusActionLabel
            : at(`partners_action_${action.key}`, {}, action.key)}
        </AdminButton>
      {/each}
    </div>
    <PartnerDetailActivity
      {at}
      {money}
      partnerId={selectedPartner.id}
      {partnerClients}
      {partnerCommissions}
      {partnerLedger}
      {partnerAudit}
      {withdrawals}
      {onOpenUserCard}
      {onOpenPaymentCard}
      {onOpenWithdrawal}
    />
  </section>
{:else if view === "application_detail"}
  <section class="partners-detail-view">
    <button class="partners-back" type="button" onclick={() => onNavigate("applications")}>
      <ArrowLeft size={16} />{at("partners_back_to_applications", {}, "Back to applications")}
    </button>
    <article class="admin-card partners-record-card">
      <header>
        <AdminEntityLink
          kind="application"
          label={at("partners_application_detail_title", {}, "Application details")}
          idText={selectedApplication.id}
        />
        <AdminBadge variant={partnerStatusVariant(selectedApplication.status)}>
          {statusLabel(selectedApplication.status)}
        </AdminBadge>
      </header>
      <dl>
        <div>
          <dt>{at("partners_applicant", {}, "Applicant")}</dt>
          <dd>
            <AdminEntityLink
              kind="user"
              label={selectedApplication.user}
              secondary={selectedApplication.handle}
              title={at("partners_open_user_card", {}, "Open user card")}
              onclick={() => onOpenUserCard(selectedApplication.userId)}
            />
          </dd>
        </div>
        <div>
          <dt>{at("partners_submitted", {}, "Submitted")}</dt>
          <dd class="admin-cell-mono">{selectedApplication.submitted}</dd>
        </div>
        <div>
          <dt>{at("partners_application_message", {}, "Application message")}</dt>
          <dd>{at(selectedApplication.messageKey, {}, selectedApplication.messageKey)}</dd>
        </div>
      </dl>
    </article>
    {#if selectedApplication.status === "pending"}
      <article class="admin-card partners-decision-card">
        <header>
          <div>
            <strong>{at("partners_decision_title", {}, "Decision")}</strong>
            <small>
              {at(
                "partners_decision_hint",
                {},
                "The applicant is notified either way. Approving creates the partner profile immediately."
              )}
            </small>
          </div>
          <div class="partners-decision-switch" role="group">
            {#each ["approved", "rejected"] as outcome (outcome)}
              <button
                type="button"
                class:active={decisionOutcome === outcome}
                aria-pressed={decisionOutcome === outcome}
                onclick={() => (decisionOutcome = outcome as "approved" | "rejected")}
              >
                {at(`partners_decision_${outcome}`, {}, outcome)}
              </button>
            {/each}
          </div>
        </header>
        <div class="partners-form">
          {#if decisionOutcome === "approved"}
            <AdminField
              label={at("partners_rate_label", {}, "Commission rate, %")}
              hint={at(
                "partners_rate_future_note",
                {},
                "The new rate applies only to future successful payments."
              )}
            >
              <Input
                class="input"
                type="number"
                min="0"
                max="100"
                step="0.01"
                bind:value={approvalRate}
              />
            </AdminField>
            <AdminField label={at("partners_welcome_label", {}, "Welcome message (optional)")}>
              <Textarea bind:value={approvalWelcome} rows={4} />
            </AdminField>
          {:else}
            <AdminField
              label={at("partners_decision_message_label", {}, "Message to the user (optional)")}
            >
              <Textarea bind:value={rejectMessage} rows={4} />
            </AdminField>
          {/if}
        </div>
        <AdminCardActions>
          <AdminButton onclick={() => onNavigate("applications")}>
            {at("cancel", {}, "Cancel")}
          </AdminButton>
          <AdminButton
            variant={decisionOutcome === "approved" ? "primary" : "danger"}
            onclick={() => decideApplication(decisionOutcome)}
          >
            {decisionOutcome === "approved"
              ? at("partners_approve", {}, "Approve")
              : at("partners_reject", {}, "Reject")}
          </AdminButton>
        </AdminCardActions>
      </article>
    {/if}
  </section>
{:else}
  <section class="partners-detail-view">
    <button class="partners-back" type="button" onclick={() => onNavigate("withdrawals")}>
      <ArrowLeft size={16} />{at("partners_back_to_withdrawals", {}, "Back to withdrawals")}
    </button>
    <article class="admin-card partners-record-card">
      <header>
        <AdminEntityLink
          kind="withdrawal"
          label={at("partners_withdrawal_detail_title", {}, "Withdrawal details")}
          idText={selectedWithdrawal.id}
        />
        <AdminBadge variant={partnerStatusVariant(selectedWithdrawal.status)}>
          {statusLabel(selectedWithdrawal.status)}
        </AdminBadge>
      </header>
      <dl>
        <div>
          <dt>{at("partners_col_partner", {}, "Partner")}</dt>
          <dd>
            <AdminEntityLink
              kind="partner"
              label={selectedWithdrawal.partner}
              secondary={selectedWithdrawal.handle}
              idText={selectedWithdrawal.partnerId}
              title={at("partners_open_partner_card", {}, "Open partner card")}
              onclick={() => openPartnerById(selectedWithdrawal.partnerId)}
            />
          </dd>
        </div>
        <div>
          <dt>{at("partners_col_amount", {}, "Amount")}</dt>
          <dd>
            <strong class="partners-record-amount">{money(selectedWithdrawal.amount)}</strong>
          </dd>
        </div>
        <div>
          <dt>{at("partners_col_method", {}, "Method")}</dt>
          <dd>
            {at(`partners_method_${selectedWithdrawal.method}`, {}, selectedWithdrawal.method)}
          </dd>
        </div>
        <div>
          <dt>{at("partners_requisites", {}, "Requisites")}</dt>
          <dd class="partners-record-requisites">
            <code>{selectedWithdrawal.masked}</code>
            <AdminButton size="sm" variant="ghost" onclick={revealWithdrawalRequisites}>
              {at("partners_reveal_requisites", {}, "Reveal and audit")}
            </AdminButton>
            {#if revealedRequisites}<pre>{revealedRequisites}</pre>{/if}
          </dd>
        </div>
        <div>
          <dt>{at("partners_requested", {}, "Requested")}</dt>
          <dd class="admin-cell-mono">{selectedWithdrawal.requested}</dd>
        </div>
        {#if selectedWithdrawal.processedAt}
          <div>
            <dt>{at("partners_processed_at", {}, "Processed")}</dt>
            <dd class="admin-cell-mono">{selectedWithdrawal.processedAt}</dd>
          </div>
        {/if}
        {#if selectedWithdrawal.noteKey}
          <div>
            <dt>{at("partners_withdrawal_note", {}, "Comment")}</dt>
            <dd>{at(selectedWithdrawal.noteKey, {}, selectedWithdrawal.noteKey)}</dd>
          </div>
        {/if}
      </dl>
      {#if selectedWithdrawal.status === "processing"}
        <div class="partners-withdrawal-settlement">
          <AdminField
            label={at(
              "partners_external_reference",
              {},
              "Transaction reference or link (optional)"
            )}
            hint={at(
              "partners_external_reference_hint",
              {},
              "Bank operation ID, blockchain transaction hash, or explorer link."
            )}
          >
            <Input class="input" autocomplete="off" bind:value={withdrawalExternalReference} />
          </AdminField>
          {#if selectedWithdrawal.method === "crypto"}
            <div
              class="partners-settlement-field"
              class:has-error={Boolean(withdrawalSettlementError)}
            >
              <AdminField
                label={at("partners_settlement_amount", {}, "Crypto settlement amount")}
                hint={withdrawalSettlementError ||
                  at(
                    "partners_settlement_amount_hint",
                    {},
                    "Required to mark a crypto withdrawal as paid. Include the asset symbol if needed."
                  )}
              >
                <Input
                  class={withdrawalSettlementError ? "input partners-input-error" : "input"}
                  aria-invalid={Boolean(withdrawalSettlementError)}
                  bind:value={withdrawalSettlementAmount}
                  oninput={() => (withdrawalSettlementError = "")}
                />
              </AdminField>
            </div>
          {/if}
        </div>
      {/if}
      {#if selectedWithdrawal.status === "requested" || selectedWithdrawal.status === "processing"}
        <div class="partners-withdrawal-settlement">
          <div
            class="partners-settlement-field"
            class:has-error={Boolean(withdrawalRejectionError)}
          >
            <AdminField
              label={at(
                "partners_withdrawal_rejection_reason",
                {},
                "Reason for rejection (required to reject)"
              )}
              hint={withdrawalRejectionError}
            >
              <Textarea
                class={withdrawalRejectionError ? "partners-input-error" : ""}
                aria-invalid={Boolean(withdrawalRejectionError)}
                aria-required="true"
                required
                rows={3}
                bind:value={withdrawalRejectionReason}
                oninput={() => (withdrawalRejectionError = "")}
              />
            </AdminField>
          </div>
        </div>
      {/if}
      <AdminCardActions>
        <AdminButton
          variant="primary"
          disabled={selectedWithdrawal.status !== "requested"}
          onclick={() => void transitionWithdrawal("processing")}
        >
          {at("partners_take_processing", {}, "Take into processing")}
        </AdminButton>
        <AdminButton
          disabled={selectedWithdrawal.status !== "processing"}
          onclick={() => void transitionWithdrawal("paid")}
        >
          {at("partners_mark_paid", {}, "Mark paid")}
        </AdminButton>
        <AdminButton
          variant="dangerSoft"
          disabled={selectedWithdrawal.status === "paid" ||
            selectedWithdrawal.status === "rejected"}
          onclick={() => void transitionWithdrawal("reject")}
        >
          {at("partners_reject_return", {}, "Reject and return")}
        </AdminButton>
      </AdminCardActions>
    </article>
  </section>
{/if}
