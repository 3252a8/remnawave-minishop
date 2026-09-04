<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import {
    AdminBadge,
    AdminButton,
    AdminSectionHeader,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { Input } from "$components/ui/index.js";
  import { Label } from "$components/ui/primitives.js";
  import { ArrowDownUp, Coins, Plus } from "$components/ui/icons.js";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState";
  import {
    balanceAdjustmentValid,
    balanceTargetAvailable,
    defaultBalanceTarget,
    resolveBalanceTarget,
    type BalanceAdjustmentMode,
    type BalanceTarget,
  } from "./userBalanceControls.js";
  import type { BadgeVariant, SelectOption, TranslateFn } from "./userDetailTypes";

  let {
    at,
    openedUserDetail,
    userActionBusy = false,
  }: {
    at: TranslateFn;
    openedUserDetail: AdminUserDetail;
    userActionBusy?: boolean;
  } = $props();

  const usersStore = getUsersStore();
  let adjustmentTarget = $state<BalanceTarget>("user");
  let adjustmentContextUserId = $state<number | null>(null);
  let adjustmentMode = $state<BalanceAdjustmentMode>("add");
  let adjustmentAmount = $state("");
  let adjustmentReason = $state("");
  let conversionDirection = $state<"partner_to_user" | "user_to_partner">("partner_to_user");
  let conversionAmount = $state("");
  let conversionReason = $state("");

  const balance = $derived(openedUserDetail.balance);
  const sources = $derived(balance?.sources || []);
  const userSource = $derived(sources.find((source) => source.id === "user") || null);
  const partnerSource = $derived(sources.find((source) => source.id === "partner") || null);
  const userBalanceEnabled = $derived(Boolean(balance?.enabled));
  const userBalanceAdjustable = $derived(Boolean(userSource?.adjustable ?? true));
  const partnerAdjustable = $derived(
    Boolean(partnerSource?.adjustable ?? partnerSource?.convertible)
  );
  const partnerConvertible = $derived(Boolean(partnerSource?.convertible));
  const currencyScale = $derived(Number(balance?.currency_scale || 0));
  const amountFactor = $derived(10 ** currencyScale);
  const amountStep = $derived(1 / amountFactor);
  const adjustmentTargetAvailable = $derived(
    balanceTargetAvailable(adjustmentTarget, userBalanceAdjustable, partnerAdjustable)
  );
  const adjustmentSource = $derived(adjustmentTarget === "partner" ? partnerSource : userSource);
  const adjustmentCurrentMinor = $derived(Math.max(0, Number(adjustmentSource?.amount_minor || 0)));
  const adjustmentValid = $derived(
    balanceAdjustmentValid({
      amountFactor,
      currentAmountMinor: adjustmentCurrentMinor,
      mode: adjustmentMode,
      targetAvailable: adjustmentTargetAvailable,
      value: adjustmentAmount,
    })
  );
  const conversionMaximumMinor = $derived(
    Math.max(
      0,
      Number(
        conversionDirection === "partner_to_user"
          ? partnerSource?.amount_minor
          : userSource?.amount_minor
      ) || 0
    )
  );
  const conversionAmountMinor = $derived(Math.round(Number(conversionAmount || 0) * amountFactor));
  const conversionValid = $derived(
    conversionAmount.trim() !== "" &&
      Number.isFinite(conversionAmountMinor) &&
      conversionAmountMinor > 0 &&
      conversionAmountMinor <= conversionMaximumMinor
  );

  const adjustmentModes = $derived<SelectOption[]>([
    { value: "add", label: at("user_balance_mode_add", {}, "Add") },
    { value: "subtract", label: at("user_balance_mode_subtract", {}, "Subtract") },
    { value: "set", label: at("user_balance_mode_set", {}, "Set exact amount") },
  ]);
  const adjustmentTargets = $derived<SelectOption[]>([
    {
      value: "user",
      label: at("user_balance_main_source", {}, "Main balance"),
      disabled: !userBalanceAdjustable,
    },
    {
      value: "partner",
      label: at("user_balance_partner_source", {}, "Partner balance"),
      disabled: !partnerAdjustable,
    },
  ]);
  const manageableTargetCount = $derived(Number(userBalanceAdjustable) + Number(partnerAdjustable));
  const conversionDirections = $derived<SelectOption[]>([
    {
      value: "partner_to_user",
      label: at("user_balance_partner_to_user", {}, "Partner → main"),
    },
    {
      value: "user_to_partner",
      label: at("user_balance_user_to_partner", {}, "Main → partner"),
    },
  ]);

  $effect(() => {
    const userId = Number(openedUserDetail.user?.user_id || 0) || null;
    if (userId !== adjustmentContextUserId) {
      adjustmentContextUserId = userId;
      adjustmentTarget = defaultBalanceTarget(userBalanceEnabled, partnerAdjustable);
      adjustmentAmount = "";
      return;
    }
    const resolved = resolveBalanceTarget(
      adjustmentTarget,
      userBalanceAdjustable,
      partnerAdjustable
    );
    if (resolved && resolved !== adjustmentTarget) {
      adjustmentTarget = resolved;
      adjustmentAmount = "";
    }
  });

  function formatMoney(amountMinor: number | undefined, currency?: string): string {
    const value = Number(amountMinor || 0) / amountFactor;
    try {
      return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: currency || balance?.currency || "RUB",
        maximumFractionDigits: currencyScale,
      }).format(value);
    } catch {
      return `${value.toFixed(currencyScale)} ${currency || balance?.currency || ""}`.trim();
    }
  }

  function operationKey(prefix: string): string {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
      return `${prefix}:${crypto.randomUUID()}`;
    }
    return `${prefix}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
  }

  function amountInputValue(amountMinor: number): string {
    const fixed = (amountMinor / amountFactor).toFixed(currencyScale);
    return currencyScale > 0 ? fixed.replace(/\.?0+$/, "") : fixed;
  }

  function useMaximumConversionAmount(): void {
    if (conversionMaximumMinor <= 0 || userActionBusy) return;
    conversionAmount = amountInputValue(conversionMaximumMinor);
  }

  function selectAdjustmentTarget(value: string): void {
    const target = value as BalanceTarget;
    if (
      target === adjustmentTarget ||
      !balanceTargetAvailable(target, userBalanceAdjustable, partnerAdjustable)
    ) {
      return;
    }
    adjustmentTarget = target;
    adjustmentAmount = "";
  }

  function selectAdjustmentMode(value: string): void {
    const mode = value as BalanceAdjustmentMode;
    if (mode === adjustmentMode) return;
    adjustmentMode = mode;
    adjustmentAmount = "";
  }

  function selectConversionDirection(value: string): void {
    const direction = value as typeof conversionDirection;
    if (direction === conversionDirection) return;
    conversionDirection = direction;
    conversionAmount = "";
  }

  function useMaximumAdjustmentAmount(): void {
    if (adjustmentMode !== "subtract" || adjustmentCurrentMinor <= 0 || userActionBusy) return;
    adjustmentAmount = amountInputValue(adjustmentCurrentMinor);
  }

  async function submitAdjustment() {
    if (!adjustmentValid) return;
    const saved = await usersStore.adjustUserBalance({
      target: adjustmentTarget,
      mode: adjustmentMode,
      amount: Number(adjustmentAmount),
      reason: adjustmentReason.trim(),
      idempotency_key: operationKey("admin-balance"),
    });
    if (saved) {
      adjustmentAmount = "";
      adjustmentReason = "";
    }
  }

  async function submitConversion() {
    if (!conversionValid) return;
    const saved = await usersStore.convertUserBalance({
      direction: conversionDirection,
      amount: Number(conversionAmount),
      reason: conversionReason.trim(),
      idempotency_key: operationKey("admin-balance-conversion"),
    });
    if (saved) {
      conversionAmount = "";
      conversionReason = "";
    }
  }

  function historyKind(kind?: string): string {
    const fallbacks: Record<string, string> = {
      payment_topup: "Payment top-up",
      payment_topup_reversal: "Payment reversal",
      admin_adjustment: "Admin adjustment",
      checkout_spend: "Purchase",
      checkout_release: "Released reservation",
      partner_conversion_in: "From partner balance",
      partner_conversion_out: "To partner balance",
      manual_adjustment: "Admin operation",
      commission_credit: "Partner commission",
      commission_reversal: "Commission reversal",
      withdrawal_reserve: "Withdrawal reserved",
      withdrawal_release: "Withdrawal released",
      subscription_spend: "Subscription payment",
      subscription_spend_release: "Subscription payment released",
      balance_conversion_in: "From main balance",
      balance_conversion_out: "To main balance",
    };
    const key = String(kind || "operation");
    return at(`user_balance_history_${key}`, {}, fallbacks[key] || key.replaceAll("_", " "));
  }

  function historySource(sourceId?: string): string {
    return sourceId === "partner"
      ? at("user_balance_partner_source", {}, "Partner balance")
      : at("user_balance_main_source", {}, "Main balance");
  }

  function partnerStatusLabel(): string {
    if (!partnerAdjustable) {
      return at("user_balance_partner_unavailable", {}, "No partner profile");
    }
    const status = String(partnerSource?.status || "available");
    const fallbacks: Record<string, string> = {
      active: "Active",
      paused: "Paused",
      closed: "Closed",
      available: "Available",
    };
    return at(
      `user_balance_partner_status_${status}`,
      {},
      fallbacks[status] || fallbacks.available
    );
  }

  function partnerStatusVariant(): BadgeVariant {
    const status = String(partnerSource?.status || "");
    if (status === "active") return "success";
    if (status === "paused") return "warning";
    return "muted";
  }
</script>

<section class="admin-user-action-sheet admin-user-action-sheet--balance">
  <AdminSectionHeader
    title={at("user_balance_admin_title", {}, "User balance")}
    description={at(
      "user_balance_admin_hint",
      {},
      "Manage the spendable balance, convert partner funds, and review the immutable ledger."
    )}
  />
  <div class="admin-user-action-sheet-body balance-card-body">
    <div class="balance-section-block balance-section-block--summary">
      <div class="balance-block-heading">
        <strong>{at("user_balance_balances_title", {}, "Balances")}</strong>
      </div>
      <div class="balance-summary-grid">
        <button
          type="button"
          class="balance-summary-tile balance-summary-tile--primary"
          class:is-selected={adjustmentTarget === "user" && adjustmentTargetAvailable}
          aria-pressed={adjustmentTarget === "user" && adjustmentTargetAvailable}
          disabled={userActionBusy || !userBalanceAdjustable}
          onclick={() => selectAdjustmentTarget("user")}
        >
          <span>{at("user_balance_main_source", {}, "Main balance")}</span>
          <strong
            >{formatMoney(
              userSource?.amount_minor ?? balance?.amount_minor,
              balance?.currency
            )}</strong
          >
          <AdminBadge variant={balance?.enabled ? "success" : "muted"}>
            {balance?.enabled
              ? at("user_balance_enabled", {}, "Enabled")
              : at("user_balance_disabled", {}, "Disabled for users")}
          </AdminBadge>
        </button>
        <button
          type="button"
          class="balance-summary-tile"
          class:is-selected={adjustmentTarget === "partner" && adjustmentTargetAvailable}
          aria-pressed={adjustmentTarget === "partner" && adjustmentTargetAvailable}
          disabled={userActionBusy || !partnerAdjustable}
          onclick={() => selectAdjustmentTarget("partner")}
        >
          <span>{at("user_balance_partner_source", {}, "Partner balance")}</span>
          <strong>{formatMoney(partnerSource?.amount_minor, partnerSource?.currency)}</strong>
          <AdminBadge variant={partnerStatusVariant()}>{partnerStatusLabel()}</AdminBadge>
          <small
            >{at(
              "user_balance_partner_withdrawal_hint",
              {},
              "Withdrawable rules are preserved"
            )}</small
          >
        </button>
      </div>
    </div>

    <div class="balance-section-block balance-section-block--adjustment">
      <div class="balance-block-heading">
        <strong>{at("user_balance_adjustment_title", {}, "Manual operation")}</strong>
        <small>{at("user_balance_adjustment_hint", {}, "Choose a balance and an action")}</small>
      </div>
      <div class="balance-control-row balance-control-row--adjustment">
        <Label.Root class="admin-field-label balance-target-field">
          <span>{at("user_balance_target", {}, "Target balance")}</span>
          <AdminSelect
            value={adjustmentTarget}
            items={adjustmentTargets}
            ariaLabel={at("user_balance_target", {}, "Target balance")}
            disabled={userActionBusy || manageableTargetCount <= 1}
            onValueChange={selectAdjustmentTarget}
          />
        </Label.Root>
        <Label.Root class="admin-field-label balance-mode-field">
          <span>{at("user_balance_adjustment_mode", {}, "Operation")}</span>
          <AdminSelect
            value={adjustmentMode}
            items={adjustmentModes}
            ariaLabel={at("user_balance_adjustment_mode", {}, "Operation")}
            disabled={userActionBusy || !adjustmentTargetAvailable}
            onValueChange={selectAdjustmentMode}
          />
        </Label.Root>
        <Label.Root class="admin-field-label balance-amount-field">
          <span>{at("user_balance_amount", {}, "Amount")}</span>
          <div class="balance-amount-input-wrap">
            <Input
              class="input balance-amount-input"
              type="number"
              min={adjustmentMode === "set" ? 0 : amountStep}
              max={adjustmentMode === "subtract"
                ? adjustmentCurrentMinor / amountFactor
                : undefined}
              step={amountStep}
              inputmode="decimal"
              placeholder="0"
              bind:value={adjustmentAmount}
              disabled={userActionBusy || !adjustmentTargetAvailable}
            />
            {#if adjustmentMode === "subtract"}
              <button
                type="button"
                class="balance-amount-max"
                onclick={useMaximumAdjustmentAmount}
                disabled={userActionBusy ||
                  !adjustmentTargetAvailable ||
                  adjustmentCurrentMinor <= 0}
                title={at("user_balance_max", {}, "Maximum")}
                aria-label={at("user_balance_max_aria", {}, "Use maximum available balance")}
              >
                {at("user_balance_max", {}, "Max")}
              </button>
            {/if}
          </div>
        </Label.Root>
        <Label.Root class="admin-field-label balance-reason-field">
          <span>{at("user_balance_reason", {}, "Reason / comment")}</span>
          <Input
            class="input"
            placeholder={at("user_balance_reason_placeholder", {}, "Optional audit note")}
            bind:value={adjustmentReason}
            disabled={userActionBusy || !adjustmentTargetAvailable}
          />
        </Label.Root>
        <AdminButton
          class="balance-operation-submit"
          variant="primary"
          onclick={submitAdjustment}
          disabled={userActionBusy || !adjustmentValid}
        >
          {#if adjustmentMode === "subtract"}<Coins size={14} />{:else}<Plus size={14} />{/if}
          {at("user_balance_adjustment_submit", {}, "Apply operation")}
        </AdminButton>
      </div>
      {#if !adjustmentTargetAvailable}
        <small class="balance-operation-unavailable">
          {at(
            "user_balance_adjustment_unavailable",
            {},
            "Enable the main balance or create a partner profile to manage funds."
          )}
        </small>
      {/if}
    </div>

    <div class="balance-section-block balance-section-block--conversion">
      <div class="balance-block-heading">
        <strong>{at("user_balance_conversion_title", {}, "Convert balances")}</strong>
        <small>{at("user_balance_conversion_hint", {}, "Move funds between balances")}</small>
      </div>
      <div class="balance-control-row balance-control-row--conversion">
        <Label.Root class="admin-field-label balance-conversion-direction-field">
          <span>{at("user_balance_conversion_direction", {}, "Direction")}</span>
          <AdminSelect
            value={conversionDirection}
            items={conversionDirections}
            ariaLabel={at("user_balance_conversion_direction", {}, "Direction")}
            disabled={userActionBusy || !partnerConvertible}
            onValueChange={selectConversionDirection}
          />
        </Label.Root>
        <Label.Root class="admin-field-label balance-amount-field">
          <span>{at("user_balance_amount", {}, "Amount")}</span>
          <div class="balance-amount-input-wrap">
            <Input
              class="input balance-amount-input"
              type="number"
              min={amountStep}
              max={conversionMaximumMinor / amountFactor}
              step={amountStep}
              inputmode="decimal"
              placeholder="0"
              bind:value={conversionAmount}
              disabled={userActionBusy || !partnerConvertible || conversionMaximumMinor <= 0}
            />
            <button
              type="button"
              class="balance-amount-max"
              onclick={useMaximumConversionAmount}
              disabled={userActionBusy || !partnerConvertible || conversionMaximumMinor <= 0}
              title={at("user_balance_max", {}, "Maximum")}
              aria-label={at("user_balance_max_aria", {}, "Use maximum available balance")}
            >
              {at("user_balance_max", {}, "Max")}
            </button>
          </div>
        </Label.Root>
        <Label.Root class="admin-field-label balance-reason-field">
          <span>{at("user_balance_reason", {}, "Reason / comment")}</span>
          <Input
            class="input"
            placeholder={at("user_balance_reason_placeholder", {}, "Optional audit note")}
            bind:value={conversionReason}
            disabled={userActionBusy || !partnerConvertible}
          />
        </Label.Root>
        <AdminButton
          class="balance-operation-submit"
          variant="default"
          onclick={submitConversion}
          disabled={userActionBusy || !conversionValid || !partnerConvertible}
        >
          <ArrowDownUp size={14} />
          {at("user_balance_conversion_submit", {}, "Convert")}
        </AdminButton>
      </div>
      {#if !partnerConvertible}
        <small class="balance-operation-unavailable">
          {at(
            "user_balance_conversion_unavailable",
            {},
            "An active partner profile is required for conversion."
          )}
        </small>
      {/if}
    </div>

    <div class="balance-history">
      <div class="balance-history-head">
        <strong>{at("user_balance_history_title", {}, "Recent operations")}</strong>
        <span>{balance?.history?.length || 0}</span>
      </div>
      {#if balance?.history?.length}
        <div class="balance-history-list">
          {#each balance.history as entry (`${entry.source_id || "user"}:${entry.entry_id}`)}
            <div class="balance-history-row">
              <div>
                <div class="balance-history-title">
                  <strong>{historyKind(entry.kind)}</strong>
                  <AdminBadge variant="muted">{historySource(entry.source_id)}</AdminBadge>
                </div>
                <small>{entry.reason || entry.reference_type || "—"}</small>
              </div>
              <div
                class="balance-history-value"
                class:is-negative={Number(entry.amount_minor || 0) < 0}
              >
                <strong
                  >{Number(entry.amount_minor || 0) > 0 ? "+" : ""}{formatMoney(
                    entry.amount_minor,
                    balance.currency
                  )}</strong
                >
                <time datetime={entry.created_at || undefined}
                  >{entry.created_at ? new Date(entry.created_at).toLocaleString() : "—"}</time
                >
              </div>
            </div>
          {/each}
        </div>
      {:else}
        <p class="balance-history-empty">
          {at("user_balance_history_empty", {}, "No operations yet")}
        </p>
      {/if}
    </div>
  </div>
</section>

<style>
  .balance-card-body,
  .balance-section-block,
  .balance-history,
  .balance-history-list {
    display: grid;
    gap: 12px;
  }
  .balance-card-body {
    container-name: balance-card;
    container-type: inline-size;
  }
  .admin-user-action-sheet--balance :global(.admin-dashboard-section-head) {
    display: grid;
    align-items: start;
    justify-content: stretch;
    gap: 4px;
  }
  .admin-user-action-sheet--balance :global(.admin-dashboard-section-head small) {
    min-width: 0;
    line-height: 1.4;
    overflow-wrap: anywhere;
  }
  .balance-summary-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }
  .balance-section-block,
  .balance-summary-tile,
  .balance-history {
    min-width: 0;
    padding: 12px;
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    background: color-mix(in srgb, var(--admin-surface-2) 88%, var(--admin-surface-1));
  }
  .balance-summary-tile {
    width: 100%;
    appearance: none;
    background: color-mix(in srgb, var(--admin-surface-1) 82%, transparent);
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
    transition:
      border-color 0.16s ease,
      background-color 0.16s ease;
  }
  .balance-summary-tile:hover:not(:disabled) {
    border-color: color-mix(in srgb, var(--accent) 32%, var(--admin-border));
    background: color-mix(in srgb, var(--accent) 4%, var(--admin-surface-1));
  }
  .balance-summary-tile:focus-visible {
    outline: none;
    box-shadow: 0 0 0 2px var(--admin-ring);
  }
  .balance-summary-tile:disabled {
    cursor: not-allowed;
    opacity: 0.62;
  }
  .balance-summary-tile.is-selected {
    border-color: color-mix(in srgb, var(--accent) 48%, var(--admin-border));
    background: color-mix(in srgb, var(--accent) 7%, var(--admin-surface-1));
  }
  .balance-block-heading,
  .balance-history-title {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .balance-block-heading {
    justify-content: space-between;
  }
  .balance-block-heading > strong,
  .balance-history-head > strong {
    font-size: 13px;
  }
  .balance-block-heading > small {
    min-width: 0;
    color: var(--admin-muted);
    font-size: 11px;
    text-align: right;
    overflow-wrap: anywhere;
  }
  .balance-summary-tile {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 10px;
  }
  .balance-summary-tile > span {
    width: 100%;
    color: var(--admin-muted);
    font-size: 12px;
  }
  .balance-summary-tile > strong {
    font-size: 20px;
    letter-spacing: -0.02em;
  }
  .balance-summary-tile small {
    color: var(--admin-muted);
  }
  .balance-control-row {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: end;
    gap: 12px;
    min-width: 0;
  }
  .balance-control-row--adjustment :global(.balance-operation-submit) {
    grid-column: 2;
  }
  .balance-control-row :global(.admin-field-label) {
    align-self: stretch;
  }
  .admin-user-action-sheet--balance .balance-control-row :global(.admin-select-trigger),
  .admin-user-action-sheet--balance .balance-control-row :global(.input),
  .admin-user-action-sheet--balance .balance-control-row :global(.balance-operation-submit) {
    height: 36px;
    min-height: 36px;
  }
  .balance-control-row :global(.balance-operation-submit) {
    width: 100%;
    white-space: nowrap;
  }
  .balance-amount-input-wrap {
    position: relative;
    min-width: 0;
  }
  .balance-amount-input-wrap :global(.balance-amount-input) {
    width: 100%;
    padding-right: 58px;
  }
  .balance-amount-max {
    position: absolute;
    top: 50%;
    right: 6px;
    min-width: 44px;
    height: 28px;
    padding: 0 8px;
    border: 0;
    border-radius: 7px;
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    color: var(--accent);
    font: inherit;
    font-size: 11px;
    font-weight: 750;
    cursor: pointer;
    transform: translateY(-50%);
  }
  .balance-amount-max:hover:not(:disabled),
  .balance-amount-max:focus-visible {
    background: color-mix(in srgb, var(--accent) 20%, transparent);
    outline: none;
  }
  .balance-amount-max:focus-visible {
    box-shadow: 0 0 0 2px var(--admin-ring);
  }
  .balance-amount-max:disabled {
    cursor: default;
    opacity: 0.45;
  }
  .balance-history-head,
  .balance-history-row,
  .balance-history-value {
    display: flex;
    align-items: center;
  }
  .balance-history-head,
  .balance-history-row {
    justify-content: space-between;
    gap: 12px;
  }
  .balance-history-head > span {
    color: var(--admin-muted);
    font-size: 12px;
  }
  .balance-history-row {
    padding-top: 10px;
    border-top: 1px solid var(--admin-border);
  }
  .balance-history-row > div:first-child,
  .balance-history-value {
    display: grid;
    gap: 3px;
    min-width: 0;
  }
  .balance-history-title {
    flex-wrap: wrap;
  }
  .balance-history-title :global(.admin-badge) {
    font-size: 9px;
  }
  .balance-history-row small,
  .balance-history-row time,
  .balance-history-empty {
    color: var(--admin-muted);
    font-size: 11px;
  }
  .balance-operation-unavailable {
    color: var(--warning);
    font-size: 11px;
    line-height: 1.35;
  }
  .balance-history-value {
    flex: 0 0 auto;
    text-align: right;
    color: var(--success);
  }
  .balance-history-value.is-negative {
    color: var(--danger);
  }
  .balance-history-value time {
    color: var(--admin-muted);
  }
  .balance-history-empty {
    margin: 0;
  }
  @container balance-card (max-width: 560px) {
    .balance-summary-grid,
    .balance-control-row--adjustment,
    .balance-control-row--conversion {
      grid-template-columns: minmax(0, 1fr);
    }
    .balance-control-row--adjustment :global(.balance-operation-submit) {
      grid-column: auto;
    }
    .balance-block-heading {
      align-items: flex-start;
      flex-direction: column;
    }
    .balance-block-heading > small {
      text-align: left;
    }
    .balance-history-row {
      align-items: flex-start;
    }
  }
</style>
