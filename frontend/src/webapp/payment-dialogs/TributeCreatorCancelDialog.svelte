<script lang="ts">
  import { TriangleAlert } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import type { Translate, VoidAction } from "$lib/webapp/types.js";

  let {
    step = 0,
    busy = false,
    onClose = () => {},
    onOpenTribute = () => {},
    onAlreadyCancelled = () => {},
    onConfirm = () => {},
    onBack = () => {},
    t = (key) => key,
  }: {
    step?: 0 | 1 | 2;
    busy?: boolean;
    onClose?: VoidAction;
    onOpenTribute?: VoidAction;
    onAlreadyCancelled?: VoidAction;
    onConfirm?: VoidAction;
    onBack?: VoidAction;
    t?: Translate;
  } = $props();
</script>

{#snippet titleIcon()}
  <TriangleAlert size={23} />
{/snippet}

<Dialog
  open={step !== 0}
  title={t(step === 2 ? "wa_tribute_creator_confirm_title" : "wa_tribute_creator_cancel_title")}
  description={t(step === 2 ? "wa_tribute_creator_confirm_desc" : "wa_tribute_creator_cancel_desc")}
  closeLabel={t("wa_close")}
  onclose={onClose}
  class="payment-dialog-card webapp-tribute-creator-cancel-dialog"
  showCloseButton={false}
  {titleIcon}
>
  <div class="payment-dialog-body">
    {#if step === 1}
      <Button class="wide" onclick={onOpenTribute} disabled={busy}>
        {t("wa_tribute_creator_open")}
      </Button>
      <Button variant="outline" class="wide" onclick={onAlreadyCancelled} disabled={busy}>
        {t("wa_tribute_creator_already_cancelled")}
      </Button>
    {:else if step === 2}
      <Button class="wide" onclick={onConfirm} disabled={busy}>
        {t("wa_tribute_creator_confirm")}
      </Button>
      <Button variant="outline" class="wide" onclick={onBack} disabled={busy}>
        {t("wa_back")}
      </Button>
    {/if}
    <Button variant="secondary" class="wide" onclick={onClose} disabled={busy}>
      {t("wa_cancel")}
    </Button>
  </div>
</Dialog>
