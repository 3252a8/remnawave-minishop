# Развертывание

Документ описывает продакшен-запуск после разделения проекта на `backend`, `frontend` и `worker`.
Перед стартом заполните минимальный `.env` по [configuration.md](configuration.md). Полный справочник переменных лежит в [env-vars.md](env-vars.md); после первого входа большинство продуктовых настроек удобнее менять через Web App админку.

## Быстрый старт

```bash
cp .env.example .env
nano .env
docker compose up -d --build
docker compose ps
docker compose logs -f backend worker frontend
```

Обычный `docker compose up -d --build` поднимает:

- `postgres` и `redis` с проверками здоровья;
- `migrate` как одноразовый сервис на backend-образе;
- `backend` только после успешных миграций;
- `worker` только после успешных миграций;
- `frontend` как отдельный nginx-образ без Python runtime.

Для обратного прокси с Caddy используйте отдельный `deploy/compose/docker-compose-caddy.yml`.

Миграции не запускаются внутри backend. Их выполняет отдельный сервис `migrate`, поэтому старт
приложения не создает гонки на схеме БД.

## Миграции

При обычном старте миграции применяются автоматически:

```bash
docker compose up -d --build
```

Для ручного повторного запуска:

```bash
docker compose run --rm migrate
```

Проверить логи миграций:

```bash
docker compose logs migrate
```

`backend` и `worker` зависят от `migrate` через `service_completed_successfully`; если миграции
падают, приложение не стартует поверх неподготовленной БД.

## Сервисы

- `backend`: aiohttp API, Telegram webhook, платежные webhooks, panel webhooks, проверка здоровья `/healthz`.
- `worker`: TariffTrafficWorker, задачи синхронизации с панелью, обработка рассылок, потребители очереди webhooks.
- `frontend`: статические Svelte-ассеты через nginx.
- `postgres`: PostgreSQL 17.
- `redis`: Redis 7 для FSM, кеша, rate-limit, очередей и locks.

`deploy/compose/docker-compose-caddy.yml` добавляет `caddy` как внешний HTTP/HTTPS reverse proxy.
Перед запуском замените example-домены прямо в `deploy/docker/caddy/Caddyfile`.

## Логи и проверка

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f frontend
```

Эндпоинты проверки здоровья:

```bash
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/health
```

В обычном compose backend публикуется на `127.0.0.1:${WEB_SERVER_PORT:-8080}`, frontend на
`127.0.0.1:${FRONTEND_PORT:-8082}`. В Caddy-варианте проверяйте `HTTP_BIND`.

## Обновление

Локальная сборка из репозитория:

```bash
git pull
docker compose up -d --build
docker compose logs -f migrate backend worker
```

Если нужно пересобрать только образы приложения:

```bash
docker compose build frontend backend worker
docker compose up -d
```

## Образы GHCR

Образы приложения называются единообразно:

```text
ghcr.io/3252a8/remnawave-minishop-backend:<tag>
ghcr.io/3252a8/remnawave-minishop-worker:<tag>
ghcr.io/3252a8/remnawave-minishop-frontend:<tag>
```

Сборка образов с конкретным тегом:

```bash
IMAGE_TAG=3.2.0 scripts/docker-build-images.sh
```

Публикация после `docker login ghcr.io`:

```bash
IMAGE_TAG=3.2.0 scripts/docker-push-images.sh
```

Для PowerShell есть варианты `scripts/docker-build-images.ps1` и
`scripts/docker-push-images.ps1`. Если публикуете образы в другой registry, namespace или с другим
префиксом имени, переопределите `IMAGE_NAMESPACE`, `IMAGE_REGISTRY` или `IMAGE_PREFIX`.

Если PowerShell блокирует локальные скрипты ошибкой `PSSecurityException` / Execution Policy,
запустите те же скрипты с обходом политики только для текущего процесса:

```powershell
$env:IMAGE_TAG = "3.2.0"
docker login ghcr.io
powershell -ExecutionPolicy Bypass -File .\scripts\docker-build-images.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\docker-push-images.ps1
```

Этот bypass действует только для запущенного процесса `powershell` и не меняет системную политику.

## Масштабирование

В текущих Compose-файлах заданы явные `container_name`, поэтому `docker compose --scale` для
`backend`, `frontend` и `worker` не используется: Docker не может создать несколько контейнеров с
одним именем. Если понадобится горизонтальное масштабирование, уберите `container_name` у
масштабируемых сервисов или перенесите конфигурацию в orchestrator.

Состояние FSM, rate-limit и краткоживущие кеши вынесены в Redis, а tariff tick защищен Redis
distributed lock; код подготовлен к нескольким репликам, но текущие Compose-файлы ориентированы на
фиксированные имена контейнеров.

## Данные и volumes

Продакшен compose использует именованные volumes:

- `postgres-data`;
- `redis-data`;
- `shop-data`;
В Caddy-варианте также используются `caddy-data` и `caddy-config`.

`shop-data` монтируется целиком в `/app/data`; внутри него лежат тарифы, темы, логотипы и прочие
файловые данные приложения.

Если вместо именованного volume включаете bind mount `./data:/app/data`, на сервере заранее дайте права
пользователю контейнера `10001`:

```bash
mkdir -p data/themes data/webapp-logo data/webapp-emoji data/tariffs
chown -R 10001:10001 data
chmod -R u+rwX data
docker compose up -d --force-recreate backend worker
```

Проверка прав:

```bash
docker compose exec backend sh -lc 'id; touch /app/data/themes/test && rm /app/data/themes/test'
```

## Резервная копия PostgreSQL

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > backup.sql
```

Восстановление в чистую БД:

```bash
docker compose stop backend worker
docker compose exec postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"'
docker compose exec postgres sh -c 'createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backup.sql
docker compose run --rm migrate
docker compose up -d backend worker
```

## Обратный прокси

Вариант `deploy/compose/docker-compose-caddy.yml` проксирует:

- webhook-домен целиком в `backend:8080`;
- Mini App-домен целиком в `frontend:80`;
- API/auth/theme routes Mini App дальше проксируются frontend nginx в `backend:8081`.

Встроенный `deploy/docker/caddy/Caddyfile` намеренно повторяет старую двухдоменную структуру:

```caddyfile
# Replace the example domains with your real webhook and Mini App hostnames.
app.example.com {
	encode zstd gzip

	reverse_proxy backend:8080
}

web.example.com {
	encode zstd gzip

	reverse_proxy frontend:80
}
```

Для внешнего Nginx используйте DNS-имена сервисов внутри Docker network:

```nginx
upstream remnawave_backend_webhooks {
    server backend:8080;
}

upstream remnawave_backend_webapp {
    server backend:8081;
}

upstream remnawave_frontend {
    server frontend:80;
}
```

Webhook и health-маршруты должны идти в `backend:8080`. Статические ассеты Mini App отдавайте через
`frontend:80`; frontend nginx уже проксирует `/api/*`, `/auth/*` и ассеты тем/логотипов в
`backend:8081`.

## Newt

Если `newt` запущен в одной Compose network с приложением, указывайте внутренние имена сервисов,
а не порты на хосте.

Если используете Caddy-вариант и хотите публиковать стек одной точкой через Newt/Pangolin, укажите:

```text
http://caddy:80
```

Если публикуете через Newt/Pangolin без Caddy, настройте отдельные ресурсы:

```text
Mini App / frontend: http://frontend:80
Webhooks / backend:  http://backend:8080
```

Такой вариант нормальный: Caddy не обязателен. Он нужен только если вы хотите заранее объединить
frontend и backend-маршруты в один внутренний upstream.

`backend:8081` является внутренним WebApp API/auth-сервером для frontend nginx; обычно его не нужно
указывать в Newt напрямую.

## Переменный env-файл

По умолчанию compose читает `.env`. Для smoke-тестов или отдельного окружения можно подставить
другой файл:

```bash
APP_ENV_FILE=.env.staging docker compose --env-file .env.staging up -d --build
```
