# Статус серверов

Minishop показывает статус серверов в Mini App. Функция выключена по умолчанию и использует один
источник: внешнюю страницу (`url`), Uptime Kuma или xray-checker. Для встроенных провайдеров данные
отображаются внутри Mini App; для `url` пользователь переходит на указанную страницу.

```env
SERVER_STATUS_ENABLED=False
SERVER_STATUS_SHOW_ON_HOME=False
SERVER_STATUS_PROVIDER=url
SERVER_STATUS_URL=
SERVER_STATUS_KUMA_URL=
SERVER_STATUS_XRAY_CHECKER_URL=
SERVER_STATUS_CACHE_TTL_SECONDS=30
SERVER_STATUS_STALE_TTL_SECONDS=300
SERVER_STATUS_TIMEOUT_SECONDS=5
```

Установите `SERVER_STATUS_ENABLED=True` и выберите один из вариантов. Карточка на главном экране
включается отдельно через `SERVER_STATUS_SHOW_ON_HOME=True`.

## Источники

### Внешняя страница

```env
SERVER_STATUS_PROVIDER=url
SERVER_STATUS_URL=https://status.example.com
```

Minishop не загружает и не кеширует состояние в этом режиме.

### Uptime Kuma

Создайте и опубликуйте страницу статуса в Uptime Kuma. Укажите её полный публичный URL:

```env
SERVER_STATUS_PROVIDER=uptime-kuma
SERVER_STATUS_KUMA_URL=https://status.example.com/status/services
```

Допустим URL с префиксом reverse-proxy: `https://status.example.com/kuma/status/services`.
Minishop выделяет этот префикс и запрашивает публичные endpoints Uptime Kuma через него. Адрес должен
быть HTTP(S), содержать путь `/status/<slug>` и не содержать query, fragment или учётные данные.
Администраторская учётная запись и API-токен Uptime Kuma не нужны.

Существующая конфигурация с отдельным legacy slug продолжает работать как **deprecated-совместимость**,
но больше не отображается и не сохраняется через админку. При следующем изменении замените базовый
адрес полным URL страницы.

### xray-checker

```env
SERVER_STATUS_PROVIDER=xray-checker
SERVER_STATUS_XRAY_CHECKER_URL=https://checker.example.com
```

Укажите базовый URL экземпляра xray-checker, доступного из контейнера `backend`.

## Кэш и диагностика

Успешный ответ встроенного провайдера кешируется на `SERVER_STATUS_CACHE_TTL_SECONDS`. При ошибке
или тайм-ауте последний успешный ответ может показываться как устаревший до
`SERVER_STATUS_STALE_TTL_SECONDS`. Если кэша нет, Mini App показывает ошибку, а не предполагаемое
состояние серверов.

После изменения `.env` пересоздайте backend и посмотрите журналы:

```bash
docker compose up -d --force-recreate backend
docker compose logs --tail=100 backend
```

Если Uptime Kuma не загружается, убедитесь, что опубликованный URL имеет общий вид
`https://example.com/status/slug` или `https://example.com/proxy-prefix/status/slug`, а DNS, TLS и
reverse proxy корректно обрабатывают этот адрес.
Не указывайте внутренние сервисы, metadata endpoints и секреты в URL: backend выполняет исходящие
запросы к настроенному адресу. Названия проверок и состояния видны пользователям, поэтому не
публикуйте там внутренние IP-адреса или служебные данные.

Полный справочник: [переменные окружения](../configuration/env-vars.md#статус-серверов).
