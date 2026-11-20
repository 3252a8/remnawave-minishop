# UI screens

Captures every customer-cabinet and admin screen of the docs demo on desktop
(1440×900) and mobile (390×844 @2x), in the dark and light themes, and writes a
browsable gallery. A second run against a baseline turns the gallery into a
before/after viewer, which is what CONTRIBUTING §4.1 asks for before a UI
change is approved.

```bash
npm --prefix docs-site run build:demo            # or pass --build
npm run screens -- --out ../ui-shots/before
# …change the UI, rebuild the demo…
npm run screens -- --build --out ../ui-shots/after --baseline ../ui-shots/before
```

Relative `--out` and `--baseline` paths are resolved from the directory you run
`npm` in, not from `frontend/`.

Open `<out>/index.html`: filter by id, viewport and theme, open a shot, switch
between `after`, `before`, `swipe` and `side` (Space toggles before/after,
arrows move between shots). “Different captures” shows raw pixel differences.
A reviewed manifest can attach `comparison: { beforeHash, afterHash, changed }`
to a shot. Matching hashes enable the “Confirmed changes” filter. Open
`index.html?changed=1` to start with the filter active.

## What is captured

- Every admin section from the sidebar (`[data-admin-section]`), so new
  sections appear without editing anything.
- Every tab of a section (`[role="tab"][data-value]`) and every settings group
  (`.admin-accordion-trigger[data-settings-anchor]`), expanded at runtime.
- The cabinet screens, mock scenarios, detail pages and dialogs listed in
  [`manifest.mjs`](manifest.mjs). Add an entry there for a new dialog or
  scenario; ids follow `<surface>.<screen>[.<state>]`.

Pages are captured at full height: the viewport grows until the main scroller
(`.admin-main`, the document, or an open dialog body) fits, up to 8000 CSS px.
The clock is fixed (`--now`), CSS animations are disabled and the local server
serves the first frame of animated raster files. The runner waits for images
to decode, including those in long lists. A comparison reuses the baseline's
local port so links printed in the UI keep the same address.

## Output

```
<out>/
  index.html             gallery (self-contained, relative image links)
  manifest.json          per shot: id, url, viewport, theme, size, sha1, errors, findings
  desktop-dark/<id>.webp
  desktop-light/…
  mobile-dark/…
  mobile-light/…
```

`findings` are layout hints from `page-probes.mjs`: horizontal page overflow,
clipped text, tap targets under 32 px on mobile, controls of different heights
in one row, and raw text such as `{count}`, `undefined` or untranslated keys.
They help a review; they are not a gate.

Support includes the inbox, a populated conversation, an internal note and the
missing-ticket state. The mobile `typing-short` and `typing-long` shots focus the
real editor and enter one or eight lines at a visible size of 390×470 CSS px.
These model the space available above a keyboard. The runner does not display
a native keyboard. The ordinary `conversation` shots keep the full viewport.
The `typing-compact` case keeps the layout at 320×568 and simulates a visual
viewport of 320×295 with a 24 px offset and 96 px of top safe area. Its image
is cropped to that visible viewport. The mobile log list also has an `end`
shot for the rows beyond the full-page height cap.

## Options

| Option                         | Default                          | Meaning                            |
| ------------------------------ | -------------------------------- | ---------------------------------- |
| `--out <dir>`                  | `test-results/ui-screens/<time>` | output directory                   |
| `--build`                      | off                              | rebuild the docs demo first        |
| `--base <url>`                 | internal server                  | use an already running demo origin |
| `--port <number>`              | baseline port or ephemeral       | port for the internal server       |
| `--only <regex>`               | all                              | capture matching screen ids only   |
| `--viewports`                  | `desktop,mobile`                 | viewport list                      |
| `--themes`                     | `dark,light`                     | theme list (`theme_preview`)       |
| `--format`                     | `webp`                           | `webp` or `png`                    |
| `--quality`                    | `82`                             | WebP quality                       |
| `--concurrency`                | `4`                              | parallel browser contexts          |
| `--baseline <dir>`             | none                             | earlier run to compare with        |
| `--now <iso\|real>`            | `2026-05-28T09:00:00Z`           | frozen clock                       |
| `--list`                       | off                              | print the expanded plan only       |
| `--no-audit` / `--no-discover` | off                              | skip heuristics / tab expansion    |

The tool needs only the frontend dev dependencies (Playwright); WebP encoding
happens in the browser.
