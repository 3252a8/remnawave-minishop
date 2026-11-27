import { getStatus } from "./api";
import type { DetailArea, Status } from "./api";
import {
  cross,
  element,
  errorState,
  language,
  reasonList,
  root,
  stateMessage,
  translator,
} from "./ui";
import type { Props, View } from "./ui";

function telegramId(view: DetailArea, props: Props): string | null {
  const value =
    view === "ticket"
      ? props.context?.ticket?.user?.telegram_id
      : (props.user?.telegram_id ?? props.userDetail?.user?.telegram_id);
  if (typeof value === "number" && Number.isSafeInteger(value) && value > 0) return String(value);
  if (typeof value === "string" && /^[1-9]\d*$/u.test(value)) return value;
  return null;
}

export class StatusView implements View {
  private readonly node: HTMLElement;
  private request: AbortController | null = null;
  private id: string | null = null;
  private enabled = false;
  private status: Status | null = null;
  private failed: { error: unknown } | null = null;

  constructor(
    target: HTMLElement,
    private props: Props,
    private readonly view: DetailArea
  ) {
    this.node = root(target);
    this.node.classList.add("blacklist-status");
    if (props.active !== false) void this.load();
  }

  update(props: Props): void {
    const changed = language(props) !== language(this.props);
    const wasActive = this.props.active !== false;
    this.props = props;
    if (props.active === false) {
      this.request?.abort();
      this.request = null;
      this.node.replaceChildren();
    } else if (!wasActive || this.id !== telegramId(this.view, props)) {
      void this.load();
    } else if (changed) {
      this.render();
    }
  }

  destroy(): void {
    this.request?.abort();
    this.node.remove();
  }

  private async load(): Promise<void> {
    this.request?.abort();
    const controller = new AbortController();
    this.request = controller;
    this.id = telegramId(this.view, this.props);
    this.failed = null;
    this.status = null;
    this.enabled = false;
    this.render();
    try {
      const result = await getStatus(this.view, this.id, controller.signal);
      if (controller.signal.aborted) return;
      this.enabled = result.enabled;
      this.status = result.status;
    } catch (error) {
      if (!controller.signal.aborted) this.failed = { error };
    } finally {
      if (!controller.signal.aborted) {
        this.request = null;
        this.render();
      }
    }
  }

  private render(): void {
    const t = translator(this.props);
    this.node.replaceChildren();
    if (this.request) {
      this.node.append(stateMessage(t("loading")));
      return;
    }
    if (this.failed) {
      this.node.append(
        errorState(t, this.failed.error, () => {
          void this.load();
        })
      );
      return;
    }
    if (!this.enabled) {
      if (this.view === "userCard") this.node.append(stateMessage(t("user_status_disabled")));
      return;
    }
    if (!this.status) {
      this.node.append(stateMessage(t("unlinked")));
      return;
    }
    const { state, reasons, stale } = this.status;
    if (state !== "match") {
      this.node.append(stateMessage(t(state)));
      return;
    }

    const badge = element("p", undefined, "blacklist-badge");
    badge.setAttribute("role", "status");
    badge.append(cross(), element("strong", t("match")));
    this.node.append(badge);
    const comments = reasonList(reasons, t);
    if (comments.childNodes.length) this.node.append(comments);
    if (stale) this.node.append(element("p", t("stale"), "blacklist-muted"));
  }
}
