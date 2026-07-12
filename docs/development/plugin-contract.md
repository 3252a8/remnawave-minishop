# Контракт плагинов

Типизированный источник истины — [`../../backend/bot/plugins/spec.py`](../../backend/bot/plugins/spec.py).
Эта страница помогает сориентироваться, но не дублирует весь контракт.

## Версия API и совместимость

Текущая публичная версия API плагинов — `PLUGIN_API_VERSION = 1`. Новый внешний плагин должен
объявить включающий диапазон `plugin_api_min_version` и `plugin_api_max_version` на своем классе
`Plugin`. Loader останавливает запуск до вызова hook'ов, если текущая версия ядра не входит в этот
диапазон или диапазон описан некорректно. Неверсионированные плагины остаются совместимы в API v1
только для обратной совместимости; их следует обновить с явным диапазоном до следующего
compatibility-breaking релиза.

Плагин наследуется от `Plugin` и переопределяет только нужные хуки:

- `setup(ctx)` — регистрация сервисов и подписок на события;
- `setup_bot(ctx, user_root, admin_root)` — подключение aiogram-роутеров;
- `setup_web(ctx, app, scope)` — добавление aiohttp routes;
- `worker_tasks(ctx)` — долгоживущие coroutine-задачи worker-процесса;
- `queue_handlers(ctx)` — обработчики webhook-очереди;
- `migrations()` — цепочка миграций плагина;
- `locales_dir()` — дополнительные JSON-каталоги локалей;
- `entitlements_provider()` — интеграция feature flags.

`entitlements_provider()` — авторитетный источник: может быть только один. Несколько плагинов,
вернувших provider, — детерминированная startup configuration error, а не порядок-зависимый выбор.

`PluginContext` содержит настройки, необязательные bot/dispatcher/session factory, i18n и общий
словарь `services`. Словарь `services` — публичная поверхность расширения; ключи должны быть
строками, а хуки должны терпеть отсутствие необязательных полей во вспомогательных entrypoint'ах.

Для внутренних core-сервисов и типизированного кода плагинов предпочитай методы-помощники на
контексте:

- `ctx.require_bot()`, `ctx.require_i18n()`, `ctx.require_session_factory()` — когда entrypoint
  обязан иметь runtime-объект;
- `ctx.panel_service`, `ctx.subscription_service`, `ctx.notification_service` и парные
  `ctx.require_*` helpers — типизированный доступ к core-сервисам без строковых ключей;
- `ctx.get_service("my_service", MyService)` / `ctx.require_service("my_service", MyService)` —
  runtime-проверяемый доступ к сервисам, добавленным плагином.

Прямой `ctx.services[...]` остается совместимым API для внешних плагинов и динамических ключей, но
новый внутренний код должен идти через типизированные helpers, если ключ заранее известен.

Web-плагины получают один из двух scope из `bot.plugins.spec`:

- `WEB_SCOPE_WEBAPP` — Mini App и admin API;
- `WEB_SCOPE_WEBHOOKS` — payment, panel, health и Telegram webhook routes.

Подписчики доменных событий сохраняют публичную сигнатуру `(event_name, dict)`. Формы payload'ов
описаны в [`../architecture/events.md`](../architecture/events.md) и проверяются pydantic-моделями
в `bot.infra.event_payloads`, но внешние подписчики получают обычный плоский `dict`.

Минимальный запускаемый пример лежит в
[`../../examples/plugins/audit_logger_plugin`](../../examples/plugins/audit_logger_plugin). Он показывает
`setup`, `setup_web` и подписку через `bot.infra.events.subscribe`.

## Стабильная identity установки

Плагин, которому нужен нейтральный идентификатор локальной установки, вызывает
`bot.services.installation_identity.get_or_create_installation_identity(session)`. Функция
возвращает persistent UUID и не зависит от включенной telemetry. Плагин получает session через
`ctx.require_session_factory()` и сам владеет commit транзакции.

## Хуки наблюдаемости

Ядро предоставляет заглушки наблюдаемости в `bot.infra.observability`. Плагин может в своем
хуке `setup(ctx)` положить в `ctx.services["error_reporter"]` реализацию `ErrorReporter` и/или
в `ctx.services["metrics"]` реализацию `Metrics`. Свойства `PluginContext.error_reporter` и
`PluginContext.metrics` возвращают реализацию плагина, если она есть, иначе откатываются к
безопасным no-op значениям по умолчанию.

Глобальные обработчики ошибок web- и worker-процессов вызывают найденный `ErrorReporter` для
необработанных исключений в handlers. Если reporter сам падает, ошибка логируется и не заменяет
исходное исключение. Ключи сервисов остаются additive extension points: существующие сигнатуры
хуков плагинов не меняются.
