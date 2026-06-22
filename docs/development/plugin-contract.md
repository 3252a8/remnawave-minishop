# Plugin Contract Reference

The typed source of truth is [`../../backend/bot/plugins/spec.py`](../../backend/bot/plugins/spec.py).
This page is an orientation layer, not a duplicate contract.

Plugins subclass `Plugin` and may override any hook:

- `setup(ctx)` for service registration and event subscriptions
- `setup_bot(ctx, user_root, admin_root)` for aiogram routers
- `setup_web(ctx, app, scope)` for aiohttp routes
- `worker_tasks(ctx)` for long-running worker coroutines
- `queue_handlers(ctx)` for webhook queue consumers
- `migrations()` for plugin migration chains
- `locales_dir()` for additive locale catalogs
- `entitlements_provider()` for feature entitlement integration

`PluginContext` carries settings, optional bot/dispatcher/session factory, i18n, and a shared
services dict. Hooks must tolerate optional fields being absent in auxiliary entrypoints.

Web plugins receive one of two scopes from `bot.plugins.spec`: `WEB_SCOPE_WEBAPP` for the
Mini App/admin API app, or `WEB_SCOPE_WEBHOOKS` for payment, panel, health, and Telegram
webhook routes.

Domain event subscribers keep the public `(event_name, dict)` signature. Core payload shapes
are documented in [`../architecture/events.md`](../architecture/events.md) and enforced by
the pydantic models in `bot.infra.event_payloads`.
