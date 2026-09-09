<script lang="ts">
  import { Switch } from "$components/ui/primitives.js";
  import type { NotificationPreferences } from "$lib/webapp/notificationPreferences.js";

  type Props = {
    preferences: NotificationPreferences;
    disabled?: boolean;
    emailOnly?: boolean;
    title: string;
    description: string;
    marketingLabel: string;
    marketingHint: string;
    systemLabel: string;
    systemHint: string;
    emailLabel: string;
    telegramLabel: string;
    note?: string;
    onChange?: (preferences: NotificationPreferences) => void;
  };

  let {
    preferences,
    disabled = false,
    emailOnly = false,
    title,
    description,
    marketingLabel,
    marketingHint,
    systemLabel,
    systemHint,
    emailLabel,
    telegramLabel,
    note = "",
    onChange = () => {},
  }: Props = $props();

  const rows = $derived([
    { id: "marketing", label: marketingLabel, hint: marketingHint },
    { id: "system", label: systemLabel, hint: systemHint },
  ] as const);

  function preferenceKey(
    category: "marketing" | "system",
    channel: "email" | "telegram"
  ): keyof NotificationPreferences {
    return `${category}_${channel}`;
  }

  function toggle(
    category: "marketing" | "system",
    channel: "email" | "telegram",
    checked: boolean
  ): void {
    onChange({ ...preferences, [preferenceKey(category, channel)]: checked });
  }
</script>

<section class="notification-preferences" aria-labelledby="notification-preferences-title">
  <div class="notification-preferences__intro">
    <strong id="notification-preferences-title">{title}</strong>
    <small>{description}</small>
  </div>

  <div class="notification-preferences__grid" class:email-only={emailOnly}>
    <div class="notification-preferences__header" aria-hidden="true"></div>
    <div class="notification-preferences__channel">{emailLabel}</div>
    {#if !emailOnly}
      <div class="notification-preferences__channel">{telegramLabel}</div>
    {/if}

    {#each rows as row (row.id)}
      <div class="notification-preferences__copy">
        <strong>{row.label}</strong>
        <small>{row.hint}</small>
      </div>
      <div class="notification-preferences__control" data-channel-label={emailLabel}>
        <Switch.Root
          checked={preferences[preferenceKey(row.id, "email")]}
          {disabled}
          aria-label={`${row.label} · ${emailLabel}`}
          onCheckedChange={(checked) => toggle(row.id, "email", checked)}
          class="notification-preferences__switch"
        >
          <Switch.Thumb class="notification-preferences__thumb" />
        </Switch.Root>
      </div>
      {#if !emailOnly}
        <div class="notification-preferences__control" data-channel-label={telegramLabel}>
          <Switch.Root
            checked={preferences[preferenceKey(row.id, "telegram")]}
            {disabled}
            aria-label={`${row.label} · ${telegramLabel}`}
            onCheckedChange={(checked) => toggle(row.id, "telegram", checked)}
            class="notification-preferences__switch"
          >
            <Switch.Thumb class="notification-preferences__thumb" />
          </Switch.Root>
        </div>
      {/if}
    {/each}
  </div>

  {#if note}
    <p class="notification-preferences__note">{note}</p>
  {/if}
</section>

<style>
  .notification-preferences {
    display: grid;
    gap: 16px;
    padding: 18px;
    border: 1px solid var(--border, var(--admin-border, #26303b));
    border-radius: var(--radius-lg, 18px);
    background: var(--card, var(--admin-surface, #0e1319));
    color: var(--foreground, var(--admin-text, #f4f7fa));
  }

  .notification-preferences__intro,
  .notification-preferences__copy {
    display: grid;
    gap: 4px;
  }

  .notification-preferences__intro > strong {
    font-size: 16px;
  }

  .notification-preferences small,
  .notification-preferences__note {
    color: var(--muted-foreground, var(--admin-muted, #8e9aaa));
    line-height: 1.45;
  }

  .notification-preferences__grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 86px 86px;
    overflow: hidden;
    border: 1px solid var(--border, var(--admin-border, #26303b));
    border-radius: 14px;
  }

  .notification-preferences__grid.email-only {
    grid-template-columns: minmax(0, 1fr) 92px;
  }

  .notification-preferences__header,
  .notification-preferences__channel,
  .notification-preferences__copy,
  .notification-preferences__control {
    padding: 13px 14px;
    border-bottom: 1px solid var(--border, var(--admin-border, #26303b));
  }

  .notification-preferences__header,
  .notification-preferences__channel {
    background: color-mix(in srgb, var(--card, #0e1319) 82%, white 4%);
  }

  .notification-preferences__channel {
    color: var(--muted-foreground, var(--admin-muted, #8e9aaa));
    font-size: 11px;
    font-weight: 700;
    text-align: center;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .notification-preferences__copy {
    min-width: 0;
  }

  .notification-preferences__copy strong {
    font-size: 13px;
  }

  .notification-preferences__copy small {
    font-size: 11px;
  }

  .notification-preferences__control {
    display: grid;
    place-items: center;
    border-left: 1px solid var(--border, var(--admin-border, #26303b));
  }

  .notification-preferences__copy:nth-last-child(-n + 3),
  .notification-preferences__control:nth-last-child(-n + 2) {
    border-bottom: 0;
  }

  :global(.notification-preferences__switch) {
    position: relative;
    width: 42px;
    height: 24px;
    padding: 2px;
    border: 0;
    border-radius: 999px;
    background: #3b4653;
    cursor: pointer;
    transition: background 160ms ease;
  }

  :global(.notification-preferences__switch[data-state="checked"]) {
    background: var(--primary, var(--admin-accent, #00fe7a));
  }

  :global(.notification-preferences__switch:disabled) {
    cursor: wait;
    opacity: 0.58;
  }

  :global(.notification-preferences__thumb) {
    display: block;
    width: 20px;
    height: 20px;
    border-radius: 999px;
    background: #fff;
    box-shadow: 0 1px 4px rgb(0 0 0 / 35%);
    transform: translateX(0);
    transition: transform 160ms ease;
  }

  :global(.notification-preferences__thumb[data-state="checked"]) {
    transform: translateX(18px);
  }

  .notification-preferences__note {
    margin: 0;
    font-size: 11px;
  }

  @media (max-width: 640px) {
    .notification-preferences {
      padding: 15px;
    }

    .notification-preferences__grid,
    .notification-preferences__grid.email-only {
      grid-template-columns: minmax(0, 1fr);
    }

    .notification-preferences__header,
    .notification-preferences__channel {
      display: none;
    }

    .notification-preferences__copy,
    .notification-preferences__control {
      padding: 12px 14px;
      border-left: 0;
      border-bottom: 1px solid var(--border, var(--admin-border, #26303b));
    }

    .notification-preferences__copy {
      padding-block: 14px;
      background: color-mix(in srgb, var(--card, #0e1319) 82%, white 4%);
    }

    .notification-preferences__control {
      display: flex;
      min-height: 48px;
      align-items: center;
      justify-content: space-between;
    }

    .notification-preferences__control::before {
      content: attr(data-channel-label);
      color: var(--muted-foreground, var(--admin-muted, #8e9aaa));
      font-size: 12px;
      font-weight: 700;
    }

    .notification-preferences__copy:nth-last-child(-n + 3),
    .notification-preferences__control:nth-last-child(-n + 2) {
      border-bottom: 1px solid var(--border, var(--admin-border, #26303b));
    }

    .notification-preferences__control:last-child {
      border-bottom: 0;
    }
  }
</style>
