<script lang="ts">
  import type { Component } from "svelte";
  import * as Icons from "$components/ui/icons.js";
  import { Tooltip } from "$components/ui/primitives.js";
  import { TELEGRAM_STARS_MINI_APP_REQUIRED } from "$lib/webapp/tariffs.js";
  import type { PaymentMethod, StringAction, Translate } from "$lib/webapp/types.js";

  type IconComponent = Component<{ size?: number | string }>;
  const iconRegistry: Record<string, unknown> = Icons;
  const LockIcon = Icons.LockKeyhole as unknown as IconComponent;

  let {
    methods = [],
    selectedMethod = "",
    t = (key) => key,
    onSelect = () => {},
  }: {
    methods?: PaymentMethod[];
    selectedMethod?: string;
    t?: Translate;
    onSelect?: StringAction;
  } = $props();

  function methodId(method: PaymentMethod): string {
    return String(method?.id || "");
  }

  function methodTitle(method: PaymentMethod) {
    return typeof method?.name === "string" && method.name
      ? method.name
      : t("wa_method_other_title");
  }

  function methodIcon(method: PaymentMethod): IconComponent | null {
    const iconName = String(method?.icon || "").trim();
    const icon = iconName ? iconRegistry[iconName] : null;
    return typeof icon === "function" ? (icon as IconComponent) : null;
  }

  function disabledTitle(method: PaymentMethod) {
    if (!method?.disabled) return "";
    if (method.disabled_reason === TELEGRAM_STARS_MINI_APP_REQUIRED) {
      return t(
        "wa_payment_stars_telegram_required",
        {},
        "Open Minishop from the bot in Telegram to pay with Stars"
      );
    }
    if (!method?.min_amount || !method?.min_currency) return "";
    return `Minimum ${method.min_amount} ${method.min_currency}`;
  }

  function requiresTelegramMiniApp(method: PaymentMethod) {
    return method.disabled_reason === TELEGRAM_STARS_MINI_APP_REQUIRED;
  }
</script>

<div
  class:method-grid-single={methods.length === 1}
  class:method-grid-many={methods.length > 2}
  class="method-grid"
>
  {#each methods as method}
    {@const Icon = methodIcon(method)}
    {@const id = methodId(method)}
    {@const disabledMessage = disabledTitle(method)}
    {#if method.disabled && disabledMessage}
      <Tooltip.Root>
        <Tooltip.Trigger
          aria-disabled="true"
          aria-label={`${methodTitle(method)}: ${disabledMessage}`}
          class={`method-card disabled${selectedMethod === id ? " active" : ""}`}
          type="button"
          onclick={(event) => event.preventDefault()}
        >
          <span class="method-card-main">
            {#if Icon}
              <Icon size={19} />
            {/if}
            <strong>{methodTitle(method)}</strong>
            {#if requiresTelegramMiniApp(method)}
              <LockIcon size={16} />
            {/if}
          </span>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content class="payment-method-tooltip" side="top">
            {disabledMessage}
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    {:else}
      <button
        class:active={selectedMethod === id}
        class:disabled={method.disabled}
        class="method-card"
        disabled={method.disabled}
        type="button"
        onclick={() => !method.disabled && onSelect(id)}
      >
        <span class="method-card-main">
          {#if Icon}
            <Icon size={19} />
          {/if}
          <strong>{methodTitle(method)}</strong>
        </span>
      </button>
    {/if}
  {/each}
</div>
