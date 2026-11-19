<script lang="ts">
  import { Badge } from "$components/ui/index.js";

  let {
    status,
    t,
  }: {
    status?: string;
    t: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  } = $props();

  const state = $derived(
    status === "closed" || status === "resolved"
      ? { tone: "closed", label: t("wa_support_status_closed") }
      : status === "awaiting_user"
        ? { tone: "awaiting_user", label: t("wa_support_status_replied", {}, "Support replied") }
        : { tone: "open", label: t("wa_support_status_waiting", {}, "Waiting for support") }
  );
</script>

<Badge variant="outline" wrap class={`ticket-status-badge ticket-status-badge--${state.tone}`}>
  {state.label}
</Badge>
