# Контракты HTTP API

Машиночитаемый источник правды для HTTP API — `docs/openapi.json`. На сайте
документации он публикуется как [`/openapi.json`](/openapi.json). Файл
генерируется из живого `aiohttp`-роутера после регистрации core-маршрутов и
встроенных web-плагинов. Тест `tests/contracts/test_openapi_artifact.py` сравнивает
артефакт с текущим роутером и падает, если `docs/openapi.json` устарел.

Эта страница описывает общие правила контракта. Детальные схемы, path-параметры,
content type и security-схемы смотрите в `openapi.json`.

## Области API

- `/api/admin/*` — API админки внутри Mini App. Все маршруты требуют сессию
  администратора: пользователь должен быть авторизован в Web App, а его Telegram ID
  должен входить в `ADMIN_IDS`.
- `/api/auth/*` — публичные маршруты входа: Telegram Mini Apps `initData`,
  Telegram OAuth, email-коды, magic link, парольный вход и logout.
- `/api/*` без `/admin` — пользовательские маршруты Mini App: профиль, платежи,
  подписки, тарифы, устройства, поддержка, промокоды и инструкции подключения.
- `/api/subscription-guides/public/{share_token}` — публичный read-only маршрут
  инструкций подключения по share-token активной подписки.

## Формат JSON-ответов

JSON-маршруты используют общий envelope:

```json
{ "ok": true }
```

Успешный ответ добавляет доменные поля рядом с `ok`, например:

```json
{
  "ok": true,
  "promo": {
    "id": 1,
    "code": "GIFT",
    "bonus_days": 7
  }
}
```

Ошибка возвращается в том же стиле:

```json
{
  "ok": false,
  "error": "invalid_payload",
  "message": "invalid_payload"
}
```

Поле `error` — стабильный код для frontend и интеграционных тестов. `message`
может быть человекочитаемым текстом или повторять код ошибки.

## Авторизация

OpenAPI-артефакт описывает четыре security-схемы:

- `AdminSession` — cookie `rw_webapp_session` для админских маршрутов.
- `AdminBearer` — bearer-токен той же Web App-сессии для админских маршрутов.
- `UserSession` — cookie `rw_webapp_session` для пользовательских маршрутов Mini App.
- `UserBearer` — bearer-токен пользовательской Web App-сессии.

Cookie и bearer-токен проверяются одним механизмом Web App-сессий. Для admin API
после проверки сессии дополнительно сверяется `ADMIN_IDS`; email-only аккаунт не
получает админский доступ без Telegram ID.

Публичные маршруты bootstrap, i18n, auth/login и публичные инструкции подключения
не имеют security-схемы в OpenAPI.

## Пагинация

Списковые admin-маршруты используют нулевую страницу:

- `page` — номер страницы, минимум `0`;
- `page_size` — размер страницы;
- `total` — общее количество элементов.

Для новых typed admin-эндпоинтов `page_size` ограничивается текущей логикой
handler'а. Чаще всего лимит равен `100`, для логов — `200`. Эти ограничения
фиксируются в OpenAPI там, где маршрут уже переведен на typed contract.

## Тела запросов

Новые typed-маршруты описывают JSON body через pydantic-модели. Handler читает тело
через `parse_body(request, Model)` и возвращает `400 invalid_payload`, если JSON
некорректный или значение не проходит модель.

Во время постепенного рефакторинга request-модели наследуются от `HttpBodyModel` и
игнорируют лишние поля (`extra="ignore"`). Это сохраняет совместимость с текущим
frontend. После проверки конкретного домена модель можно ужесточить до
`extra="forbid"`, но только точечно.

PATCH-маршруты должны различать отсутствующее поле и явный `null` через
`body.model_fields_set`.

## Не-JSON маршруты

Не все `/api/*` маршруты являются JSON:

- `/api/admin/payments/export.csv` возвращает `text/csv`;
- avatar/logo/favicon и часть backup-маршрутов работают с binary или multipart;
- такие маршруты документируются отдельным `content_type` и не прогоняются через
  `parse_body`.

## Где живут контракты

HTTP-контракты регистрируются рядом с доменом через
`bot.app.web.route_contracts.register_contract(...)`. Генератор OpenAPI читает общий
registry, поэтому `backend/bot/app/web/openapi.py` не импортирует доменные модели
напрямую.

Общие pydantic-базы:

- `HttpBodyModel` и `HttpResponseModel` — `backend/bot/app/web/http_contracts.py`;
- `RouteContract`, `ok_envelope_for(...)`, security-константы — `backend/bot/app/web/route_contracts.py`;
- текущие admin-модели — `backend/bot/app/web/admin_api_impl/schemas.py`;
- будущие модели Mini App должны жить в доменных schema-модулях webapp-слоя и
  использовать те же базовые классы.

## Генерация и проверки

После изменения HTTP-контрактов обновите артефакт:

```bash
PYTHONPATH=backend python -m bot.app.web.openapi
```

После изменения event emitters или моделей обновите каталог событий:

```bash
PYTHONPATH=backend python -m bot.infra.event_catalog
```

Минимальный набор проверок для API-контрактов:

```bash
PYTHONPATH=backend python -m pytest tests/contracts/test_openapi_artifact.py tests/contracts/test_contract_docs_accuracy.py -q
python -m ruff check backend tests
python -m ruff format --check backend tests
```

Для полного контроля перед сдачей фазы запускается весь `pytest -q`.
