<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import { AdminButton, AdminSectionHeader } from "$components/patterns/admin/index.js";
  import { Textarea } from "$components/ui/index.js";
  import { Eye, Send } from "$components/ui/icons.js";
  import type { TranslateFn } from "./userDetailTypes";

  let {
    at,
    userActionBusy = false,
    userMessageDraft = "",
  }: {
    at: TranslateFn;
    userActionBusy?: boolean;
    userMessageDraft?: string;
  } = $props();

  const usersStore = getUsersStore();
</script>

<section class="admin-user-action-sheet admin-user-action-sheet--telegram-message">
  <AdminSectionHeader
    title={at("user_label_telegram_msg", {}, "Сообщение в Telegram")}
    description={at("user_hint_telegram_msg", {}, "Поддерживается HTML-разметка Telegram")}
  />
  <div class="admin-user-action-sheet-body">
    <Textarea
      class="admin-textarea"
      rows={3}
      placeholder={at("user_placeholder_msg", {}, "Текст сообщения")}
      ariaLabel={at("user_label_telegram_msg", {}, "Сообщение в Telegram")}
      bind:value={usersStore.userMessageDraft}
    />
    <div class="admin-message-actions">
      <AdminButton
        onclick={usersStore.previewUserMessage}
        disabled={userActionBusy || !userMessageDraft.trim()}
      >
        <Eye size={14} />
        {at("btn_preview_tg", {}, "Превью в Telegram")}
      </AdminButton>
      <AdminButton
        variant="primary"
        data-admin-action="request-user-message"
        onclick={usersStore.requestSendUserMessage}
        disabled={userActionBusy || !userMessageDraft.trim()}
      >
        <Send size={14} />
        {at("btn_send_msg", {}, "Отправить сообщение")}
      </AdminButton>
    </div>
  </div>
</section>
