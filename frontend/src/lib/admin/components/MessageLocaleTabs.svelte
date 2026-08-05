<script lang="ts">
  /**
   * Language switcher for content that goes out to customers.
   *
   * A message and its button captions reach people who chose different
   * languages, so they are authored one language at a time. The tab set comes
   * from whatever languages the deployment actually has rather than from a
   * list hardcoded anywhere: adding a language to the translations screen adds
   * a tab here. A tab with nothing written is marked, so an untranslated
   * language is visible while authoring instead of after a customer notices.
   */
  import type { TranslationLanguage } from "$lib/admin/stores/translationsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    languages,
    active,
    written,
    at,
    onSelect,
  }: {
    languages: TranslationLanguage[];
    active: string;
    /** Language codes that currently have content. */
    written: string[];
    at: TranslateFn;
    onSelect: (code: string) => void;
  } = $props();

  const filled = $derived(new Set(written));
</script>

{#if languages.length > 1}
  <div
    class="message-locale-tabs"
    role="tablist"
    aria-label={at("broadcast_language_label", {}, "Language")}
  >
    {#each languages as language (language.code)}
      <button
        type="button"
        role="tab"
        class="message-locale-tab"
        class:message-locale-tab--active={language.code === active}
        class:message-locale-tab--empty={!filled.has(language.code)}
        aria-selected={language.code === active}
        onclick={() => onSelect(language.code)}
      >
        {language.label || language.code.toUpperCase()}
      </button>
    {/each}
  </div>
{/if}

<style>
  .message-locale-tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 8px;
  }

  .message-locale-tab {
    padding: 5px 10px;
    border: 1px solid var(--admin-border);
    border-radius: 999px;
    background: var(--admin-surface-2);
    color: var(--admin-muted);
    font-size: 12px;
    cursor: pointer;
  }

  .message-locale-tab--active {
    border-color: var(--admin-accent);
    color: var(--admin-text);
  }

  /* An unwritten language is marked while authoring rather than discovered
     when its customers receive somebody else's language. */
  .message-locale-tab--empty::after {
    content: " •";
    color: var(--admin-warning, #f59e0b);
  }
</style>
