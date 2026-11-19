<script lang="ts">
  import { AdminButton, AdminField, AdminSelect } from "$components/patterns/admin/index.js";
  import { CheckCheck } from "$components/ui/icons.js";
  import type { SupportTicketLike, TranslateFn } from "./types";

  type PatchableKey = "category" | "priority" | "status";
  type Props = {
    ticket: SupportTicketLike | null;
    at?: TranslateFn;
    onPatch?: (updates: Partial<Record<PatchableKey, string>>) => void;
    onClose?: () => void;
  };

  let { ticket, at = (key) => key, onPatch = () => {}, onClose = () => {} }: Props = $props();

  const statusOptions = $derived(
    ["open", "awaiting_user", "awaiting_admin", "resolved", "closed"].map((item) => ({
      value: item,
      label: at(`support_status_${item}`, {}, item),
    }))
  );
  const priorityOptions = $derived(
    ["low", "normal", "high", "urgent"].map((item) => ({
      value: item,
      label: at(`support_priority_${item}`, {}, item),
    }))
  );
  const categoryOptions = $derived(
    ["billing", "technical", "account", "other"].map((item) => ({
      value: item,
      label: at(`support_category_${item}`, {}, item),
    }))
  );
  function patch(key: PatchableKey, value: string) {
    if (!ticket || ticket[key] === value) return;
    onPatch({ [key]: value });
  }
</script>

{#if ticket}
  <div class="support-ticket-header">
    <div class="support-ticket-controls">
      <AdminField label={at("support_status", {}, "Status")}>
        <AdminSelect
          value={ticket.status}
          items={statusOptions}
          ariaLabel={at("support_status", {}, "Status")}
          onValueChange={(value) => patch("status", value)}
        />
      </AdminField>
      <AdminField label={at("support_priority", {}, "Priority")}>
        <AdminSelect
          value={ticket.priority}
          items={priorityOptions}
          ariaLabel={at("support_priority", {}, "Priority")}
          onValueChange={(value) => patch("priority", value)}
        />
      </AdminField>
      <AdminField label={at("support_category", {}, "Category")}>
        <AdminSelect
          value={ticket.category}
          items={categoryOptions}
          ariaLabel={at("support_category", {}, "Category")}
          onValueChange={(value) => patch("category", value)}
        />
      </AdminField>
    </div>
    <div class="support-ticket-actions">
      <AdminButton
        class="support-ticket-close"
        variant="dangerSoft"
        onclick={onClose}
        disabled={ticket.status === "closed"}
      >
        <CheckCheck size={14} />
        {at("support_close_ticket", {}, "Close")}
      </AdminButton>
    </div>
  </div>
{/if}
