<script lang="ts">
  import { cn } from "$lib/utils.js";
  import type { Snippet } from "svelte";
  import type { HTMLAttributes } from "svelte/elements";

  type Props = Omit<HTMLAttributes<HTMLDivElement>, "children" | "class"> & {
    children?: Snippet;
    class?: string;
    columns?: number;
  };

  let { columns = 1, class: className = "", children, ...restProps }: Props = $props();
</script>

<div
  class={cn(
    "admin-cn-dashboard-grid",
    columns === 3 && "admin-cn-dashboard-grid--3",
    columns === 4 && "admin-cn-dashboard-grid--4",
    className
  )}
  {...restProps}
>
  {@render children?.()}
</div>
