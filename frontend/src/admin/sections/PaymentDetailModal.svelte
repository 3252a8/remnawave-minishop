<script lang="ts">
  import { getPaymentsStore } from "$lib/admin/context";
  import {
    CalendarDays,
    Copy,
    CreditCard,
    Database,
    Tag,
    User,
    WalletCards,
  } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import type { AdminPayment } from "../../lib/admin/stores/paymentsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type MetaRow = {
    label: string;
    value: unknown;
    copy?: unknown;
  };

  let {
    at = (key, _params = {}, fallback = "") => fallback || key,
    fmtDate = (value) => String(value || ""),
    fmtMoney = (amount, currency) => `${amount} ${currency || ""}`.trim(),
    paymentStatusLabel = (status) => String(status || "—"),
    paymentStatusVariant = () => "muted",
    onOpenUserCard = () => {},
  }: {
    at?: TranslateFn;
    fmtDate?: (value: string | null | undefined) => string;
    fmtMoney?: (amount: unknown, currency?: string | null) => string;
    paymentStatusLabel?: (status: string | null | undefined) => string;
    paymentStatusVariant?: (status: string | null | undefined) => string;
    onOpenUserCard?: (userId: number) => void;
  } = $props();

  const paymentsStore = getPaymentsStore();
  const closePayment = (): void => paymentsStore.closePayment();
  const openedPaymentId = $derived(paymentsStore.openedPaymentId as number | null);
  const openedPayment = $derived(paymentsStore.openedPayment as AdminPayment | null);
  const paymentDetailLoading = $derived(Boolean(paymentsStore.paymentDetailLoading));
  const payment = $derived(
    (openedPayment ||
      (openedPaymentId ? { payment_id: openedPaymentId } : null)) as AdminPayment | null
  );
  const title = $derived(
    payment
      ? at("payment_detail_title", { id: payment.payment_id }, `支付 #${payment.payment_id}`)
      : ""
  );
  const description = $derived(
    payment
      ? [
          payment.provider,
          payment.created_at ? fmtDate(payment.created_at) : "",
          payment.user_label || payment.user_id,
        ]
          .filter(Boolean)
          .join(" · ")
      : ""
  );

  function present(value: unknown): boolean {
    return value !== null && value !== undefined && value !== "";
  }

  function display(value: unknown): string {
    return present(value) ? String(value) : "—";
  }

  function money(value: unknown, currency?: string | null): string {
    return present(value) ? fmtMoney(value, currency) : "—";
  }

  function formatGb(value: unknown): string {
    if (!present(value)) return "—";
    const n = Number(value);
    if (Number.isNaN(n)) return display(value);
    const rounded = Math.abs(n - Math.round(n)) < 1e-9 ? Math.round(n) : Math.round(n * 100) / 100;
    return `${rounded} GB`;
  }

  function formatTrafficSplit(p: AdminPayment | null): string {
    const parts: string[] = [];
    const regularGb = p?.traffic_regular_gb;
    const premiumGb = p?.traffic_premium_gb;
    if (present(regularGb)) {
      parts.push(
        at(
          "payment_detail_regular_traffic",
          { gb: formatGb(regularGb) },
          `标准流量：${formatGb(regularGb)}`
        )
      );
    }
    if (present(premiumGb)) {
      parts.push(
        at(
          "payment_detail_premium_traffic",
          { gb: formatGb(premiumGb) },
          `高级流量：${formatGb(premiumGb)}`
        )
      );
    }
    return parts.join(" · ") || "—";
  }

  function paymentDescription(p: AdminPayment | null): string {
    const traffic = formatTrafficSplit(p);
    if (traffic !== "—") return traffic;
    const hwidDevices = p?.purchased_hwid_devices;
    if (present(hwidDevices) && Number(hwidDevices) > 0) {
      return at(
        "payments_desc_hwid_devices",
        { count: hwidDevices },
        `加购 HWID 设备 ${hwidDevices} 台`
      );
    }
    const months = p?.subscription_duration_months;
    if (present(months) && Number(months) > 0) {
      return at("payments_desc_subscription_months", { count: months }, `订阅 ${months} 个月`);
    }
    const raw = p?.description && String(p.description).trim();
    if (raw) return raw;
    return "—";
  }

  function copy(value: unknown): void {
    paymentsStore.copyToClipboard(value, at("payment_detail_copied", {}, "已复制"));
  }

  function openUser(): void {
    if (!payment?.user_id) return;
    paymentsStore.closePayment({ skipPush: true });
    onOpenUserCard(payment.user_id);
  }

  function durationText(p: AdminPayment | null): string {
    const months = p?.subscription_duration_months;
    return present(months)
      ? at("payment_detail_months_count", { count: months }, `${months} 个月`)
      : "";
  }

  function purchasedGbText(p: AdminPayment | null): string {
    const purchasedGb = p?.purchased_gb;
    return present(purchasedGb) ? formatGb(purchasedGb) : "";
  }

  const paymentRows = $derived([
    {
      label: "ID",
      value: payment?.payment_id ? `#${payment.payment_id}` : "",
      copy: payment?.payment_id,
    },
    {
      label: at("amount", {}, "金额"),
      value: money(payment?.amount, payment?.currency),
    },
    { label: at("status", {}, "状态"), value: paymentStatusLabel(payment?.status) },
    {
      label: at("date", {}, "日期"),
      value: payment?.created_at ? fmtDate(payment.created_at) : "",
    },
    {
      label: at("payment_detail_updated_at", {}, "已更新"),
      value: payment?.updated_at ? fmtDate(payment.updated_at) : "",
    },
    { label: at("description", {}, "描述"), value: paymentDescription(payment) },
  ] satisfies MetaRow[]);

  const providerRows = $derived([
    { label: at("provider", {}, "支付方式"), value: payment?.provider },
    {
      label: at("payment_detail_provider_payment_id", {}, "渠道支付 ID"),
      value: payment?.provider_payment_id,
      copy: payment?.provider_payment_id,
    },
    {
      label: "YooKassa ID",
      value: payment?.yookassa_payment_id,
      copy: payment?.yookassa_payment_id,
    },
    {
      label: at("payment_detail_idempotence_key", {}, "幂等键"),
      value: payment?.idempotence_key,
      copy: payment?.idempotence_key,
    },
  ] satisfies MetaRow[]);

  const purchaseRows = $derived([
    { label: at("payment_detail_sale_mode", {}, "销售模式"), value: payment?.sale_mode },
    { label: at("payment_detail_tariff_key", {}, "套餐"), value: payment?.tariff_key },
    {
      label: at("payment_detail_duration_months", {}, "周期"),
      value: durationText(payment),
    },
    {
      label: at("payment_detail_traffic", {}, "流量"),
      value: formatTrafficSplit(payment),
    },
    {
      label: at("payment_detail_purchased_gb", {}, "购买流量"),
      value: purchasedGbText(payment),
    },
    {
      label: at("payment_detail_hwid_devices", {}, "HWID 设备"),
      value: payment?.purchased_hwid_devices,
    },
    { label: at("payment_detail_promo_code", {}, "优惠码"), value: payment?.promo_code },
  ] satisfies MetaRow[]);

  const userRows = $derived([
    { label: at("user", {}, "用户"), value: payment?.user_label },
    { label: "User ID", value: payment?.user_id, copy: payment?.user_id },
    { label: "Telegram ID", value: payment?.telegram_id, copy: payment?.telegram_id },
  ] satisfies MetaRow[]);
</script>

<Dialog
  open={Boolean(openedPaymentId)}
  {title}
  {description}
  closeLabel={at("close", {}, "关闭")}
  onclose={closePayment}
  class="admin-dialog admin-payment-dialog"
>
  {#if payment}
    <div class="admin-payment-dialog-body">
      <aside class="admin-payment-aside">
        <div class="admin-payment-summary">
          <span class="admin-payment-icon" aria-hidden="true">
            <WalletCards size={24} />
          </span>
          <div class="admin-payment-summary-meta">
            <strong>{money(payment.amount, payment.currency)}</strong>
            <small>{paymentDescription(payment)}</small>
            <div class="admin-payment-summary-tags">
              <AdminBadge variant={paymentStatusVariant(payment.status)}
                >{paymentStatusLabel(payment.status)}</AdminBadge
              >
              {#if payment.provider}
                <AdminBadge variant="muted">{payment.provider}</AdminBadge>
              {/if}
            </div>
          </div>
        </div>

        <div class="admin-payment-stats">
          <div class="admin-payment-stat">
            <CreditCard size={15} />
            <span>{at("payment_detail_provider", {}, "支付方式")}</span>
            <strong>{display(payment.provider)}</strong>
          </div>
          <div class="admin-payment-stat">
            <CalendarDays size={15} />
            <span>{at("date", {}, "日期")}</span>
            <strong>{payment.created_at ? fmtDate(payment.created_at) : "—"}</strong>
          </div>
        </div>

        <div class="admin-subsection-title">
          {at("payment_detail_user_section", {}, "用户")}
        </div>
        <ul class="admin-meta-list admin-payment-meta-list">
          {#each userRows as row}
            <li>
              <span>{row.label}</span>
              <strong class:admin-meta-truncate={row.copy}>{display(row.value)}</strong>
              {#if row.copy}
                <AdminButton
                  size="icon"
                  variant="icon"
                  title={at("user_copy_tooltip", {}, "复制")}
                  onclick={() => copy(row.copy)}
                >
                  <Copy size={14} />
                </AdminButton>
              {/if}
            </li>
          {/each}
        </ul>

        <AdminButton variant="ghost" onclick={openUser} disabled={!payment.user_id}>
          <User size={14} />
          {at("payments_open_user", {}, "打开用户卡片")}
        </AdminButton>
      </aside>

      <main class="admin-payment-main">
        {#if paymentDetailLoading && !openedPayment}
          <p class="admin-muted">{at("loading", {}, "加载中...")}</p>
        {:else}
          <section class="admin-payment-panel">
            <div class="admin-payment-panel-head">
              <CreditCard size={16} />
              <h3>{at("payment_detail_payment_section", {}, "支付")}</h3>
            </div>
            <ul class="admin-meta-list admin-payment-meta-list">
              {#each paymentRows as row}
                <li>
                  <span>{row.label}</span>
                  <strong class:admin-meta-truncate={row.copy}>{display(row.value)}</strong>
                  {#if row.copy}
                    <AdminButton
                      size="icon"
                      variant="icon"
                      title={at("user_copy_tooltip", {}, "复制")}
                      onclick={() => copy(row.copy)}
                    >
                      <Copy size={14} />
                    </AdminButton>
                  {/if}
                </li>
              {/each}
            </ul>
          </section>

          <section class="admin-payment-panel">
            <div class="admin-payment-panel-head">
              <Database size={16} />
              <h3>{at("payment_detail_provider_section", {}, "支付方式")}</h3>
            </div>
            <ul class="admin-meta-list admin-payment-meta-list">
              {#each providerRows as row}
                <li>
                  <span>{row.label}</span>
                  <strong class:admin-meta-truncate={row.copy}>{display(row.value)}</strong>
                  {#if row.copy}
                    <AdminButton
                      size="icon"
                      variant="icon"
                      title={at("user_copy_tooltip", {}, "复制")}
                      onclick={() => copy(row.copy)}
                    >
                      <Copy size={14} />
                    </AdminButton>
                  {/if}
                </li>
              {/each}
            </ul>
          </section>

          <section class="admin-payment-panel">
            <div class="admin-payment-panel-head">
              <Tag size={16} />
              <h3>{at("payment_detail_purchase_section", {}, "购买信息")}</h3>
            </div>
            <ul class="admin-meta-list admin-payment-meta-list">
              {#each purchaseRows as row}
                <li>
                  <span>{row.label}</span>
                  <strong>{display(row.value)}</strong>
                </li>
              {/each}
            </ul>
          </section>
        {/if}
      </main>
    </div>
  {/if}
</Dialog>
