# Public subscription gateway

`/s/<token>` has two representations. Browser navigation and preview crawlers receive the existing
installation page; subscription applications receive the raw bytes from Core's delivery service.
`?view=page` and `?view=subscription` select explicitly. The optional format suffix is restricted
to `stash`, `singbox`, `mihomo`, `json`, `v2ray-json`, and `clash`. `HEAD` is not supported.
The `/api/subscription-guides/public/<token>` JSON endpoint retains its `config` field and adds
`guide_document` with `schemaVersion: 1`. The document is built from the validated Remnawave v1
input. It has ordered platform IDs and typed button targets; resource resolution remains separate
from its shared content. Client delivery never reads the instruction document.

The delivery service accepts a server-resolved resource binding and a client request. Its first
source adapter calls the configured Remnawave `/api/sub/<shortUuid>` endpoint. Core forwards
the response bytes, status, and safe headers without an API envelope. It does not send the
administrative bearer token. The adapter does not follow redirects, share user cookies, cache
profiles, or accept upstream URLs from public requests. The panel still chooses format and
applies HWID and Response Rules.

## Rollout

1. Apply migration `0088_bind_install_share_to_panel_link` before routing traffic to the new
   backend. The nullable column is compatible with the preceding backend version.
2. From a trusted operator environment, run
   `PYTHONPATH=backend python -m scripts.bind_install_share_tokens` and inspect `verified` and
   `skipped`. Run the same command
   with `--apply` to bind existing active tokens to the *current* panel link. Resolve skipped
   records explicitly; a public request never binds an old token. Existing historical token
   exposure cannot be inferred or repaired automatically.
3. Deploy the frontend Nginx configuration with its dedicated `/s/` route and the backend. Confirm
   that an upstream failure remains a 5xx through the actual public ingress. For a split
   deployment, the frontend injects `MINISHOP_EDGE_TOKEN`; direct access to the protected
   backend `/s/` route must be denied.
4. Set `SUBSCRIPTION_GATEWAY_ENABLED=True`, keeping `SUBSCRIPTION_LINK_MODE=panel`. Verify a
   browser, Telegram preview, initial client import, repeated update, HWID device behavior,
   format suffixes, panel Response Rules, link reissue, and failure handling through the
   public address. Compare controlled direct-panel and gateway responses for the same headers.
5. After the client matrix is green, set `SUBSCRIPTION_LINK_MODE=minishop` to issue the canonical
   `/s/` URL. Existing directly imported panel URLs continue to work; users must reimport to
   change the saved URL. `SUBSCRIPTION_GATEWAY_REWRITE_PROFILE_PAGE_URL` is optional and defaults
   to false so panel-admin page choices remain intact.

The raw route is intentionally outside the JSON OpenAPI envelope; its response depends on the
client and panel. The JSON instructions API remains in OpenAPI. The configured
`SUBSCRIPTION_MINI_APP_URL` supplies the public origin; forwarded `Host` does not select it.
The frontend proxy turns off access logs for `/s/` so tokens are not written to that log.

## Reissue and rollback

User and admin reissue clear every local public grant for the panel user and commit that change
before calling the panel. A failed panel call leaves old tokens revoked. An authenticated account
request issues a fresh token bound to the current short UUID. A panel-side short UUID change also
invalidates the former token on the next request. Public JSON and raw delivery both check the
current database grant and a fresh panel user lookup; neither uses the former 300-second public
payload cache.

Switching `SUBSCRIPTION_LINK_MODE` back to `panel` affects new links only. Keep the gateway
available while issued `/s/` URLs may still be stored in client apps. If emergency shutdown is
required, client requests must receive 503 and users must reimport a direct panel URL. Reverting
to a backend without the gateway will break updates for imported `/s/` profiles.
