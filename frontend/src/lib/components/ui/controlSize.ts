import "./control-size.css";

/** Matching form controls; md grows to a touch target on narrow screens. */
export type ControlSize = "md" | "lg";

export function controlSizeClass(size?: ControlSize): string {
  return size ? `ui-control ui-control-${size}` : "";
}
