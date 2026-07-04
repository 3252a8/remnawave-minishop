# AGENTS.md

Entry point for AI agents working on this fork. The upstream engineering contract still lives in
[CONTRIBUTING.md](CONTRIBUTING.md) and the architecture overview is
[docs/architecture.md](docs/architecture.md). Read both before changing code.

This repository is a Remnawave MiniShop fork being adapted for a China-market Web App first flow:
Chinese UI, CNY catalog pricing, BEPUSDT / EasyPay-compatible payments, and a practical
customer purchase/import experience without requiring Telegram as the primary client entry.

## Non-Negotiables

- Do not revert user changes in this dirty worktree. Inspect diffs first and work with them.
- Branch policy for this fork:
  - `main` mirrors the upstream author's `main` only; do not develop or deploy from it.
  - `dev` is the local development branch and receives upstream sync merges from `main`.
  - `prod` is the production deployment branch and receives releases by merging `dev`.
- Never hand-edit generated artifacts unless the corresponding generator is unavailable and the
  manual sync is explicitly documented. Generated surfaces include OpenAPI files,
  `frontend/src/lib/api/openapi.generated.ts`, and the settings manifest.
- DB migrations are append-only. Never edit or reorder existing migrations.
- Do not silence type checks on first-party code with `# type: ignore`, broad `any`, or equivalent
  shortcuts.
- Keep the HTTP `{"ok": ...}` envelope, flat event payloads, and plugin `(event_name, dict)`
  subscriber contract intact.
- Frontend under `frontend/src` is Svelte runes-only. Do not introduce `export let`, `$:`,
  `$$props`, `$$restProps`, `<slot>`, `<svelte:component>`, `createEventDispatcher`, or class API
  `$set`.
- Use literal generated API paths and unwrap API envelopes through the existing helpers.
- Keep compatibility with other bots and legacy Remnawave shop flows unless the user explicitly
  asks to remove it.

## Current Business Scope

- Primary UX target: WebApp purchase, renewal, payment, subscription import, device management, and
  install guide for Simplified Chinese users.
- Telegram remains supported but must not be required for the customer WebApp flow when email-code
  or password login is already available.
- Default language for this fork is `zh-cn`. The locale file is `locales/zh-cn.json` using the
  lowercase key used by the app.
- Default catalog currency for this fork is CNY. Do not casually reintroduce RUB as the visible
  default in new UI, examples, or seed data unless a test explicitly covers legacy RUB behavior.
- Current NetFlow-style catalog expectation is CNY numbers matching the referenced USD numbers:
  `60GB/月 = 5`, `200GB/月 = 10`, `500GB/月 = 20`, `1TB/月 = 40`, with 1/3/6/12 month periods
  multiplying the monthly price.
- Product/provider/technical names such as Remnawave, BEPUSDT, EasyPay, Stripe, CryptoPay, HWID,
  URL, API, Token, and Webhook should remain recognizable. Do not force-translate platform names.
- Chinese copy must be natural. Avoid machine fragments like `小节X`, `字段`, `套餐标签model`, or
  mixed Russian/English labels in Simplified Chinese mode.
- The WebApp homepage large logo/title block is controlled by `WEBAPP_HOME_BRAND_VISIBLE` and is
  exposed in Admin -> Appearance -> Logo. Keep this setting wired through backend settings,
  bootstrap payload, frontend state, and cache invalidation.
- Device quota display should read as a ratio, for example `2/3`, not separated labels like
  `设备数量 2 3`.

## Payments

- BEPUSDT and EasyPay-compatible gateways are separate providers:
  - provider id `bepusdt` for self-hosted BEPUSDT crypto collection;
  - provider id `epay` for EasyPay / 易支付-compatible redirect gateways.
- Provider code belongs in `backend/bot/payment_providers/<provider>/` and registration belongs in
  `backend/bot/payment_providers/registry.py`.
- Provider configuration must be visible in the admin settings manifest and localized in
  `locales/zh-cn.json`, `locales/en.json`, and `locales/ru.json` when user-facing.
- Never hardcode merchant ids, secrets, gateway URLs, exchange rates, support links, or payment
  labels in business logic.
- Payment tests must cover at least: signature validation, amount/currency mismatch, duplicate
  webhook delivery, missing payment, disabled/unconfigured provider behavior, unsupported status,
  and idempotent paid-order handling.
- Webhook paths and provider ids are deployment contracts. Do not rename them casually after they
  exist in tests or documentation.

## Tariffs And WebApp UX

- Prefer the JSON tariff catalog and Admin -> Tariffs UI for product configuration. Treat legacy
  remnawave-tg-shop tariff settings as compatibility only.
- Do not duplicate the same plan concept across several hidden sub-configurations. If a tariff card
  has configuration, it must map clearly to one customer-visible product.
- Admin pages should be dense, operational, and explicit. Avoid decorative redesigns or nested-card
  layouts that make configuration harder to scan.
- WebApp customer flow should be verified end to end after changes:
  1. Login without Telegram where configured.
  2. View active subscription and traffic/device status.
  3. Choose a tariff and period.
  4. Choose payment provider.
  5. Create payment and handle callback/mock verification.
  6. Import/copy subscription using the install flow.

## Localization Rules

- `zh-cn` is not a quick machine-translation dump. Review Chinese strings in context.
- Fix visible Russian or awkward English in Chinese mode unless it is a platform name, protocol,
  currency, code key, or admin-only environment variable.
- Keep admin labels action-oriented: describe what the setting does, not just the raw env key.
- When adding settings fields, add i18n keys for label/description and verify the generated settings
  manifest contains those keys.
- Do not solve Chinese UI by mutating only `ru.json` or `en.json`. Add/repair the Chinese key.

## Validation Commands

Use the smallest useful gate first, then broaden when risk warrants it.

- Dev stack status: `npm run dev:stand:ps`
- Rebuild local full stack: `npm run dev:stand:up`
- Frontend WebApp build: `npm run build:webapp`
- Backend tests: `pytest -q`
- Targeted settings manifest test:
  `docker exec remnawave-minishop-backend sh -c 'cd /app/compose-source && PYTHONPATH=backend python -m unittest tests.contracts.test_settings_manifest_demo_sync'`
- Format/patch sanity: `git diff --check`

In this workspace, host `frontend/node_modules` may be absent. If host `npm run build:webapp` fails
with `vite: command not found`, use `npm run dev:stand:up`; the Docker build runs the Vite/Svelte
bundle inside the image and is the reliable local validation path.

## Browser QA Checklist

Use the in-app browser against `http://127.0.0.1:8082`.

- Admin: `/admin/stats`, `/admin/tariffs`, `/admin/promos`, `/admin/payments`, `/admin/appearance`,
  `/admin/settings/payments`, `/admin/settings/migrations/remnashop`.
- WebApp: `/home`, `/devices`, `/settings`, payment dialogs, install/import dialogs.
- In Simplified Chinese mode, scan for:
  - raw Russian text;
  - placeholder English that is not a brand/provider/protocol name;
  - awkward generated labels such as `小节...`, `...字段`, `...model`;
  - overflow, clipped button text, and overlapping controls.
- For `WEBAPP_HOME_BRAND_VISIBLE`, verify both states: off hides `.home-brand`, on restores it.
- For devices, verify quota text renders as `{current}/{max}`.

## Review Stance

When asked for a code review, lead with findings: bugs, regressions, missing tests, broken UX,
security/payment risks, and deployment hazards. Include file/line references. If no issue is found,
say so directly and name any untested residual risk.

When asked to implement, keep changes scoped and then verify with code-level tests plus browser
evidence for user-facing flows.
