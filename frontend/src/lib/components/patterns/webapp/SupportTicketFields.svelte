<script lang="ts">
  import { Button } from "$components/ui";
  import { Check, ChevronDown } from "$components/ui/icons";
  import { Select } from "$components/ui/primitives";
  import type { PostPayload } from "$lib/webapp/publicApi";
  import type { SupportPayment } from "$lib/webapp/stores/supportStore.svelte";

  type Category = NonNullable<PostPayload<"/api/support/tickets">["category"]>;
  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  let {
    category = $bindable<Category>("other"),
    paymentId = $bindable(""),
    disabled = false,
    t,
    loadPayments,
  }: {
    category?: Category;
    paymentId?: string;
    disabled?: boolean;
    t: Translate;
    loadPayments: () => Promise<SupportPayment[]>;
  } = $props();

  let payments = $state<SupportPayment[]>([]);
  let loading = $state(false);
  let failed = $state(false);
  let attempt = $state(0);
  const categories = $derived(
    (["other", "billing", "technical", "account"] as const).map((value) => ({
      value,
      label: t(`wa_support_category_${value}`),
    }))
  );
  const paymentItems = $derived([
    { value: "none", label: t("wa_support_payment_none") },
    ...payments.map((payment) => ({
      value: String(payment.payment_id),
      label: `#${payment.payment_id} · ${payment.amount} ${payment.currency || ""} · ${payment.provider || "—"} · ${payment.created_at?.slice(0, 10) || "—"} · ${t(`wa_payment_history_state_${payment.history_state}`)}`,
    })),
  ]);

  $effect(() => {
    if (category !== "billing") {
      paymentId = "";
      return;
    }
    void attempt;
    let active = true;
    loading = true;
    failed = false;
    loadPayments()
      .then((items) => {
        if (!active) return;
        payments = items;
        if (!items.some((item) => String(item.payment_id) === paymentId)) paymentId = "";
      })
      .catch(() => {
        if (active) {
          failed = true;
          payments = [];
          paymentId = "";
        }
      })
      .finally(() => {
        if (active) loading = false;
      });
    return () => {
      active = false;
    };
  });
</script>

{#snippet field(
  label: string,
  value: string,
  items: { value: string; label: string }[],
  change: (value: string) => void,
  busy = false
)}
  <div class="support-choice-field">
    <span>{label}</span>
    <Select.Root type="single" {value} {items} disabled={disabled || busy} onValueChange={change}>
      <Select.Trigger class="input support-choice-trigger" aria-label={label}>
        <span>{items.find((item) => item.value === value)?.label}</span>
        <ChevronDown size={16} />
      </Select.Trigger>
      <Select.Portal>
        <Select.Content class="support-choice-content" sideOffset={6} collisionPadding={12}>
          <Select.Viewport>
            {#each items as item (item.value)}
              <Select.Item class="support-choice-item" value={item.value} label={item.label}>
                <span>{item.label}</span>
                {#if item.value === value}<Check size={16} />{/if}
              </Select.Item>
            {/each}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  </div>
{/snippet}

<div class="support-ticket-fields">
  {@render field(t("wa_support_category"), category, categories, (value) => {
    category = value as Category;
  })}
  {#if category === "billing"}
    <div class="support-payment-field">
      {#if !loading && !failed && payments.length}
        {@render field(
          t("wa_support_payment_optional"),
          paymentId || "none",
          paymentItems,
          (value) => {
            paymentId = value === "none" ? "" : value;
          }
        )}
      {/if}
      <small role="status">
        {loading
          ? t("wa_loading")
          : failed
            ? t("wa_support_payments_failed")
            : payments.length
              ? t("wa_support_payment_hint")
              : t("wa_support_payments_empty")}
      </small>
      {#if failed}<Button variant="ghost" {disabled} onclick={() => attempt++}
          >{t("wa_support_payments_retry")}</Button
        >{/if}
    </div>
  {/if}
</div>

<style>
  .support-ticket-fields,
  .support-choice-field,
  .support-payment-field {
    display: grid;
    gap: 8px;
    min-width: 0;
  }
  .support-ticket-fields {
    gap: 14px;
  }
  .support-choice-field > span {
    font-size: 13px;
    color: var(--dim);
  }
  .support-payment-field small {
    color: var(--dim);
  }
  :global(.support-choice-trigger) {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    text-align: start;
  }
  :global(.support-choice-trigger > span) {
    min-width: 0;
    overflow-wrap: anywhere;
  }
  :global(.support-choice-trigger > svg) {
    flex-shrink: 0;
  }
  :global(.support-choice-content) {
    z-index: 100;
    width: var(--bits-select-anchor-width);
    max-width: calc(100vw - 24px);
    max-height: min(300px, var(--bits-select-content-available-height));
    overflow-y: auto;
    padding: 6px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--panel-2);
    color: var(--text);
  }
  :global(.support-choice-item) {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 10px;
    border-radius: 6px;
    overflow-wrap: anywhere;
    cursor: pointer;
  }
  :global(.support-choice-item[data-highlighted]) {
    background: color-mix(in srgb, var(--accent) 18%, transparent);
    outline: none;
  }
  :global(.support-choice-item > svg) {
    flex-shrink: 0;
  }
</style>
