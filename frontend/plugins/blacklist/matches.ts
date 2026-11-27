import { getMatches } from "./api";
import type { MatchFilters, MatchPage } from "./api";
import {
  listAddress,
  MATCH_PAGE_SIZE,
  matchesPagination,
  matchesToolbar,
  replaceListAddress,
} from "./match-controls";
import { matchesTable } from "./match-table";
import type { MatchProps } from "./match-table";
import { element, errorState, language, root, stateMessage, translator } from "./ui";
import type { View } from "./ui";
import "./matches.css";

let returnPosition: { href: string; top: number } | null = null;

export class MatchesView implements View {
  private readonly node: HTMLElement;
  private request: AbortController | null = null;
  private page: MatchPage | null = null;
  private offset: number;
  private filters: MatchFilters;
  private queryDraft: string;
  private failed: { offset: number; error: unknown } | null = null;

  constructor(
    target: HTMLElement,
    private props: MatchProps
  ) {
    const address = listAddress();
    this.offset = address.offset;
    this.filters = address.filters;
    this.queryDraft = this.filters.q;
    this.node = root(target);
    this.node.classList.add("blacklist-native-users");
    void this.load(this.offset);
  }

  update(props: MatchProps): void {
    const changed =
      language(props) !== language(this.props) ||
      props.routePrefix !== this.props.routePrefix ||
      props.onOpenUserCard !== this.props.onOpenUserCard;
    this.props = props;
    if (changed) this.render();
  }

  destroy(): void {
    this.request?.abort();
    this.node.remove();
  }

  private changeFilters(patch: Partial<MatchFilters>): void {
    this.filters = { ...this.filters, ...patch };
    void this.load(0);
  }

  private async load(offset: number): Promise<void> {
    this.request?.abort();
    const request = new AbortController();
    const { signal } = request;
    this.request = request;
    this.failed = null;
    const active = document.activeElement;
    const focusName = active && this.node.contains(active) ? active.getAttribute("name") : null;
    const filters = this.filters;
    this.render();
    try {
      let page = await getMatches(MATCH_PAGE_SIZE, offset, signal, filters);
      if (signal.aborted) return;
      if (page.enabled && offset > 0 && offset >= page.total) {
        offset = Math.max(0, Math.floor((page.total - 1) / MATCH_PAGE_SIZE) * MATCH_PAGE_SIZE);
        page = await getMatches(MATCH_PAGE_SIZE, offset, signal, filters);
      }
      if (signal.aborted) return;
      this.offset = offset;
      this.page = page;
      replaceListAddress(offset, filters);
    } catch (error) {
      if (!signal.aborted) this.failed = { offset, error };
    } finally {
      if (!signal.aborted) {
        this.request = null;
        this.render();
        this.restoreReturnPosition();
        if (focusName && document.activeElement === document.body) {
          const controls = this.node.querySelectorAll<HTMLElement>("[name]:not(:disabled)");
          const replacement = Array.from(controls).find(
            (control) => control.getAttribute("name") === focusName
          );
          (replacement || this.node.querySelector<HTMLElement>("[aria-current=page]"))?.focus();
        }
      }
    }
  }

  private restoreReturnPosition(): void {
    if (
      this.failed ||
      !returnPosition ||
      typeof window === "undefined" ||
      returnPosition.href !== window.location.href
    )
      return;
    const contents = this.node.closest<HTMLElement>(".admin-main");
    if (contents) contents.scrollTop = returnPosition.top;
    returnPosition = null;
  }

  private tableProps(): MatchProps {
    const open = this.props.onOpenUserCard;
    if (!open) return this.props;
    return {
      ...this.props,
      onOpenUserCard: (user) => {
        const contents = this.node.closest<HTMLElement>(".admin-main");
        if (contents && typeof window !== "undefined") {
          returnPosition = { href: window.location.href, top: contents.scrollTop };
        }
        open(user);
      },
    };
  }

  private render(): void {
    const t = translator(this.props);
    this.node.replaceChildren();
    this.node.setAttribute("aria-busy", String(this.request !== null));
    if (this.page?.enabled) {
      this.node.append(
        matchesToolbar(
          this.page,
          this.filters,
          this.queryDraft,
          this.props,
          (text) => {
            this.queryDraft = text;
          },
          (patch) => this.changeFilters(patch)
        )
      );
    }
    if (this.request) {
      const shell = element("div", undefined, "admin-table-wrap blacklist-native-skeleton");
      const loading = stateMessage(t("loading"));
      shell.append(loading);
      for (let index = 0; index < 5; index += 1) {
        const line = element("span", undefined, "admin-skeleton admin-skeleton-line");
        line.setAttribute("aria-hidden", "true");
        shell.append(line);
      }
      this.node.append(shell);
      return;
    }
    if (this.failed) {
      const { error, offset } = this.failed;
      this.node.append(
        errorState(t, error, () => {
          void this.load(offset);
        })
      );
      return;
    }
    if (!this.page) return;
    if (!this.page.enabled) {
      this.node.append(stateMessage(t("users_disabled")));
      return;
    }
    const { rows, total } = this.page;
    if (rows.length) {
      this.node.append(
        matchesTable(this.page, this.tableProps(), this.filters.sort, (sort) =>
          this.changeFilters({ sort })
        )
      );
    } else {
      const empty = stateMessage(t("users_empty"));
      empty.classList.add("admin-card", "blacklist-native-empty");
      this.node.append(empty);
    }
    this.node.append(
      matchesPagination(this.offset, total, rows.length, this.props, (offset) => {
        void this.load(offset);
      })
    );
  }
}
