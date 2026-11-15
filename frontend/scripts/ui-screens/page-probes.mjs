/* global document, window, getComputedStyle, MutationObserver */

// Functions in this module run inside the page via `page.evaluate`, so each
// one must be self-contained (no closures over module scope).

export const FREEZE_CSS = `
  *, *::before, *::after {
    animation-duration: 0s !important;
    animation-delay: 0s !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0s !important;
    transition-delay: 0s !important;
    caret-color: transparent !important;
    scroll-behavior: auto !important;
  }
`;

/** Resolve once the DOM stops changing and no loading markers are visible. */
export function waitForQuietDom({ quiet, timeout }) {
  return new Promise((resolve) => {
    const started = performance.now();
    const busySelector =
      '[aria-busy="true"], [data-loading="true"], .skeleton, .admin-skeleton, .screen-loading';
    const isBusy = () =>
      [...document.querySelectorAll(busySelector)].some((element) => {
        const box = element.getBoundingClientRect();
        return box.width > 0 && box.height > 0;
      });
    let timer = 0;
    const finish = () => {
      observer.disconnect();
      window.clearTimeout(timer);
      resolve(performance.now() - started);
    };
    const arm = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        if (isBusy() && performance.now() - started < timeout) arm();
        else finish();
      }, quiet);
    };
    const observer = new MutationObserver(() => {
      if (performance.now() - started > timeout) finish();
      else arm();
    });
    observer.observe(document.documentElement, {
      subtree: true,
      childList: true,
      attributes: true,
      characterData: true,
    });
    arm();
  });
}

/**
 * How much taller the viewport must be to show the whole page. The admin
 * scrolls `.admin-main`, the cabinet scrolls the document, and an open dialog
 * scrolls its own body, so the largest relevant scroller wins.
 */
export function measureOverflow() {
  const visible = (element) => {
    const box = element.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  };
  const dialog = [...document.querySelectorAll('[role="dialog"], [role="alertdialog"]')]
    .filter(visible)
    .pop();
  const root = dialog || document.body;
  let best = 0;
  const doc = document.scrollingElement || document.documentElement;
  if (!dialog) best = Math.max(0, doc.scrollHeight - window.innerHeight);
  for (const element of root.querySelectorAll("*")) {
    if (!dialog && element.closest('[role="dialog"]')) continue;
    const style = getComputedStyle(element);
    if (!/(auto|scroll)/.test(style.overflowY)) continue;
    if (!visible(element)) continue;
    const overflow = element.scrollHeight - element.clientHeight;
    if (overflow <= 4) continue;
    if (!dialog && element.clientHeight < window.innerHeight * 0.4) continue;
    best = Math.max(best, overflow);
  }
  return Math.ceil(best);
}

/** Discover expandable variants of the current screen. */
export function discoverVariants({ kind, within }) {
  const visible = (element) => {
    const box = element.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  };
  const label = (element) =>
    (element.innerText || element.getAttribute("aria-label") || "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 60);
  const scope =
    (within && document.querySelector(within)) ||
    document.querySelector(".admin-section-stage:not([inert])") ||
    document.querySelector(".admin-main") ||
    document.querySelector(".app-shell") ||
    document.body;
  if (kind === "tabs") {
    return [...scope.querySelectorAll('[role="tab"][data-value]')]
      .filter((tab) => visible(tab) && !tab.closest('[role="dialog"]'))
      .filter((tab) => tab.getAttribute("data-state") !== "active")
      .filter((tab) => tab.getAttribute("aria-selected") !== "true")
      .map((tab) => {
        const key = String(tab.getAttribute("data-value") || "").trim();
        const twins = [...document.querySelectorAll('[role="tab"][data-value]')].filter(
          (other) => other.getAttribute("data-value") === key && visible(other)
        );
        return {
          key,
          selector: `[role="tab"][data-value="${key}"]`,
          nth: twins.indexOf(tab),
          label: label(tab),
        };
      })
      .filter((tab) => tab.key);
  }
  if (kind === "accordions") {
    return [...scope.querySelectorAll(".admin-accordion-trigger[data-settings-anchor]")]
      .filter((trigger) => visible(trigger) && trigger.getAttribute("aria-expanded") !== "true")
      .map((trigger) => {
        const anchor = String(trigger.getAttribute("data-settings-anchor"));
        return {
          key: anchor.split(":").pop(),
          selector: `.admin-accordion-trigger[data-settings-anchor="${anchor}"]`,
          nth: 0,
          label: label(trigger),
        };
      });
  }
  return [];
}

/**
 * Cheap layout heuristics that catch the regressions screenshots are usually
 * taken for. Findings are hints for a reviewer, not failures.
 */
export function auditLayout({ mobile }) {
  const findings = [];
  const seen = new Set();
  const visible = (element) => {
    const box = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return (
      box.width > 0 &&
      box.height > 0 &&
      style.visibility !== "hidden" &&
      style.display !== "none" &&
      Number(style.opacity) > 0.05
    );
  };
  const describe = (element) => {
    const parts = [];
    let node = element;
    for (let depth = 0; node && depth < 3 && node !== document.body; depth++) {
      let part = node.tagName.toLowerCase();
      const classes = [...node.classList].filter((name) => !/^s-|^svelte-/.test(name)).slice(0, 2);
      if (classes.length) part += "." + classes.join(".");
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(" > ");
  };
  const text = (element) =>
    (element.innerText || element.getAttribute("aria-label") || "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 60);
  const add = (kind, element, detail) => {
    const key = kind + describe(element) + detail;
    if (seen.has(key) || findings.length > 80) return;
    seen.add(key);
    findings.push({ kind, target: describe(element), text: text(element), detail });
  };

  const doc = document.scrollingElement || document.documentElement;
  if (doc.scrollWidth > window.innerWidth + 2) {
    findings.push({
      kind: "page-horizontal-overflow",
      target: "document",
      text: "",
      detail: `${doc.scrollWidth}px > ${window.innerWidth}px`,
    });
  }

  const controls = [
    ...document.querySelectorAll(
      'button, [role="button"], [role="tab"], [role="combobox"], a.btn, a.admin-btn, input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]), textarea'
    ),
  ].filter(visible);

  for (const element of document.querySelectorAll("body *")) {
    if (!visible(element) || element.children.length > 0) continue;
    const style = getComputedStyle(element);
    if (style.overflow === "visible" && style.overflowX === "visible") continue;
    if (style.textOverflow === "ellipsis" || style.webkitLineClamp !== "none") continue;
    if (element.scrollWidth > element.clientWidth + 2 && text(element)) {
      add("clipped-text", element, `${element.scrollWidth}px in ${element.clientWidth}px`);
    }
  }

  if (mobile) {
    for (const control of controls) {
      const box = control.getBoundingClientRect();
      if (control.closest("table")) continue;
      if (box.height < 32 || box.width < 32) {
        add("small-tap-target", control, `${Math.round(box.width)}x${Math.round(box.height)}`);
      }
    }
  }

  const rows = new Map();
  for (const control of controls) {
    if (control.closest("table")) continue;
    const parent = control.parentElement;
    if (!parent) continue;
    const style = getComputedStyle(parent);
    if (!/flex|grid/.test(style.display)) continue;
    if (style.display.includes("flex") && style.flexDirection.startsWith("column")) continue;
    const box = control.getBoundingClientRect();
    const key = parent;
    const row = rows.get(key) || [];
    row.push({ control, top: box.top, height: Math.round(box.height) });
    rows.set(key, row);
  }
  for (const [parent, row] of rows) {
    const sameLine = row.filter((item) => Math.abs(item.top - row[0].top) < 8);
    if (sameLine.length < 2) continue;
    const heights = [...new Set(sameLine.map((item) => item.height))];
    if (heights.length > 1 && Math.max(...heights) - Math.min(...heights) >= 4) {
      add("uneven-control-heights", parent, heights.join("/") + "px");
    }
  }

  const walker = document.createTreeWalker(document.body, 4);
  // Unfilled interpolation, leaked JS values, or a whole text node that is a
  // locale key such as `admin_users_title` (usernames and URLs are skipped).
  const placeholder = /\{[a-z_]+\}|\bundefined\b|\bNaN\b|\[object Object\]/;
  const localeKey = /^[a-z][a-z0-9]*(?:_[a-z0-9]+){2,}$/;
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const value = String(node.nodeValue || "").trim();
    if (!value || !(placeholder.test(value) || localeKey.test(value))) continue;
    const element = node.parentElement;
    if (
      !element ||
      !visible(element) ||
      element.closest("code, pre, script, style, textarea, .admin-cell-mono, a[href]")
    ) {
      continue;
    }
    if (element.closest("input, [contenteditable='true']")) continue;
    add("raw-text", element, value.slice(0, 80));
  }
  return findings;
}
