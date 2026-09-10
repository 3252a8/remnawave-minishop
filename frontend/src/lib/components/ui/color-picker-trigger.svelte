<script lang="ts">
  type Props = {
    labelElement?: HTMLLabelElement;
    hex: string | null;
    label: string;
    name?: string;
    dir: "ltr" | "rtl";
  };

  let { labelElement = $bindable(), hex, label, name = undefined, dir }: Props = $props();

  function preventNativePicker(event: MouseEvent): void {
    // The color picker library handles this event at window level.
    event.preventDefault();
  }

</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions, a11y_click_events_have_key_events -->
<label bind:this={labelElement} onmousedown={preventNativePicker} onclick={preventNativePicker} {dir}>
  <input
    type="color"
    {name}
    value={hex || "#000000"}
    aria-label={label}
    aria-haspopup="dialog"
    onmousedown={preventNativePicker}
    onclick={preventNativePicker}
  />
  <span class="color-picker-trigger-swatch" style={`background-color: ${hex || "#000000"}`}></span>
</label>

<style>
  label {
    display: grid;
    width: 100%;
    height: 100%;
    min-width: var(--input-size, 25px);
    min-height: var(--input-size, 25px);
    place-items: center;
    cursor: pointer;
  }

  input {
    position: absolute;
    width: 1px;
    height: 1px;
    opacity: 0;
  }

  .color-picker-trigger-swatch {
    width: var(--input-size, 25px);
    height: var(--input-size, 25px);
    border-radius: 50%;
  }

  input:focus-visible + .color-picker-trigger-swatch {
    outline: 2px solid var(--focus-color, var(--accent));
    outline-offset: 2px;
  }
</style>
