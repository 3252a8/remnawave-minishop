<script lang="ts">
  import { Checkbox } from "$components/ui/index.js";
  import { Switch } from "$components/ui/primitives.js";
  import type { AdminSettingField } from "$lib/admin/settingsSections.js";
  import type { SettingsDirtyEntry } from "$lib/admin/stores/settingsStore.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  const rows = [
    [
      "payments",
      "USER_NOTIFICATION_PAYMENTS_TELEGRAM_ENABLED",
      "USER_NOTIFICATION_PAYMENTS_EMAIL_ENABLED",
    ],
    [
      "subscriptions",
      "SUBSCRIPTION_NOTIFICATIONS_ENABLED",
      "SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED",
    ],
    [
      "traffic",
      "USER_NOTIFICATION_TRAFFIC_TELEGRAM_ENABLED",
      "USER_NOTIFICATION_TRAFFIC_EMAIL_ENABLED",
    ],
    [
      "devices",
      "USER_NOTIFICATION_DEVICES_TELEGRAM_ENABLED",
      "USER_NOTIFICATION_DEVICES_EMAIL_ENABLED",
    ],
    [
      "limits",
      "TORRENT_BLOCKER_TELEGRAM_NOTIFICATIONS_ENABLED",
      "TORRENT_BLOCKER_EMAIL_NOTIFICATIONS_ENABLED",
    ],
    [
      "support",
      "USER_NOTIFICATION_SUPPORT_TELEGRAM_ENABLED",
      "USER_NOTIFICATION_SUPPORT_EMAIL_ENABLED",
    ],
    [
      "referrals",
      "USER_NOTIFICATION_REFERRALS_TELEGRAM_ENABLED",
      "USER_NOTIFICATION_REFERRALS_EMAIL_ENABLED",
    ],
  ] as const;

  const FALLBACK_KEY = "USER_NOTIFICATION_SINGLE_CHANNEL_FALLBACK_ENABLED";

  let {
    at,
    fields,
    settingsDirty,
    valueFor,
    onValueChange,
    resetField,
    isOverridden,
  }: {
    at: TranslateFn;
    fields: AdminSettingField[];
    settingsDirty: Record<string, SettingsDirtyEntry>;
    valueFor: (field: AdminSettingField) => unknown;
    onValueChange: (key: string, value: boolean) => void;
    resetField: (field: AdminSettingField) => void;
    isOverridden: (field: AdminSettingField) => boolean;
  } = $props();

  const fieldMap = $derived(new Map(fields.map((field) => [field.key, field])));
  const fallbackField = $derived(fieldMap.get(FALLBACK_KEY));

  function checked(key: string): boolean {
    const field = fieldMap.get(key);
    return field ? Boolean(valueFor(field)) : false;
  }

  function canReset(key: string): boolean {
    const field = fieldMap.get(key);
    return Boolean(field && (isOverridden(field) || settingsDirty[key]));
  }

  function reset(key: string): void {
    const field = fieldMap.get(key);
    if (field) resetField(field);
  }
</script>

<div class="notification-delivery">
  <div class="notification-delivery-intro">
    <strong>{at("notification_delivery_title", {}, "User notification delivery")}</strong>
    <small>
      {at(
        "notification_delivery_hint",
        {},
        "Choose channels for each automatic notification type. If both are off, this type is never sent."
      )}
    </small>
  </div>

  <div class="notification-delivery-table-wrap">
    <table class="notification-delivery-table">
      <thead>
        <tr>
          <th>{at("notification_delivery_type", {}, "Notification type")}</th>
          <th>{at("notification_delivery_telegram", {}, "Telegram")}</th>
          <th>{at("notification_delivery_email", {}, "Email")}</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as [id, telegramKey, emailKey]}
          <tr>
            <th scope="row">
              <strong>
                {at(`notification_delivery_category_${id}`, {}, id)}
              </strong>
              <small>{at(`notification_delivery_category_${id}_hint`, {}, "")}</small>
            </th>
            {#each [telegramKey, emailKey] as key}
              <td data-settings-anchor={`settings-field:${key}`}>
                <div class="notification-delivery-channel">
                  <Checkbox
                    checked={checked(key)}
                    disabled={!fieldMap.has(key)}
                    ariaLabel={`${at(`notification_delivery_category_${id}`, {}, id)} · ${key === telegramKey ? "Telegram" : "Email"}`}
                    onCheckedChange={(value) => onValueChange(key, value)}
                  />
                  {#if canReset(key)}
                    <button
                      type="button"
                      class="notification-delivery-reset"
                      title={at("reset", {}, "Reset")}
                      aria-label={at("reset", {}, "Reset")}
                      onclick={() => reset(key)}>↺</button
                    >
                  {/if}
                </div>
              </td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  {#if fallbackField}
    <div
      class="notification-delivery-fallback"
      data-settings-anchor={`settings-field:${FALLBACK_KEY}`}
    >
      <Switch.Root
        checked={checked(FALLBACK_KEY)}
        aria-label={at(
          "notification_delivery_fallback_title",
          {},
          "Use the only linked channel as a fallback"
        )}
        onCheckedChange={(value) => onValueChange(FALLBACK_KEY, value)}
        class="admin-switch-root"
      >
        <Switch.Thumb class="admin-switch-thumb" />
      </Switch.Root>
      <div>
        <strong>
          {at(
            "notification_delivery_fallback_title",
            {},
            "Use the only linked channel as a fallback"
          )}
        </strong>
        <small>
          {at(
            "notification_delivery_fallback_hint",
            {},
            "If the selected channel is not linked, use the user's only other available channel. This never overrides a row with both channels off."
          )}
        </small>
      </div>
      {#if canReset(FALLBACK_KEY)}
        <button
          type="button"
          class="notification-delivery-reset"
          title={at("reset", {}, "Reset")}
          aria-label={at("reset", {}, "Reset")}
          onclick={() => reset(FALLBACK_KEY)}>↺</button
        >
      {/if}
    </div>
  {/if}

  <small class="notification-delivery-note">
    {at(
      "notification_delivery_availability_hint",
      {},
      "A channel is available only when it is linked and delivery is configured. Temporary send errors do not trigger fallback."
    )}
  </small>
</div>

<style>
  .notification-delivery {
    display: grid;
    gap: 14px;
    width: 100%;
    min-width: 0;
  }

  .notification-delivery-intro,
  .notification-delivery-intro > small,
  .notification-delivery-fallback > div {
    display: grid;
    gap: 4px;
  }

  .notification-delivery-intro strong,
  .notification-delivery-fallback strong {
    color: var(--admin-text);
    font-size: 13px;
  }

  .notification-delivery-intro small,
  .notification-delivery-fallback small,
  .notification-delivery-note {
    color: var(--admin-muted);
    font-size: 11px;
    line-height: 1.45;
  }

  .notification-delivery-table-wrap {
    overflow-x: auto;
    border: 1px solid var(--admin-border);
    border-radius: 9px;
  }

  .notification-delivery-table {
    width: 100%;
    min-width: 470px;
    border-collapse: collapse;
  }

  .notification-delivery-table th,
  .notification-delivery-table td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--admin-border);
    text-align: left;
  }

  .notification-delivery-table thead th {
    background: color-mix(in srgb, var(--admin-surface-2) 78%, transparent);
    color: var(--admin-muted);
    font-size: 10px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  .notification-delivery-table thead th:not(:first-child),
  .notification-delivery-table td {
    width: 112px;
    text-align: center;
  }

  .notification-delivery-table tbody tr:last-child > * {
    border-bottom: 0;
  }

  .notification-delivery-table tbody th {
    display: grid;
    gap: 3px;
    font-weight: 400;
  }

  .notification-delivery-table tbody th strong {
    color: var(--admin-text);
    font-size: 12px;
  }

  .notification-delivery-table tbody th small {
    color: var(--admin-muted);
    font-size: 10px;
    font-weight: 400;
  }

  .notification-delivery-channel {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .notification-delivery-reset {
    display: inline-grid;
    place-items: center;
    width: 20px;
    height: 20px;
    padding: 0;
    border: 0;
    border-radius: 4px;
    background: transparent;
    color: var(--admin-muted);
    cursor: pointer;
  }

  .notification-delivery-reset:hover {
    background: var(--admin-surface-2);
    color: var(--admin-text);
  }

  .notification-delivery-fallback {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 10px;
    align-items: center;
    padding: 12px;
    border: 1px solid var(--admin-border);
    border-radius: 9px;
    background: color-mix(in srgb, var(--admin-surface-2) 58%, transparent);
  }

  @media (max-width: 560px) {
    .notification-delivery-table th,
    .notification-delivery-table td {
      padding: 9px;
    }
  }
</style>
