<script lang="ts">
  import { AdminButton } from "$components/patterns/admin/index.js";
  import { Copy } from "$components/ui/icons.js";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState";
  import type { TranslateFn, UsersStoreBridge } from "./userDetailTypes";
  let {
    at,
    usersStore,
    openedUserDetail,
  }: {
    at: TranslateFn;
    usersStore: UsersStoreBridge;
    openedUserDetail: AdminUserDetail;
  } = $props();
</script>

{#if openedUserDetail.panel_user_url || openedUserDetail.subscription_url || openedUserDetail.install_share_url || openedUserDetail.referral?.bot_link || openedUserDetail.referral?.webapp_link}
  <section class="admin-user-links-panel">
    <div class="admin-subsection-title">{at("user_section_links", {}, "Links")}</div>
    <div class="admin-link-list">
      {#if openedUserDetail.panel_user_url}
        <div class="admin-link-row">
          <div class="admin-link-row-meta">
            <span class="admin-link-row-label"
              >{at("user_label_remnawave_card", {}, "Remnawave user card")}</span
            >
            <a
              class="admin-link-row-url"
              href={openedUserDetail.panel_user_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {openedUserDetail.panel_user_url}
            </a>
          </div>
          <AdminButton
            size="icon"
            variant="icon"
            title={at("user_copy_tooltip", {}, "Copy")}
            onclick={() =>
              usersStore.copyToClipboard(
                openedUserDetail.panel_user_url!,
                at("user_panel_link_copied", {}, "Remnawave user card link copied")
              )}
          >
            <Copy size={14} />
          </AdminButton>
        </div>
      {/if}
      {#if openedUserDetail.subscription_url}
        <div class="admin-link-row">
          <div class="admin-link-row-meta">
            <span class="admin-link-row-label">{at("status_subscription", {}, "Subscription")}</span
            >
            <a
              class="admin-link-row-url"
              href={openedUserDetail.subscription_url}
              target="_blank"
              rel="noopener"
            >
              {openedUserDetail.subscription_url}
            </a>
          </div>
          <AdminButton
            size="icon"
            variant="icon"
            title={at("user_copy_tooltip", {}, "Copy")}
            onclick={() =>
              usersStore.copyToClipboard(
                openedUserDetail.subscription_url,
                at("user_sub_link_copied", {}, "Subscription link copied")
              )}
          >
            <Copy size={14} />
          </AdminButton>
        </div>
      {/if}
      {#if openedUserDetail.install_share_url}
        <div class="admin-link-row">
          <div class="admin-link-row-meta">
            <span class="admin-link-row-label"
              >{at("user_label_install_share", {}, "Install guide")}</span
            >
            <a
              class="admin-link-row-url"
              href={openedUserDetail.install_share_url}
              target="_blank"
              rel="noopener"
            >
              {openedUserDetail.install_share_url}
            </a>
          </div>
          <AdminButton
            size="icon"
            variant="icon"
            title={at("user_copy_tooltip", {}, "Copy")}
            onclick={() =>
              usersStore.copyToClipboard(
                openedUserDetail.install_share_url,
                at("user_install_share_link_copied", {}, "Install guide link copied")
              )}
          >
            <Copy size={14} />
          </AdminButton>
        </div>
      {/if}
      {#if openedUserDetail.referral?.bot_link}
        <div class="admin-link-row">
          <div class="admin-link-row-meta">
            <span class="admin-link-row-label"
              >{at("user_label_ref_bot", {}, "Referral link (bot)")}</span
            >
            <a
              class="admin-link-row-url"
              href={openedUserDetail.referral.bot_link}
              target="_blank"
              rel="noopener"
            >
              {openedUserDetail.referral.bot_link}
            </a>
          </div>
          <AdminButton
            size="icon"
            variant="icon"
            title={at("user_copy_tooltip", {}, "Copy")}
            onclick={() =>
              usersStore.copyToClipboard(
                openedUserDetail.referral.bot_link,
                at("user_ref_link_copied", {}, "Referral link copied")
              )}
          >
            <Copy size={14} />
          </AdminButton>
        </div>
      {/if}
      {#if openedUserDetail.referral?.webapp_link}
        <div class="admin-link-row">
          <div class="admin-link-row-meta">
            <span class="admin-link-row-label"
              >{at("user_label_ref_web", {}, "Referral link (web)")}</span
            >
            <a
              class="admin-link-row-url"
              href={openedUserDetail.referral.webapp_link}
              target="_blank"
              rel="noopener"
            >
              {openedUserDetail.referral.webapp_link}
            </a>
          </div>
          <AdminButton
            size="icon"
            variant="icon"
            title={at("user_copy_tooltip", {}, "Copy")}
            onclick={() =>
              usersStore.copyToClipboard(
                openedUserDetail.referral.webapp_link,
                at("user_ref_link_copied", {}, "Referral link copied")
              )}
          >
            <Copy size={14} />
          </AdminButton>
        </div>
      {/if}
    </div>
  </section>
{/if}
