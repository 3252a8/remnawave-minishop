# Audit Logger Plugin

Минимальный внешний плагин для проверки структуры пакета и публичных хуков.
Он не добавляет бизнес-логику: только регистрирует сервис-маркер, подписывается
на событие `user.registered` и публикует небольшой health route в webapp scope.

## Установка в dev-окружение

```bash
pip install -e examples/plugins/audit_logger_plugin
```

После установки entry point `minishop.plugins` вернёт объект `plugin` из пакета
`minishop_audit_logger`.

## Что показывает пример

- `Plugin.setup(ctx)` — доступ к `PluginContext.services` и подписка на доменные события.
- `events.subscribe(...)` — публичная сигнатура подписчика `(event_name, payload: dict)`.
- `Plugin.setup_web(ctx, app, scope=WEB_SCOPE_WEBAPP)` — добавление route только в нужный web scope.
