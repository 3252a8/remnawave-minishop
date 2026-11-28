# AGENTS.md

Entry point for AI agents. The single source of truth for conventions, architecture, and
enforced quality gates is [CONTRIBUTING.md](CONTRIBUTING.md) (written in Russian) — **read it
before changing code.** Architecture overview: [docs/architecture.md](docs/architecture.md).

For a GitLab image publication network failure, check the effective HTTP(S) proxy in the
Docker daemon for the affected job. Verify registry authentication and pull the exact failed
image through that daemon or a disposable daemon on the same runner network. Use this evidence
before retrying, then verify the scanner ran and the published tags match the requested revision.

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
  navigation may name Minishop PRO, document public operator workflows and release history,
  and link to the official PRO site; this exception does not allow copying PRO code, private contracts, assets, or runtime
  dependencies into core.
- Balance work must include gift-deletion refunds. The temporary user flow that discards an unused
  paid gift without a refund may exist only until balance refund integration is implemented. When
  implementing or changing the user-balance flow, replace that behavior with an atomic credit of
  the gift's actually paid value to the purchaser's balance before revoking/removing the gift
  entitlement. Keep the `TODO(balance-gift-refund)` marker until the refund path and regression
  tests are implemented.

Before pushing, use the changed-zone validation matrix in CONTRIBUTING.md §1. Product or shared
code changes still run their relevant gates (and the full suite when isolation is unclear), while
prose-only documentation and docs-site-only changes use the scoped documentation checks defined
there. Commits: Conventional Commits, no `Co-Authored-By` trailer.

Maintain root `CHANGELOG.md` as the single source of release history, published at `/changelog/`
by the docs generator. Before committing a noteworthy Core change, update `В разработке · dev`:
describe the resulting behavior, merge related work into existing entries, and remove superseded
or duplicate entries. Do not append one bullet per commit or repeat already released behavior.
Use neutral wording such as «коды активации» / "activation codes" in changelogs and commit messages.
See CONTRIBUTING.md §8 for release rollover and history provenance.

## Keeping public documentation current

When a change affects what a customer or operator can do, update the corresponding source under
`docs/` in the same change. Cover changed defaults, navigation, prerequisites, limits and upgrade
steps. For renamed or removed behavior, fix incoming links and outdated instructions. Keep new
pages reachable from the hub and sidebar. Run the docs gates in CONTRIBUTING.md §1 and check the
rendered route as a signed-out reader. Explain an unchanged guide when the diff has no reader impact.

`docs/features/minishop-pro/changelog.md` is the public history of Minishop PRO, with its own
`В разработке · dev` section and dated releases. Keep that history separate from the root Minishop
changelog. Maintain it alongside the affected PRO guide. At release, use the published plugin
version, original publication date in UTC and verified compatible Minishop version. Preserve
unreleased changes at the top and keep private sources and release evidence out of public files.
