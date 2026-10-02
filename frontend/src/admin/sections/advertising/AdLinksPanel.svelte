<script lang="ts">
  import { Input } from "$components/ui/index.js";
  import {
    AdminBadge,
    AdminButton,
    AdminCardActions,
    AdminEmptyState,
    AdminFormGrid,
    AdminSectionHeader,
    AdminSettingsGroup,
    AdminField,
    AdminSelect,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import CopyLinkField from "$components/patterns/CopyLinkField.svelte";
  import { adDate, type AdDetail, type Translate, type Mutate } from "./types";
  let {
    data,
    at,
    mutate,
    offers = false,
  }: { data: AdDetail; at: Translate; mutate: Mutate; offers?: boolean } = $props();
  let label = $state("");
  let landing = $state("/");
  let destination = $state("web");
  let appName = $state("");
  let source = $state("telegram");
  let medium = $state("paid");
  let campaign = $state("");
  let content = $state("");
  let term = $state("");
  let codeId = $state("");
  let linkId = $state("");
  let purpose = $state("offer");
  let copied = $state("");
  let copyError = $state(false);
  const codeItems = $derived(
    Object.entries(data.available_codes).map(([code, id]) => ({ value: String(id), label: code }))
  );
  const linkItems = $derived([
    { value: "", label: at("ads_campaign_default") },
    ...data.links.map((link) => ({ value: String(link.id), label: link.label || link.code })),
  ]);
  function bindingScope(id: number | null): string {
    if (!id) return at("ads_campaign_default");
    const link = data.links.find((item) => item.id === id);
    return link?.label || link?.code || String(id);
  }
  async function createLink() {
    const utm = Object.fromEntries(
      Object.entries({
        utm_source: source,
        utm_medium: medium,
        utm_campaign: campaign,
        utm_content: content,
        utm_term: term,
      }).filter(([, value]) => value.trim())
    );
    if (await mutate("links", { label, destination, landing_path: landing, utm })) label = "";
  }
  async function copy(value: string) {
    copyError = false;
    try {
      await navigator.clipboard.writeText(value);
      copied = value;
    } catch {
      copyError = true;
    }
  }
  function namedUrl(url: string): string {
    if (!/^[A-Za-z0-9_]+$/.test(appName)) return "";
    const parsed = new URL(url);
    parsed.pathname += `/${appName}`;
    return parsed.toString();
  }
</script>

<div class="ad-links-panel">
  {#if offers}
    <AdminSettingsGroup title={at("ads_bind_code")} description={at("ads_offers_hint")}>
      <AdminFormGrid columns={3}>
        <AdminField label={at("ads_offer_code")}>
          <AdminSelect bind:value={codeId} items={codeItems} ariaLabel={at("ads_offer_code")} />
        </AdminField>
        <AdminField label={at("ads_link_scope")}>
          <AdminSelect bind:value={linkId} items={linkItems} ariaLabel={at("ads_link_scope")} />
        </AdminField>
        <AdminField label={at("ads_binding_purpose")}>
          <AdminSelect
            bind:value={purpose}
            items={[
              { value: "offer", label: at("ads_offer") },
              { value: "manual_code_source", label: at("ads_manual_code_source") },
            ]}
            ariaLabel={at("ads_binding_purpose")}
          />
        </AdminField>
      </AdminFormGrid>
      <AdminCardActions divider={false}>
        <AdminButton
          variant="primary"
          disabled={!codeId || Boolean(data.archived_at)}
          onclick={() =>
            mutate("bindings", {
              promo_code_id: Number(codeId),
              link_id: linkId ? Number(linkId) : null,
              purpose,
            })}>{at("ads_bind_code")}</AdminButton
        >
      </AdminCardActions>
    </AdminSettingsGroup>

    <AdminSettingsGroup title={at("ads_binding_history")}>
      {#if data.bindings.length}
        <AdminTable
          layout="fixed"
          class="admin-table-compact"
          aria-label={at("ads_binding_history")}
        >
          <thead>
            <tr>
              <th>{at("ads_offer_code")}</th>
              <th>{at("ads_link_scope")}</th>
              <th>{at("ads_binding_purpose")}</th>
              <th>{at("ads_version")}</th>
              <th>{at("ads_period")}</th>
              <th>{at("actions")}</th>
            </tr>
          </thead>
          <tbody>
            {#each data.bindings as binding (binding.id)}
              <tr>
                <td class="admin-cell-primary" data-label={at("ads_offer_code")}>
                  <strong>{binding.code}</strong>
                  {#if !binding.is_active}<small class="admin-muted">{at("ads_paused")}</small>{/if}
                </td>
                <td data-label={at("ads_link_scope")}>{bindingScope(binding.link_id)}</td>
                <td data-label={at("ads_binding_purpose")}>{at(`ads_${binding.purpose}`)}</td>
                <td data-label={at("ads_version")}>
                  <div class="ad-cell-stack">
                    <strong>{binding.version}</strong>
                    <small class="admin-muted"
                      >{at("ads_offer_counts", {
                        activations: binding.activations,
                        purchases: binding.purchases,
                        pending: binding.pending,
                        refunded: binding.refunded,
                      })}</small
                    >
                  </div>
                </td>
                <td data-label={at("ads_period")}>
                  <div class="ad-cell-stack">
                    <span>{adDate(binding.starts_at)}</span>
                    <span>→ {binding.ends_at ? adDate(binding.ends_at) : at("ads_active")}</span>
                  </div>
                </td>
                <td class="admin-cell-actions" data-label={at("actions")}>
                  {#if !binding.ends_at}
                    <AdminButton size="sm" onclick={() => mutate("endBinding", {}, binding.id)}>
                      {at("ads_end_binding")}
                    </AdminButton>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </AdminTable>
      {:else}
        <AdminEmptyState>{at("ads_bindings_empty")}</AdminEmptyState>
      {/if}
    </AdminSettingsGroup>
  {:else}
    <AdminSettingsGroup title={at("ads_create_link")} description={at("ads_links_hint")}>
      <AdminFormGrid columns={3}>
        <AdminField label={at("ads_link_label")}>
          <Input bind:value={label} maxlength={160} aria-label={at("ads_link_label")} />
        </AdminField>
        <AdminField label={at("ads_destination")}>
          <AdminSelect
            bind:value={destination}
            items={[
              { value: "web", label: at("ads_web") },
              { value: "bot", label: at("ads_bot") },
              { value: "miniapp", label: at("ads_miniapp") },
            ]}
            ariaLabel={at("ads_destination")}
          />
        </AdminField>
        <AdminField label={at("ads_landing")}>
          <Input bind:value={landing} placeholder="/" aria-label={at("ads_landing")} />
        </AdminField>
      </AdminFormGrid>
      <AdminSectionHeader title={at("ads_link_utm")} />
      <AdminFormGrid columns={3}>
        <AdminField label="utm_source"
          ><Input bind:value={source} maxlength={256} aria-label="utm_source" /></AdminField
        >
        <AdminField label="utm_medium"
          ><Input bind:value={medium} maxlength={256} aria-label="utm_medium" /></AdminField
        >
        <AdminField label="utm_campaign"
          ><Input bind:value={campaign} maxlength={256} aria-label="utm_campaign" /></AdminField
        >
        <AdminField label="utm_content"
          ><Input bind:value={content} maxlength={256} aria-label="utm_content" /></AdminField
        >
        <AdminField label="utm_term"
          ><Input bind:value={term} maxlength={256} aria-label="utm_term" /></AdminField
        >
      </AdminFormGrid>
      <AdminCardActions divider={false}>
        <AdminButton
          variant="primary"
          disabled={!source.trim() || Boolean(data.archived_at)}
          onclick={createLink}>{at("ads_create_link")}</AdminButton
        >
      </AdminCardActions>
    </AdminSettingsGroup>

    {#if Object.keys(data.legacy_urls || {}).length || data.legacy_warning}
      <AdminSettingsGroup title={at("ads_legacy_links")}>
        {#if data.legacy_warning}<p class="admin-muted ad-panel-note" role="status">
            {at("ads_legacy_warning")}
          </p>{/if}
        <AdminFormGrid columns={2}>
          {#each Object.entries(data.legacy_urls || {}) as [kind, url] (kind)}
            <AdminField label={kind === "miniapp" ? at("ads_miniapp") : at(`ads_${kind}`)}>
              <CopyLinkField
                variant="admin"
                value={url}
                inputLabel={at("ads_link")}
                copyLabel={at("copy")}
                copied={copied === url}
                oncopy={copy}
              />
            </AdminField>
          {/each}
        </AdminFormGrid>
      </AdminSettingsGroup>
    {/if}

    <AdminSectionHeader title={at("ads_generated_links")} />
    <AdminField label={at("ads_named_app")} hint={at("ads_named_app_hint")}>
      <Input bind:value={appName} placeholder="my_app" aria-label={at("ads_named_app")} />
    </AdminField>
    {#if copyError}<p class="ad-panel-note" role="status">{at("ads_copy_fallback")}</p>{/if}
    {#each data.links as link (link.id)}
      <AdminSettingsGroup
        title={link.label || link.code}
        description={`${link.code} · ${Object.entries(link.utm)
          .map(([key, value]) => `${key}=${value}`)
          .join(" · ")}`}
      >
        {#snippet actions()}
          <AdminBadge variant={link.is_active ? "success" : "muted"}>
            {link.is_active ? at("ads_active") : at("ads_paused")}
          </AdminBadge>
          <AdminButton
            size="sm"
            disabled={Boolean(data.archived_at)}
            onclick={() => mutate("linkToggle", { is_active: !link.is_active }, link.id)}
            >{link.is_active ? at("btn_disable") : at("btn_enable")}</AdminButton
          >
        {/snippet}
        <AdminFormGrid columns={2}>
          {#each Object.entries(link.urls) as [kind, url] (kind)}
            <AdminField label={kind === "miniapp" ? at("ads_main_miniapp") : at(`ads_${kind}`)}>
              <CopyLinkField
                variant="admin"
                value={url}
                inputLabel={at("ads_link")}
                copyLabel={at("copy")}
                copied={copied === url}
                oncopy={copy}
              />
            </AdminField>
          {/each}
          {#if appName && link.urls.miniapp}
            <AdminField label={at("ads_named_app")}>
              <CopyLinkField
                variant="admin"
                value={namedUrl(link.urls.miniapp)}
                inputLabel={at("ads_link")}
                copyLabel={at("copy")}
                copied={copied === namedUrl(link.urls.miniapp)}
                oncopy={copy}
              />
            </AdminField>
          {/if}
        </AdminFormGrid>
        {#if !link.urls.bot}<p class="admin-muted ad-panel-note">
            {at("ads_telegram_unavailable")}
          </p>{/if}
      </AdminSettingsGroup>
    {:else}
      <AdminEmptyState>{at("ads_links_empty")}</AdminEmptyState>
    {/each}
  {/if}
</div>

<style>
  .ad-links-panel {
    display: grid;
    gap: 18px;
    min-width: 0;
  }
  .ad-links-panel :global(.admin-settings-group-copy) {
    overflow-wrap: anywhere;
  }
  .ad-cell-stack {
    display: grid;
    gap: 4px;
    min-width: 0;
  }
  .ad-links-panel :global(.admin-cell-actions .admin-btn) {
    max-width: 100%;
    white-space: normal;
  }
  .ad-panel-note {
    margin: 0;
    line-height: 1.5;
  }
</style>
