<script>
  import { cn } from "../../utils.js";

  export let type = "button";
  export let variant = "default";
  export let size = "default";
  export let disabled = false;
  export let href = "";
  export let onclick = undefined;
  let className = "";
  export { className as class };

  const variants = {
    default: "btn btn-primary",
    secondary: "btn btn-secondary",
    outline: "btn btn-outline",
    ghost: "btn btn-ghost",
    telegram: "btn btn-telegram",
    icon: "btn btn-icon",
  };

  const sizes = {
    default: "",
    sm: "btn-sm",
    lg: "btn-lg",
    icon: "btn-square",
  };
</script>

{#if href}
  <a class={cn(variants[variant], sizes[size], className)} {href} on:click={onclick} {...$$restProps}>
    <slot />
  </a>
{:else}
  <button class={cn(variants[variant], sizes[size], className)} {type} {disabled} on:click={onclick} {...$$restProps}>
    <slot />
  </button>
{/if}
