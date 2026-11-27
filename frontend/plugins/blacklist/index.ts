import { MatchesView } from "./matches";
import { SettingsView } from "./settings";
import { StatusView } from "./status";
import type { Props, View } from "./ui";
import "./styles.css";

export function mountView(view: string, target: HTMLElement, props: Props): View {
  switch (view) {
    case "settings":
      return new SettingsView(target, props);
    case "matched-users":
      return new MatchesView(target, props);
    case "user-status":
      return new StatusView(target, props, "userCard");
    case "ticket-status":
      return new StatusView(target, props, "ticket");
    default:
      throw new Error("unsupported_view");
  }
}

export function updateView(instance: View, props: Props): void {
  instance.update(props);
}

export function unmountView(instance: View): void {
  instance.destroy();
}
