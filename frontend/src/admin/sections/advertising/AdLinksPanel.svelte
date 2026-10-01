<script lang="ts">
  import { Input } from "$components/ui/index.js";
  import {
    AdminButton,
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

{#if offers}
  <p class="admin-muted">{at("ads_offers_hint")}</p>
  <div class="admin-form ad-form-grid">
    <AdminField label={at("ads_offer_code")}
      ><AdminSelect
        bind:value={codeId}
        items={codeItems}
        ariaLabel={at("ads_offer_code")}
      /></AdminField
    >
    <AdminField label={at("ads_link_scope")}
      ><AdminSelect
        bind:value={linkId}
        items={linkItems}
        ariaLabel={at("ads_link_scope")}
      /></AdminField
    >
    <AdminField label={at("ads_binding_purpose")}
      ><AdminSelect
        bind:value={purpose}
        items={[
          { value: "offer", label: at("ads_offer") },
          { value: "manual_code_source", label: at("ads_manual_code_source") },
        ]}
        ariaLabel={at("ads_binding_purpose")}
      /></AdminField
    >
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
  </div>
  <AdminTable
    ><thead
      ><tr
        ><th>{at("ads_offer_code")}</th><th>{at("ads_link_scope")}</th><th
          >{at("ads_binding_purpose")}</th
        ><th>{at("ads_version")}</th><th>{at("ads_period")}</th><th>{at("actions")}</th></tr
      ></thead
    >
    <tbody
      >{#each data.bindings as binding}<tr>
          <td data-label={at("ads_offer_code")}
            >{binding.code}{#if !binding.is_active}
              · {at("ads_paused")}{/if}</td
          >
          <td data-label={at("ads_link_scope")}>{binding.link_id || at("ads_campaign_default")}</td>
          <td data-label={at("ads_binding_purpose")}>{at(`ads_${binding.purpose}`)}</td>
          <td data-label={at("ads_version")}
            >{binding.version}
            <small
              >{at("ads_offer_counts", {
                activations: binding.activations,
                purchases: binding.purchases,
                pending: binding.pending,
                refunded: binding.refunded,
              })}</small
            ></td
          >
          <td data-label={at("ads_period")}
            >{adDate(binding.starts_at)} → {binding.ends_at
              ? adDate(binding.ends_at)
              : at("ads_active")}</td
          >
          <td data-label={at("actions")}
            >{#if !binding.ends_at}<AdminButton onclick={() => mutate("endBinding", {}, binding.id)}
                >{at("ads_end_binding")}</AdminButton
              >{/if}</td
          >
        </tr>{/each}</tbody
    >
  </AdminTable>
{:else}
  <p class="admin-muted">{at("ads_links_hint")}</p>
  {#if data.legacy_warning}<p role="status">{at("ads_legacy_warning")}</p>{/if}
  {#each Object.entries(data.legacy_urls || {}) as [kind, url]}
    <AdminField
      label={`${at("ads_legacy")} · ${kind === "miniapp" ? "Mini App" : at(`ads_${kind}`)}`}
    >
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
  <div class="admin-form ad-form-grid">
    <AdminField label={at("ads_link_label")}
      ><Input bind:value={label} maxlength={160} /></AdminField
    >
    <AdminField label={at("ads_destination")}
      ><AdminSelect
        bind:value={destination}
        items={[
          { value: "web", label: at("ads_web") },
          { value: "bot", label: at("ads_bot") },
          { value: "miniapp", label: "Mini App" },
        ]}
        ariaLabel={at("ads_destination")}
      /></AdminField
    >
    <AdminField label={at("ads_landing")}><Input bind:value={landing} placeholder="/" /></AdminField
    >
    <AdminField label="utm_source"><Input bind:value={source} maxlength={256} /></AdminField>
    <AdminField label="utm_medium"><Input bind:value={medium} maxlength={256} /></AdminField>
    <AdminField label="utm_campaign"><Input bind:value={campaign} maxlength={256} /></AdminField>
    <AdminField label="utm_content"><Input bind:value={content} maxlength={256} /></AdminField>
    <AdminField label="utm_term"><Input bind:value={term} maxlength={256} /></AdminField>
    <AdminButton
      variant="primary"
      disabled={!source.trim() || Boolean(data.archived_at)}
      onclick={createLink}>{at("ads_create_link")}</AdminButton
    >
  </div>
  <AdminField label={at("ads_named_app")} hint={at("ads_named_app_hint")}
    ><Input bind:value={appName} placeholder="my_app" /></AdminField
  >
  {#if copyError}<p role="status">{at("ads_copy_fallback")}</p>{/if}
  {#each data.links as link}
    <div class="ad-link-card">
      <h3>{link.label || link.code}</h3>
      <AdminButton
        disabled={Boolean(data.archived_at)}
        onclick={() => mutate("linkToggle", { is_active: !link.is_active }, link.id)}
        >{link.is_active ? at("btn_disable") : at("btn_enable")}</AdminButton
      >
      <p class="admin-muted">
        {link.code} · {Object.entries(link.utm)
          .map(([key, value]) => `${key}=${value}`)
          .join(" · ")}
      </p>
      {#each Object.entries(link.urls) as [kind, url]}<AdminField
          label={kind === "miniapp" ? "Main Mini App" : at(`ads_${kind}`)}
          ><CopyLinkField
            variant="admin"
            value={url}
            inputLabel={at("ads_link")}
            copyLabel={at("copy")}
            copied={copied === url}
            oncopy={copy}
          /></AdminField
        >{/each}
      {#if appName && link.urls.miniapp}<AdminField label={at("ads_named_app")}
          ><CopyLinkField
            variant="admin"
            value={namedUrl(link.urls.miniapp)}
            inputLabel={at("ads_link")}
            copyLabel={at("copy")}
            copied={copied === namedUrl(link.urls.miniapp)}
            oncopy={copy}
          /></AdminField
        >{/if}
      {#if !link.urls.bot}<p class="admin-muted">{at("ads_telegram_unavailable")}</p>{/if}
    </div>
  {/each}
{/if}

<style>
  .ad-form-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 12px;
    margin-bottom: 20px;
  }
  .ad-link-card {
    padding: 16px;
    border: 1px solid var(--border);
    border-radius: 12px;
    margin-top: 16px;
    display: grid;
    gap: 12px;
  }
  .ad-link-card p {
    overflow-wrap: anywhere;
  }
</style>
