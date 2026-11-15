<script lang="ts">
  import { Send } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import { AttentionDot } from "$components/ui/index.js";

  type Props = {
    startLink?: string;
    status?: string;
    onOpenBot?: () => void;
    t?: (key: string) => string;
  };

  let {
    startLink = "",
    status = "unknown",
    onOpenBot = () => {},
    t = (key) => key,
  }: Props = $props();

  const isBlocked = $derived(status === "blocked");
  const title = $derived(
    isBlocked
      ? t("wa_telegram_notifications_blocked_title")
      : t("wa_telegram_notifications_banner_title")
  );
  const description = $derived(
    isBlocked
      ? t("wa_telegram_notifications_blocked_text")
      : t("wa_telegram_notifications_banner_text")
  );
</script>

<Card class={`telegram-notifications-card attention-wrap${isBlocked ? " is-blocked" : ""}`}>
  {#if isBlocked}<AttentionDot class="telegram-notifications-dot" />{/if}
  <div class="telegram-notifications-icon">
    <Send size={20} />
  </div>
  <div class="telegram-notifications-copy">
    <strong>{title}</strong>
    <small>{description}</small>
  </div>
  <div class="telegram-notifications-actions">
    <Button
      variant="telegram"
      size="sm"
      class="telegram-notifications-primary"
      onclick={onOpenBot}
      data-start-link={startLink}
    >
      <Send size={15} />
      {t("wa_telegram_notifications_open_bot")}
    </Button>
  </div>
</Card>
