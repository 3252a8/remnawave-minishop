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
        <span>{at("user_label_active_until", {}, "Активна до")}</span><strong
          >{fmtDate(openedUserDetail.active_subscription.end_date)}</strong
        >
      </li>
      <li>
        <span>{at("user_label_tariff", {}, "Тариф")}</span><strong
          >{subscriptionDisplayLabel(openedUserDetail.active_subscription)}</strong
        >
      </li>
      <li>
        <span>{at("user_label_auto_renew", {}, "Авто-продление")}</span><strong
          >{pretty(openedUserDetail.active_subscription.auto_renew_enabled)}</strong
        >
      </li>
      <li>
        <span>{at("user_label_provider", {}, "Провайдер")}</span><strong
          >{openedUserDetail.active_subscription.provider || "—"}</strong
        >
      </li>
      <li>
        <span>{at("user_label_hwid_devices", {}, "HWID-устройства")}</span><strong
          >{hwidLimitLabel(openedUserDetail.active_subscription)}</strong
        >
      </li>
    </ul>
    <div class="admin-traffic-summary">
      <AdminTrafficCard
        title={at("user_label_main_traffic", {}, "Основной трафик")}
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
          "Осталось: " +
            trafficLeftLabel(
              openedUserDetail.active_subscription.traffic_used_bytes,
              openedUserDetail.active_subscription.traffic_limit_bytes
            )
        )}
        percent={trafficPercentValue(
          openedUserDetail.active_subscription.traffic_used_bytes,
          openedUserDetail.active_subscription.traffic_limit_bytes
        )}
        warning={openedUserDetail.active_subscription.is_throttled}
        label={at("aria_label_main_traffic", {}, "Использование основного трафика")}
      />
      {#if openedUserDetail.active_subscription.premium_unlimited_override}
        <AdminTrafficCard
          premium
          title={at("user_label_premium_squads", {}, "Premium-сквады")}
          value={at(
            "user_premium_unlimited_value",
            {
              used: trafficLeftLabel(0, openedUserDetail.active_subscription.premium_used_bytes),
            },
            "∞ (использовано " +
              trafficLeftLabel(0, openedUserDetail.active_subscription.premium_used_bytes) +
              ")"
          )}
          left={at("user_premium_unlimited_hint", {}, "Безлимит (админ-оверрайд)")}
          percent={0}
          warning={false}
          label={at("aria_label_premium_traffic", {}, "Использование premium-трафика")}
        />
      {:else if Number(openedUserDetail.active_subscription.premium_limit_bytes || 0) > 0}
        <AdminTrafficCard
          premium
          title={at("user_label_premium_squads", {}, "Premium-сквады")}
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
            "Осталось: " +
              trafficLeftLabel(
                openedUserDetail.active_subscription.premium_used_bytes,
                openedUserDetail.active_subscription.premium_limit_bytes
              )
          )}
          percent={trafficPercentValue(
            openedUserDetail.active_subscription.premium_used_bytes,
            openedUserDetail.active_subscription.premium_limit_bytes
          )}
          warning={openedUserDetail.active_subscription.premium_is_limited}
          label={at("aria_label_premium_traffic", {}, "Использование premium-трафика")}
        />
      {/if}
    </div>
  {:else}
    <p class="admin-muted">{at("user_no_active_subscription", {}, "Активной подписки нет")}</p>
  {/if}

  {#if openedUserDetail?.trial}
    <ul class="admin-meta-list">
      <li>
        <span>{at("user_label_trial", {}, "Пробник / триал")}</span><strong
          >{trialSummaryText(openedUserDetail.trial)}</strong
        >
      </li>
      {#if openedUserDetail.trial.used && openedUserDetail.trial.latest_end_date}
        <li>
          <span>{at("user_label_trial_until", {}, "Триал до")}</span><strong
            >{fmtDate(openedUserDetail.trial.latest_end_date)}</strong
          >
        </li>
      {/if}
      {#if Number(openedUserDetail.trial.count || 0) > 1}
        <li>
          <span>{at("user_label_trial_count", {}, "Триалов")}</span><strong
            >{openedUserDetail.trial.count}</strong
          >
        </li>
      {/if}
      {#if openedUserDetail.trial.last_reset_at}
        <li>
          <span>{at("user_label_trial_reset_at", {}, "Сброс триала")}</span><strong
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
        `История подписок · ${openedUserDetail.subscriptions.length}`
      )}
    </div>
    <div class="admin-mini-list">
      {#each openedUserDetail.subscriptions.slice(0, 8) as sub}
        <div class="admin-mini-list-row">
          <div>
            <strong>{subscriptionDisplayLabel(sub)}</strong>
            <small
              >{at(
                "user_history_until",
                { date: fmtDate(sub.end_date) },
                `до ${fmtDate(sub.end_date)}`
              )}</small
            >
          </div>
          {#if sub.is_active}
            <AdminBadge variant="success">{at("user_history_active", {}, "Активна")}</AdminBadge>
          {:else}
            <AdminBadge variant="muted"
              >{sub.status_from_panel || at("user_history_status_panel", {}, "История")}</AdminBadge
            >
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</Tabs.Content>
