<script>
  import { AdminBadge, AdminButton, AdminSelect } from "$components/patterns/admin/index.js";
  import { CheckCheck } from "$components/ui/icons.js";

  export let ticket;
  export let at = (key) => key;
  export let onPatch = () => {};
  export let onClose = () => {};

  $: statusOptions = ["open", "awaiting_user", "awaiting_admin", "resolved", "closed"].map(
    (item) => ({
      value: item,
      label: at(`support_status_${item}`, {}, item),
    })
  );
  $: priorityOptions = ["low", "normal", "high", "urgent"].map((item) => ({
    value: item,
    label: at(`support_priority_${item}`, {}, item),
  }));
  $: categoryOptions = ["billing", "technical", "account", "other"].map((item) => ({
    value: item,
    label: at(`support_category_${item}`, {}, item),
  }));
  $: statusVariant =
    ticket?.status === "closed" || ticket?.status === "resolved" ? "muted" : "success";
  $: priorityVariant =
    ticket?.priority === "urgent" ? "danger" : ticket?.priority === "high" ? "warning" : "muted";

  function patch(key, value) {
    if (!ticket || ticket[key] === value) return;
    onPatch({ [key]: value });
  }
</script>

{#if ticket}
  <div class="support-ticket-header">
    <div class="support-ticket-statusbar">
      <AdminBadge variant={statusVariant}>
        {at(`support_status_${ticket.status}`, {}, ticket.status)}
      </AdminBadge>
      <AdminBadge variant={priorityVariant}>
        {at(`support_priority_${ticket.priority}`, {}, ticket.priority)}
      </AdminBadge>
    </div>

    <div class="support-ticket-actions">
      <AdminButton
        class="support-ticket-close"
        variant="dangerSoft"
        onclick={onClose}
        disabled={ticket.status === "closed"}
      >
        <CheckCheck size={14} />
        {at("support_close_ticket", {}, "Закрыть тикет")}
      </AdminButton>
    </div>

    <div class="support-ticket-controls">
      <AdminSelect
        value={ticket.status}
        items={statusOptions}
        ariaLabel={at("support_status", {}, "Статус")}
        onValueChange={(value) => patch("status", value)}
      />
      <AdminSelect
        value={ticket.priority}
        items={priorityOptions}
        ariaLabel={at("support_priority", {}, "Приоритет")}
        onValueChange={(value) => patch("priority", value)}
      />
      <AdminSelect
        value={ticket.category}
        items={categoryOptions}
        ariaLabel={at("support_category", {}, "Категория")}
        onValueChange={(value) => patch("category", value)}
      />
    </div>
  </div>
{/if}
