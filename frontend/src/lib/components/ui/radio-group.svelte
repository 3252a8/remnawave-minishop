<script lang="ts">
  import { RadioGroup as RadioGroupPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = RadioGroupPrimitive.RootProps & {
    onValueChange?: (value: string) => void;
  };

  let {
    value = $bindable(""),
    orientation = "vertical",
    name = "",
    disabled = false,
    onValueChange = () => {},
    class: className = "",
    children,
    ...rest
  }: Props = $props();

  const fallbackName = `ui-radio-group-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
  const groupName = $derived(name || fallbackName);

  function handleValueChange(next: string): void {
    value = next;
    onValueChange(next);
  }
</script>

<RadioGroupPrimitive.Root
  class={cn("ui-radio-group", className)}
  {value}
  {orientation}
  name={groupName}
  {disabled}
  onValueChange={handleValueChange}
  {...rest}
>
  {@render children?.()}
</RadioGroupPrimitive.Root>

<style>
  :global(.ui-radio-group) {
    display: grid;
    gap: 8px;
  }
</style>
