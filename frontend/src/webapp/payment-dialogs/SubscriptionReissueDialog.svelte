<script lang="ts">
  import { Mail, TriangleAlert } from "$components/ui/icons.js";

  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import type { Translate, VoidAction } from "$lib/webapp/types.js";

  let {
    subscriptionReissueDialogOpen = false,
    subscriptionReissueBusy = false,
    userEmail = "",
    confirmSubscriptionReissue = () => {},
    closeSubscriptionReissueDialog = () => {},
    openLinkEmailDialog = () => {},
    t = (key) => key,
  }: {
    subscriptionReissueDialogOpen?: boolean;
    subscriptionReissueBusy?: boolean;
    userEmail?: string;
    confirmSubscriptionReissue?: VoidAction;
    closeSubscriptionReissueDialog?: VoidAction;
    openLinkEmailDialog?: VoidAction;
    t?: Translate;
  } = $props();

  const hasEmail = $derived(Boolean(String(userEmail || "").trim()));

  function linkEmailInstead() {
    closeSubscriptionReissueDialog();
    openLinkEmailDialog();
  }
</script>

<Dialog
  open={subscriptionReissueDialogOpen}
  title={t("wa_subscription_reissue_title")}
  description={hasEmail
    ? t("wa_subscription_reissue_warning", { email: userEmail })
    : t("wa_subscription_reissue_email_required")}
  closeLabel={t("wa_close")}
  onclose={closeSubscriptionReissueDialog}
  class="payment-dialog-card webapp-subscription-reissue-dialog"
>
  <div class="payment-dialog-body">
    {#if hasEmail}
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
    {:else}
      <Button
        data-webapp-action="open-link-email"
        variant="secondary"
        class="wide"
        onclick={linkEmailInstead}
      >
        <Mail size={17} />
        {t("wa_settings_link_email_action")}
      </Button>
    {/if}
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
