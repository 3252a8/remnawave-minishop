<script lang="ts">
  import Input from "$components/ui/input.svelte";

  type Props = {
    ariaLabel: string;
    code?: string;
    disabled?: boolean;
    oninput?: () => void;
  };

  let { ariaLabel, code = $bindable(""), disabled = false, oninput = () => {} }: Props = $props();

  function updateCode(event: Event): void {
    const input = event.currentTarget as HTMLInputElement;
    code = input.value.replace(/\D/g, "").slice(0, 6);
    oninput();
  }
</script>

<label class="otp-input-wrap">
  <Input
    value={code}
    inputmode="numeric"
    autocomplete="one-time-code"
    maxlength={6}
    aria-label={ariaLabel}
    {disabled}
    oninput={updateCode}
  />
  <span class="otp-slots" aria-hidden="true">
    {#each Array.from({ length: 6 }) as _, index}
      <span class:filled={code[index]}>{code[index] || ""}</span>
    {/each}
  </span>
</label>
