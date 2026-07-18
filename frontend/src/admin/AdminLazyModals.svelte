<script lang="ts">
  import { getPaymentsStore, getTariffsStore, getUsersStore } from "$lib/admin/context";
  import { loadDynamicComponent, type DynamicComponent } from "./adminLazyComponents";
  import type { AdminUser } from "$lib/admin/stores/usersStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type BadgeVariant = "success" | "danger" | "warning" | "muted";

  let {
    at,
    fmtDate,
    fmtDateShort,
    fmtMoney,
    openTelegramProfileLink,
    paymentStatusVariant,
    resolvedAvatarUrl,
    trafficLeftLabel,
    trafficOfLabel,
    trafficPercentValue,
    userDisplayName,
    userInitials,
    userSecondaryName,
    userTelegramProfileLink,
    userTelegramProfileLinkKind,
    onCloseUser,
    onOpenPaymentUserCard,
    routePrefix,
  }: {
    at: TranslateFn;
    fmtDate: (value: unknown) => string;
    fmtDateShort: (value: unknown) => string;
    fmtMoney: (value: unknown, currency?: string | null) => string;
    openTelegramProfileLink: (url: string) => boolean;
    paymentStatusVariant: (status: unknown) => BadgeVariant;
    resolvedAvatarUrl: (user: AdminUser) => string;
    trafficLeftLabel: (used: unknown, limit: unknown) => string;
    trafficOfLabel: (used: unknown, limit: unknown) => string;
    trafficPercentValue: (used: unknown, limit: unknown) => number;
    userDisplayName: (user: AdminUser) => string;
    userInitials: (user: AdminUser) => string;
    userSecondaryName: (user: AdminUser) => string;
    userTelegramProfileLink: (user: AdminUser) => string;
    userTelegramProfileLinkKind: (user: AdminUser) => string;
    onCloseUser: () => void;
    onOpenPaymentUserCard: (userId: unknown) => void;
    routePrefix: string;
  } = $props();

  const tariffsStore = getTariffsStore();
  const paymentsStore = getPaymentsStore();
  const usersStore = getUsersStore();

  let TariffEditorModalComponent = $state<DynamicComponent | null>(null);
  let PaymentDetailModalComponent = $state<DynamicComponent | null>(null);
  let UserDetailModalComponent = $state<DynamicComponent | null>(null);

  const tariffEditorModalOpen = $derived(
    Boolean(tariffsStore.tariffEditorOpen || tariffsStore.tariffDeleteOpen)
  );
  const paymentDetailModalOpen = $derived(Boolean(paymentsStore.openedPaymentId));
  const userDetailModalOpen = $derived(Boolean(usersStore.openedUser));

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

  $effect(() => {
    if (userDetailModalOpen) {
      loadDynamicComponent(
        UserDetailModalComponent,
        () => import("./sections/UserDetailModal.svelte"),
        (component) => (UserDetailModalComponent = component)
      );
    }
  });
</script>

{#if TariffEditorModalComponent}
  <TariffEditorModalComponent {at} />
{/if}

{#if PaymentDetailModalComponent}
  <PaymentDetailModalComponent
    {at}
    {fmtDate}
    {fmtMoney}
    {paymentStatusVariant}
    onOpenUserCard={onOpenPaymentUserCard}
  />
{/if}

{#if UserDetailModalComponent}
  <UserDetailModalComponent
    {at}
    {fmtDate}
    {fmtDateShort}
    {fmtMoney}
    {resolvedAvatarUrl}
    {userDisplayName}
    {userSecondaryName}
    {userInitials}
    {userTelegramProfileLink}
    {userTelegramProfileLinkKind}
    {openTelegramProfileLink}
    {paymentStatusVariant}
    {trafficPercentValue}
    {trafficLeftLabel}
    {trafficOfLabel}
    {routePrefix}
    onClose={onCloseUser}
  />
{/if}
