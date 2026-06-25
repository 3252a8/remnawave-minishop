<script>
  import { cva } from "class-variance-authority";
  import { cn } from "$lib/utils.js";

  let {
    type = "button",
    variant = "default",
    size = "default",
    disabled = false,
    href = "",
    onclick = undefined,
    class: className = "",
    children,
    ...rest
  } = $props();

  const buttonVariants = cva("btn", {
    variants: {
      variant: {
        default: "btn-primary",
        secondary: "btn-secondary",
        outline: "btn-outline",
        ghost: "btn-ghost",
        telegram: "btn-telegram",
        icon: "btn-icon",
      },
      size: {
        default: "",
        sm: "btn-sm",
        lg: "btn-lg",
        icon: "btn-square",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  });
</script>

{#if href}
  <a class={cn(buttonVariants({ variant, size }), className)} {href} {onclick} {...rest}>
    {@render children?.()}
  </a>
{:else}
  <button
    class={cn(buttonVariants({ variant, size }), className)}
    {type}
    {disabled}
    {onclick}
    {...rest}
  >
    {@render children?.()}
  </button>
{/if}
