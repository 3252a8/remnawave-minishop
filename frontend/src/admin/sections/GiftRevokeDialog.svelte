<script lang="ts">
  import { Checkbox, Textarea } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminButton, AdminField } from "$components/patterns/admin/index.js";
  import type { components } from "$lib/api/openapi.generated.js";
  import { giftRefundWarningKey } from "$lib/admin/giftRevoke.js";
  import { isReversalReasonValid } from "$lib/admin/reversalReason.js";
  import { buildAdminGiftRevokePath, unwrap, type ApiClient } from "$lib/webapp/publicApi.js";

  type AdminGift = components["schemas"]["AdminGiftView"];
  let {
    api,
    at,
    gift,
    fmtMoney,
    onclose,
    onrevoked,
  }: {
    api: ApiClient["api"];
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
    gift: AdminGift;
    fmtMoney: (amount: number, currency?: string | null) => string;
    onclose: () => void;
    onrevoked: (gift: AdminGift) => void;
  } = $props();
  let reason = $state("");
  let withoutReason = $state(false);
  let refundToBalance = $state(true);
  let busy = $state(false);
  let failed = $state(false);

  async function revoke(): Promise<void> {
    const normalizedReason = reason.trim();
    if (busy || !isReversalReasonValid(normalizedReason, withoutReason)) return;
    busy = true;
    failed = false;
    try {
      const result = unwrap(
        await api(buildAdminGiftRevokePath(gift.gift_id), {
          method: "POST",
          body: JSON.stringify({
            reason: normalizedReason,
            without_reason: withoutReason,
            restore_promo_usage: true,
            refund_to_balance: refundToBalance,
          }),
        })
      );
      if (!("gift" in result)) throw new Error("Invalid gift revoke response");
      onrevoked(result.gift);
    } catch {
      failed = true;
    } finally {
      busy = false;
    }
  }
</script>

<Dialog
  open
  title={at("gifts_revoke_title", { id: gift.gift_id })}
  closeLabel={at("close")}
  onclose={() => {
    if (!busy) onclose();
  }}
  class="admin-dialog admin-dialog-compact"
>
  <div class="admin-form gift-revoke-form">
    <p>{at("gifts_revoke_confirm", { amount: fmtMoney(gift.total_amount, gift.currency) })}</p>
    <label class="gift-revoke-check">
      <Checkbox bind:checked={refundToBalance} ariaLabel={at("gifts_revoke_refund_label")} />
      {at("gifts_revoke_refund_label")}
    </label>
    {#if refundToBalance}
      <p class="gift-revoke-warning">{at(giftRefundWarningKey(gift.balance_enabled))}</p>
    {/if}
    <AdminField label={at("gifts_revoke_reason")}>
      <Textarea bind:value={reason} rows={3} maxlength={500} />
    </AdminField>
    <label class="gift-revoke-check">
      <Checkbox bind:checked={withoutReason} ariaLabel={at("gifts_revoke_without_reason")} />
      {at("gifts_revoke_without_reason")}
    </label>
    {#if failed}<p role="alert">{at("gifts_revoke_failed")}</p>{/if}
    <div class="admin-dialog-actions">
      <AdminButton disabled={busy} onclick={onclose}>{at("cancel")}</AdminButton>
      <AdminButton
        variant="danger"
        disabled={busy || !isReversalReasonValid(reason, withoutReason)}
        onclick={revoke}
      >
        {at(busy ? "gifts_revoking" : "gifts_revoke_confirm_action")}
      </AdminButton>
    </div>
  </div>
</Dialog>

<style>
  .gift-revoke-form {
    display: grid;
    gap: 14px;
  }
  .gift-revoke-check {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .gift-revoke-warning {
    margin: 0;
    color: var(--muted);
    font-size: 13px;
  }
</style>
