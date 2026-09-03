<script lang="ts">
  import { ArrowRight, TriangleAlert } from "$components/ui/icons.js";
  import { Checkbox, Input, Textarea } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminButton, AdminField } from "$components/patterns/admin/index.js";
  import type { PartnerRow } from "$lib/admin/previewMock/partnerProgram.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type DialogKind = "" | "create" | "rate" | "balance" | "import" | "status" | "link";
  type BalanceMode = "add" | "subtract" | "set";
  type ImportPreview = { found: number; new_clients: number; existing: number; conflicts: number };

  let {
    at,
    selectedPartner,
    previewMode,
    importPreview,
    balanceModes,
    balancePreviewValue,
    money,
    completeDialog,
    actionBusy,
    dialog = $bindable(),
    createUserId = $bindable(),
    createRate = $bindable(),
    importOnCreate = $bindable(),
    dialogRate = $bindable(),
    dialogReason = $bindable(),
    dialogAmount = $bindable(),
    balanceMode = $bindable(),
  }: {
    at: TranslateFn;
    selectedPartner: PartnerRow;
    previewMode: boolean;
    importPreview: ImportPreview;
    balanceModes: readonly BalanceMode[];
    balancePreviewValue: number;
    money: (value: number) => string;
    completeDialog: () => Promise<void>;
    actionBusy: boolean;
    dialog: DialogKind;
    createUserId: string;
    createRate: string;
    importOnCreate: boolean;
    dialogRate: string;
    dialogReason: string;
    dialogAmount: string;
    balanceMode: BalanceMode;
  } = $props();

  const rateChangeInvalid = $derived(
    dialog === "rate" &&
      (!dialogReason.trim() ||
        !Number.isFinite(Number(dialogRate)) ||
        Number(dialogRate) < 0 ||
        Number(dialogRate) > 100)
  );
</script>

<Dialog
  open={Boolean(dialog)}
  title={at(`partners_dialog_${dialog || "create"}_title`, {}, dialog)}
  description={dialog === "create" ? "" : selectedPartner.id}
  closeLabel={at("close", {}, "Close")}
  onclose={() => (dialog = "")}
  class="admin-dialog admin-dialog-compact admin-partners-dialog"
>
  <div class="admin-form partners-dialog-form" data-dialog-content>
    {#if dialog === "create"}
      <AdminField label={at("partners_user_search", {}, "Existing user")}>
        <Input
          class="input"
          placeholder={at("partners_user_search_placeholder", {}, "Name, username, email, or ID")}
          bind:value={createUserId}
        />
      </AdminField>
      <AdminField label={at("partners_rate_label", {}, "Commission rate, %")}>
        <Input class="input" type="number" min="0" max="100" step="0.01" bind:value={createRate} />
      </AdminField>
      <label class="partners-check">
        <Checkbox
          bind:checked={importOnCreate}
          ariaLabel={at("partners_import_on_create", {}, "Import referrals as clients")}
        />
        {at("partners_import_on_create", {}, "Import referrals as clients")}
      </label>
    {:else if dialog === "rate"}
      <AdminField
        label={at("partners_rate_label", {}, "Commission rate, %")}
        hint={at(
          "partners_rate_future_note",
          {},
          "The new rate applies only to future successful payments."
        )}
      >
        <Input class="input" type="number" min="0" max="100" step="0.01" bind:value={dialogRate} />
      </AdminField>
      <AdminField label={at("partners_reason_required", {}, "Reason (required)")}>
        <Textarea bind:value={dialogReason} rows={3} />
      </AdminField>
    {:else if dialog === "balance"}
      <div
        class="partners-segmented"
        role="group"
        aria-label={at("partners_col_amount", {}, "Amount")}
      >
        {#each balanceModes as mode (mode)}
          <button
            type="button"
            class:active={balanceMode === mode}
            aria-pressed={balanceMode === mode}
            onclick={() => (balanceMode = mode)}
          >
            {at(`partners_balance_${mode}`, {}, mode)}
          </button>
        {/each}
      </div>
      <AdminField label={at("partners_col_amount", {}, "Amount")}>
        <Input class="input" type="number" min="0" step="0.01" bind:value={dialogAmount} />
      </AdminField>
      <AdminField label={at("partners_balance_description", {}, "Description (optional)")}>
        <Textarea bind:value={dialogReason} rows={4} />
      </AdminField>
      <div class="partners-balance-preview">
        <span>{money(selectedPartner.available)}</span>
        <ArrowRight size={15} />
        <strong>{money(balancePreviewValue)}</strong>
      </div>
    {:else if dialog === "import"}
      <div class="partners-import-preview">
        <span>
          <strong>{previewMode ? 12 : importPreview.found}</strong>
          {at("partners_import_found", {}, "referrals found")}
        </span>
        <span>
          <strong>{previewMode ? 7 : importPreview.new_clients}</strong>
          {at("partners_import_new", {}, "new clients")}
        </span>
        <span>
          <strong>{previewMode ? 3 : importPreview.existing}</strong>
          {at("partners_import_existing", {}, "already assigned")}
        </span>
        <span>
          <strong>{previewMode ? 2 : importPreview.conflicts}</strong>
          {at("partners_import_conflicts", {}, "conflicts")}
        </span>
      </div>
      <div class="partners-warning">
        <TriangleAlert size={17} />{at(
          "partners_import_no_retro",
          {},
          "Historical payments will not be recalculated. Eligibility starts now."
        )}
      </div>
    {:else if dialog === "status"}
      <AdminField label={at("partners_reason", {}, "Reason")}>
        <Textarea bind:value={dialogReason} rows={4} />
      </AdminField>
      <div class="partners-warning">
        <TriangleAlert size={17} />{at(
          "partners_pause_effect",
          {},
          "New attribution, accruals, withdrawals, and balance spending will be paused."
        )}
      </div>
    {:else if dialog === "link"}
      <div class="partners-warning">
        <TriangleAlert size={17} />{at(
          "partners_rotate_warning",
          {},
          "The old code stops accepting new attributions immediately."
        )}
      </div>
    {/if}
    <div class="admin-dialog-actions">
      <AdminButton onclick={() => (dialog = "")}>{at("cancel", {}, "Cancel")}</AdminButton>
      <AdminButton
        variant={dialog === "status" || dialog === "link" ? "danger" : "primary"}
        onclick={completeDialog}
        disabled={actionBusy || rateChangeInvalid}
      >
        {at("confirm", {}, "Confirm")}
      </AdminButton>
    </div>
  </div>
</Dialog>
