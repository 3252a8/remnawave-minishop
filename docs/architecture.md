# Архитектура проекта

Документ описывает, **как устроена система** (раздел «Архитектура ПО»), и **как разложен
репозиторий и деплой** (последующие разделы). Соглашения для контрибьюторов и проверяемые
гейты — в [CONTRIBUTING.md](../CONTRIBUTING.md).

## Архитектура ПО

### Рантайм-процессы

Приложение запускается двумя процессами, разделяющими одну проводку:

- **backend** (`main_backend.py`) — aiohttp: HTTP API Mini App и админки, Telegram-вебхук,
  вебхуки платёжных провайдеров и панели. Поднимает два aiohttp-приложения на разных портах:
  вебхуки и Subscription WebApp (Mini App + `/api/*`).
- **worker** (`main_worker.py`) — фоновые задачи: тарифный воркер, синхронизация с панелью,
  обработчики очереди вебхуков.

Оба процесса вызывают `run_setup(ctx)` и `register_core_reactions(ctx)` — то есть **оба
слушают шину доменных событий** и активируют плагины. Любое изменение событийного слоя должно
одинаково работать в обоих.

### Слои и поток запроса

```text
HTTP-роут → parse_body / контракт запроса → сервис (бизнес-логика) → DAL → конверт _ok/_error
                                              │
                                              └─ emit_model(...)  → шина событий → реакции/плагины
```

- **Роуты** регистрируются явно (`setup_subscription_webapp_routes`, `setup_admin_routes`) и
  плагинами в рантайме (`Plugin.setup_web`).
- **DAL** (`db/dal`) — единственная точка доступа к БД; сервисы не пишут SQL мимо него.
- **Сервисы** (`bot/services`) держат бизнес-логику и публикуют события в ключевых точках.

### Три типизированных контракта

Архитектура держится на трёх явных, машинопроверяемых контрактах — это единый источник правды:

1. **HTTP API** — pydantic request/response-модели + реестр `route_contracts`, из которого
   генерируется `openapi.json`. Подробно: [architecture/http-api.md](architecture/http-api.md).
2. **Шина доменных событий** — одна pydantic-модель на событие (`bot/infra/event_payloads.py`),
   публикация через `emit_model`; payload — flat-dict из примитивов. Каталог:
   [architecture/events.md](architecture/events.md).
3. **Плагины** — ABC `Plugin` + `PluginContext`, обнаружение через entry-point группу
   `minishop.plugins`. Контракт: [development/plugin-contract.md](development/plugin-contract.md).

### Расширяемость

Внешний код расширяет приложение через плагины (отдельные пакеты, entry points), не форкая ядро:
HTTP-роуты (`setup_web`), aiogram-роутеры (`setup_bot`), фоновые задачи, обработчики очереди,
миграции (неймспейснутые цепочки), локали, провайдер entitlements. Встроенные плагины активны
всегда; внешние гейтятся `PLUGINS_ENABLED`.

### Контракт фронт↔бэк

OpenAPI-спек (`docs/openapi.json`) генерируется из живого роутера, из него генерируются
TypeScript-типы фронта (`frontend/src/lib/api/openapi.generated.ts`), а типизированный клиент
`publicApi.ts` выводит формы запроса/ответа по пути вызова. Оба артефакта защищены drift-guard
в CI — изменение контракта на бэке, не отражённое во фронте, валит сборку.

## Раскладка репозитория

Репозиторий разделён по зонам ответственности рантайма:

```text
backend/              Python-код приложения
  bot/
    app/web/          aiohttp API: webapp + admin, контракты роутов (route_contracts),
                      парсинг запросов, генератор OpenAPI
    infra/            шина доменных событий (events, event_payloads), redis, очередь вебхуков
    plugins/          точки расширения (entry points minishop.plugins)
    payment_providers/ платёжные провайдеры (пакет на провайдера)
    handlers/         aiogram-хендлеры (user/admin)
    services/         бизнес-логика, реакции на события
    middlewares/, keyboards/, utils/   инфраструктура бота
  config/             Pydantic-настройки и загрузчики тарифов/тем
  db/                 SQLAlchemy-модели, DAL, идемпотентный мигратор
  main_backend.py     точка входа aiohttp backend
  main_worker.py      точка входа фонового worker
  main_migrate.py     одноразовый запуск миграций
  requirements.txt    Python-зависимости рантайма

frontend/             Svelte/Vite Mini App и админка
  src/                исходный код Svelte (типизированный API-клиент в lib/webapp/publicApi.ts)
  src/lib/api/        сгенерированные из OpenAPI TypeScript-типы
  scripts/            вспомогательные скрипты сборки frontend
  package.json        Node-скрипты и зависимости

deploy/
  docker/             Dockerfile, nginx- и caddy-конфиги рантайма
  examples/           готовые Docker Compose примеры запуска

data/                 данные рантайма, монтируемые в контейнеры
locales/              переводы бота и Web App
docs/                 документация (в т.ч. сгенерированные openapi.json и каталог событий)
tests/                Python-тесты
```

## Деплой

Основной `docker-compose.yml` находится в корне репозитория, чтобы `docker compose up` оставался простым продакшен-путем. Он собирает три прикладных образа из `deploy/docker/Dockerfile`:

- `backend`: aiohttp API и вебхуки.
- `worker`: worker тарифов, синхронизация с панелью, обработчики очередей вебхуков.
- `frontend`: статические Svelte-ассеты, которые отдает nginx.

Сервис `migrate` - одноразовый контейнер на базе backend-образа. Он входит в стандартный Compose-граф: Postgres и Redis переходят в healthy-состояние, `migrate` применяет `Base.metadata.create_all` и ожидающие `schema_migrations`, а затем `backend` и `worker` стартуют только после успешного завершения `migrate`. Так миграции остаются автоматическими для `docker compose up`, но не запускаются внутри каждой backend-реплики.

Python-импорты намеренно остаются в пространствах `bot.*`, `config.*` и `db.*`. Контейнеры рантайма выставляют `PYTHONPATH=/app/backend`; локальные тесты используют такую же раскладку через `pytest.ini`.

Основные команды:

```bash
docker compose up -d --build
docker compose run --rm migrate
docker compose logs -f backend worker frontend
npm run build:webapp
pytest -q
```
