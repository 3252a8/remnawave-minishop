<script lang="ts">
  import { onDestroy } from "svelte";
  import { Clock, RefreshCw, ShieldCheck } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import Input from "$components/ui/input.svelte";
  import Spinner from "$components/ui/spinner.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";
  import type { TrialCaptchaStore } from "$lib/webapp/stores/trialCaptchaStore.svelte.js";
  import type { Translate } from "$lib/webapp/types.js";

  let { store, t }: { store: TrialCaptchaStore; t: Translate } = $props();
  let form = $state<HTMLFormElement | null>(null);

  onDestroy(() => store.cancel());

  $effect(() => {
    if (!store.open || store.loading || store.verifying || !store.challengeId) return;
    form?.querySelector<HTMLInputElement>("input")?.focus();
  });
</script>

<Dialog
  open={store.open}
  title={t("wa_trial_captcha_title")}
  closeLabel={t("wa_close")}
  onclose={store.cancel}
  focusOnOpen={!store.challengeId && !store.loading}
  focusKey={store.challengeId}
  class="trial-captcha-dialog"
  portal
>
  {#snippet titleIcon()}<ShieldCheck size={21} />{/snippet}
  <form
    bind:this={form}
    class="trial-captcha-body"
    aria-busy={store.loading || store.verifying}
    onsubmit={(event) => {
      event.preventDefault();
      void store.verify();
    }}
  >
    <p class="trial-captcha-description">{t("wa_trial_captcha_description")}</p>
    <div class="trial-captcha-challenge">
      <div class="trial-captcha-image">
        {#if store.loading}
          <div role="status" aria-label={t("wa_loading")}><Spinner size="lg" /></div>
        {:else if store.image}
          <img src={store.image} alt={t("wa_trial_captcha_image_alt")} width="320" height="112" />
        {:else}
          <ShieldCheck size={28} aria-hidden="true" />
        {/if}
      </div>
      <div class="trial-captcha-tools">
        <Button
          variant="ghost"
          size="sm"
          class="trial-captcha-refresh"
          type="button"
          onclick={() => void store.refresh()}
          disabled={store.loading || store.verifying}
        >
          <RefreshCw size={14} />
          {t("wa_trial_captcha_refresh")}
        </Button>
      </div>
    </div>
    <label class="trial-captcha-field" for="trial-captcha-answer">
      <span>{t("wa_trial_captcha_answer_label")}</span>
      <Input
        id="trial-captcha-answer"
        class="trial-captcha-answer"
        bind:value={store.answer}
        autocomplete="off"
        autocapitalize="off"
        spellcheck={false}
        inputmode="numeric"
        pattern={"[0-9]{5}"}
        maxlength={5}
        disabled={store.loading || store.verifying || !store.challengeId}
        placeholder={t("wa_trial_captcha_answer_placeholder")}
        aria-describedby={store.error
          ? "trial-captcha-error trial-captcha-hint"
          : "trial-captcha-hint"}
        aria-invalid={Boolean(store.error)}
      />
    </label>
    {#if store.error}
      <StatusMessage id="trial-captcha-error" class="trial-captcha-error" role="alert" error>
        {store.error}
      </StatusMessage>
    {/if}
    <Button
      type="submit"
      class="wide trial-captcha-submit"
      disabled={store.loading ||
        store.verifying ||
        !store.challengeId ||
        !/^\d{5}$/.test(store.answer.trim())}
    >
      {#if store.verifying}<Spinner size="sm" />{/if}
      {t("wa_trial_captcha_continue")}
    </Button>
    <p id="trial-captcha-hint" class="trial-captcha-hint">
      <Clock size={13} aria-hidden="true" />
      {t("wa_trial_captcha_hint")}
    </p>
  </form>
</Dialog>

<style>
  :global(.dialog-card.trial-captcha-dialog) {
    width: min(100%, 420px);
    gap: 12px;
    padding: 22px;
    border-radius: 16px;
    background: var(--panel);
    background-image: none;
  }

  :global(.dialog-card.trial-captcha-dialog > .dialog-head) {
    gap: 10px;
    align-items: center;
    background: transparent;
  }

  :global(.trial-captcha-dialog .dialog-title-with-icon) {
    gap: 8px;
    align-items: center;
  }

  :global(.trial-captcha-dialog .dialog-head h2) {
    font-size: 20px;
    line-height: 1.25;
    font-weight: 750;
  }

  :global(.trial-captcha-dialog .dialog-close-button) {
    background: transparent;
    background-image: none;
    border-color: transparent;
    color: var(--muted);
    box-shadow: none;
    transform: none;
  }

  :global(.trial-captcha-dialog .dialog-close-button:hover:not(:disabled)) {
    background: var(--surface-hover);
    border-color: transparent;
    color: var(--text);
    box-shadow: none;
    transform: none;
  }

  .trial-captcha-body {
    display: grid;
    min-width: 0;
    gap: 16px;
    padding: 0;
  }

  .trial-captcha-description {
    margin: 0;
    color: var(--muted);
    font-size: 14px;
    line-height: 1.5;
  }

  .trial-captcha-challenge {
    display: grid;
    width: min(100%, 320px);
    gap: 2px;
    margin-inline: auto;
  }

  .trial-captcha-tools {
    display: flex;
    justify-content: flex-end;
  }

  :global(.trial-captcha-dialog .trial-captcha-refresh) {
    min-height: 36px;
    gap: 6px;
    padding: 0 4px;
    background: transparent;
    background-image: none;
    color: var(--muted);
    font-size: 12px;
    font-weight: 650;
    box-shadow: none;
  }

  :global(.trial-captcha-dialog .trial-captcha-refresh:hover:not(:disabled)) {
    color: var(--text);
    background: transparent;
    box-shadow: none;
    transform: none;
  }

  :global(.trial-captcha-dialog .dialog-close-button:focus-visible),
  :global(.trial-captcha-dialog .trial-captcha-refresh:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
    box-shadow: none;
  }

  .trial-captcha-image {
    display: grid;
    box-sizing: content-box;
    width: calc(100% - 2px);
    aspect-ratio: 20 / 7;
    place-items: center;
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: 12px;
    color: var(--muted);
    background: var(--surface-subtle);
  }

  .trial-captcha-image img {
    display: block;
    width: 100%;
    height: auto;
    object-fit: contain;
  }

  .trial-captcha-field {
    display: grid;
    gap: 8px;
    font-size: 13px;
    font-weight: 650;
  }

  :global(.trial-captcha-dialog .trial-captcha-answer) {
    min-height: 60px;
    padding: 10px 16px 10px calc(16px + 0.14em);
    border: 2px solid var(--border-strong);
    border-radius: 12px;
    background: var(--panel-2);
    color: var(--text);
    font-family: var(--font-mono);
    font-size: 28px;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.14em;
    line-height: 1.2;
    text-align: center;
    caret-color: var(--accent);
    outline: none;
    box-shadow: none;
  }

  :global(.trial-captcha-dialog .trial-captcha-answer:placeholder-shown) {
    padding-inline: 16px;
  }

  :global(.trial-captcha-dialog .trial-captcha-answer::placeholder) {
    color: var(--dim);
    font-family: var(--font-ui);
    font-size: 16px;
    font-weight: 450;
    letter-spacing: normal;
  }

  :global(.trial-captcha-dialog .trial-captcha-answer::selection) {
    color: var(--accent-contrast);
    background: var(--accent);
  }

  :global(.trial-captcha-dialog .trial-captcha-answer:focus),
  :global(.trial-captcha-dialog .trial-captcha-answer:focus-visible) {
    border-color: var(--accent);
    outline: none;
    box-shadow: none;
  }

  :global(.trial-captcha-dialog .trial-captcha-answer[aria-invalid="true"]) {
    border-color: var(--danger);
    caret-color: var(--danger);
  }

  :global(.trial-captcha-dialog .trial-captcha-answer[aria-invalid="true"]:focus),
  :global(.trial-captcha-dialog .trial-captcha-answer[aria-invalid="true"]:focus-visible) {
    border-color: var(--danger);
    outline: none;
    box-shadow: none;
  }

  :global(.trial-captcha-dialog .trial-captcha-error) {
    margin: -8px 0 0;
    background: transparent;
    font-size: 12px;
    line-height: 1.5;
  }

  :global(.dialog-card.trial-captcha-dialog .btn.trial-captcha-submit),
  :global(.dialog-card.trial-captcha-dialog .btn.trial-captcha-submit:hover:not(:disabled)) {
    min-height: 48px;
    background: var(--accent);
    background-image: none;
    border-color: var(--accent);
    color: var(--accent-contrast);
    box-shadow: none;
    transform: none;
  }

  :global(.dialog-card.trial-captcha-dialog .btn.trial-captcha-submit:hover:not(:disabled)) {
    background: color-mix(in srgb, var(--accent) 88%, var(--text));
  }

  :global(.dialog-card.trial-captcha-dialog .btn.trial-captcha-submit:focus-visible) {
    outline: 2px solid var(--accent-contrast);
    outline-offset: -4px;
    box-shadow: none;
  }

  .trial-captcha-hint {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    margin: -6px 0 0;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.45;
  }

  @media (max-width: 400px) {
    :global(.dialog-card.trial-captcha-dialog) {
      padding: 18px;
    }

    :global(.trial-captcha-dialog .dialog-head h2) {
      font-size: 18px;
    }

    .trial-captcha-body {
      gap: 14px;
    }
  }

  @media (max-height: 560px) {
    :global(.dialog-card.trial-captcha-dialog) {
      gap: 8px;
      padding: 16px;
    }

    .trial-captcha-body {
      gap: 10px;
    }

    .trial-captcha-challenge {
      max-width: 240px;
    }

    :global(.trial-captcha-dialog .trial-captcha-refresh) {
      min-height: 30px;
    }

    :global(.trial-captcha-dialog .trial-captcha-answer) {
      min-height: 54px;
      padding-block: 6px;
    }

    :global(.dialog-card.trial-captcha-dialog .btn.trial-captcha-submit) {
      min-height: 44px;
    }
  }
</style>
