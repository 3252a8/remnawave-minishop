<script lang="ts">
  import { AdminButton, AdminSelect, AdminBadge } from "$components/patterns/admin/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import Input from "$components/ui/input.svelte";
  import { Gift } from "$components/ui/icons.js";
  import { unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import type { BillingPlan, CheckoutAddonKind } from "$lib/webapp/tariffs.js";
  import type { components } from "$lib/api/openapi.generated.js";
  import { onMount } from "svelte";
  import { billingDurationDays } from "$lib/webapp/subscriptionPeriods.js";

  let {
    api,
    at,
    onclose,
    oncreated,
  }: {
    api: ApiClient["api"];
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
    onclose: () => void;
    oncreated: (gift: components["schemas"]["AdminGiftView"]) => void;
  } = $props();
  let plans = $state<BillingPlan[]>([]);
  let planId = $state("");
  let emailAvailable = $state(false);
  let email = $state("");
  let loading = $state(true);
  let busy = $state(false);
  let attempted = $state(false);
  let error = $state("");
  const requestId = crypto.randomUUID();
  const plan = $derived(plans.find((item) => String(item.id) === planId));
  const tariffKey = $derived(String(plan?.tariff_key || ""));
  const tariffs = $derived([
    ...new Map(
      plans.map((item) => [
        String(item.tariff_key || ""),
        {
          value: String(item.tariff_key || ""),
          label: String(item.tariff_name || at("gifts_subscription")),
        },
      ])
    ).values(),
  ]);
  const periods = $derived(
    plans
      .filter((item) => String(item.tariff_key || "") === tariffKey)
      .map((item) => ({
        value: String(item.id),
        label: at("gifts_days", { days: billingDurationDays(item) }),
      }))
  );
  const kinds: CheckoutAddonKind[] = ["devices", "traffic", "premium_traffic"];
  let units = $state<Record<CheckoutAddonKind, string>>({
    devices: "0",
    traffic: "0",
    premium_traffic: "0",
  });
  function choose(id: string) {
    planId = id;
    const next = plans.find((item) => String(item.id) === id);
    for (const kind of kinds) units[kind] = String(next?.checkout_addons?.[kind]?.base_units ?? 0);
  }
  onMount(() => {
    void (async () => {
      try {
        const result = unwrap(await api("/admin/gifts/options"));
        if (!("plans" in result)) throw new Error("Invalid gift options response");
        plans = result.plans as BillingPlan[];
        emailAvailable = result.email_available;
        choose(String(plans[0]?.id || ""));
      } catch {
        error = "gifts_load_failed";
      } finally {
        loading = false;
      }
    })();
  });
  async function create(event: SubmitEvent) {
    event.preventDefault();
    if (busy || !plan) return;
    busy = true;
    attempted = true;
    error = "";
    try {
      const addons = plan.checkout_addons;
      const result = unwrap(
        await api("/admin/gifts", {
          method: "POST",
          body: JSON.stringify({
            request_id: requestId,
            plan_id: planId,
            recipient_email: email.trim() || null,
            checkout_addons: {
              device_count: addons?.devices ? Number(units.devices) - addons.devices.base_units : 0,
              regular_limit_gb: addons?.traffic ? Number(units.traffic) : null,
              premium_limit_gb: addons?.premium_traffic ? Number(units.premium_traffic) : null,
            },
          }),
        })
      );
      if (!("gift" in result)) throw new Error("Invalid gift creation response");
      oncreated(result.gift);
    } catch (failure) {
      const code =
        failure && typeof failure === "object" && "error" in failure ? String(failure.error) : "";
      if (
        [
          "invalid_plan",
          "checkout_addon_unavailable",
          "invalid_checkout_addon",
          "gift_email_unavailable",
          "invalid_payload",
        ].includes(code)
      ) {
        attempted = false;
        error = "gifts_selection_changed";
      } else error = "gifts_create_failed";
    } finally {
      busy = false;
    }
  }
</script>

<Dialog
  open
  title={at("gifts_create")}
  closeLabel={at("close")}
  onclose={() => {
    if (!busy) onclose();
  }}
  class="admin-dialog admin-gift-create-dialog"
>
  <form class="gift-create-form" onsubmit={create}>
    <div class="gift-create-note">
      <Gift size={20} /><span>{at("gifts_create_hint")}</span><AdminBadge
        >{at("gifts_free")}</AdminBadge
      >
    </div>
    {#if loading}<p class="gift-create-muted">{at("loading")}</p>
    {:else if plan}
      <div class="gift-create-plan">
        <div class="admin-toolbar-field">
          <span class="admin-toolbar-field-label">{at("gifts_tariff")}</span>
          <AdminSelect
            value={tariffKey}
            items={tariffs}
            ariaLabel={at("gifts_tariff")}
            disabled={attempted}
            onValueChange={(value) =>
              choose(
                String(plans.find((item) => String(item.tariff_key || "") === value)?.id || "")
              )}
          />
        </div>
        <div class="admin-toolbar-field">
          <span class="admin-toolbar-field-label">{at("gifts_period")}</span>
          <AdminSelect
            value={planId}
            items={periods}
            ariaLabel={at("gifts_period")}
            disabled={attempted}
            onValueChange={choose}
          />
        </div>
      </div>
      <div class="gift-create-limits">
        {#each kinds as kind}
          {@const addon = plan.checkout_addons?.[kind]}
          <div class="admin-toolbar-field">
            <span class="admin-toolbar-field-label">{at(`gifts_limit_${kind}`)}</span>
            {#if addon}
              <AdminSelect
                bind:value={units[kind]}
                disabled={attempted}
                ariaLabel={at(`gifts_limit_${kind}`)}
                items={addon.options.map((option) => ({
                  value: String(option.total_units),
                  label: `${option.total_units === 0 && (kind !== "premium_traffic" || plan.premium_unlimited) ? "∞" : option.total_units}${kind === "devices" ? "" : " GB"}`,
                }))}
              />
            {:else}
              <div class="gift-create-fixed">
                {kind === "devices"
                  ? (plan.effective_hwid_device_limit ?? plan.hwid_device_limit ?? "—") || "∞"
                  : kind === "traffic"
                    ? (plan.monthly_gb ?? "—") || "∞"
                    : plan.premium_unlimited
                      ? "∞"
                      : plan.premium_monthly_gb || 0}{kind === "devices" ? "" : " GB"}
              </div>
            {/if}
          </div>
        {/each}
      </div>
      {#if emailAvailable}<label class="admin-toolbar-field"
          ><span class="admin-toolbar-field-label">{at("gifts_create_email")}</span><Input
            class="input"
            type="email"
            bind:value={email}
            disabled={attempted}
            maxlength={254}
            placeholder="friend@example.com"
          /></label
        >{/if}
      <div class="gift-create-footer">
        <span class="gift-create-muted">{at("gifts_create_total")}</span><AdminButton
          type="submit"
          variant="primary"
          disabled={busy}
          >{at(
            busy ? "gifts_creating" : attempted && error ? "gifts_create_retry" : "gifts_create"
          )}</AdminButton
        >
      </div>
    {:else if !error}<p>{at("gifts_no_plans")}</p>{/if}
    {#if error}<p role="alert" class="gift-create-error">{at(error)}</p>{/if}
  </form>
</Dialog>

<style>
  .gift-create-form {
    display: grid;
    gap: 18px;
    min-width: 0;
  }
  .gift-create-note {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px;
    background: var(--admin-surface-2);
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    font-size: 13px;
  }
  .gift-create-note > span {
    flex: 1;
  }
  .gift-create-note :global(svg) {
    flex-shrink: 0;
    color: var(--accent);
  }
  .gift-create-plan {
    display: grid;
    grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
    gap: 12px;
  }
  .gift-create-limits {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
  }
  .gift-create-fixed {
    display: flex;
    align-items: center;
    height: 36px;
    font-size: 14px;
    font-weight: 600;
  }
  .gift-create-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    padding-top: 14px;
    border-top: 1px solid var(--admin-border);
  }
  .gift-create-muted {
    color: var(--admin-muted);
    font-size: 12px;
  }
  .gift-create-error {
    margin: 0;
    font-size: 13px;
    color: var(--danger);
  }
  :global(.admin-gift-create-dialog) {
    width: min(100%, 640px);
  }
  :global(.admin-gift-create-dialog .scroll-area__viewport > div) {
    display: block !important;
    min-width: 0;
    max-width: 100%;
  }
  @media (max-width: 520px) {
    .gift-create-plan {
      grid-template-columns: minmax(0, 1fr);
    }
    .gift-create-limits {
      grid-template-columns: minmax(0, 1fr);
      gap: 10px;
    }
    .gift-create-limits .admin-toolbar-field {
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      align-items: center;
    }
    .gift-create-fixed {
      justify-content: end;
    }
    .gift-create-footer {
      flex-direction: column;
      align-items: stretch;
    }
    .gift-create-form {
      gap: 14px;
    }
  }
</style>
