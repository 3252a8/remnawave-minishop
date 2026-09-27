<script lang="ts">
  import { Checkbox } from "$components/ui/index.js";
  let {
    at,
    checked = false,
    onchange,
    disabled = false,
  }: {
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
    checked?: boolean;
    onchange: (checked: boolean) => void;
    disabled?: boolean;
  } = $props();
</script>

<div class="effects-consent">
  <strong>{at("theme_effects_title", {}, "JavaScript effects")}</strong>
  <p>
    {at(
      "theme_effects_warning",
      {},
      "This code can read page data and act as the visitor. Only allow code from a source you trust. You can install the theme without JavaScript."
    )}
  </p>
  <label>
    <Checkbox {checked} {disabled} onCheckedChange={onchange} />
    <span
      >{at(
        "theme_effects_accept",
        {},
        "I trust this source and allow this version of JavaScript for store visitors."
      )}</span
    >
  </label>
</div>

<style>
  .effects-consent {
    display: grid;
    gap: 0.65rem;
    overflow-wrap: anywhere;
  }
  p {
    margin: 0;
    font-size: 0.875rem;
    color: var(--admin-muted);
  }
  label {
    display: flex;
    align-items: flex-start;
    gap: 0.6rem;
    font-size: 0.875rem;
  }
</style>
