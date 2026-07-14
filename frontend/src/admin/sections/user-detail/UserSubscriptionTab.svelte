<script lang="ts">
  import { AdminBadge, AdminTrafficCard } from "$components/patterns/admin/index.js";
  import { Separator, Tabs } from "$components/ui/primitives.js";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState";
  import type { DateFormatter, TranslateFn } from "./userDetailTypes";

  let {
    at,
    openedUserDetail,
    fmtDate,
    subscriptionDisplayLabel,
    pretty,
    hwidLimitLabel,
    trafficOfLabel,
    trafficLeftLabel,
    trafficPercentValue,
    trialSummaryText,
  }: {
    at: TranslateFn;
    openedUserDetail: AdminUserDetail;
    fmtDate: DateFormatter;
    subscriptionDisplayLabel: (sub: Record<string, unknown> | null | undefined) => string;
    pretty: (value: unknown) => string;
    hwidLimitLabel: (sub: Record<string, unknown> | null | undefined) => string;
    trafficOfLabel: (used: unknown, limit: unknown) => string;
    trafficLeftLabel: (used: unknown, limit: unknown) => string;
    trafficPercentValue: (left: unknown, total: unknown) => number;
    trialSummaryText: (trial: Record<string, unknown> | null | undefined) => string;
  } = $props();
</script>

<Tabs.Content value="subscription" class="admin-tabs-content">
  {#if openedUserDetail.active_subscription}
    <ul class="admin-meta-list">
      <li>
        <span>{at("user_label_active_until", {}, "Active until")}</span><strong
          >{fmtDate(openedUserDetail.active_subscription.end_date)}</strong
        >
      </li>
      <li>
        <span>{at("user_label_tariff", {}, "Tariff")}</span><strong
          >{subscriptionDisplayLabel(openedUserDetail.active_subscription)}</strong
        >
      </li>
      <li>
        <span>{at("user_label_auto_renew", {}, "Auto-renew")}</span><strong
          >{pretty(openedUserDetail.active_subscription.auto_renew_enabled)}</strong
        >
      </li>
      <li>
        <span>{at("user_label_provider", {}, "Provider")}</span><strong
          >{openedUserDetail.active_subscription.provider || "—"}</strong
        >
      </li>
      <li>
        <span>{at("user_label_hwid_devices", {}, "HWID devices")}</span><strong
          >{hwidLimitLabel(openedUserDetail.active_subscription)}</strong
        >
      </li>
    </ul>
    <div class="admin-traffic-summary">
      <AdminTrafficCard
        title={at("user_label_main_traffic", {}, "Main Traffic")}
        value={trafficOfLabel(
          openedUserDetail.active_subscription.traffic_used_bytes,
          openedUserDetail.active_subscription.traffic_limit_bytes
        )}
        left={at(
          "user_traffic_left",
          {
            left: trafficLeftLabel(
              openedUserDetail.active_subscription.traffic_used_bytes,
              openedUserDetail.active_subscription.traffic_limit_bytes
            ),
          },
          "Left: {left}"
        )}
        percent={trafficPercentValue(
          openedUserDetail.active_subscription.traffic_used_bytes,
          openedUserDetail.active_subscription.traffic_limit_bytes
        )}
        warning={openedUserDetail.active_subscription.is_throttled}
        label={at("aria_label_main_traffic", {}, "Main traffic usage")}
      />
      {#if openedUserDetail.active_subscription.premium_unlimited_override}
        <AdminTrafficCard
          premium
          title={at("user_label_premium_squads", {}, "Premium Squads")}
          value={at(
            "user_premium_unlimited_value",
            {
              used: trafficLeftLabel(0, openedUserDetail.active_subscription.premium_used_bytes),
            },
            "∞ (used {used})"
          )}
          left={at("user_premium_unlimited_hint", {}, "Unlimited (admin override)")}
          percent={0}
          warning={false}
          label={at("aria_label_premium_traffic", {}, "Premium traffic usage")}
        />
      {:else if Number(openedUserDetail.active_subscription.premium_limit_bytes || 0) > 0}
        <AdminTrafficCard
          premium
          title={at("user_label_premium_squads", {}, "Premium Squads")}
          value={trafficOfLabel(
            openedUserDetail.active_subscription.premium_used_bytes,
            openedUserDetail.active_subscription.premium_limit_bytes
          )}
          left={at(
            "user_traffic_left",
            {
              left: trafficLeftLabel(
                openedUserDetail.active_subscription.premium_used_bytes,
                openedUserDetail.active_subscription.premium_limit_bytes
              ),
            },
            "Left: {left}"
          )}
          percent={trafficPercentValue(
            openedUserDetail.active_subscription.premium_used_bytes,
            openedUserDetail.active_subscription.premium_limit_bytes
          )}
          warning={openedUserDetail.active_subscription.premium_is_limited}
          label={at("aria_label_premium_traffic", {}, "Premium traffic usage")}
        />
      {/if}
    </div>
  {:else}
    <p class="admin-muted">{at("user_no_active_subscription", {}, "No active subscription")}</p>
  {/if}

  {#if openedUserDetail?.trial}
    <ul class="admin-meta-list">
      <li>
        <span>{at("user_label_trial", {}, "Trial")}</span><strong
          >{trialSummaryText(openedUserDetail.trial)}</strong
        >
      </li>
      {#if openedUserDetail.trial.used && openedUserDetail.trial.latest_end_date}
        <li>
          <span>{at("user_label_trial_until", {}, "Trial until")}</span><strong
            >{fmtDate(openedUserDetail.trial.latest_end_date)}</strong
          >
        </li>
      {/if}
      {#if Number(openedUserDetail.trial.count || 0) > 1}
        <li>
          <span>{at("user_label_trial_count", {}, "Trials")}</span><strong
            >{openedUserDetail.trial.count}</strong
          >
        </li>
      {/if}
      {#if openedUserDetail.trial.last_reset_at}
        <li>
          <span>{at("user_label_trial_reset_at", {}, "Trial reset")}</span><strong
            >{fmtDate(openedUserDetail.trial.last_reset_at)}</strong
          >
        </li>
      {/if}
    </ul>
  {/if}

  {#if (openedUserDetail.subscriptions || []).length}
    <Separator.Root class="admin-separator" />
    <div class="admin-subsection-title">
      {at(
        "user_history_title",
        { count: openedUserDetail.subscriptions.length },
        "Subscription History · {count}"
      )}
    </div>
    <div class="admin-mini-list">
      {#each openedUserDetail.subscriptions.slice(0, 8) as sub}
        <div class="admin-mini-list-row">
          <div>
            <strong>{subscriptionDisplayLabel(sub)}</strong>
            <small
              >{at("user_history_until", { date: fmtDate(sub.end_date) }, "until {date}")}</small
            >
          </div>
          {#if sub.is_active}
            <AdminBadge variant="success">{at("user_history_active", {}, "Active")}</AdminBadge>
          {:else}
            <AdminBadge variant="muted"
              >{sub.status_from_panel || at("user_history_status_panel", {}, "History")}</AdminBadge
            >
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</Tabs.Content>
