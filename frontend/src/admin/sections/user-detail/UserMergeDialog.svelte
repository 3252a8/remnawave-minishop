<script lang="ts">
  import { getAdminApi } from "$lib/admin/context";
  import { AdminButton, AdminField, AdminUserCell } from "$components/patterns/admin/index.js";
  import AdminUserPicker from "$components/patterns/admin/AdminUserPicker.svelte";
  import { Input } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { ArrowRight, Merge, TriangleAlert } from "$components/ui/icons.js";
  import {
    fetchMergeContext,
    fetchMergeUser,
    mergeErrorKey,
    mergeErrorBlocksRetry,
    mergeUsers,
    type UserMergeContext,
  } from "$lib/admin/userMergeApi.js";
  import { userDisplayName, userInitials, userSecondaryName } from "$lib/admin/users.js";
  import type { AdminUser, AdminUserDetail } from "$lib/admin/stores/usersStoreState.js";
  import type { TranslateFn, DateFormatter } from "./userDetailTypes.js";
  import UserMergeAccountCard from "./UserMergeAccountCard.svelte";

  let {
    open,
    target,
    at,
    fmtDate,
    onclose,
    onmerged,
    oncomplete,
  }: {
    open: boolean;
    target: AdminUserDetail;
    at: TranslateFn;
    fmtDate: DateFormatter;
    onclose: () => void;
    onmerged: (detail: AdminUserDetail) => void;
    oncomplete: (source: AdminUser, target: AdminUser) => void;
  } = $props();
  const api = getAdminApi();
  let source = $state<AdminUserDetail | null>(null);
  let freshTarget = $state<AdminUserDetail | null>(null);
  let sourceContext = $state<UserMergeContext | null>(null);
  let targetContext = $state<UserMergeContext | null>(null);
  let selected = $state<AdminUser | null>(null);
  let confirmation = $state("");
  let stage = $state<"select" | "confirm">("select");
  let loading = $state(false);
  let merging = $state(false);
  let error = $state("");
  let mergeBlocked = $state(false);
  let errorElement = $state<HTMLDivElement | null>(null);
  let result = $state<"complete" | "pending" | null>(null);
  let generation = 0;
  const targetId = $derived(Number(target.user.user_id));
  const knownConflict = $derived.by(() => {
    if (!source || !freshTarget || !sourceContext || !targetContext) return "";
    if (
      source.user.telegram_id &&
      freshTarget.user.telegram_id &&
      source.user.telegram_id !== freshTarget.user.telegram_id
    )
      return "user_merge_telegram_conflict";
    const providers = new Set(targetContext.auth_identities.map((identity) => identity.provider));
    if (sourceContext.auth_identities.some((identity) => providers.has(identity.provider)))
      return "user_merge_provider_conflict";
    return "";
  });
  const canMerge = $derived(
    stage === "confirm" &&
      source &&
      freshTarget &&
      sourceContext?.merge_eligibility.allowed &&
      targetContext?.merge_eligibility.allowed &&
      Number(source.user.user_id) !== targetId &&
      confirmation.trim() === String(targetId) &&
      !knownConflict &&
      !mergeBlocked &&
      !merging &&
      !loading &&
      !result
  );
  $effect(() => {
    if (error && errorElement) errorElement.focus();
  });

  $effect(() => {
    void targetId;
    void open;
    generation += 1;
    source = null;
    freshTarget = null;
    sourceContext = null;
    targetContext = null;
    selected = null;
    confirmation = "";
    stage = "select";
    loading = false;
    merging = false;
    error = "";
    mergeBlocked = false;
    result = null;
    return () => {
      generation += 1;
    };
  });

  function clearSelection() {
    generation += 1;
    source = null;
    freshTarget = null;
    sourceContext = null;
    targetContext = null;
    selected = null;
    confirmation = "";
    error = "";
    mergeBlocked = false;
    loading = false;
  }

  async function selectSource(user: AdminUser) {
    if (merging || result) return;
    clearSelection();
    if (Number(user.user_id) === targetId) {
      error = at("user_merge_same_user");
      return;
    }
    selected = user;
    const request = generation;
    loading = true;
    try {
      const [sourceDetail, targetDetail, sourceInfo, targetInfo] = await Promise.all([
        fetchMergeUser(api, String(user.user_id)),
        fetchMergeUser(api, String(targetId)),
        fetchMergeContext(api, Number(user.user_id)),
        fetchMergeContext(api, targetId),
      ]);
      if (request !== generation) return;
      if (Number(sourceDetail.user.user_id) === targetId) {
        error = at("user_merge_same_user");
        return;
      }
      if (
        Number(sourceDetail.user.user_id) !== Number(user.user_id) ||
        Number(targetDetail.user.user_id) !== targetId ||
        sourceInfo.user_id !== Number(user.user_id) ||
        targetInfo.user_id !== targetId
      ) {
        error = at("user_merge_not_found");
        return;
      }
      source = sourceDetail;
      freshTarget = targetDetail;
      sourceContext = sourceInfo;
      targetContext = targetInfo;
      stage = "confirm";
    } catch (cause) {
      if (request === generation) error = at(mergeErrorKey(cause));
    } finally {
      if (request === generation) loading = false;
    }
  }

  function chooseAnother() {
    if (merging) return;
    clearSelection();
    stage = "select";
  }

  async function confirmMerge() {
    if (!canMerge || !source || !freshTarget) return;
    const request = generation;
    const mergingSource = source;
    const mergingTarget = freshTarget;
    merging = true;
    error = "";
    try {
      const response = await mergeUsers(
        api,
        targetId,
        Number(mergingSource.user.user_id),
        Number(confirmation)
      );
      // Cache invalidation belongs to the completed transaction even if the dialog was replaced.
      oncomplete(mergingSource.user, mergingTarget.user);
      if (request !== generation) return;
      result = response.panel_reconciliation_pending ? "pending" : "complete";
      try {
        const detail = await fetchMergeUser(api, String(mergingTarget.user.user_id));
        if (request === generation) onmerged(detail);
      } catch {
        /* A successful merge stays successful if the detail refresh is unavailable. */
      }
    } catch (cause) {
      if (request === generation) {
        error = at(mergeErrorKey(cause));
        mergeBlocked = mergeErrorBlocksRetry(cause);
        if (mergeErrorKey(cause) === "user_merge_not_found") {
          clearSelection();
          stage = "select";
          error = at("user_merge_not_found");
          merging = false;
        }
      }
    } finally {
      if (request === generation) merging = false;
    }
  }
  function close() {
    if (!merging) onclose();
  }
</script>

<Dialog
  {open}
  title={at("user_merge_title")}
  description={at(
    stage === "select" ? "user_merge_select_description" : "user_merge_review_description"
  )}
  closeLabel={at("close")}
  onclose={close}
  focusKey={result || stage}
  class="admin-dialog admin-user-merge-dialog"
  portal
>
  {#if result}
    <p class="merge-result" role="status">
      {at(result === "pending" ? "user_merge_success_pending" : "user_merge_success")}
    </p>
  {:else}
    <div hidden={stage !== "select"}>
      <div class="merge-target-summary">
        <span>{at("user_merge_retained")}</span>
        <AdminUserCell
          name={userDisplayName(target.user)}
          secondary={userSecondaryName(target.user)}
          idText={target.user.minishop_id || String(targetId)}
          initials={userInitials(target.user)}
        />
      </div>
      <AdminUserPicker
        {at}
        excludedId={targetId}
        disabled={merging}
        onselect={(user) => void selectSource(user)}
        onquerychange={clearSelection}
      />
      {#if loading}<p class="admin-muted" role="status">{at("user_merge_loading_details")}</p>{/if}
    </div>
    {#if stage === "confirm" && source && freshTarget && sourceContext && targetContext}
      <div class="merge-direction">
        <span>{at("user_merge_direction")}</span><strong
          >{userDisplayName(source.user)}
          <ArrowRight size={14} />
          {userDisplayName(freshTarget.user)}</strong
        >
      </div>
      {#if knownConflict}<p class="merge-error" role="alert">{at(knownConflict)}</p>{/if}
      <div class="merge-comparison">
        <UserMergeAccountCard
          detail={source}
          context={sourceContext}
          retained={false}
          {at}
          {fmtDate}
        />
        <UserMergeAccountCard
          detail={freshTarget}
          context={targetContext}
          retained
          {at}
          {fmtDate}
        />
      </div>
      <div class="merge-effects">
        <p><TriangleAlert size={16} />{at("user_merge_warning")}</p>
        <ul>
          <li>{at("user_merge_effect_balance")}</li>
          <li>{at("user_merge_effect_promos")}</li>
          <li>{at("user_merge_effect_subscription")}</li>
          <li>{at("user_merge_effect_logins")}</li>
          <li>{at("user_merge_effect_recurring")}</li>
        </ul>
      </div>
      {#if sourceContext.merge_eligibility.allowed && targetContext.merge_eligibility.allowed && !knownConflict}
        <AdminField
          label={at("user_merge_confirmation", { id: targetId })}
          hint={at("user_merge_confirmation_hint")}
        >
          <Input
            value={confirmation}
            disabled={merging}
            inputmode="numeric"
            autocomplete="off"
            aria-label={at("user_merge_confirmation", { id: targetId })}
            oninput={(event) => (confirmation = event.currentTarget.value)}
          />
        </AdminField>
      {/if}
    {/if}
    {#if error}
      <div bind:this={errorElement} class="merge-error" role="alert" tabindex="-1">
        <p>{error}</p>
        {#if stage === "select" && selected && !loading}<AdminButton
            onclick={() => selected && void selectSource(selected)}>{at("retry")}</AdminButton
          >{/if}
      </div>
    {/if}
  {/if}
  {#snippet footer()}
    <div class="admin-action-grid merge-dialog-actions">
      <AdminButton controlSize="md" disabled={merging} onclick={close}
        >{at(result ? "close" : "cancel")}</AdminButton
      >
      {#if !result && stage === "confirm"}
        <AdminButton controlSize="md" disabled={merging} onclick={chooseAnother}
          >{at("user_merge_choose_another")}</AdminButton
        >
        <AdminButton
          controlSize="md"
          variant="danger"
          disabled={!canMerge}
          onclick={() => void confirmMerge()}
          ><Merge size={15} />{at(merging ? "user_merge_busy" : "user_merge_confirm")}</AdminButton
        >
      {/if}
    </div>
  {/snippet}
</Dialog>

<style>
  :global(.admin-user-merge-dialog) {
    width: min(820px, 100%);
  }
  .merge-target-summary {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    padding: 10px 12px;
    margin-bottom: 12px;
    border: 1px solid var(--admin-border);
    border-radius: var(--radius-card);
  }
  .merge-target-summary > span {
    color: var(--success);
    font-size: 12px;
  }
  .merge-direction {
    display: grid;
    gap: 6px;
    margin-bottom: 12px;
    font-size: 12px;
  }
  .merge-direction > span {
    color: var(--admin-muted);
  }
  .merge-direction strong {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }
  .merge-comparison {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin-bottom: 14px;
  }
  .merge-effects {
    font-size: 12px;
    line-height: 1.5;
    margin-bottom: 14px;
  }
  .merge-effects p {
    display: flex;
    align-items: start;
    gap: 8px;
    color: var(--warning);
    margin: 0 0 6px;
  }
  .merge-effects :global(svg) {
    flex-shrink: 0;
    margin-top: 2px;
  }
  .merge-effects ul {
    padding-left: 20px;
    margin: 0;
  }
  .merge-error {
    color: var(--danger);
    font-size: 13px;
    margin-top: 10px;
  }
  .merge-error p {
    margin: 0 0 8px;
  }
  .merge-result {
    line-height: 1.6;
  }
  .merge-dialog-actions {
    flex: 1;
    min-width: 0;
    grid-template-columns: none;
    grid-auto-flow: column;
    grid-auto-columns: max-content;
    justify-content: end;
  }
  @media (max-width: 640px) {
    .merge-dialog-actions {
      grid-template-columns: minmax(0, 1fr);
      grid-auto-flow: row;
    }
  }
  @media (max-width: 600px) {
    .merge-comparison {
      grid-template-columns: 1fr;
      gap: 10px;
    }
  }
</style>
