<script lang="ts">
  import {
    Coins,
    CreditCard,
    FileText,
    History,
    TrendingUp,
    UserPlus,
    UsersRound,
    WalletCards,
  } from "$components/ui/icons.js";
  import { AdminKpiTile } from "$components/patterns/admin/index.js";
  import type { AdminPartnerDashboard } from "$lib/admin/partnerProgramApi.js";

  let {
    at,
    dashboard,
    money,
    empty,
  }: {
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
    dashboard: AdminPartnerDashboard | null;
    money: (value: number) => string;
    empty: boolean;
  } = $props();

  const dashboardMetrics: Array<{
    key: string;
    value: string;
    icon: typeof UsersRound;
    tone: "default" | "success" | "info" | "warning";
  }> = $derived([
    {
      key: "active",
      value: empty ? "0 / 0" : dashboard ? `${dashboard.active} / ${dashboard.paused}` : "18 / 2",
      icon: UsersRound,
      tone: "success",
    },
    {
      key: "clients",
      value: empty ? "0" : dashboard ? String(dashboard.clients) : "247",
      icon: UserPlus,
      tone: "info",
    },
    {
      key: "gross",
      value: money(empty ? 0 : (dashboard?.gross ?? 482700)),
      icon: TrendingUp,
      tone: "success",
    },
    {
      key: "commissions",
      value: money(empty ? 0 : (dashboard?.commissions ?? 144810)),
      icon: Coins,
      tone: "warning",
    },
    {
      key: "paid",
      value: money(empty ? 0 : (dashboard?.paid ?? 87300)),
      icon: WalletCards,
      tone: "default",
    },
    {
      key: "available",
      value: money(empty ? 0 : (dashboard?.available ?? 42840)),
      icon: CreditCard,
      tone: "info",
    },
    {
      key: "requested",
      value: money(empty ? 0 : (dashboard?.requested ?? 11700)),
      icon: History,
      tone: "warning",
    },
    {
      key: "hold",
      value: money(empty ? 0 : (dashboard?.hold ?? 9340)),
      icon: FileText,
      tone: "default",
    },
  ]);
</script>

<section
  class="partners-kpi-grid"
  aria-label={at("partners_kpi_title", {}, "Partner program summary")}
>
  {#each dashboardMetrics as metric (metric.key)}
    {@const MetricIcon = metric.icon}
    <AdminKpiTile
      label={at(`partners_kpi_${metric.key}`, {}, metric.key)}
      value={metric.value}
      tone={metric.tone}
    >
      {#snippet icon()}<MetricIcon size={14} />{/snippet}
    </AdminKpiTile>
  {/each}
</section>
