# Статус серверов

Minishop может показывать пользователю состояние серверов в Web App. Функция выключена по
умолчанию и поддерживает ровно один источник данных за раз:

- `url` — открыть внешнюю страницу по `SERVER_STATUS_URL`;
- `uptime-kuma` — получить данные опубликованной страницы статуса Uptime Kuma и показать их
  внутри Web App;
- `xray-checker` — получить данные xray-checker и показать их внутри Web App.

Значение `both` не поддерживается. Если нужно объединить несколько источников, сделайте это на
стороне выбранного источника и подключите к Minishop один адрес API.

## Включение

Добавьте в `.env` полный блок с безопасными значениями по умолчанию:

```env
SERVER_STATUS_ENABLED=False
SERVER_STATUS_PROVIDER=url
SERVER_STATUS_URL=
SERVER_STATUS_KUMA_URL=
SERVER_STATUS_KUMA_SLUG=default
SERVER_STATUS_XRAY_CHECKER_URL=
SERVER_STATUS_CACHE_TTL_SECONDS=30
SERVER_STATUS_STALE_TTL_SECONDS=300
SERVER_STATUS_TIMEOUT_SECONDS=5
```

Затем выберите один из вариантов ниже, установите `SERVER_STATUS_ENABLED=True` и пересоздайте
серверную часть (`backend`). `SERVER_STATUS_URL` используется только для источника `url`; для
`uptime-kuma` и `xray-checker` пользовательская кнопка открывает внутренний экран статуса.

### Внешняя страница

```env
SERVER_STATUS_ENABLED=True
SERVER_STATUS_PROVIDER=url
SERVER_STATUS_URL=https://status.example.com
```

В этом режиме Minishop не загружает и не кеширует состояние внешней системы, а направляет
пользователя на заданный HTTP(S) URL.

### Uptime Kuma

Сначала создайте страницу статуса в Uptime Kuma, добавьте на неё нужные проверки и опубликуйте
её. Если полный адрес страницы — `https://status.example.com/status/default`, то:

- базовый URL — `https://status.example.com`, то есть адрес Uptime Kuma без пути страницы;
- идентификатор страницы (`slug`) — `default`, то есть часть после `/status/`.

```env
SERVER_STATUS_ENABLED=True
SERVER_STATUS_PROVIDER=uptime-kuma
SERVER_STATUS_KUMA_URL=https://status.example.com
SERVER_STATUS_KUMA_SLUG=default
```

В `SERVER_STATUS_KUMA_URL` указывайте базовый URL, например `https://status.example.com`, а в
`SERVER_STATUS_KUMA_SLUG` — идентификатор страницы, например `default`. Minishop использует данные
опубликованной страницы статуса; учётная запись администратора и API-токен Uptime Kuma не нужны.
Страница должна быть доступна из контейнера `backend`.

### xray-checker

Укажите базовый HTTP(S) URL доступного экземпляра xray-checker. Например, если полный адрес API —
`https://checker.example.com/api/v1/public/proxies`, базовый URL —
`https://checker.example.com`, без пути `/api/v1/public/proxies`:

```env
SERVER_STATUS_ENABLED=True
SERVER_STATUS_PROVIDER=xray-checker
SERVER_STATUS_XRAY_CHECKER_URL=https://checker.example.com
```

`SERVER_STATUS_XRAY_CHECKER_URL` должен быть доступен из `backend` и отдавать совместимый ответ
xray-checker.

## Кэш и устаревшие данные

Для встроенных источников успешный ответ сохраняется в кэше на
`SERVER_STATUS_CACHE_TTL_SECONDS` секунд. Это уменьшает нагрузку на Uptime Kuma или xray-checker
при одновременном открытии раздела многими пользователями.

Если очередное обращение к источнику завершилось ошибкой или превысило
`SERVER_STATUS_TIMEOUT_SECONDS`, Minishop может отдать последний успешный ответ не дольше
`SERVER_STATUS_STALE_TTL_SECONDS`. Такой ответ помечается как устаревший. Когда допустимого
ответа в кэше нет, Web App показывает ошибку загрузки, а не придумывает состояние серверов.
Кэш не заменяет мониторинг и не гарантирует мгновенное отображение изменения статуса.

## Безопасность

- Используйте HTTPS для адреса источника и `SERVER_STATUS_URL`, если запрос выходит за пределы
  доверенной сети Docker.
- Подключайте только контролируемые URL. Серверная часть выполняет исходящие запросы к
  настроенному источнику, поэтому не указывайте закрытые адреса служебных метаданных, панели
  администрирования и другие внутренние службы, которые приложение не должно опрашивать.
- Не помещайте токены, пароли и другие секреты в URL или параметры запроса. Uptime Kuma должен
  предоставлять именно опубликованную страницу статуса.
- Считайте отображаемые названия и состояния публичными: они предназначены для пользовательского
  Web App. Не публикуйте в источнике внутренние имена узлов, IP-адреса и служебные комментарии.
- Оставляйте небольшое время ожидания. Увеличивайте его только после проверки сетевой задержки,
  иначе медленный источник будет дольше удерживать запросы серверной части.

## Диагностика

После изменения `.env` пересоздайте контейнер `backend` и проверьте его журналы:

```bash
docker compose up -d --force-recreate backend
docker compose logs --tail=100 backend
```

Если раздел статуса не появился:

- проверьте `SERVER_STATUS_ENABLED=True` и точное значение источника: `url`, `uptime-kuma` или
  `xray-checker`;
- для `url` заполните `SERVER_STATUS_URL` абсолютным HTTP(S) URL;
- для Uptime Kuma проверьте, что страница статуса опубликована, базовый URL не содержит
  `/status/<slug>`, а `SERVER_STATUS_KUMA_SLUG` совпадает с публичным адресом;
- для xray-checker проверьте `SERVER_STATUS_XRAY_CHECKER_URL` и совместимость запущенной версии;
- выполните проверку URL из сети или контейнера `backend`: адрес `localhost` внутри контейнера
  указывает на сам контейнер, а не на основную систему Docker;
- проверьте DNS, сертификат TLS, межсетевой экран и обратный прокси, если в журналах есть ошибка
  ожидания или соединения;
- учитывайте срок хранения кэша: после исправления источника старый успешный ответ может
  отображаться до истечения настроенного времени.

Полный справочник переменных: [переменные окружения](../configuration/env-vars.md#статус-серверов).
