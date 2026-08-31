<script lang="ts">
  import { getPaymentsStore } from "$lib/admin/context";
  import {
    CalendarDays,
    Copy,
    CreditCard,
    Database,
    Tag,
    User,
    UsersRound,
    WalletCards,
  } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton, AdminCopyableValue } from "$components/patterns/admin/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import type { AdminPayment } from "../../lib/admin/stores/paymentsStore";
  import type { AdminBadgeVariant } from "$components/patterns/admin/types";
  import { paymentDiscountDisplay } from "$lib/admin/paymentTable.js";
  import { demoPartnerAttributionForPayment } from "$lib/webapp/mockApi/partnerProgram.js";
  import { partnerStatusVariant } from "$lib/admin/partnerProgramUi.js";
  import PaymentPurchasesCell from "./PaymentPurchasesCell.svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type MetaRow = {
    label: string;
    value: unknown;
    copy?: unknown;
    href?: string | null;
    promo?: boolean;
  };

  let {
    at = (key, _params = {}, fallback = "") => fallback || key,
    fmtDate = (value) => String(value || ""),
    fmtMoney = (amount, currency) => `${amount} ${currency || ""}`.trim(),
    paymentStatusVariant = () => "muted",
    onOpenUserCard = () => {},
    onOpenPartnerCard = () => {},
    onOpenPromoCard = () => {},
  }: {
    at?: TranslateFn;
    fmtDate?: (value: string | null | undefined) => string;
    fmtMoney?: (amount: unknown, currency?: string | null) => string;
    paymentStatusVariant?: (status: string | null | undefined) => AdminBadgeVariant;
    onOpenUserCard?: (userId: number) => void;
    onOpenPartnerCard?: (partnerId: string) => void;
    onOpenPromoCard?: (promoId: number) => void;
  } = $props();

  const paymentsStore = getPaymentsStore();
  const closePayment = (): void => paymentsStore.closePayment();
  const openedPaymentId = $derived(paymentsStore.openedPaymentId as number | null);
  const openedPayment = $derived(paymentsStore.openedPayment as AdminPayment | null);
  const paymentDetailLoading = $derived(Boolean(paymentsStore.paymentDetailLoading));
  const paymentActionBusy = $derived(Boolean(paymentsStore.paymentActionBusy));
  let actionMode = $state<"finalize" | "reverse" | null>(null);
  let actionReason = $state("");
  let confirmPromoConflict = $state(false);
  let restorePromoUsage = $state(true);
  const payment = $derived(
    (openedPayment ||
      (openedPaymentId ? { payment_id: openedPaymentId } : null)) as AdminPayment | null
  );
  const title = $derived(
    payment
      ? at("payment_detail_title", { id: payment.payment_id }, `Payment #${payment.payment_id}`)
      : ""
  );
  const description = $derived(
    payment
      ? [
          payment.provider,
          payment.created_at ? fmtDate(payment.created_at) : "",
          payment.user_label || payment.user_id,
        ]
          .filter(Boolean)
          .join(" · ")
      : ""
  );

  function present(value: unknown): boolean {
    return value !== null && value !== undefined && value !== "";
  }

  function display(value: unknown): string {
    return present(value) ? String(value) : "—";
  }

  function money(value: unknown, currency?: string | null): string {
    return present(value) ? fmtMoney(value, currency) : "—";
  }

  function formatGb(value: unknown): string {
    if (!present(value)) return "—";
    const n = Number(value);
    if (Number.isNaN(n)) return display(value);
    const rounded = Math.abs(n - Math.round(n)) < 1e-9 ? Math.round(n) : Math.round(n * 100) / 100;
    return `${rounded} GB`;
  }

  function formatTrafficSplit(p: AdminPayment | null): string {
    const parts: string[] = [];
    const regularGb = p?.traffic_regular_gb;
    const premiumGb = p?.traffic_premium_gb;
    if (present(regularGb)) {
      parts.push(
        at(
          "payment_detail_regular_traffic",
          { gb: formatGb(regularGb) },
          `Regular: ${formatGb(regularGb)}`
        )
      );
    }
    if (present(premiumGb)) {
      parts.push(
        at(
          "payment_detail_premium_traffic",
          { gb: formatGb(premiumGb) },
          `Premium: ${formatGb(premiumGb)}`
        )
      );
    }
    return parts.join(" · ") || "—";
  }

  function paymentDescription(p: AdminPayment | null): string {
    const raw = p?.description && String(p.description).trim();
    if (raw) return raw;
    return formatTrafficSplit(p);
  }

  function copy(value: unknown): void {
    paymentsStore.copyToClipboard(value, at("payment_detail_copied", {}, "Copied"));
  }

  function copyLabel(value: unknown): string {
    return at("copy_value", { value }, "Copy {value}");
  }

  function openPartner(): void {
    if (!partnerAttribution) return;
    paymentsStore.closePayment({ skipPush: true });
    onOpenPartnerCard(partnerAttribution.partnerId);
  }

  function openUser(): void {
    if (!payment?.user_id) return;
    paymentsStore.closePayment({ skipPush: true });
    onOpenUserCard(payment.user_id);
  }

  function openPromo(): void {
    const promoId = Number(payment?.promo_code_id);
    if (!Number.isFinite(promoId) || promoId <= 0) return;
    paymentsStore.closePayment({ skipPush: true });
    onOpenPromoCard(promoId);
  }

  function startAction(mode: "finalize" | "reverse"): void {
    actionMode = mode;
    actionReason = "";
    confirmPromoConflict = false;
    restorePromoUsage = true;
  }

  function cancelAction(): void {
    actionMode = null;
    actionReason = "";
  }

  async function submitAction(): Promise<void> {
    const reason = actionReason.trim();
    if (reason.length < 3 || !actionMode) return;
    const succeeded =
      actionMode === "finalize"
        ? await paymentsStore.finalizePayment(reason, confirmPromoConflict)
        : await paymentsStore.reversePayment(reason, restorePromoUsage);
    if (succeeded) cancelAction();
  }

  function warningLabel(code: string): string {
    if (code === "promo_used_by_another_payment") {
      return at(
        "payment_warning_promo_used_by_another_payment",
        {},
        "The promo code was already used by another payment."
      );
    }
    if (code === "provider_payment_id_missing") {
      return at(
        "payment_warning_provider_payment_id_missing",
        {},
        "Provider payment ID is missing; verify the charge externally."
      );
    }
    if (code === "provider_status_not_failed") {
      return at(
        "payment_warning_provider_status_not_failed",
        {},
        "The current provider status is not a terminal failure."
      );
    }
    return at(
      "payment_warning_purchase_context_missing",
      {},
      "The immutable purchase context is incomplete."
    );
  }

  function fulfillmentSourceLabel(source: string | null | undefined): string {
    if (source === "admin") {
      return at("payment_fulfillment_source_admin", {}, "Administrator");
    }
    if (source) {
      return at("payment_fulfillment_source_provider", {}, "Payment provider");
    }
    return "—";
  }

  function reversalBlockLabel(code: string | null | undefined): string {
    if (code === "fulfillment_snapshot_missing") {
      return at(
        "payment_reversal_snapshot_missing",
        {},
        "This payment has no fulfillment snapshots and cannot be reversed safely."
      );
    }
    if (code === "payment_already_reversed") {
      return at("payment_reversal_already_reversed", {}, "This payment is already reversed.");
    }
    return at(
      "payment_reversal_not_succeeded",
      {},
      "Only successfully applied payments can be reversed."
    );
  }

  function durationText(p: AdminPayment | null): string {
    const months = p?.subscription_duration_months;
    return present(months)
      ? at("payment_detail_months_count", { count: months }, `${months} mo.`)
      : "";
  }

  const paymentRows = $derived([
    {
      label: "ID",
      value: payment?.payment_id ? `#${payment.payment_id}` : "",
      copy: payment?.payment_id,
    },
    {
      label: at("amount", {}, "Amount"),
      value: money(payment?.amount, payment?.currency),
    },
    { label: at("status", {}, "Status"), value: payment?.status },
    {
      label: at("date", {}, "Date"),
      value: payment?.created_at ? fmtDate(payment.created_at) : "",
    },
    {
      label: at("payment_detail_updated_at", {}, "Updated"),
      value: payment?.updated_at ? fmtDate(payment.updated_at) : "",
    },
    {
      label: at("payment_detail_fulfillment_source", {}, "Applied by"),
      value: fulfillmentSourceLabel(payment?.fulfillment_source),
    },
    {
      label: at("payment_detail_fulfilled_at", {}, "Applied at"),
      value: payment?.fulfilled_at ? fmtDate(payment.fulfilled_at) : "",
    },
    {
      label: at("payment_detail_reversed_at", {}, "Reversed at"),
      value: payment?.reversed_at ? fmtDate(payment.reversed_at) : "",
    },
    {
      label: at("payment_detail_fulfilled_by_admin", {}, "Applied by admin ID"),
      value: payment?.fulfilled_by_admin_id,
      copy: payment?.fulfilled_by_admin_id,
    },
    {
      label: at("payment_detail_fulfillment_note", {}, "Application reason"),
      value: payment?.fulfillment_note,
    },
    {
      label: at("payment_detail_reversed_by_admin", {}, "Reversed by admin ID"),
      value: payment?.reversed_by_admin_id,
      copy: payment?.reversed_by_admin_id,
    },
    {
      label: at("payment_detail_reversal_note", {}, "Reversal reason"),
      value: payment?.reversal_note,
    },
    { label: at("description", {}, "Description"), value: paymentDescription(payment) },
  ] satisfies MetaRow[]);

  const providerRows = $derived([
    { label: at("provider", {}, "Provider"), value: payment?.provider },
    {
      label: at("payment_detail_provider_payment_id", {}, "Provider ID"),
      value: payment?.provider_payment_id,
      copy: payment?.provider_payment_id,
    },
    {
      label: at("payment_detail_provider_payment_url", {}, "Payment link"),
      value: payment?.provider_payment_url,
      href: payment?.provider_payment_url,
      copy: payment?.provider_payment_url,
    },
    {
      label: "YooKassa ID",
      value: payment?.yookassa_payment_id,
      copy: payment?.yookassa_payment_id,
    },
    {
      label: at("payment_detail_idempotence_key", {}, "Idempotence key"),
      value: payment?.idempotence_key,
      copy: payment?.idempotence_key,
    },
  ] satisfies MetaRow[]);

  const purchaseRows = $derived([
    { label: at("payment_detail_sale_mode", {}, "Sale type"), value: payment?.sale_mode },
    { label: at("payment_detail_tariff_key", {}, "Tariff"), value: payment?.tariff_key },
    {
      label: at("payment_detail_duration_months", {}, "Period"),
      value: durationText(payment),
    },
    {
      label: at("payments_col_discount", {}, "Discount"),
      value: payment
        ? paymentDiscountDisplay(payment, (value, currency) => fmtMoney(value, currency))
        : "—",
    },
    {
      label: at("payment_detail_promo_code", {}, "Promo code"),
      value: payment?.promo_code,
      promo: Boolean(payment?.promo_code_id),
    },
  ] satisfies MetaRow[]);

  const userRows = $derived([
    { label: at("user", {}, "User"), value: payment?.user_label },
    { label: "User ID", value: payment?.user_id, copy: payment?.user_id },
    { label: "Telegram ID", value: payment?.telegram_id, copy: payment?.telegram_id },
  ] satisfies MetaRow[]);

  // Demo partner attribution is derived from the same payment rows as the
  // payments table, so the linked user, payment, and commission stay aligned.
  const partnerAttribution = $derived(demoPartnerAttributionForPayment(payment?.payment_id));
</script>

<Dialog
  open={Boolean(openedPaymentId)}
  {title}
  {description}
  closeLabel={at("close", {}, "Close")}
  onclose={closePayment}
  class="admin-dialog admin-payment-dialog"
>
  {#if payment}
    <div class="admin-payment-dialog-body">
      <aside class="admin-payment-aside">
        <div class="admin-payment-summary">
          <span class="admin-payment-icon" aria-hidden="true">
            <WalletCards size={24} />
          </span>
          <div class="admin-payment-summary-meta">
            <strong>{money(payment.amount, payment.currency)}</strong>
            <small>{paymentDescription(payment)}</small>
            <div class="admin-payment-summary-tags">
              <AdminBadge variant={paymentStatusVariant(payment.status)}
                >{display(payment.status)}</AdminBadge
              >
              {#if payment.provider}
                <AdminBadge variant="muted">{payment.provider}</AdminBadge>
              {/if}
              {#if payment.fulfillment_source === "admin"}
                <AdminBadge variant="warning">
                  {at("payment_manual_badge", {}, "Applied manually")}
                </AdminBadge>
              {/if}
            </div>
          </div>
        </div>

        <div class="admin-payment-stats">
          <div class="admin-payment-stat">
            <CreditCard size={15} />
            <span>{at("payment_detail_provider", {}, "Provider")}</span>
            <strong>{display(payment.provider)}</strong>
          </div>
          <div class="admin-payment-stat">
            <CalendarDays size={15} />
            <span>{at("date", {}, "Date")}</span>
            <strong>{payment.created_at ? fmtDate(payment.created_at) : "—"}</strong>
          </div>
        </div>

        <div class="admin-subsection-title">
          {at("payment_detail_user_section", {}, "User")}
        </div>
        <ul class="admin-meta-list admin-payment-meta-list">
          {#each userRows as row}
            <li>
              <span>{row.label}</span>
              <strong class:admin-meta-truncate={row.copy}>
                {#if row.copy}
                  <AdminCopyableValue
                    value={row.copy}
                    text={display(row.value)}
                    copyLabel={copyLabel(row.copy)}
                    showIcon={false}
                    oncopy={copy}
                  />
                {:else}
                  {display(row.value)}
                {/if}
              </strong>
              {#if row.copy}
                <AdminButton
                  size="icon"
                  variant="icon"
                  title={at("user_copy_tooltip", {}, "Copy")}
                  onclick={() => copy(row.copy)}
                >
                  <Copy size={14} />
                </AdminButton>
              {/if}
            </li>
          {/each}
        </ul>

        <AdminButton variant="ghost" onclick={openUser} disabled={!payment.user_id}>
          <User size={14} />
          {at("payments_open_user", {}, "Open user card")}
        </AdminButton>

        {#if partnerAttribution}
          <div class="admin-subsection-title">
            {at("payment_detail_partner_section", {}, "Partner program")}
          </div>
          <ul class="admin-meta-list admin-payment-meta-list">
            <li>
              <span>{at("payment_detail_partner", {}, "Partner")}</span>
              <strong class="admin-meta-truncate">{partnerAttribution.partnerName}</strong>
            </li>
            <li>
              <span>{at("payment_detail_partner_rate", {}, "Rate")}</span>
              <strong>{partnerAttribution.rate}%</strong>
            </li>
            <li>
              <span>{at("payment_detail_partner_commission", {}, "Commission")}</span>
              <strong>{money(partnerAttribution.amount, payment.currency)}</strong>
            </li>
            <li>
              <span>{at("payment_detail_partner_commission_status", {}, "Commission status")}</span>
              <strong>
                <AdminBadge variant={partnerStatusVariant(partnerAttribution.status)}>
                  {at(
                    `partners_status_${partnerAttribution.status}`,
                    {},
                    partnerAttribution.status
                  )}
                </AdminBadge>
              </strong>
            </li>
          </ul>
          <AdminButton variant="ghost" onclick={openPartner}>
            <UsersRound size={14} />
            {at("payment_detail_open_partner", {}, "Open partner card")}
          </AdminButton>
        {/if}
      </aside>

      <main class="admin-payment-main">
        {#if paymentDetailLoading && !openedPayment}
          <p class="admin-muted">{at("loading", {}, "Loading…")}</p>
        {:else}
          <section class="admin-payment-panel">
            <div class="admin-payment-panel-head">
              <CreditCard size={16} />
              <h3>{at("payment_detail_payment_section", {}, "Payment")}</h3>
            </div>
            <ul class="admin-meta-list admin-payment-meta-list">
              {#each paymentRows as row}
                <li>
                  <span>{row.label}</span>
                  <strong class:admin-meta-truncate={row.copy}>
                    {#if row.copy}
                      <AdminCopyableValue
                        value={row.copy}
                        text={display(row.value)}
                        copyLabel={copyLabel(row.copy)}
                        showIcon={false}
                        oncopy={copy}
                      />
                    {:else}
                      {display(row.value)}
                    {/if}
                  </strong>
                  {#if row.copy}
                    <AdminButton
                      size="icon"
                      variant="icon"
                      title={at("user_copy_tooltip", {}, "Copy")}
                      onclick={() => copy(row.copy)}
                    >
                      <Copy size={14} />
                    </AdminButton>
                  {/if}
                </li>
              {/each}
            </ul>
          </section>

          <section class="admin-payment-panel">
            <div class="admin-payment-panel-head">
              <Database size={16} />
              <h3>{at("payment_detail_provider_section", {}, "Provider")}</h3>
            </div>
            <ul class="admin-meta-list admin-payment-meta-list">
              {#each providerRows as row}
                <li>
                  <span>{row.label}</span>
                  {#if row.href}
                    <a
                      class="admin-payment-meta-link admin-meta-truncate"
                      href={row.href}
                      target="_blank"
                      rel="noopener noreferrer">{display(row.value)}</a
                    >
                  {:else}
                    <strong class:admin-meta-truncate={row.copy}>
                      {#if row.copy}
                        <AdminCopyableValue
                          value={row.copy}
                          text={display(row.value)}
                          copyLabel={copyLabel(row.copy)}
                          showIcon={false}
                          oncopy={copy}
                        />
                      {:else}
                        {display(row.value)}
                      {/if}
                    </strong>
                  {/if}
                  {#if row.copy}
                    <AdminButton
                      size="icon"
                      variant="icon"
                      title={at("user_copy_tooltip", {}, "Copy")}
                      onclick={() => copy(row.copy)}
                    >
                      <Copy size={14} />
                    </AdminButton>
                  {/if}
                </li>
              {/each}
            </ul>
          </section>

          <section class="admin-payment-panel">
            <div class="admin-payment-panel-head">
              <Tag size={16} />
              <h3>{at("payment_detail_purchase_section", {}, "Purchase")}</h3>
            </div>
            <PaymentPurchasesCell {payment} {at} mode="detail" />
            <ul class="admin-meta-list admin-payment-meta-list">
              {#each purchaseRows as row}
                <li>
                  <span>{row.label}</span>
                  {#if row.promo}
                    <AdminButton variant="ghost" size="sm" onclick={openPromo}>
                      {display(row.value)}
                    </AdminButton>
                  {:else}
                    <strong>{display(row.value)}</strong>
                  {/if}
                </li>
              {/each}
            </ul>
          </section>

          {#if payment.can_manual_finalize || payment.can_reverse || payment.status === "succeeded" || actionMode}
            <section class="admin-payment-panel admin-payment-actions-panel">
              <div class="admin-payment-panel-head">
                <Database size={16} />
                <h3>{at("payment_actions_title", {}, "Manual actions")}</h3>
              </div>

              {#if !actionMode}
                <div class="admin-payment-action-buttons">
                  {#if payment.can_manual_finalize}
                    <AdminButton variant="primary" onclick={() => startAction("finalize")}>
                      {at("payment_manual_finalize", {}, "Apply payment")}
                    </AdminButton>
                  {/if}
                  {#if payment.can_reverse}
                    <AdminButton variant="danger" onclick={() => startAction("reverse")}>
                      {at("payment_reverse", {}, "Reverse payment")}
                    </AdminButton>
                  {/if}
                </div>
                {#if payment.status === "succeeded" && !payment.can_reverse}
                  <p class="admin-payment-action-unavailable">
                    {reversalBlockLabel(payment.reversal_block_reason)}
                  </p>
                {/if}
              {:else}
                <div class="admin-payment-action-confirm">
                  <p>
                    {actionMode === "finalize"
                      ? at(
                          "payment_manual_finalize_confirm",
                          {},
                          "Apply all frozen purchase effects to this customer?"
                        )
                      : at(
                          "payment_reverse_confirm",
                          {},
                          "Reverse only the effects recorded for this payment?"
                        )}
                  </p>

                  {#if actionMode === "finalize" && payment.manual_finalize_warnings?.length}
                    <ul class="admin-payment-warning-list">
                      {#each payment.manual_finalize_warnings as warning}
                        <li>{warningLabel(warning)}</li>
                      {/each}
                    </ul>
                  {/if}

                  {#if actionMode === "finalize" && payment.manual_finalize_requires_promo_confirmation}
                    <label class="admin-payment-action-check">
                      <input type="checkbox" bind:checked={confirmPromoConflict} />
                      <span>
                        {at(
                          "payment_manual_confirm_promo_conflict",
                          {},
                          "Honor the frozen promo terms and record an extra override use"
                        )}
                      </span>
                    </label>
                  {/if}

                  {#if actionMode === "reverse" && payment.promo_code_id}
                    <label class="admin-payment-action-check">
                      <input type="checkbox" bind:checked={restorePromoUsage} />
                      <span>
                        {at(
                          "payment_reverse_restore_promo",
                          {},
                          "Return this use to the promo code"
                        )}
                      </span>
                    </label>
                  {/if}

                  <label class="admin-payment-action-reason">
                    <span>{at("payment_action_reason", {}, "Reason")}</span>
                    <textarea
                      rows="3"
                      maxlength="500"
                      bind:value={actionReason}
                      placeholder={at(
                        "payment_action_reason_placeholder",
                        {},
                        "Record why this manual action is required"
                      )}></textarea>
                  </label>

                  <div class="admin-payment-action-buttons">
                    <AdminButton
                      variant="ghost"
                      disabled={paymentActionBusy}
                      onclick={cancelAction}
                    >
                      {at("cancel", {}, "Cancel")}
                    </AdminButton>
                    <AdminButton
                      variant={actionMode === "reverse" ? "danger" : "primary"}
                      disabled={paymentActionBusy ||
                        actionReason.trim().length < 3 ||
                        (actionMode === "finalize" &&
                          payment.manual_finalize_requires_promo_confirmation &&
                          !confirmPromoConflict)}
                      onclick={submitAction}
                    >
                      {paymentActionBusy
                        ? at("saving", {}, "Saving…")
                        : at("confirm", {}, "Confirm")}
                    </AdminButton>
                  </div>
                </div>
              {/if}
            </section>
          {/if}
        {/if}
      </main>
    </div>
  {/if}
</Dialog>

<style>
  .admin-payment-meta-link {
    color: var(--admin-primary);
    font-weight: 700;
  }

  .admin-payment-action-buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .admin-payment-action-confirm {
    display: grid;
    gap: 12px;
  }

  .admin-payment-action-confirm p,
  .admin-payment-warning-list {
    margin: 0;
  }

  .admin-payment-warning-list {
    display: grid;
    gap: 6px;
    padding: 10px 12px 10px 28px;
    border: 1px solid color-mix(in srgb, var(--admin-warning) 45%, transparent);
    border-radius: 10px;
    color: var(--admin-text);
    background: color-mix(in srgb, var(--admin-warning) 10%, transparent);
  }

  .admin-payment-action-check,
  .admin-payment-action-reason {
    display: flex;
    gap: 8px;
  }

  .admin-payment-action-check {
    align-items: flex-start;
  }

  .admin-payment-action-reason {
    flex-direction: column;
    font-size: 12px;
    font-weight: 700;
  }

  .admin-payment-action-reason textarea {
    width: 100%;
    resize: vertical;
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    padding: 10px 12px;
    color: var(--admin-text);
    background: var(--admin-surface);
    font: inherit;
  }
</style>
