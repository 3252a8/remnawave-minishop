<script lang="ts">
  import type { Component } from "svelte";
  import { Check, ChevronsUpDown, LockKeyhole } from "$components/ui/icons.js";
  import * as Icons from "$components/ui/icons.js";
  import { Select, Tooltip } from "$components/ui/primitives.js";
  import { formatMoney } from "$lib/webapp/formatters.js";
  import { paymentMethodMinimum, TELEGRAM_STARS_MINI_APP_REQUIRED } from "$lib/webapp/tariffs.js";
  import type { PaymentMethod, StringAction, Translate } from "$lib/webapp/types.js";
  import PaymentMethodGrid from "./PaymentMethodGrid.svelte";

  type IconComponent = Component<{ size?: number | string; class?: string }>;
  const iconRegistry: Record<string, unknown> = Icons;

  let {
    methods = [],
    selectedMethod = "",
    mode = "dropdown",
    disabled = false,
    t = (key) => key,
    onSelect = () => {},
  }: {
    methods?: PaymentMethod[];
    selectedMethod?: string;
    mode?: "dropdown" | "buttons" | string;
    disabled?: boolean;
    t?: Translate;
    onSelect?: StringAction;
  } = $props();

  let openDisabledTooltipMethod = $state("");

  const selected = $derived(
    methods.find((method) => String(method.id || "") === String(selectedMethod || ""))
  );
  const SelectedIcon = $derived(methodIcon(selected));

  function methodTitle(method: PaymentMethod | undefined): string {
    return typeof method?.name === "string" && method.name
      ? method.name
      : t("wa_method_other_title");
  }

  function methodIcon(method: PaymentMethod | undefined): IconComponent | null {
    const iconName = String(method?.icon || "").trim();
    const icon = iconName ? iconRegistry[iconName] : null;
    return typeof icon === "function" ? (icon as IconComponent) : null;
  }

  function disabledTitle(method: PaymentMethod): string {
    if (!method.disabled) return "";
    if (method.disabled_reason === TELEGRAM_STARS_MINI_APP_REQUIRED) {
      return t(
        "wa_payment_stars_telegram_required",
        {},
        "Open Minishop from the bot in Telegram to pay with Stars"
      );
    }
    const minimum = paymentMethodMinimum(method);
    if (!minimum) return "";
    const amount = minimum.text || formatMoney(minimum.amount, minimum.currency);
    return t("wa_payment_method_minimum", { amount }, `Minimum payment amount: ${amount}`);
  }

  function methodId(method: PaymentMethod): string {
    return String(method.id || "");
  }

  function handleDisabledTooltipOpenChange(method: PaymentMethod, open: boolean): void {
    const id = methodId(method);
    if (open) {
      openDisabledTooltipMethod = id;
    } else if (openDisabledTooltipMethod === id) {
      openDisabledTooltipMethod = "";
    }
  }

  function showDisabledTooltip(event: Event, method: PaymentMethod): void {
    event.preventDefault();
    event.stopPropagation();
    openDisabledTooltipMethod = methodId(method);
  }

  function handleDisabledTooltipKeydown(event: KeyboardEvent, method: PaymentMethod): void {
    if (event.key !== "Enter" && event.key !== " ") return;
    showDisabledTooltip(event, method);
  }
</script>

{#if mode === "buttons"}
  <PaymentMethodGrid {methods} {selectedMethod} {disabled} {t} {onSelect} />
{:else}
  <div class="payment-method-picker">
    <span class="payment-method-picker-label">{t("wa_payment_method", {}, "Payment method")}</span>
    <Select.Root
      type="single"
      {disabled}
      value={selectedMethod}
      items={methods.map((method) => ({
        value: methodId(method),
        label: methodTitle(method),
        disabled: Boolean(method.disabled),
      }))}
      onValueChange={onSelect}
      onOpenChange={(open) => {
        if (!open) openDisabledTooltipMethod = "";
      }}
    >
      <Select.Trigger
        class="payment-method-select-trigger"
        aria-label={t("wa_payment_method", {}, "Payment method")}
      >
        {#if SelectedIcon}
          <SelectedIcon size={16} class="payment-method-select-provider-icon" />
        {/if}
        <span>{methodTitle(selected)}</span>
        <ChevronsUpDown size={16} />
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          class="payment-method-select-content"
          side="bottom"
          align="start"
          sideOffset={6}
          collisionPadding={12}
        >
          <Select.Viewport class="payment-method-select-viewport">
            {#each methods as method (String(method.id || ""))}
              {@const disabledMessage = disabledTitle(method)}
              {@const MethodIcon = methodIcon(method)}
              {#if disabledMessage}
                <Tooltip.Root
                  open={openDisabledTooltipMethod === methodId(method)}
                  onOpenChange={(open) => handleDisabledTooltipOpenChange(method, open)}
                  delayDuration={180}
                  disableCloseOnTriggerClick
                >
                  <Tooltip.Trigger>
                    {#snippet child({ props })}
                      <div
                        {...props}
                        role="button"
                        tabindex="0"
                        aria-label={`${methodTitle(method)}: ${disabledMessage}`}
                        class="payment-method-disabled-tooltip-trigger"
                        onpointerup={(event) => showDisabledTooltip(event, method)}
                        onclick={(event) => showDisabledTooltip(event, method)}
                        onkeydown={(event) => handleDisabledTooltipKeydown(event, method)}
                      >
                        <Select.Item
                          value={methodId(method)}
                          label={methodTitle(method)}
                          disabled
                          aria-hidden="true"
                          class="payment-method-select-item"
                        >
                          {#if MethodIcon}
                            <MethodIcon size={16} class="payment-method-select-provider-icon" />
                          {/if}
                          <span>{methodTitle(method)}</span>
                          <LockKeyhole size={14} />
                        </Select.Item>
                      </div>
                    {/snippet}
                  </Tooltip.Trigger>
                  <Tooltip.Portal>
                    <Tooltip.Content class="payment-method-tooltip" side="top">
                      {disabledMessage}
                    </Tooltip.Content>
                  </Tooltip.Portal>
                </Tooltip.Root>
              {:else}
                <Select.Item
                  value={methodId(method)}
                  label={methodTitle(method)}
                  disabled={Boolean(method.disabled)}
                  class="payment-method-select-item"
                >
                  {#if MethodIcon}
                    <MethodIcon size={16} class="payment-method-select-provider-icon" />
                  {/if}
                  <span>{methodTitle(method)}</span>
                  {#if method.disabled}
                    <LockKeyhole size={14} />
                  {:else}
                    <Check size={15} class="payment-method-select-check" />
                  {/if}
                </Select.Item>
              {/if}
            {/each}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  </div>
{/if}
