<script>
  import { cva } from "class-variance-authority";
  import { cn } from "$lib/utils.js";

  export let type = "button";
  export let variant = "default";
  export let size = "default";
  export let disabled = false;
  export let onclick = undefined;

  let className = "";
  export { className as class };

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
  class={cn(buttonVariants({ variant, size }), className)}
  {type}
  {disabled}
  onclick={onclick}
  {...$$restProps}
>
  <slot />
</button>
