<script>
  import { Label, Select, Separator, Tabs } from "$components/ui/primitives.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminBadge, AdminButton, AdminTrafficCard } from "$components/patterns/admin/index.js";
  import {
    CalendarDays, Copy, CreditCard, ExternalLink, Eye, Info, Key,
    Mail, Map, MessageSquare, MousePointerClick, QrCode, RefreshCw, Send,
    Plus, Settings, Shield, Trash2, User, UserMinus, UserPlus, Users
  } from "$components/ui/icons.js";
  import { getContext } from "svelte";
  
  export let at;
  export let fmtDate;
  export let fmtMoney;
  export let resolvedAvatarUrl;
  export let userDisplayName;
  export let userSecondaryName;
  export let paymentStatusVariant;
  export let trafficPercentValue;
  export let trafficLeftLabel;
  export let trafficOfLabel;
  export let userInitials = () => "";
  export let fmtDateShort = (v) => v;
  
  function pretty(val) {
    if (val === true) return at("yes", {}, "Да");
    if (val === false) return at("no", {}, "Нет");
    return String(val ?? "—");
  }

  const usersStore = getContext("usersStore");
  
  $: ({
    openedUser,
    openedUserDetail,
    userDetailLoading,
    userMessageDraft,
    userExtendDays,
    userActionBusy,
    userDeleteOpen,
    userBanConfirmOpen,
    userMessageConfirmOpen,
    userDetailTab,
  } = $usersStore);

</script>

<Dialog
  open={Boolean(openedUser)}
  title={openedUser ? at("user_detail_title", { id: openedUser.user_id }, `Пользователь #${openedUser.user_id}`) : ""}
  description={openedUser?.username ? "@" + openedUser.username : ""}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={usersStore.closeUser}
  class="admin-dialog admin-user-dialog"
>
  {#if openedUser}
    {#if userDetailLoading || !openedUserDetail}
      <p class="admin-muted">{at("loading", {}, "Загрузка…")}</p>
    {:else}
      <div class="admin-user-dialog-body">
        <aside class="admin-user-aside">
          <div class="admin-user-summary">
            <span class="admin-avatar admin-avatar-lg">
              {#if resolvedAvatarUrl(openedUser)}
                <img src={resolvedAvatarUrl(openedUser)} alt="" loading="lazy" referrerpolicy="no-referrer" />
              {:else}
                <span>{userInitials(openedUser)}</span>
              {/if}
            </span>
            <div class="admin-user-summary-meta">
              <strong>{userDisplayName(openedUser)}</strong>
              <small>{userSecondaryName(openedUser)}</small>
              <div class="admin-user-summary-tags">
                {#if openedUser.is_banned}
                  <AdminBadge variant="danger">{at("badge_banned", {}, "Бан")}</AdminBadge>
                {:else}
                  <AdminBadge variant="success">{at("badge_active", {}, "Активен")}</AdminBadge>
                {/if}
                {#if openedUserDetail.active_subscription}
                  <AdminBadge variant="success">{at("badge_subscription", {}, "Подписка")}</AdminBadge>
                {:else}
                  <AdminBadge variant="muted">{at("badge_no_subscription", {}, "Без подписки")}</AdminBadge>
                {/if}
              </div>
            </div>
          </div>

          <div class="admin-user-stats">
            <div class="admin-user-stat">
              <span>{at("user_label_paid", {}, "Заплачено")}</span>
              <strong>{fmtMoney(openedUserDetail.total_paid)}</strong>
            </div>
            <div class="admin-user-stat">
              <span>{at("user_label_logs", {}, "Логов")}</span>
              <strong>{openedUserDetail.log_count}</strong>
            </div>
          </div>

          <div class="admin-subsection-title">{at("user_section_profile", {}, "Профиль")}</div>
          <ul class="admin-meta-list">
            <li><span>ID</span><strong>{openedUser.user_id}</strong></li>
            <li><span>Telegram ID</span><strong>{openedUser.telegram_id || "—"}</strong></li>
            <li><span>Username</span><strong>{openedUser.username ? "@" + openedUser.username : "—"}</strong></li>
            <li><span>Email</span><strong class="admin-meta-truncate">{openedUser.email || "—"}</strong></li>
            <li><span>{at("user_label_registration", {}, "Регистрация")}</span><strong>{fmtDate(openedUser.registration_date)}</strong></li>
            <li><span>{at("user_label_ref_code", {}, "Реф. код")}</span><strong>{openedUserDetail.referral?.code || openedUserDetail.user?.referral_code || "—"}</strong></li>
          </ul>

          {#if openedUserDetail.subscription_url || openedUserDetail.referral?.bot_link || openedUserDetail.referral?.webapp_link}
            <div class="admin-subsection-title">{at("user_section_links", {}, "Ссылки")}</div>
            <div class="admin-link-list">
              {#if openedUserDetail.subscription_url}
                <div class="admin-link-row">
                  <div class="admin-link-row-meta">
                    <span class="admin-link-row-label">{at("status_subscription", {}, "Подписка")}</span>
                    <a class="admin-link-row-url" href={openedUserDetail.subscription_url} target="_blank" rel="noopener">
                      {openedUserDetail.subscription_url}
                    </a>
                  </div>
                  <AdminButton size="icon" variant="icon" title={at("user_copy_tooltip", {}, "Скопировать")} onclick={() => usersStore.copyToClipboard(openedUserDetail.subscription_url, at("user_sub_link_copied", {}, "Ссылка на подписку скопирована"))}>
                    <Copy size={14} />
                  </AdminButton>
                </div>
              {/if}
              {#if openedUserDetail.referral?.bot_link}
                <div class="admin-link-row">
                  <div class="admin-link-row-meta">
                    <span class="admin-link-row-label">{at("user_label_ref_bot", {}, "Реф. ссылка (бот)")}</span>
                    <a class="admin-link-row-url" href={openedUserDetail.referral.bot_link} target="_blank" rel="noopener">
                      {openedUserDetail.referral.bot_link}
                    </a>
                  </div>
                  <AdminButton size="icon" variant="icon" title={at("user_copy_tooltip", {}, "Скопировать")} onclick={() => usersStore.copyToClipboard(openedUserDetail.referral.bot_link, at("user_ref_link_copied", {}, "Реф. ссылка скопирована"))}>
                    <Copy size={14} />
                  </AdminButton>
                </div>
              {/if}
              {#if openedUserDetail.referral?.webapp_link}
                <div class="admin-link-row">
                  <div class="admin-link-row-meta">
                    <span class="admin-link-row-label">{at("user_label_ref_web", {}, "Реф. ссылка (веб)")}</span>
                    <a class="admin-link-row-url" href={openedUserDetail.referral.webapp_link} target="_blank" rel="noopener">
                      {openedUserDetail.referral.webapp_link}
                    </a>
                  </div>
                  <AdminButton size="icon" variant="icon" title={at("user_copy_tooltip", {}, "Скопировать")} onclick={() => usersStore.copyToClipboard(openedUserDetail.referral.webapp_link, at("user_ref_link_copied", {}, "Реф. ссылка скопирована"))}>
                    <Copy size={14} />
                  </AdminButton>
                </div>
              {/if}
            </div>
          {/if}
        </aside>

        <main class="admin-user-main">
          <Tabs.Root bind:value={$usersStore.userDetailTab} class="admin-tabs-root admin-user-tabs-root">
            <Tabs.List class="admin-tabs-list">
              <Tabs.Trigger value="subscription" class="admin-tabs-trigger">{at("user_tab_subscription", {}, "Подписка")}</Tabs.Trigger>
              <Tabs.Trigger value="activity" class="admin-tabs-trigger">{at("user_tab_activity", {}, "Активность")}</Tabs.Trigger>
              <Tabs.Trigger value="actions" class="admin-tabs-trigger">{at("user_tab_actions", {}, "Действия")}</Tabs.Trigger>
            </Tabs.List>

            <Tabs.Content value="subscription" class="admin-tabs-content">
          {#if openedUserDetail.active_subscription}
            <ul class="admin-meta-list">
              <li><span>{at("user_label_active_until", {}, "Активна до")}</span><strong>{fmtDate(openedUserDetail.active_subscription.end_date)}</strong></li>
              <li><span>{at("user_label_tariff", {}, "Тариф")}</span><strong>{openedUserDetail.active_subscription.tariff_key || "—"}</strong></li>
              <li><span>{at("user_label_auto_renew", {}, "Авто-продление")}</span><strong>{pretty(openedUserDetail.active_subscription.auto_renew_enabled)}</strong></li>
              <li><span>{at("user_label_provider", {}, "Провайдер")}</span><strong>{openedUserDetail.active_subscription.provider || "—"}</strong></li>
            </ul>
            <div class="admin-traffic-summary">
              <AdminTrafficCard
                title={at("user_label_main_traffic", {}, "Основной трафик")}
                value={trafficOfLabel(openedUserDetail.active_subscription.traffic_used_bytes, openedUserDetail.active_subscription.traffic_limit_bytes)}
                left={at("user_traffic_left", { left: trafficLeftLabel(openedUserDetail.active_subscription.traffic_used_bytes, openedUserDetail.active_subscription.traffic_limit_bytes) }, "Осталось: " + trafficLeftLabel(openedUserDetail.active_subscription.traffic_used_bytes, openedUserDetail.active_subscription.traffic_limit_bytes))}
                percent={trafficPercentValue(openedUserDetail.active_subscription.traffic_used_bytes, openedUserDetail.active_subscription.traffic_limit_bytes)}
                warning={openedUserDetail.active_subscription.is_throttled}
                label={at("aria_label_main_traffic", {}, "Использование основного трафика")}
              />
              {#if Number(openedUserDetail.active_subscription.premium_limit_bytes || 0) > 0}
                <AdminTrafficCard
                  premium
                  title={at("user_label_premium_squads", {}, "Premium-сквады")}
                  value={trafficOfLabel(openedUserDetail.active_subscription.premium_used_bytes, openedUserDetail.active_subscription.premium_limit_bytes)}
                  left={at("user_traffic_left", { left: trafficLeftLabel(openedUserDetail.active_subscription.premium_used_bytes, openedUserDetail.active_subscription.premium_limit_bytes) }, "Осталось: " + trafficLeftLabel(openedUserDetail.active_subscription.premium_used_bytes, openedUserDetail.active_subscription.premium_limit_bytes))}
                  percent={trafficPercentValue(openedUserDetail.active_subscription.premium_used_bytes, openedUserDetail.active_subscription.premium_limit_bytes)}
                  warning={openedUserDetail.active_subscription.premium_is_limited}
                  label={at("aria_label_premium_traffic", {}, "Использование premium-трафика")}
                />
              {/if}
            </div>
          {:else}
            <p class="admin-muted">{at("user_no_active_subscription", {}, "Активной подписки нет")}</p>
          {/if}

          {#if (openedUserDetail.subscriptions || []).length}
            <Separator.Root class="admin-separator" />
            <div class="admin-subsection-title">{at("user_history_title", { count: openedUserDetail.subscriptions.length }, `История подписок · ${openedUserDetail.subscriptions.length}`)}</div>
            <div class="admin-mini-list">
              {#each openedUserDetail.subscriptions.slice(0, 8) as sub}
                <div class="admin-mini-list-row">
                  <div>
                    <strong>{sub.tariff_key || at("user_history_no_tariff", {}, "Без тарифа")}</strong>
                    <small>{at("user_history_until", { date: fmtDate(sub.end_date) }, `до ${fmtDate(sub.end_date)}`)}</small>
                  </div>
                  {#if sub.is_active}
                    <AdminBadge variant="success">{at("user_history_active", {}, "Активна")}</AdminBadge>
                  {:else}
                    <AdminBadge variant="muted">{sub.status_from_panel || at("user_history_status_panel", {}, "История")}</AdminBadge>
                  {/if}
                </div>
              {/each}
            </div>
          {/if}
        </Tabs.Content>

        <Tabs.Content value="activity" class="admin-tabs-content">
          <div class="admin-subsection-title">{at("user_recent_payments_title", { count: (openedUserDetail.recent_payments || []).length }, `Последние платежи · ${(openedUserDetail.recent_payments || []).length}`)}</div>
          {#if (openedUserDetail.recent_payments || []).length}
            <div class="admin-mini-list">
              {#each openedUserDetail.recent_payments.slice(0, 8) as payment}
                <div class="admin-mini-list-row">
                  <div>
                    <strong>{fmtMoney(payment.amount, payment.currency)}</strong>
                    <small>{payment.provider} · {fmtDateShort(payment.created_at)}</small>
                  </div>
                  <AdminBadge variant={paymentStatusVariant(payment.status)}>{payment.status}</AdminBadge>
                </div>
              {/each}
            </div>
          {:else}
            <p class="admin-muted">{at("user_no_payments", {}, "Платежей нет")}</p>
          {/if}
        </Tabs.Content>

        <Tabs.Content value="actions" class="admin-tabs-content admin-actions-tab">
          <div class="admin-user-quick-actions">
            <AdminButton class="admin-reset-trial-btn" onclick={usersStore.resetTrialUser} disabled={userActionBusy}>
              <RefreshCw size={14} /> {at("user_btn_reset_trial", {}, "Сбросить триал")}
            </AdminButton>
            <Label.Root class="admin-field-label admin-extend-field">
              <span>{at("user_label_extend", {}, "Продлить подписку")}</span>
              <div class="admin-extend-control">
                <input class="input" type="number" min="1" bind:value={$usersStore.userExtendDays} aria-label={at("user_label_extend_days", {}, "Дней")} />
                <AdminButton onclick={usersStore.extendUser} disabled={userActionBusy}>
                  <Plus size={14} /> {at("user_btn_extend", {}, "Продлить")}
                </AdminButton>
              </div>
            </Label.Root>
          </div>

          <Label.Root class="admin-field-label">
            <span>{at("user_label_telegram_msg", {}, "Сообщение в Telegram")}</span>
            <small>{at("user_hint_telegram_msg", {}, "Поддерживается HTML-разметка Telegram")}</small>
            <textarea class="admin-textarea" rows="3" placeholder={at("user_placeholder_msg", {}, "Текст сообщения")} bind:value={$usersStore.userMessageDraft}></textarea>
          </Label.Root>
          <div class="admin-message-actions">
            <AdminButton onclick={usersStore.previewUserMessage} disabled={userActionBusy || !userMessageDraft.trim()}>
              <Eye size={14} /> {at("btn_preview_tg", {}, "Превью в Telegram")}
            </AdminButton>
            <AdminButton variant="primary" onclick={usersStore.requestSendUserMessage} disabled={userActionBusy || !userMessageDraft.trim()}>
              <Send size={14} /> {at("btn_send_msg", {}, "Отправить сообщение")}
            </AdminButton>
          </div>

          <section class="admin-danger-zone">
            <header class="admin-danger-zone-head">
              <strong>{at("user_danger_zone_title", {}, "Опасные действия")}</strong>
              <small>{at("user_danger_zone_subtitle", {}, "Эти действия требуют подтверждения и (для удаления) необратимы")}</small>
            </header>
            <div class="admin-action-grid">
              {#if openedUser.is_banned}
                <AdminButton variant="dangerSoft" onclick={usersStore.requestBanToggle} disabled={userActionBusy}>
                  <UserPlus size={14} /> {at("btn_unban", {}, "Разбанить пользователя")}
                </AdminButton>
              {:else}
                <AdminButton variant="danger" onclick={usersStore.requestBanToggle} disabled={userActionBusy}>
                  <UserMinus size={14} /> {at("btn_ban", {}, "Заблокировать")}
                </AdminButton>
              {/if}
              <AdminButton variant="danger" onclick={() => usersStore.updateState({ userDeleteOpen: true })} disabled={userActionBusy}>
                <Trash2 size={14} /> {at("btn_delete_account", {}, "Удалить аккаунт")}
              </AdminButton>
            </div>
          </section>
        </Tabs.Content>
          </Tabs.Root>
        </main>
      </div>
    {/if}
  {/if}
</Dialog>

<Dialog
  open={userMessageConfirmOpen}
  title={at("user_msg_confirm_title", {}, "Отправить сообщение пользователю?")}
  description={openedUser ? at("user_msg_confirm_recipient", { name: userDisplayName(openedUser) }, `Получатель: ${userDisplayName(openedUser)}`) : ""}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={() => usersStore.updateState({ userMessageConfirmOpen: false })}
  class="admin-dialog"
>
  <div class="admin-confirm-message-preview">{userMessageDraft}</div>
  <div class="admin-dialog-actions">
    <AdminButton onclick={() => usersStore.updateState({ userMessageConfirmOpen: false })}>{at("btn_cancel", {}, "Отмена")}</AdminButton>
    <AdminButton variant="primary" onclick={usersStore.sendUserMessage} disabled={userActionBusy || !userMessageDraft.trim()}>
      <Send size={14} /> {at("btn_confirm_send", {}, "Подтвердить отправку")}
    </AdminButton>
  </div>
</Dialog>

<Dialog
  open={userBanConfirmOpen}
  title={at("user_ban_confirm_title", {}, "Заблокировать пользователя?")}
  description={openedUser ? at("user_ban_confirm_subtitle", { name: userDisplayName(openedUser) }, `${userDisplayName(openedUser)} больше не сможет взаимодействовать с ботом. Действие можно отменить позже.`) : ""}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={() => usersStore.updateState({ userBanConfirmOpen: false })}
  class="admin-dialog"
>
  <div class="admin-dialog-actions">
    <AdminButton onclick={() => usersStore.updateState({ userBanConfirmOpen: false })}>{at("btn_cancel", {}, "Отмена")}</AdminButton>
    <AdminButton variant="danger" onclick={() => usersStore.applyBanToggle(true)} disabled={userActionBusy}>
      <UserMinus size={14} /> {at("btn_ban", {}, "Заблокировать")}
    </AdminButton>
  </div>
</Dialog>

<Dialog
  open={userDeleteOpen}
  title={at("user_delete_confirm_title", {}, "Удалить пользователя?")}
  description={at("user_delete_confirm_subtitle", {}, "Действие необратимо. Удалятся все платежи, подписки и логи.")}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={() => usersStore.updateState({ userDeleteOpen: false })}
  class="admin-dialog"
>
  <div class="admin-form-row">
    <AdminButton onclick={() => usersStore.updateState({ userDeleteOpen: false })}>{at("btn_cancel", {}, "Отмена")}</AdminButton>
    <AdminButton variant="danger" onclick={usersStore.deleteUser} disabled={userActionBusy}>
      <Trash2 size={14} /> {at("btn_confirm_delete", {}, "Подтвердить удаление")}
    </AdminButton>
  </div>
</Dialog>
