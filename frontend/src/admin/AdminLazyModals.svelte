<script lang="ts">
  import { getPaymentsStore, getTariffsStore } from "$lib/admin/context";
  import { loadDynamicComponent, type DynamicComponent } from "./adminLazyComponents";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type BadgeVariant = "success" | "danger" | "warning" | "muted";

  let {
    at,
    fmtDate,
    fmtMoney,
    paymentStatusVariant,
    onOpenPaymentUserCard,
    onOpenPaymentPromoCard,
    onOpenPartnerCard,
    routePrefix,
  }: {
    at: TranslateFn;
    fmtDate: (value: unknown) => string;
    fmtMoney: (value: unknown, currency?: string | null) => string;
    paymentStatusVariant: (status: unknown) => BadgeVariant;
    onOpenPaymentUserCard: (userId: unknown) => void;
    onOpenPaymentPromoCard: (promoId: number) => void;
    onOpenPartnerCard: (partnerId: string) => void;
    routePrefix: string;
  } = $props();

  const tariffsStore = getTariffsStore();
  const paymentsStore = getPaymentsStore();

  let TariffEditorModalComponent = $state<DynamicComponent | null>(null);
  let PaymentDetailModalComponent = $state<DynamicComponent | null>(null);

  const tariffEditorModalOpen = $derived(
    Boolean(tariffsStore.tariffEditorOpen || tariffsStore.tariffDeleteOpen)
  );
  const paymentDetailModalOpen = $derived(Boolean(paymentsStore.openedPaymentId));

  $effect(() => {
    if (tariffEditorModalOpen) {
      loadDynamicComponent(
        TariffEditorModalComponent,
        () => import("./sections/TariffEditorModal.svelte"),
        (component) => (TariffEditorModalComponent = component)
      );
    }
  });

  $effect(() => {
    if (paymentDetailModalOpen) {
      loadDynamicComponent(
        PaymentDetailModalComponent,
        () => import("./sections/PaymentDetailModal.svelte"),
        (component) => (PaymentDetailModalComponent = component)
      );
    }
  });
</script>

{#if TariffEditorModalComponent}
  <TariffEditorModalComponent {at} {routePrefix} />
{/if}

{#if PaymentDetailModalComponent}
  <PaymentDetailModalComponent
    {at}
    {fmtDate}
    {fmtMoney}
    {paymentStatusVariant}
    onOpenUserCard={onOpenPaymentUserCard}
    onOpenPromoCard={onOpenPaymentPromoCard}
    {onOpenPartnerCard}
  />
{/if}
