<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { getAdminApi } from "$lib/admin/context.js";
  import { fetchMergeCandidates } from "$lib/admin/userMergeApi.js";
  import { createUserPicker } from "$lib/admin/userPicker.svelte.js";
  import {
    userAvatarUrl,
    userDisplayName,
    userInitials,
    userSecondaryName,
  } from "$lib/admin/users.js";
  import type { AdminUser, TranslateFn } from "$lib/admin/stores/usersStoreState.js";
  import Input from "$components/ui/input.svelte";
  import { Search } from "$components/ui/icons.js";
  import AdminBadge from "./AdminBadge.svelte";
  import AdminButton from "./AdminButton.svelte";
  import AdminListToolbar from "./AdminListToolbar.svelte";
  import AdminPagination from "./AdminPagination.svelte";
  import AdminUserCell from "./AdminUserCell.svelte";

  let {
    at,
    excludedId,
    disabled = false,
    onselect,
    onquerychange = () => {},
  }: {
    at: TranslateFn;
    excludedId: number;
    disabled?: boolean;
    onselect: (user: AdminUser) => void;
    onquerychange?: () => void;
  } = $props();
  const api = getAdminApi();
  const picker = createUserPicker((query, page) => fetchMergeCandidates(api, query, page));
  onMount(() => {
    void picker.load();
  });
  onDestroy(() => picker.dispose());
  function load(page = 0) {
    onquerychange();
    void picker.load(page);
  }
</script>

<div class="admin-user-picker" aria-busy={picker.loading}>
  <AdminListToolbar
    total={picker.total ?? undefined}
    totalLabel={at("total")}
    onsubmit={() => load()}
  >
    {#snippet search()}
      <Input
        type="search"
        value={picker.query}
        {disabled}
        aria-label={at("user_merge_search")}
        placeholder={at("users_search_placeholder")}
        oninput={(event) => {
          picker.changeQuery(event.currentTarget.value);
          onquerychange();
        }}
      />
    {/snippet}
    {#snippet searchActions()}
      <AdminButton variant="primary" disabled={disabled || picker.loading} onclick={() => load()}>
        <Search size={15} />{at("find")}
      </AdminButton>
    {/snippet}
  </AdminListToolbar>
  {#if picker.loading}
    <p class="admin-muted" role="status">{at("loading")}</p>
  {:else if picker.failed}
    <div class="picker-error" role="alert">
      <p>{at("user_merge_search_failed")}</p>
      <AdminButton {disabled} onclick={() => load(picker.page)}>{at("retry")}</AdminButton>
    </div>
  {:else if picker.dirty}
    <p class="admin-muted">{at("user_merge_search_submit")}</p>
  {:else if !picker.users.length}
    <p class="admin-muted" role="status">{at("user_merge_search_empty")}</p>
  {:else}
    <ul class="picker-users">
      {#each picker.users as user (user.user_id)}
        <li>
          <AdminButton
            class="picker-user"
            variant="ghost"
            disabled={disabled || Number(user.user_id) === excludedId}
            aria-label={at("user_merge_select_user", { name: userDisplayName(user) })}
            onclick={() => onselect(user)}
          >
            <AdminUserCell
              name={userDisplayName(user)}
              secondary={userSecondaryName(user)}
              idText={user.minishop_id || String(user.user_id)}
              initials={userInitials(user)}
              avatarUrl={userAvatarUrl(user)}
            />
            <span class="picker-user-state">
              <span>{at("user_merge_internal_id")}: {user.user_id}</span>
              {#if Number(user.user_id) === excludedId}<AdminBadge variant="success"
                  >{at("user_merge_retained")}</AdminBadge
                >
              {:else if user.is_banned}<AdminBadge variant="danger">{at("badge_banned")}</AdminBadge
                >{/if}
            </span>
          </AdminButton>
        </li>
      {/each}
    </ul>
    {#if picker.pageCount > 1}
      <AdminPagination
        page={picker.page}
        pageCount={picker.pageCount}
        total={picker.total}
        disabled={disabled || picker.loading}
        pageLabel={at("page_short")}
        ofLabel={at("pagination_of")}
        totalLabel={at("total")}
        jumpLabel={at("page_short")}
        jumpAriaLabel={at("pagination_jump_aria")}
        goLabel={at("pagination_go")}
        prevLabel={at("back")}
        nextLabel={at("next")}
        onPageChange={(page) => load(page)}
      />
    {/if}
  {/if}
</div>

<style>
  .admin-user-picker {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  .picker-users {
    display: grid;
    gap: 6px;
    padding: 0;
    margin: 0;
    list-style: none;
  }
  .picker-users :global(.picker-user) {
    width: 100%;
    justify-content: space-between;
    padding: 10px;
    height: auto;
    min-height: 64px;
    gap: 12px;
    border: 1px solid var(--admin-border);
  }
  .picker-user-state {
    display: grid;
    justify-items: end;
    gap: 4px;
    font-size: 11px;
    color: var(--admin-muted);
  }
  .picker-error {
    color: var(--danger);
  }
  .picker-error p {
    margin: 0 0 8px;
  }
  @media (max-width: 600px) {
    .picker-users :global(.picker-user) {
      flex-wrap: wrap;
    }
    .picker-user-state {
      justify-items: start;
    }
  }
</style>
