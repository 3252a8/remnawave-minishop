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
- Frontend: no global `checkJs`; typing is opt-in (`.ts` / `<script lang="ts">`); use literal
  API paths; `unwrap` the envelope.
- Decompose, then type; no module > ~1000 lines without a reason; mind the
  monkeypatch/re-export trap (CONTRIBUTING.md §5).
- "Compatibility with other bots" is a feature (keep), not legacy.

Before pushing, run the gates in CONTRIBUTING.md §1 (`pytest`, `ruff`, `mypy`,
`npm run check`). Commits: Conventional Commits, no `Co-Authored-By` trailer.
