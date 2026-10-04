<script lang="ts">
  import { cva } from "class-variance-authority";
  import { cn } from "$lib/utils.js";
  import { controlSizeClass, type ControlSize } from "$components/ui/controlSize";
  import type { Snippet } from "svelte";
  import type { HTMLButtonAttributes } from "svelte/elements";

  type AdminButtonVariant = "danger" | "dangerSoft" | "default" | "ghost" | "icon" | "primary";
  type AdminButtonSize = "default" | "icon" | "sm";
  type Props = Omit<
    HTMLButtonAttributes,
    "children" | "class" | "disabled" | "onclick" | "type"
  > & {
    children?: Snippet;
    class?: string;
    disabled?: boolean;
    onclick?: (event: MouseEvent) => void;
    size?: AdminButtonSize;
    controlSize?: ControlSize;
    type?: HTMLButtonAttributes["type"];
    variant?: AdminButtonVariant;
  };

  let {
    type = "button",
    variant = "default",
    size = "default",
    controlSize,
    disabled = false,
    onclick = undefined,
    class: className = "",
    children,
    ...restProps
  }: Props = $props();

  const buttonVariants = cva("admin-btn", {
    variants: {
      variant: {
        default: "",
        primary: "admin-btn-primary",
        ghost: "admin-btn-ghost",
        danger: "admin-btn-danger",
        dangerSoft: "admin-btn-danger-soft",
        icon: "admin-btn-icon",
      },
      size: {
        default: "",
        sm: "admin-btn-sm",
        icon: "admin-btn-icon",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  });
</script>

<button
  class={cn(buttonVariants({ variant, size }), controlSizeClass(controlSize), className)}
  data-control-size={controlSize}
  {type}
  {disabled}
  {onclick}
  {...restProps}
>
  {@render children?.()}
</button>
