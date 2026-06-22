# HTTP API Contracts

The canonical machine-readable contract is [`../openapi.json`](../openapi.json). It is
generated from the live aiohttp router after core routes and built-in web plugins are
registered, and `tests/test_openapi_artifact.py` fails when the committed artifact drifts.

All JSON endpoints keep the existing envelope:

- success: `{"ok": true, ...}`
- failure: `{"ok": false, "error": "<code>", "message": "<human-readable text>"}`

Admin endpoints under `/api/admin/*` require the existing admin webapp session or bearer
token; the resolved Telegram user id must be listed in `settings.ADMIN_IDS`. Public Mini
App endpoints keep their current Telegram/email session checks in the handlers.

Pagination uses the existing endpoint-local conventions. Admin list endpoints generally use
`page` and `page_size`, with `page_size` capped at 100; `/api/admin/promos` is the typed
template for this pattern.

Typed endpoints parse request bodies through `parse_body(request, Model)`. During the
incremental refactor request models ignore extra fields for compatibility, while malformed
JSON or invalid typed values return `400 invalid_payload`.
