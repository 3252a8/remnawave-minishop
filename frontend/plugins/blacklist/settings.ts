import { AREAS, EVENTS, getSettings, putSettings, startSourceRefresh } from "./api";
import type { Settings, SettingsData } from "./api";
import {
  button,
  element,
  errorState,
  errorText,
  language,
  root,
  stateMessage,
  translator,
} from "./ui";
import type { Props, Translate, View } from "./ui";

const displayLabels = {
  usersTable: "display_users_table",
  users: "display_users",
  userCard: "display_user_card",
  ticket: "display_ticket",
} as const;

interface Draft {
  sources: string;
  refreshHours: string;
  display: Settings["display"];
  chatId: string;
  topicId: string;
  events: Set<Settings["events"][number]>;
}

function draftFrom(settings: Settings): Draft {
  return {
    sources: settings.sources.join("\n"),
    refreshHours: String(settings.refreshHours),
    display: { ...settings.display },
    chatId: settings.chatId ?? "",
    topicId: settings.topicId ?? "",
    events: new Set(settings.events),
  };
}

function field(label: string, control: HTMLElement, hint?: string): HTMLLabelElement {
  const node = element("label", undefined, "blacklist-field");
  node.append(element("span", label), control);
  if (hint) node.append(element("small", hint));
  return node;
}

function input(name: string, value: string, onInput: (value: string) => void): HTMLInputElement {
  const control = element("input");
  control.name = name;
  control.value = value;
  control.addEventListener("input", () => onInput(control.value));
  return control;
}

function checkbox(name: string, checked: boolean): HTMLInputElement {
  const control = element("input");
  control.type = "checkbox";
  control.name = name;
  control.checked = checked;
  return control;
}

function checkLabel(text: string, control: HTMLInputElement): HTMLLabelElement {
  const label = element("label", undefined, "blacklist-check");
  label.append(control, element("span", text));
  return label;
}

function checkGroup(title: string): HTMLFieldSetElement {
  const group = element("fieldset", undefined, "blacklist-group");
  group.append(element("legend", title));
  return group;
}

export class SettingsView implements View {
  private readonly node: HTMLElement;
  private readonly sourceSection = element("section", undefined, "blacklist-sources");
  private readonly controller = new AbortController();
  private data: SettingsData | null = null;
  private draft: Draft | null = null;
  private operation: "load" | "refresh" | "save" | null = null;
  private feedback: { operation: "load" | "refresh" | "save"; error: unknown } | null = null;
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;
  private refreshRead: AbortController | null = null;
  private refreshFeedback: { error: unknown } | null = null;
  private refreshFinished = false;
  private saved = false;

  constructor(
    target: HTMLElement,
    private props: Props
  ) {
    this.node = root(target);
    void this.load();
  }

  update(props: Props): void {
    const changed = language(props) !== language(this.props);
    this.props = props;
    if (changed) this.render();
  }

  destroy(): void {
    this.controller.abort();
    this.stopPolling();
    this.node.remove();
  }

  private async load(): Promise<void> {
    await this.run("load", async () => {
      const data = await getSettings(this.controller.signal);
      this.draft = draftFrom(data.settings);
      this.data = data;
    });
  }

  private async refreshSources(): Promise<void> {
    await this.run("refresh", async () => {
      const data = await startSourceRefresh(this.controller.signal);
      this.data = data;
      this.refreshFinished = !data.refreshPending;
    });
  }

  private stopPolling(): void {
    if (this.refreshTimer !== null) clearTimeout(this.refreshTimer);
    this.refreshTimer = null;
    this.refreshRead?.abort();
    this.refreshRead = null;
  }

  private schedulePoll(): void {
    if (!this.data?.refreshPending || this.operation || this.controller.signal.aborted) return;
    this.refreshTimer = setTimeout(
      () => {
        this.refreshTimer = null;
        void this.pollRefresh();
      },
      this.refreshFeedback ? 10_000 : 3_000
    );
  }

  private async pollRefresh(): Promise<void> {
    const request = new AbortController();
    this.refreshRead = request;
    try {
      const data = await getSettings(request.signal);
      if (request.signal.aborted) return;
      this.data = data;
      this.refreshFinished = !data.refreshPending;
      this.refreshFeedback = null;
    } catch (error) {
      if (!request.signal.aborted) this.refreshFeedback = { error };
    } finally {
      if (this.refreshRead === request) {
        this.refreshRead = null;
        if (this.data) this.renderSourceList(this.data, translator(this.props));
        this.schedulePoll();
      }
    }
  }

  private async save(draft: Draft): Promise<void> {
    const previousUsersTable = this.data?.settings.display.usersTable;
    await this.run("save", async () => {
      const data = await putSettings(
        {
          sources: draft.sources
            .split(/\r?\n/u)
            .map((value) => value.trim())
            .filter(Boolean),
          refreshHours: Number(draft.refreshHours),
          display: draft.display,
          chatId: draft.chatId.trim() || null,
          topicId: draft.topicId.trim() || null,
          events: EVENTS.filter((event) => draft.events.has(event)),
        },
        this.controller.signal
      );
      this.data = data;
      this.draft = draftFrom(data.settings);
      this.saved = true;
    });
    if (
      this.saved &&
      this.data?.supportsUsersTable &&
      this.data.settings.display.usersTable !== previousUsersTable &&
      !this.controller.signal.aborted
    ) {
      // Minishop can reuse a cached list when returning to /admin/users.
      window.location.reload();
    }
  }

  private async run(
    operation: "load" | "refresh" | "save",
    action: () => Promise<void>
  ): Promise<void> {
    if (this.operation || this.controller.signal.aborted) return;
    this.stopPolling();
    this.operation = operation;
    this.feedback = null;
    this.refreshFeedback = null;
    this.refreshFinished = false;
    this.saved = false;
    const focus = this.node.contains(document.activeElement);
    this.render();
    try {
      await action();
    } catch (error) {
      this.feedback = { operation, error };
    } finally {
      this.operation = null;
      if (!this.controller.signal.aborted) {
        this.render();
        this.schedulePoll();
        if (focus && document.activeElement === document.body) {
          const control = operation === "save" ? "save" : "sourceRefresh";
          this.node.querySelector<HTMLButtonElement>(`button[name="${control}"]`)?.focus();
        }
      }
    }
  }

  private displayControls(draft: Draft, t: Translate): HTMLFieldSetElement {
    const group = checkGroup(t("display"));
    for (const area of AREAS) {
      if (area === "usersTable" && !this.data?.supportsUsersTable) continue;
      const control = checkbox(area, draft.display[area]);
      control.addEventListener("change", () => {
        draft.display[area] = control.checked;
      });
      group.append(checkLabel(t(displayLabels[area]), control));
    }
    return group;
  }

  private alertsControls(draft: Draft, t: Translate): HTMLFieldSetElement {
    const alerts = checkGroup(t("alerts"));
    const destination = element("div", undefined, "blacklist-fields-grid");
    const chatId = input("chatId", draft.chatId, (value) => {
      draft.chatId = value;
    });
    const topicId = input("topicId", draft.topicId, (value) => {
      draft.topicId = value;
    });
    topicId.inputMode = "numeric";
    destination.append(field(t("chat_id"), chatId), field(t("topic_id"), topicId, t("topic_hint")));

    const events = checkGroup(t("events"));
    const selectAll = checkbox("allEvents", draft.events.size === EVENTS.length);
    const eventControls = EVENTS.map((event) => {
      const control = checkbox(event, draft.events.has(event));
      control.addEventListener("change", () => {
        if (control.checked) draft.events.add(event);
        else draft.events.delete(event);
        updateAll();
      });
      return control;
    });
    const updateAll = (): void => {
      selectAll.checked = draft.events.size === EVENTS.length;
      selectAll.indeterminate = draft.events.size > 0 && draft.events.size < EVENTS.length;
    };
    selectAll.addEventListener("change", () => {
      draft.events = new Set(selectAll.checked ? EVENTS : []);
      for (const control of eventControls) control.checked = selectAll.checked;
    });
    updateAll();
    events.append(checkLabel(t("all_events"), selectAll));
    for (const [index, event] of EVENTS.entries()) {
      const control = eventControls[index];
      if (control) events.append(checkLabel(t(event), control));
    }
    alerts.append(destination, events);
    return alerts;
  }

  private form(draft: Draft, t: Translate): HTMLFormElement {
    const form = element("form");
    const fields = element("fieldset", undefined, "blacklist-config");
    fields.disabled = this.operation !== null;
    const sources = element("textarea");
    sources.name = "sources";
    sources.rows = 4;
    sources.spellcheck = false;
    sources.value = draft.sources;
    sources.addEventListener("input", () => {
      draft.sources = sources.value;
    });

    const interval = input("refreshHours", draft.refreshHours, (value) => {
      draft.refreshHours = value;
    });
    interval.type = "number";
    interval.min = "1";
    interval.max = "8760";
    interval.step = "1";
    interval.required = true;
    const submit = button(t(this.operation === "save" ? "saving" : "save"));
    submit.type = "submit";
    submit.name = "save";
    submit.classList.add("blacklist-primary");
    fields.append(
      field(t("sources"), sources, t("sources_hint")),
      field(t("refresh_hours"), interval),
      this.displayControls(draft, t),
      this.alertsControls(draft, t),
      submit
    );
    form.append(fields);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this.save(draft);
    });
    return form;
  }

  private renderSourceList(data: SettingsData, t: Translate): void {
    const section = this.sourceSection;
    section.replaceChildren();
    const toolbar = element("div", undefined, "blacklist-toolbar");
    const pending = data.refreshPending || this.operation === "refresh";
    const refresh = button(t(pending ? "sources_refreshing" : "refresh_sources"), () => {
      void this.refreshSources();
    });
    refresh.name = "sourceRefresh";
    refresh.disabled = pending || this.operation !== null || !data.sourceStatuses.length;
    toolbar.append(element("h3", t("source_statuses")), refresh);
    section.append(toolbar);
    if (this.refreshFeedback) {
      section.append(
        stateMessage(errorText(t, this.refreshFeedback.error, "request_failed"), "alert")
      );
    }
    if (this.refreshFinished) section.append(stateMessage(t("sources_refresh_finished")));
    if (!data.sourceStatuses.length) {
      section.append(stateMessage(t("source_none")));
      return;
    }

    const date = new Intl.DateTimeFormat(language(this.props), {
      dateStyle: "medium",
      timeStyle: "short",
    });
    const stamp = (value: string | null): string | null => {
      const time = value ? Date.parse(value) : NaN;
      return Number.isFinite(time) ? date.format(time) : null;
    };
    const list = element("ul", undefined, "blacklist-source-statuses");
    for (const source of data.sourceStatuses) {
      const item = element("li");
      const lastSuccess = stamp(source.lastSuccessAt);
      item.append(element("strong", source.url));
      if (source.lastError) {
        const attempt = stamp(source.lastAttemptAt);
        const failure = attempt ? t("source_failed_at", { date: attempt }) : t("source_failed");
        item.append(element("p", failure, "blacklist-error"));
      }
      if (lastSuccess)
        item.append(
          element("p", t("source_last_success", { date: lastSuccess }), "blacklist-muted")
        );
      else if (!source.lastError) item.append(element("p", t("source_pending"), "blacklist-muted"));
      if (source.count !== null)
        item.append(element("p", t("source_count", { count: source.count }), "blacklist-muted"));
      if (source.invalidLines) {
        item.append(
          element("p", t("source_invalid_lines", { count: source.invalidLines }), "blacklist-muted")
        );
      }
      list.append(item);
    }
    section.append(list);
  }

  private render(): void {
    const t = translator(this.props);
    this.node.replaceChildren();
    this.node.setAttribute("aria-busy", String(this.operation !== null));
    if (!this.data || !this.draft) {
      this.node.append(
        this.feedback
          ? errorState(t, this.feedback.error, () => {
              void this.load();
            })
          : stateMessage(t("loading"))
      );
      return;
    }

    if (this.feedback) {
      const key = this.feedback.operation === "save" ? "save_failed" : "request_failed";
      this.node.append(stateMessage(errorText(t, this.feedback.error, key), "alert"));
    }
    if (this.saved) this.node.append(stateMessage(t("saved")));
    this.renderSourceList(this.data, t);
    this.node.append(this.form(this.draft, t), this.sourceSection);
  }
}
