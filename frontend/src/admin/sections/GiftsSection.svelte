<script lang="ts">
  import {
    AdminBadge,
    AdminButton,
    AdminPagination,
    AdminTable,
    AdminSortableHeader,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import Input from "$components/ui/input.svelte";
  import { Gift, Plus, Copy, Check, RefreshCw, User } from "$components/ui/icons.js";
  import { unwrap, buildAdminGiftPath, type ApiClient } from "$lib/webapp/publicApi.js";
  import type { components } from "$lib/api/openapi.generated.js";
  import PaymentProviderCell from "./PaymentProviderCell.svelte";
  import GiftCreateDialog from "./GiftCreateDialog.svelte";
  type AdminGift = components["schemas"]["AdminGiftView"];
  let {
    api,
    at = (key) => key,
    fmtDate = (value) => String(value || "—"),
    fmtMoney = (amount, currency) => `${amount} ${currency || ""}`,
    onOpenUserCard = () => {},
    onOpenPaymentCard = () => {},
  }: {
    api: ApiClient["api"];
    at?: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
    fmtDate?: (value: unknown) => string;
    fmtMoney?: (amount: number, currency?: string | null) => string;
    onOpenUserCard?: (id: number) => void;
    onOpenPaymentCard?: (id: number) => void;
  } = $props();
  let gifts = $state<AdminGift[]>([]);
  let total = $state(0);
  let page = $state(0);
  let status = $state("");
  let source = $state("");
  let createOpen = $state(false);
  let copied = $state(false);
  let copyFailed = $state(false);
  let query = $state("");
  let appliedQuery = $state("");
  let busy = $state(false);
  let failed = $state(false);
  let selected = $state<AdminGift | null>(null);
  let sort = $state("date_desc");
  const columns = [
    ["id", "id"],
    ["buyer", "gifts_buyer_or_creator"],
    ["recipient", "gifts_recipient"],
    ["tariff", "gifts_tariff"],
    ["amount", "amount"],
    ["provider", "provider"],
    ["status", "status"],
    ["date", "date"],
  ];
  function changeSort(value: string) {
    page = 0;
    sort = value;
  }
  function openUser(id: number) {
    selected = null;
    onOpenUserCard(id);
  }
  function openPayment(id: number) {
    selected = null;
    onOpenPaymentCard(id);
  }
  let requestId = 0;

  async function load(
    currentPage: number,
    currentStatus: string,
    currentQuery: string,
    currentSort: string,
    currentSource = source
  ) {
    const request = ++requestId;
    busy = true;
    failed = false;
    try {
      const result = unwrap(
        await api(
          `/admin/gifts?page=${currentPage}&status=${encodeURIComponent(currentStatus)}&q=${encodeURIComponent(currentQuery)}&sort=${encodeURIComponent(currentSort)}&source=${encodeURIComponent(currentSource)}`
        )
      );
      if (request === requestId) {
        gifts = result.gifts;
        total = result.total;
      }
    } catch {
      if (request === requestId) failed = true;
    } finally {
      if (request === requestId) busy = false;
    }
  }
  $effect(() => {
    void load(page, status, appliedQuery, sort, source);
  });
  async function openGift(gift: AdminGift) {
    selected = gift;
    copied = false;
    copyFailed = false;
    try {
      const result = unwrap(await api(buildAdminGiftPath(gift.gift_id)));
      if ("gift" in result && selected?.gift_id === gift.gift_id) selected = result.gift;
    } catch {
      /* The list still provides the gift details. */
    }
  }
  async function copyLink(link: string) {
    try {
      await navigator.clipboard.writeText(link);
      copied = true;
      copyFailed = false;
    } catch {
      copyFailed = true;
    }
  }
  function created(gift: AdminGift) {
    createOpen = false;
    selected = gift;
    copied = false;
    copyFailed = false;
    page = 0;
    status = "";
    source = "";
    query = "";
    appliedQuery = "";
    sort = "date_desc";
    void load(0, "", "", "date_desc", "");
  }
  function search(event: SubmitEvent) {
    event.preventDefault();
    page = 0;
    appliedQuery = query.trim();
  }
</script>

<div class="gifts-admin">
  <form class="admin-toolbar admin-toolbar-users gifts-toolbar" onsubmit={search}>
    <div class="admin-toolbar-search">
      <Input
        class="input"
        type="search"
        bind:value={query}
        placeholder={at("gifts_search")}
        aria-label={at("gifts_search")}
      />
      <AdminButton type="submit" variant="primary">{at("find")}</AdminButton>
    </div>
    <div class="admin-toolbar-controls">
      <div class="admin-toolbar-field">
        <span class="admin-toolbar-field-label">{at("gifts_status")}</span>
        <AdminSelect
          bind:value={status}
          class="admin-toolbar-select"
          ariaLabel={at("gifts_status")}
          onValueChange={() => (page = 0)}
          items={[
            { value: "", label: at("gifts_all") },
            ...["ready", "activating", "activated", "revoked"].map((value) => ({
              value,
              label: at(`gifts_status_${value}`),
            })),
          ]}
        />
      </div>
      <div class="admin-toolbar-field">
        <span class="admin-toolbar-field-label">{at("gifts_source")}</span>
        <AdminSelect
          bind:value={source}
          class="admin-toolbar-select"
          ariaLabel={at("gifts_source")}
          onValueChange={() => (page = 0)}
          items={[
            { value: "", label: at("filter_all") },
            { value: "purchase", label: at("gifts_source_purchase") },
            { value: "admin", label: at("gifts_source_admin") },
          ]}
        />
      </div>
      <div class="admin-toolbar-summary">
        <span class="admin-toolbar-field-label">{at("total")}</span><strong>{total}</strong>
      </div>
    </div>
  </form>
  <div class="gifts-actions">
    <AdminButton variant="primary" onclick={() => (createOpen = true)}
      ><Plus size={16} />{at("gifts_create")}</AdminButton
    >
    <AdminButton
      variant="ghost"
      disabled={busy}
      onclick={() => load(page, status, appliedQuery, sort)}
      ><RefreshCw size={15} />{at("refresh")}</AdminButton
    >
  </div>
  {#if failed}<p role="alert">{at("gifts_load_failed")}</p>{/if}
  <div class="gift-desktop" aria-busy={busy}>
    <AdminTable>
      <thead
        ><tr
          >{#each columns as [key, label]}
            <AdminSortableHeader
              label={at(label)}
              column={{ asc: `${key}_asc`, desc: `${key}_desc`, defaultDirection: "desc" }}
              currentSort={sort}
              {at}
              onSort={changeSort}
            />
          {/each}</tr
        ></thead
      >
      <tbody
        >{#each gifts as gift (gift.gift_id)}
          <tr>
            <td>{@render giftLink(gift)}</td>
            <td
              >{@render userLink(
                gift.purchaser_id,
                gift.purchaser_label
              )}{#if gift.provider === "admin_gift"}<small>{at("gifts_created_by")}</small>{/if}</td
            >
            <td
              >{#if gift.recipient_id}{@render userLink(
                  gift.recipient_id,
                  gift.recipient_label
                )}{:else}<span class="gift-secondary">{at("gifts_not_claimed")}</span>{/if}</td
            >
            <td
              ><strong>{gift.tariff_title || at("gifts_subscription")}</strong><small
                >{at("gifts_duration", {
                  days: gift.duration_days,
                  bonus: gift.bonus_days || 0,
                })}</small
              ></td
            >
            <td><strong>{fmtMoney(gift.total_amount, gift.currency)}</strong></td>
            <td>{@render provider(gift)}</td>
            <td>{@render badge(gift.status)}</td>
            <td>{fmtDate(gift.created_at)}</td>
          </tr>
        {/each}</tbody
      >
    </AdminTable>
  </div>
  <div class="gift-mobile" aria-busy={busy}>
    <div class="gift-mobile-sort">
      <span>{at("gifts_sort")}</span>
      <AdminSelect
        bind:value={sort}
        ariaLabel={at("gifts_sort")}
        onValueChange={() => (page = 0)}
        items={columns.flatMap(([key, label]) => [
          { value: `${key}_desc`, label: `${at(label)} ↓` },
          { value: `${key}_asc`, label: `${at(label)} ↑` },
        ])}
      />
    </div>
    {#each gifts as gift (gift.gift_id)}
      <article class="gift-mobile-card">
        <span class="gift-mobile-line"
          >{@render giftLink(gift, true)}{@render badge(gift.status)}</span
        >
        <span class="gift-mobile-line"
          >{@render provider(gift)}<strong>{fmtMoney(gift.total_amount, gift.currency)}</strong
          ></span
        >
        <div class="gift-mobile-users">
          <div>
            <small>{at(gift.provider === "admin_gift" ? "gifts_created_by" : "gifts_buyer")}</small
            >{@render userLink(gift.purchaser_id, gift.purchaser_label)}
          </div>
          <div>
            <small>{at("gifts_recipient")}</small>{#if gift.recipient_id}{@render userLink(
                gift.recipient_id,
                gift.recipient_label
              )}{:else}<span class="gift-secondary">{at("gifts_not_claimed")}</span>{/if}
          </div>
        </div>
        <span class="gift-mobile-line gift-secondary"
          ><span
            >{at("gifts_duration", { days: gift.duration_days, bonus: gift.bonus_days || 0 })}</span
          ><span>{fmtDate(gift.created_at)}</span></span
        >
      </article>
    {/each}
  </div>
  {#if !busy && !gifts.length}<p class="gift-secondary">
      {at("gifts_empty", {}, "No gifts found")}
    </p>{/if}
  <AdminPagination
    {page}
    {total}
    pageCount={Math.max(1, Math.ceil(total / 25))}
    disabled={busy}
    onPageChange={(value) => (page = value)}
    pageLabel={at("page_short", {}, "Page")}
    ofLabel={at("pagination_of", {}, "of")}
    totalLabel={at("total", {}, "Total")}
    jumpLabel={at("page_short", {}, "Page")}
    jumpAriaLabel={at("pagination_jump_aria", {}, "Go to page")}
    goLabel={at("pagination_go", {}, "Go")}
    prevLabel={at("back", {}, "Back")}
    nextLabel={at("next", {}, "Next")}
  />
</div>

{#snippet userLink(id: number | null, label: string)}
  {#if id}<span class="gift-user-cell">
      <AdminButton
        class="gift-user-link"
        variant="ghost"
        size="icon"
        title={at("payments_open_user", {}, "Open user card")}
        aria-label={`${at("payments_open_user", {}, "Open user card")}: ${label || id} (#${id})`}
        onclick={() => openUser(id)}><User size={14} /></AdminButton
      >
      <span class="gift-user-identity"
        ><strong title={label || `#${id}`}>{label || `#${id}`}</strong>{#if label}<small
            >#{id}</small
          >{/if}</span
      >
    </span>{:else}<span>—</span>{/if}
{/snippet}

{#snippet giftLink(gift: AdminGift, withTariff = false)}
  <span class="gift-id-actions">
    <AdminButton
      class="gift-detail-button details-toggle"
      variant="ghost"
      size="icon"
      title={at("gifts_detail_title", { id: gift.gift_id })}
      aria-label={at("gifts_detail_title", { id: gift.gift_id })}
      onclick={() => openGift(gift)}><Gift size={14} /></AdminButton
    >
    <span
      ><span class="gift-id">#{gift.gift_id}</span>{#if withTariff}
        · <strong>{gift.tariff_title || at("gifts_subscription")}</strong>{/if}</span
    >
  </span>
{/snippet}

{#snippet provider(gift: AdminGift)}
  <PaymentProviderCell {at} provider={gift.provider} />
{/snippet}

{#if createOpen}<GiftCreateDialog
    {api}
    {at}
    onclose={() => (createOpen = false)}
    oncreated={created}
  />{/if}

{#snippet badge(status: string)}
  <AdminBadge
    variant={status === "activated" ? "success" : status === "revoked" ? "danger" : "muted"}
    >{at(`gifts_status_${status}`)}</AdminBadge
  >
{/snippet}

<Dialog
  open={Boolean(selected)}
  title={at("gifts_detail_title", { id: selected?.gift_id || "" })}
  closeLabel={at("close", {}, "Close")}
  onclose={() => (selected = null)}
  class="admin-dialog admin-gift-dialog"
>
  {#if selected}{@const gift = selected}
    <div class="gift-modal-summary">
      <div>
        <strong>{gift.tariff_title || at("gifts_subscription")}</strong><span class="gift-secondary"
          >{at("gifts_duration", { days: gift.duration_days, bonus: gift.bonus_days || 0 })}</span
        >
      </div>
      <div>
        <strong>{fmtMoney(gift.total_amount, gift.currency)}</strong>{@render badge(gift.status)}
      </div>
    </div>
    {#if gift.link}
      <div class="gift-admin-link-block">
        <span class="gift-secondary">{at("gifts_link_hint")}</span>
        <div class="gift-admin-link">
          <Input
            class="input"
            readonly
            value={gift.link}
            aria-label={at("gifts_link")}
            onclick={(event) => event.currentTarget.select()}
          />
          <AdminButton variant="primary" onclick={() => copyLink(gift.link || "")}
            >{#if copied}<Check size={16} />{:else}<Copy size={16} />{/if}{at(
              copied ? "gifts_copied" : "gifts_copy"
            )}</AdminButton
          >
        </div>
        {#if copyFailed}<span role="alert" class="gift-secondary">{at("gifts_copy_failed")}</span
          >{/if}
      </div>
    {/if}
    <div class="gift-modal-buyer">
      <span>{at(gift.provider === "admin_gift" ? "gifts_created_by" : "gifts_buyer")}</span
      >{@render userLink(gift.purchaser_id, gift.purchaser_label)}
      <div class="gift-payment-meta">
        {@render provider(gift)}<span class="gift-secondary">{fmtDate(gift.created_at)}</span>
      </div>
    </div>
    <div class="gift-admin-details">
      <div>
        <small>{at("gifts_recipient", {}, "Recipient")}</small
        >{#if gift.recipient_id}{@render userLink(
            gift.recipient_id,
            gift.recipient_label
          )}{:else}<span>{at("gifts_not_claimed", {}, "Not claimed yet")}</span>{/if}<span
          >{fmtDate(gift.activated_at)}</span
        >
      </div>
      <div>
        <small>{at("gifts_composition", {}, "Gift contents")}</small><span
          >{at(
            "gifts_limits",
            {
              devices: gift.devices === 0 ? "∞" : (gift.devices ?? "—"),
              traffic: gift.regular_limit_gb === 0 ? "∞" : (gift.regular_limit_gb ?? "—"),
              premium: gift.premium_unlimited ? "∞" : (gift.premium_limit_gb ?? "—"),
            },
            "Devices: {devices} · Traffic: {traffic} GB · Premium: {premium} GB"
          )}</span
        ><span
          >{at(
            "gifts_bonus_traffic",
            { regular: gift.regular_bonus_gb || 0, premium: gift.premium_bonus_gb || 0 },
            "Bonus traffic: {regular} GB + {premium} GB premium"
          )}</span
        >
      </div>
      <div>
        <small>{at("gifts_funding", {}, "Payment breakdown")}</small>
        {#if gift.provider === "admin_gift"}<span>{at("gifts_free_accounting")}</span>{:else}<span
            >{at("gifts_user_balance", {}, "User balance")}: {fmtMoney(
              gift.user_balance_amount,
              gift.currency
            )}</span
          ><span
            >{at("gifts_partner_balance", {}, "Partner balance")}: {fmtMoney(
              gift.partner_balance_amount,
              gift.currency
            )}</span
          ><span
            >{at("gifts_discount", {}, "Promo discount")}: {fmtMoney(
              gift.discount_amount,
              gift.currency
            )}{gift.promo_code_id ? ` · #${gift.promo_code_id}` : ""}</span
          >{/if}<AdminButton
          variant="ghost"
          size="sm"
          class="gift-link"
          onclick={() => openPayment(gift.payment_id)}
          >{at("gifts_payment", {}, "Payment")} #{gift.payment_id}</AdminButton
        >
      </div>
      <div>
        <small>{at("gifts_email", {}, "Email delivery")}</small><span
          >{gift.recipient_email || "—"}</span
        ><span>{at(`gifts_delivery_${gift.delivery_status || "not_requested"}`)}</span><span
          >{fmtDate(gift.delivered_at)}</span
        >
      </div>
    </div>
  {/if}
</Dialog>

<style>
  .gifts-admin {
    display: grid;
    gap: 14px;
    min-width: 0;
  }
  .gifts-toolbar {
    min-width: 0;
  }
  .gifts-toolbar :global(.admin-toolbar-search .input),
  .gifts-toolbar :global(.admin-toolbar-search .admin-btn) {
    height: 36px;
    min-height: 36px;
  }
  .gifts-toolbar :global(.admin-toolbar-controls) {
    grid-template-columns: repeat(2, minmax(0, 1fr)) auto;
  }
  .gifts-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .gift-admin-link-block {
    display: grid;
    gap: 8px;
    padding-bottom: 16px;
  }
  .gift-admin-link {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .gift-admin-link :global(input) {
    min-width: 0;
    flex: 1;
  }
  .gift-admin-link :global(.admin-btn) {
    flex-shrink: 0;
  }
  :global(.admin-gift-dialog .gift-link) {
    border: 0;
    background: transparent;
    color: var(--accent);
    padding: 0;
    cursor: pointer;
    font: inherit;
    text-align: left;
    overflow-wrap: anywhere;
  }
  small,
  .gift-secondary {
    display: block;
    color: var(--muted);
    font-size: 12px;
  }
  td small {
    margin-top: 4px;
  }
  td {
    font-size: 13px;
  }
  .gift-mobile {
    display: none;
  }
  .gift-modal-summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding-bottom: 14px;
  }
  .gift-modal-summary > div {
    display: grid;
    gap: 7px;
  }
  .gift-modal-summary > div:last-child {
    justify-items: end;
  }
  .gift-modal-buyer {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    padding: 12px 0;
    border-top: 1px solid var(--border);
    font-size: 13px;
  }
  .gift-payment-meta {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    width: 100%;
  }
  .gift-user-cell,
  .gift-id-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    color: var(--admin-text);
  }
  .gift-id-actions {
    gap: 2px;
  }
  .gift-user-identity {
    display: grid;
    gap: 2px;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  .gift-user-identity strong {
    font-weight: 650;
  }
  .gift-desktop .gift-user-identity {
    max-width: 140px;
  }
  .gift-desktop .gift-user-identity strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .gift-user-identity small,
  .gift-id {
    font-family: var(--font-mono);
    font-size: 11px;
    margin: 0;
  }
  :global(.gift-user-link.admin-btn),
  :global(.gift-detail-button.admin-btn) {
    width: 30px;
    height: 30px;
    min-width: 30px;
    min-height: 30px;
    flex-shrink: 0;
    padding: 0;
    border-radius: 7px;
    color: var(--admin-text);
  }
  :global(.gift-detail-button.admin-btn) {
    width: 28px;
    height: 28px;
    min-width: 28px;
    min-height: 28px;
  }
  .gift-admin-details {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 18px;
    padding-top: 14px;
    border-top: 1px solid var(--border);
    font-size: 13px;
  }
  .gift-admin-details > div {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  :global(.admin-gift-dialog) {
    width: min(100%, 680px);
  }
  :global(.admin-gift-dialog .scroll-area__viewport > div) {
    display: block !important;
    min-width: 0;
    max-width: 100%;
  }
  @media (max-width: 760px) {
    .gift-desktop {
      display: none;
    }
    .gift-mobile {
      display: grid;
      gap: 8px;
    }
    .gift-mobile-sort {
      display: flex;
      gap: 10px;
      align-items: center;
      font-size: 12px;
      color: var(--muted);
    }
    .gift-mobile-sort :global(.admin-select-trigger) {
      flex: 1;
      min-width: 0;
    }
    .gift-mobile-card {
      display: grid;
      gap: 10px;
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 12px;
      background: var(--panel);
      color: var(--text);
      font: inherit;
      font-size: 12px;
      text-align: left;
    }
    .gift-mobile-users {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .gift-mobile-users > div {
      display: grid;
      align-content: start;
      gap: 4px;
      min-width: 0;
    }
    .gift-mobile-line {
      display: flex;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
    }
    .gift-mobile-line > span {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .gifts-toolbar :global(.admin-toolbar-controls) {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .gifts-toolbar :global(.admin-toolbar-summary) {
      grid-column: 1 / -1;
      display: flex;
      justify-content: space-between;
      min-height: 20px;
    }
    .gift-admin-details {
      gap: 14px;
      font-size: 12px;
    }
  }
</style>
