<script lang="ts">
  import { cva } from "class-variance-authority";
  import { cn } from "$lib/utils.js";
  import { controlSizeClass, type ControlSize } from "./controlSize";
  import type { Snippet } from "svelte";
  import type { HTMLAnchorAttributes, HTMLButtonAttributes } from "svelte/elements";

  type ButtonVariant = "default" | "ghost" | "icon" | "outline" | "secondary" | "telegram";
  type ButtonSize = "default" | "icon" | "icon-sm" | "lg" | "sm";
  type ClickHandler = ((event: MouseEvent) => void) | ((value?: string) => void) | (() => void);
  type Props = Omit<HTMLButtonAttributes, "children" | "class" | "disabled" | "onclick" | "type"> &
    Omit<HTMLAnchorAttributes, "children" | "class" | "href" | "onclick"> & {
      children?: Snippet;
      class?: string;
      disabled?: boolean;
      href?: string;
      onclick?: ClickHandler;
      size?: ButtonSize;
      controlSize?: ControlSize;
      type?: HTMLButtonAttributes["type"];
      variant?: ButtonVariant;
    };

  let {
    type = "button",
    variant = "default",
    size = "default",
    controlSize,
    disabled = false,
    href = "",
    onclick = undefined,
    class: className = "",
    children,
    ...rest
  }: Props = $props();

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
        "icon-sm": "btn-square-sm",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  });

  function forwardClick(event: MouseEvent) {
    (onclick as ((event: MouseEvent) => void) | undefined)?.(event);
  }
</script>

{#if href}
  <a
    class={cn(buttonVariants({ variant, size }), controlSizeClass(controlSize), className)}
    data-control-size={controlSize}
    {href}
    onclick={forwardClick}
    {...rest}
  >
    {@render children?.()}
  </a>
{:else}
  <button
    class={cn(buttonVariants({ variant, size }), controlSizeClass(controlSize), className)}
    data-control-size={controlSize}
    {type}
    {disabled}
    onclick={forwardClick}
    {...rest}
  >
    {@render children?.()}
  </button>
{/if}
