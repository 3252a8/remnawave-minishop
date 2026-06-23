# Контракт плагинов

Типизированный источник истины — [`../../backend/bot/plugins/spec.py`](../../backend/bot/plugins/spec.py).
Эта страница помогает сориентироваться, но не дублирует весь контракт.

Плагин наследуется от `Plugin` и переопределяет только нужные хуки:

- `setup(ctx)` — регистрация сервисов и подписок на события;
- `setup_bot(ctx, user_root, admin_root)` — подключение aiogram-роутеров;
- `setup_web(ctx, app, scope)` — добавление aiohttp routes;
- `worker_tasks(ctx)` — долгоживущие coroutine-задачи worker-процесса;
- `queue_handlers(ctx)` — обработчики webhook-очереди;
- `migrations()` — цепочка миграций плагина;
- `locales_dir()` — дополнительные JSON-каталоги локалей;
- `entitlements_provider()` — интеграция feature flags.

`PluginContext` содержит настройки, optional bot/dispatcher/session factory, i18n и общий словарь
`services`. Словарь `services` — публичная поверхность расширения; ключи должны быть строками,
а хуки должны терпеть отсутствие optional-полей в вспомогательных entrypoint'ах.

Web-плагины получают один из двух scope из `bot.plugins.spec`:

- `WEB_SCOPE_WEBAPP` — Mini App и admin API;
- `WEB_SCOPE_WEBHOOKS` — payment, panel, health и Telegram webhook routes.

Подписчики доменных событий сохраняют публичную сигнатуру `(event_name, dict)`. Формы payload'ов
описаны в [`../architecture/events.md`](../architecture/events.md) и проверяются pydantic-моделями
в `bot.infra.event_payloads`, но внешние подписчики получают обычный плоский `dict`.

Минимальный runnable sample лежит в
[`../../examples/plugins/audit_logger_plugin`](../../examples/plugins/audit_logger_plugin). Он показывает
`setup`, `setup_web` и подписку через `bot.infra.events.subscribe`.
