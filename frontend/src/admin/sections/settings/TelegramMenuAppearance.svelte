<script lang="ts">
  import { onMount } from "svelte";
  import { AdminBadge, AdminButton, AdminField, AdminSelect } from "$components/patterns/admin";
  import { Check, Paintbrush, RotateCcw, Save, Send, Sparkles } from "$components/ui/icons";
  import EmojiGlyph from "$lib/telegramEmoji/EmojiGlyph.svelte";
  import EmojiPicker from "$lib/telegramEmoji/EmojiPicker.svelte";
  import EmojiLibraryManager from "$lib/telegramEmoji/EmojiLibraryManager.svelte";
  import {
    defaultTelegramEmojiApi,
    getEmojiAdminId,
    getMenuConfiguration,
    getMenuPreview,
    saveMenuAppearance,
    sendMenuTest,
    telegramEmojiErrorCode,
    type TelegramEmojiApi,
  } from "$lib/telegramEmoji/api";
  import { cacheMenuDraft, clearMenuDraft, readMenuDraft } from "$lib/telegramEmoji/menuDraft";
  import type {
    ButtonAppearance,
    ButtonStyle,
    EmojiItem,
    IconMode,
    MenuAppearance,
    MenuConfiguration,
    MenuPreview,
    MenuPreviewRequest,
    MenuScenario,
    MenuScreen,
    TranslateFn,
  } from "$lib/telegramEmoji/types";
  import TelegramMenuPreview from "./TelegramMenuPreview.svelte";

  let {
    at,
    api = defaultTelegramEmojiApi,
    onOpenCustomButtons = () => {},
    onSaved = () => {},
    subscribeSettingsSaved,
  }: {
    at: TranslateFn;
    api?: TelegramEmojiApi;
    onOpenCustomButtons?: () => void;
    onSaved?: (appearance: MenuAppearance) => void;
    subscribeSettingsSaved?: (listener: () => void) => () => void;
  } = $props();
  const defaults = (): MenuAppearance => ({ schema_version: 1, buttons: {} });
  const copy = (value: MenuAppearance): MenuAppearance => structuredClone($state.snapshot(value));
  let configuration = $state<MenuConfiguration | null>(null);
  let saved = $state<MenuAppearance>(defaults());
  let draft = $state<MenuAppearance>(defaults());
  let loading = $state(true);
  let saving = $state(false);
  let testing = $state(false);
  let error = $state("");
  let notice = $state("");
  let preview = $state<MenuPreview | null>(null);
  let previewLoading = $state(true);
  let previewError = $state("");
  let previewGeneration = $state(0);
  let screen = $state<MenuScreen>("main");
  let language = $state("");
  let scenario = $state<MenuScenario>("new");
  let theme = $state<"light" | "dark">("dark");
  let selectedId = $state("");
  let pickerOpen = $state(false);
  let selectedEmoji = $state<EmojiItem | null>(null);
  let alive = true;
  let adminId = "";
  let loadSequence = 0;
  let discardDraftOnUnmount = false;
  const dirty = $derived(JSON.stringify(draft) !== JSON.stringify(saved));
  const conflict = $derived(error.includes("conflict"));
  const buttons = $derived(
    (configuration?.buttons || []).filter((button) => button.screens.includes(screen))
  );
  const selectedButton = $derived(
    buttons.find((button) => button.id === selectedId) || buttons[0] || null
  );
  const current = $derived(
    selectedButton
      ? draft.buttons[selectedButton.id] || {
          style: "default" as const,
          icon_custom_emoji_id: null,
          icon_mode: "inherit" as const,
        }
      : null
  );
  const currentPreview = $derived(
    preview?.rows.flat().find((button) => button.id === selectedButton?.id)
  );
  const hiddenButton = $derived(preview?.hidden.find((button) => button.id === selectedButton?.id));
  const iconMode = $derived(
    current?.icon_mode || (current?.icon_custom_emoji_id ? "custom" : "inherit")
  );
  const screens = $derived(
    (["main", "bot", "information"] as const).map((value) => ({
      value,
      label: at(`telegram_menu_screen_${value}`),
    }))
  );
  const scenarios = $derived(
    (["new", "active", "trial_unavailable"] as const).map((value) => ({
      value,
      label: at(`telegram_menu_scenario_${value}`),
    }))
  );
  const styles = $derived(
    (["default", "primary", "success", "danger"] as const).map((value) => ({
      value,
      label: at(`telegram_menu_style_${value}`),
    }))
  );
  const iconModes = $derived(
    (["inherit", "none", "custom"] as const).map((value) => ({
      value,
      label: at(`telegram_menu_icon_${value}`),
    }))
  );

  function labelFor(id: string): string {
    const shown = preview?.rows.flat().find((button) => button.id === id);
    const hidden = preview?.hidden.find((button) => button.id === id);
    const registered = configuration?.buttons.find((button) => button.id === id);
    return (
      shown?.label || hidden?.label || registered?.label || at(`telegram_menu_button_${id}`, {}, id)
    );
  }
  async function load(discardDraft = false) {
    const sequence = ++loadSequence;
    loading = true;
    error = "";
    try {
      const [menu, identity] = await Promise.allSettled([
        getMenuConfiguration(api),
        getEmojiAdminId(api),
      ]);
      if (!alive || sequence !== loadSequence) return;
      if (menu.status === "rejected") throw menu.reason;
      const result = menu.value;
      adminId = identity.status === "fulfilled" ? identity.value : "";
      if (discardDraft) clearMenuDraft(api, adminId);
      const cached = readMenuDraft(api, adminId);
      configuration = cached ? { ...result, revision: cached.revision } : result;
      saved = copy(cached?.saved || result.appearance);
      draft = copy(cached?.draft || result.appearance);
      discardDraftOnUnmount = false;
      notice = cached ? "telegram_menu_draft_restored" : "";
      if (cached && cached.revision !== result.revision) error = "telegram_menu_revision_conflict";
      if (!language) language = result.languages[0]?.code || "en";
      previewGeneration += 1;
    } catch (failure) {
      if (alive && sequence === loadSequence)
        error = telegramEmojiErrorCode(failure, "telegram_menu_load_failed");
    } finally {
      if (alive && sequence === loadSequence) loading = false;
    }
  }
  function update(patch: Partial<ButtonAppearance>) {
    if (!selectedButton || !current || saving) return;
    const value = { ...current, ...patch };
    const values = { ...draft.buttons };
    if (
      value.style === "default" &&
      !value.icon_custom_emoji_id &&
      (value.icon_mode || "inherit") === "inherit"
    )
      delete values[selectedButton.id];
    else values[selectedButton.id] = value;
    draft = { schema_version: 1, buttons: values };
    notice = "";
  }
  function resetButton() {
    if (!selectedButton) return;
    const values = { ...draft.buttons };
    delete values[selectedButton.id];
    draft = { schema_version: 1, buttons: values };
    selectedEmoji = null;
    notice = "";
  }
  function setIconMode(mode: IconMode) {
    if (saving) return;
    if (mode === "custom" && !current?.icon_custom_emoji_id) pickerOpen = true;
    else update({ icon_mode: mode });
  }
  function chooseEmoji(item: EmojiItem) {
    if (!item.id || saving) return;
    selectedEmoji = item;
    update({ icon_mode: "custom", icon_custom_emoji_id: item.id });
  }
  async function save() {
    if (!configuration || !dirty || saving) return;
    saving = true;
    error = "";
    notice = "";
    try {
      const result = await saveMenuAppearance(api, copy(draft), configuration.revision);
      clearMenuDraft(api, adminId);
      onSaved(copy(result.appearance));
      if (!alive) return;
      configuration = result;
      saved = copy(result.appearance);
      draft = copy(result.appearance);
      notice = "telegram_menu_saved";
    } catch (failure) {
      if (alive) error = telegramEmojiErrorCode(failure, "telegram_menu_save_failed");
    } finally {
      if (alive) saving = false;
    }
  }
  async function test() {
    if (!configuration || testing) return;
    testing = true;
    error = "";
    notice = "";
    try {
      const result = await sendMenuTest(api, {
        appearance: copy(draft),
        screen,
        language,
        scenario,
      });
      if (!alive) return;
      configuration = { ...configuration, capabilities: result.capabilities };
      notice = result.sent ? "telegram_menu_test_sent" : "telegram_menu_test_not_sent";
      previewGeneration += 1;
    } catch (failure) {
      if (alive) error = telegramEmojiErrorCode(failure, "telegram_menu_test_failed");
    } finally {
      if (alive) testing = false;
    }
  }
  $effect(() => {
    const body: MenuPreviewRequest = { appearance: copy(draft), screen, language, scenario };
    const generation = previewGeneration;
    if (!configuration || loading || !language) return;
    const controller = new AbortController();
    previewLoading = true;
    previewError = "";
    const timer = window.setTimeout(
      () => {
        void getMenuPreview(api, body, controller.signal)
          .then((result) => {
            if (!controller.signal.aborted) preview = result;
          })
          .catch((failure: unknown) => {
            if (!controller.signal.aborted)
              previewError = telegramEmojiErrorCode(failure, "telegram_menu_preview_failed");
          })
          .finally(() => {
            if (!controller.signal.aborted) previewLoading = false;
          });
      },
      generation ? 100 : 180
    );
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  });
  onMount(() => {
    const unsubscribe = subscribeSettingsSaved?.(() => {
      discardDraftOnUnmount = true;
      clearMenuDraft(api, adminId);
      void load(true);
    });
    void load();
    return () => {
      unsubscribe?.();
      if (configuration && dirty && !discardDraftOnUnmount)
        cacheMenuDraft(api, adminId, {
          revision: configuration.revision,
          saved: copy(saved),
          draft: copy(draft),
        });
      else clearMenuDraft(api, adminId);
      alive = false;
    };
  });
</script>

<div class="menu-appearance">
  {#if error}<div class="menu-notice error" role="alert">
      <p>{at(error, {}, at("telegram_menu_save_failed"))}</p>
      {#if conflict}<AdminButton
          size="sm"
          controlSize="md"
          onclick={() => {
            void load(true);
          }}>{at("telegram_menu_reload")}</AdminButton
        >{/if}
    </div>{/if}
  {#if notice}<p class="menu-notice" role="status">{at(notice)}</p>{/if}
  {#if loading}<p class="muted" role="status">{at("loading")}</p>
  {:else if configuration}
    <div class="menu-introduction">
      <Paintbrush size={19} />
      <p>{at("telegram_menu_description")}</p>
    </div>
    <div class="preview-controls">
      <AdminField label={at("telegram_menu_screen")}
        ><AdminSelect
          controlSize="md"
          value={screen}
          items={screens}
          ariaLabel={at("telegram_menu_screen")}
          onValueChange={(value) => {
            screen = value as MenuScreen;
          }}
        /></AdminField
      >
      <AdminField label={at("telegram_menu_language")}
        ><AdminSelect
          controlSize="md"
          value={language}
          items={configuration.languages.map((item) => ({ value: item.code, label: item.name }))}
          ariaLabel={at("telegram_menu_language")}
          onValueChange={(value) => {
            language = value;
          }}
        /></AdminField
      >
      <AdminField label={at("telegram_menu_scenario")}
        ><AdminSelect
          controlSize="md"
          value={scenario}
          items={scenarios}
          ariaLabel={at("telegram_menu_scenario")}
          onValueChange={(value) => {
            scenario = value as MenuScenario;
          }}
        /></AdminField
      >
      <AdminField label={at("telegram_menu_theme")}
        ><AdminSelect
          controlSize="md"
          value={theme}
          items={[
            { value: "dark", label: at("telegram_menu_theme_dark") },
            { value: "light", label: at("telegram_menu_theme_light") },
          ]}
          ariaLabel={at("telegram_menu_theme")}
          onValueChange={(value) => {
            theme = value as "light" | "dark";
          }}
        /></AdminField
      >
    </div>
    <div class="menu-workspace">
      <section class="button-editor" aria-label={at("telegram_menu_button_editor")}>
        <AdminField label={at("telegram_menu_button")}
          ><AdminSelect
            controlSize="md"
            value={selectedButton?.id || ""}
            disabled={saving}
            items={buttons.map((button) => ({ value: button.id, label: labelFor(button.id) }))}
            ariaLabel={at("telegram_menu_button")}
            onValueChange={(value) => {
              selectedId = value;
              selectedEmoji = null;
            }}
          /></AdminField
        >
        {#if selectedButton && current}
          <div class="button-identity">
            <code>{selectedButton.id}</code>{#if draft.buttons[selectedButton.id]}<AdminBadge
                >{at("telegram_menu_customized")}</AdminBadge
              >{/if}
          </div>
          {#if hiddenButton}<p class="hidden-reason">
              {at("telegram_menu_hidden", {
                reason: at(`telegram_menu_hidden_${hiddenButton.reason}`, {}, hiddenButton.reason),
              })}
            </p>{/if}
          <fieldset class="style-field">
            <legend>{at("telegram_menu_color")}</legend>
            <div class="style-options">
              {#each styles as item (item.value)}<AdminButton
                  size="sm"
                  controlSize="md"
                  variant="ghost"
                  class="style-choice"
                  disabled={saving}
                  aria-pressed={current.style === item.value}
                  onclick={() => update({ style: item.value as ButtonStyle })}
                  ><span class="color-swatch" data-style={item.value}
                  ></span>{item.label}{#if current.style === item.value}<Check
                      size={13}
                    />{/if}</AdminButton
                >{/each}
            </div>
          </fieldset>
          <AdminField label={at("telegram_menu_icon")}
            ><AdminSelect
              controlSize="md"
              value={iconMode}
              disabled={saving}
              items={iconModes}
              ariaLabel={at("telegram_menu_icon")}
              onValueChange={(value) => setIconMode(value as IconMode)}
            /></AdminField
          >
          {#if iconMode === "custom" && current.icon_custom_emoji_id}
            <div class="chosen-emoji">
              <EmojiGlyph
                fallback={selectedEmoji?.id === current.icon_custom_emoji_id
                  ? selectedEmoji.fallback
                  : currentPreview?.emoji_fallback || selectedButton.emoji_fallback}
                url={selectedEmoji?.id === current.icon_custom_emoji_id
                  ? selectedEmoji.thumbnail_url
                  : currentPreview?.thumbnail_url}
                size={30}
              /><code>{current.icon_custom_emoji_id}</code><AdminButton
                size="sm"
                controlSize="md"
                disabled={saving}
                onclick={() => {
                  pickerOpen = true;
                }}><Sparkles size={14} />{at("telegram_menu_change_emoji")}</AdminButton
              >
            </div>
          {/if}
          <p class="muted">{at("telegram_menu_icon_hint")}</p>
          <div class="editor-secondary">
            <AdminButton
              size="sm"
              controlSize="md"
              variant="ghost"
              disabled={!draft.buttons[selectedButton.id] || saving}
              onclick={resetButton}
              ><RotateCcw size={14} />{at("telegram_menu_reset_button")}</AdminButton
            >
          </div>
        {:else}<p class="muted">{at("telegram_menu_no_buttons")}</p>{/if}
        <div class="custom-buttons-note">
          <p>{at("telegram_menu_custom_buttons_hint")}</p>
          <AdminButton size="sm" controlSize="md" variant="ghost" onclick={onOpenCustomButtons}
            >{at("telegram_menu_custom_buttons_link")}</AdminButton
          >
        </div>
      </section>
      <div class="preview-column">
        <TelegramMenuPreview
          {at}
          {preview}
          loading={previewLoading}
          error={previewError}
          {theme}
          selectedId={selectedButton?.id || ""}
          onSelect={(id) => {
            selectedId = id;
            selectedEmoji = null;
          }}
        />
        <p class="muted approximate-note">{at("telegram_menu_approximate")}</p>
        {#if previewError}<AdminButton
            size="sm"
            controlSize="md"
            onclick={() => {
              previewGeneration += 1;
            }}>{at("retry")}</AdminButton
          >{/if}
      </div>
    </div>
    {#if preview?.hidden.length}<details class="hidden-buttons">
        <summary>{at("telegram_menu_hidden_buttons", { count: preview.hidden.length })}</summary>
        <ul>
          {#each preview.hidden as hidden (hidden.id)}<li>
              <strong>{hidden.label}</strong><span
                >{at(`telegram_menu_hidden_${hidden.reason}`, {}, hidden.reason)}</span
              >
            </li>{/each}
        </ul>
      </details>{/if}
    <div class="menu-savebar">
      <span class="draft-state" aria-live="polite"
        >{dirty ? at("telegram_menu_unsaved") : at("telegram_menu_saved_state")}</span
      >
      <div>
        <AdminButton
          size="sm"
          variant="ghost"
          controlSize="md"
          disabled={saving || !Object.keys(draft.buttons).length}
          onclick={() => {
            draft = defaults();
            notice = "";
          }}>{at("telegram_menu_reset_all")}</AdminButton
        ><AdminButton
          controlSize="md"
          disabled={saving || !dirty}
          variant="ghost"
          onclick={() => {
            draft = copy(saved);
            clearMenuDraft(api, adminId);
            selectedEmoji = null;
            notice = "";
            error = "";
          }}>{at("cancel")}</AdminButton
        ><AdminButton
          controlSize="md"
          variant="primary"
          disabled={saving || !dirty}
          onclick={() => {
            void save();
          }}><Save size={15} />{saving ? at("saving") : at("save")}</AdminButton
        >
      </div>
    </div>
    <section class="capability-panel" aria-label={at("telegram_menu_telegram_test")}>
      <div class="capability-heading">
        <div>
          <h3>{at("telegram_menu_telegram_test")}</h3>
          <p>{at("telegram_menu_test_hint")}</p>
        </div>
        <AdminButton
          controlSize="md"
          disabled={testing || saving}
          onclick={() => {
            void test();
          }}
          ><Send size={15} />{testing
            ? at("telegram_menu_testing")
            : at("telegram_menu_test_self")}</AdminButton
        >
      </div>
      <div class="capability-list">
        {#each ["icon", "text"] as kind (kind)}{@const capability =
            configuration.capabilities[kind as "icon" | "text"]}
          <div>
            <span>{at(`telegram_menu_capability_${kind}`)}</span><AdminBadge
              variant={capability.state === "supported"
                ? "success"
                : capability.state === "unavailable"
                  ? "warning"
                  : "muted"}>{at(`telegram_menu_capability_${capability.state}`)}</AdminBadge
            >{#if capability.tested_at}<time datetime={capability.tested_at}
                >{new Date(capability.tested_at).toLocaleString(language)}</time
              >{/if}
          </div>{/each}
      </div>
    </section>
    <div class="menu-library"><EmojiLibraryManager {at} {api} /></div>
  {:else}<AdminButton
      controlSize="md"
      onclick={() => {
        void load();
      }}>{at("retry")}</AdminButton
    >{/if}
</div>
<EmojiPicker
  open={pickerOpen}
  onOpenChange={(value) => {
    pickerOpen = value;
  }}
  onSelect={chooseEmoji}
  {at}
  {api}
  allowOrdinary={false}
/>

<style>
  .menu-appearance {
    display: grid;
    gap: 18px;
    min-width: 0;
    width: 100%;
  }
  p,
  h3 {
    margin: 0;
  }
  .muted {
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.5;
  }
  .menu-introduction {
    display: flex;
    align-items: flex-start;
    gap: 9px;
    color: var(--admin-muted);
    font-size: 13px;
    line-height: 1.5;
  }
  .menu-introduction > :global(svg) {
    flex: 0 0 auto;
    margin-top: 1px;
    color: var(--admin-accent);
  }
  .preview-controls {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
    align-items: end;
  }
  .menu-workspace {
    display: grid;
    grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);
    gap: 20px;
    align-items: start;
  }
  .preview-column {
    min-width: 0;
  }
  .button-editor {
    display: grid;
    align-content: start;
    gap: 14px;
    min-width: 0;
    padding: 16px;
    border: 1px solid var(--admin-border);
    border-radius: 12px;
  }
  .button-identity {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-top: -5px;
  }
  code {
    color: var(--admin-muted);
    font-size: 11px;
    overflow-wrap: anywhere;
  }
  .style-field {
    margin: 0;
    padding: 0;
    border: 0;
    min-width: 0;
  }
  .style-field legend {
    font-size: 12px;
    font-weight: 600;
    padding: 0 0 8px;
  }
  .style-options {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 6px;
  }
  .style-options :global(.style-choice) {
    justify-content: flex-start;
  }
  .style-options :global(.style-choice[aria-pressed="true"]) {
    border-color: var(--admin-accent);
    background: color-mix(in srgb, var(--admin-accent) 8%, var(--admin-card-bg));
  }
  .style-options :global(.style-choice svg) {
    margin-left: auto;
    flex: 0 0 auto;
  }
  .color-swatch {
    width: 13px;
    height: 13px;
    border: 1px solid var(--admin-border);
    border-radius: 4px;
    flex: 0 0 auto;
    background: var(--admin-muted);
  }
  .color-swatch[data-style="primary"] {
    background: #3589d2;
  }
  .color-swatch[data-style="success"] {
    background: #2b9460;
  }
  .color-swatch[data-style="danger"] {
    background: #cc4c53;
  }
  .chosen-emoji {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 9px;
    border: 1px solid var(--admin-border);
    border-radius: 9px;
  }
  .chosen-emoji code {
    flex: 1;
    min-width: 0;
  }
  .chosen-emoji > :global(.admin-btn) {
    flex: 0 0 auto;
  }
  .editor-secondary {
    display: flex;
    justify-content: flex-start;
  }
  .custom-buttons-note {
    border-top: 1px solid var(--admin-border);
    padding-top: 12px;
    display: grid;
    justify-items: start;
    gap: 5px;
  }
  .custom-buttons-note p {
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.5;
  }
  .preview-column {
    min-width: 0;
    display: grid;
    gap: 9px;
  }
  .approximate-note {
    padding: 0 3px;
  }
  .hidden-reason {
    color: var(--admin-muted);
    font-size: 12px;
    padding: 9px 10px;
    background: var(--admin-surface-bg, var(--admin-card-bg));
    border-left: 2px solid var(--admin-border);
    line-height: 1.5;
  }
  .hidden-buttons {
    padding: 12px 14px;
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    font-size: 12px;
  }
  .hidden-buttons summary {
    cursor: pointer;
    color: var(--admin-muted);
  }
  .hidden-buttons ul {
    list-style: none;
    margin: 12px 0 0;
    padding: 0;
    display: grid;
    gap: 8px;
  }
  .hidden-buttons li {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
  }
  .hidden-buttons li span {
    color: var(--admin-muted);
  }
  .menu-savebar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding-top: 14px;
    border-top: 1px solid var(--admin-border);
  }
  .menu-savebar > div {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
  .draft-state {
    color: var(--admin-muted);
    font-size: 12px;
  }
  .capability-panel {
    display: grid;
    gap: 14px;
    padding: 16px;
    border: 1px solid var(--admin-border);
    border-radius: 12px;
  }
  .capability-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 14px;
  }
  .capability-heading h3 {
    font-size: 14px;
  }
  .capability-heading p {
    margin-top: 5px;
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.5;
    max-width: 460px;
  }
  .capability-heading > :global(.admin-btn) {
    flex: 0 0 auto;
  }
  .capability-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }
  .capability-list > div {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    font-size: 12px;
  }
  .capability-list time {
    color: var(--admin-muted);
    font-size: 11px;
    width: 100%;
  }
  .menu-library {
    padding-top: 6px;
  }
  .menu-notice {
    border-radius: 8px;
    padding: 12px;
    color: var(--admin-accent);
    background: var(--admin-surface-bg, var(--admin-card-bg));
    font-size: 13px;
    line-height: 1.5;
  }
  .menu-notice.error {
    color: var(--admin-danger, #ef4444);
    display: grid;
    gap: 10px;
    justify-items: start;
  }
  @media (max-width: 1000px) {
    .preview-controls {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
  @media (max-width: 680px) {
    .menu-workspace {
      grid-template-columns: minmax(0, 1fr);
      gap: 14px;
    }
    .button-editor {
      padding: 12px;
    }
    .preview-column {
      order: -1;
    }
    .menu-savebar,
    .capability-heading {
      align-items: stretch;
      flex-direction: column;
    }
    .menu-savebar > div {
      justify-content: flex-end;
    }
    .capability-heading > :global(.admin-btn) {
      align-self: flex-start;
    }
    .capability-list {
      grid-template-columns: minmax(0, 1fr);
    }
    .hidden-buttons li {
      align-items: flex-start;
      flex-direction: column;
      gap: 2px;
    }
  }
  @media (max-width: 380px) {
    .preview-controls {
      grid-template-columns: minmax(0, 1fr);
    }
    .chosen-emoji {
      flex-wrap: wrap;
    }
  }
</style>
