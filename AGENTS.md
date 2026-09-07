# AGENTS.md

Entry point for AI agents. The single source of truth for conventions, architecture, and
enforced quality gates is [CONTRIBUTING.md](CONTRIBUTING.md) (written in Russian) — **read it
before changing code.** Architecture overview: [docs/architecture.md](docs/architecture.md).

Non-negotiables (details in CONTRIBUTING.md §2):

- Never hand-edit generated artifacts — run their generator (`openapi.json`, `events.md`,
  `openapi.generated.ts`, settings manifest).
- DB migrations are append-only — never edit or reorder existing ones.
- Never silence the type checker on first-party code (`# type: ignore` / `any`); the whole
  backend mypy run must stay green.
- Never break the wire contracts: the HTTP `{"ok": …}` envelope, flat-dict event payloads,
  the plugin `(event_name, dict)` subscriber signature.
- Frontend: first-party Svelte code is runes-only and enforced for `frontend/src`; no
  `export let`, `$:`, `$$props`, `$$restProps`, `<slot>`, `<svelte:component>`,
  `createEventDispatcher`, or class API `$set`. First-party frontend code is TypeScript-only
  (`.ts` / `<script lang="ts">`, enforced by architecture gates); no global `checkJs`;
  use literal API paths; `unwrap` the envelope.
- User/admin-facing copy is localized, not hard-coded: every new or changed UI/bot text key must
  have at least `locales/ru.json` and `locales/en.json` entries; component fallbacks are not a
  substitute for base locale keys.
- UI reuse is mandatory: follow CONTRIBUTING.md §4.1 and its component map. Prefer the existing
  component for the entity/action, inspect two actual consumers, and extend shared patterns before
  assembling a local replacement. Shared CSS classes are not a substitute for a shared component.
  Verify every affected consumer on desktop/mobile, including open menus and dialogs.
- Decompose, then type; no module > ~900 lines without a reason; mind the
  monkeypatch/re-export trap (CONTRIBUTING.md §5).
- "Compatibility with other bots" is a feature (keep), not legacy.
- Keep core and separately shipped PRO functionality isolated. Public core documentation and
  navigation may mention minishop PRO, summarize its public capabilities, and link to the official
  PRO site; this exception does not allow copying PRO code, private contracts, assets, or runtime
  dependencies into core.

Before pushing, run the gates in CONTRIBUTING.md §1 (`pytest`, `ruff`, `mypy`,
`npm run check`). Commits: Conventional Commits, no `Co-Authored-By` trailer.

No `CHANGELOG.md` — the project deliberately has none; do not create or maintain one.
Change history lives in Conventional Commits and PR descriptions (`pr-changelog` skill).
