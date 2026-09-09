<script lang="ts">
  import { TriangleAlert } from "$components/ui/icons.js";

  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import type { Translate, VoidAction } from "$lib/webapp/types.js";

  let {
    subscriptionReissueDialogOpen = false,
    subscriptionReissueBusy = false,
    confirmSubscriptionReissue = () => {},
    closeSubscriptionReissueDialog = () => {},
    t = (key) => key,
  }: {
    subscriptionReissueDialogOpen?: boolean;
    subscriptionReissueBusy?: boolean;
    confirmSubscriptionReissue?: VoidAction;
    closeSubscriptionReissueDialog?: VoidAction;
    t?: Translate;
  } = $props();
</script>

{#snippet titleIcon()}
  <TriangleAlert size={23} />
{/snippet}

<Dialog
  open={subscriptionReissueDialogOpen}
  title={t("wa_subscription_reissue_title")}
  description={t("wa_subscription_reissue_warning")}
  closeLabel={t("wa_close")}
  onclose={closeSubscriptionReissueDialog}
  class="payment-dialog-card webapp-subscription-reissue-dialog"
  {titleIcon}
>
  <div class="payment-dialog-body">
    <Button
      data-webapp-action="confirm-subscription-reissue"
      variant="outline"
      class="wide device-danger-button"
      onclick={confirmSubscriptionReissue}
      disabled={subscriptionReissueBusy}
    >
      <TriangleAlert size={17} />
      {t("wa_subscription_reissue_confirm")}
    </Button>
    <Button
      variant="secondary"
      class="wide"
      onclick={closeSubscriptionReissueDialog}
      disabled={subscriptionReissueBusy}
    >
      {t("wa_cancel")}
    </Button>
  </div>
</Dialog>
