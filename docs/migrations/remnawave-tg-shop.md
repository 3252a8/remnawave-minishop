# Миграция с `remnawave-tg-shop` на `remnawave-minishop`

Для переноса со старого родственного стека используйте общий install wizard:

```bash
curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/install.sh -o install.sh
sh install.sh
```

Та же ссылка на install-скрипт в GitLab:

```bash
curl -fsSL https://gitlab.com/3252a8/remnawave-minishop/-/raw/main/scripts/install.sh -o install.sh
sh install.sh
```

В меню выберите `Install new stack and run migration` для нового
сервера или `Run migration only`, если compose-папка уже готова. Затем
выберите источник `Old remnawave-tg-shop`.

Wizard поддерживает два способа переноса:

- `Copy old Docker volumes` - для старого compose-стека на том же Docker host.
  Скрипт подготавливает новый stack, копирует
  `remnawave-tg-shop-db-data` в `remnawave-minishop-db-data`, опционально
  переносит Caddy volumes и запускает новый stack.
- `Dump from a source PostgreSQL DSN` - для старой БД, доступной по DSN.
  Скрипт поднимает целевой `postgres`, сбрасывает целевую БД, делает
  `pg_dump` из старой БД, восстанавливает дамп в compose-БД и запускает
  сервис `migrate`.

В обоих режимах старые volumes и старая БД не удаляются автоматически.

## Как работает перенос

`remnawave-tg-shop` и `remnawave-minishop` имеют совместимую историю схемы.
После переноса старой PostgreSQL-БД сервис `migrate` накатывает недостающие
миграции из `backend/db/migrator.py`: сначала применяются `Base.metadata`,
затем последовательные записи `schema_migrations`. Это one-shot сервис: он
должен завершиться с кодом `0`, после чего стартуют `backend` и `worker`.

При volume-миграции wizard:

1. Останавливает известные контейнеры старого и переходного стеков, если вы
   подтверждаете этот шаг.
2. Запускает `docker compose up --no-start`, чтобы Docker Compose создал новые
   volumes.
3. Копирует старый volume БД:

   ```bash
   docker run --rm \
     -v remnawave-tg-shop-db-data:/from:ro \
     -v remnawave-minishop-db-data:/to \
     alpine sh -c "cd /from && cp -a . /to"
   ```

4. Если старые Caddy volumes существуют, переносит
   `remnawave-tg-shop-caddy-data` -> `remnawave-minishop-caddy-data` и
   `remnawave-tg-shop-caddy-config` -> `remnawave-minishop-caddy-config`.
5. Запускает новый stack через Docker Compose.

Если целевой DB volume уже непустой, wizard не перетирает его молча: он
останавливается и просит отдельное подтверждение на продолжение без копирования
старой БД.

## Что меняется в архитектуре

**Контейнеры**:

| Версия | Сервисы |
| --- | --- |
| `v2.7.0` | `remnawave-tg-shop`, `remnawave-tg-shop-db` |
| `v3.1.x-v3.3.x` | `remnawave-minishop`, `remnawave-minishop-db` |
| `v3.4+` | `remnawave-minishop-backend`, `remnawave-minishop-worker`, `remnawave-minishop-frontend`, `remnawave-minishop-migrate`, `remnawave-minishop-postgres`, `remnawave-minishop-redis` |

**Volumes**:

| Volume | Что происходит |
| --- | --- |
| `remnawave-minishop-db-data` | переносится из `remnawave-tg-shop-db-data` или восстанавливается из source DSN |
| `remnawave-minishop-redis-data` | создается пустым |
| `remnawave-minishop-shop-data` | создается пустым; runtime-файлы в `/app/data` дальше настраиваются через админку или вручную |
| `remnawave-minishop-caddy-data` / `remnawave-minishop-caddy-config` | переносятся из `remnawave-tg-shop-caddy-*`, если старый стек использовал Caddy |

Доступные compose-профили: `docker-compose.yml`,
`deploy/examples/caddy/docker-compose.yml`,
`deploy/examples/nginx/docker-compose.yml`,
`deploy/examples/newt/docker-compose.yml`,
`deploy/examples/no-proxy/docker-compose.yml`.

## Переменные окружения

Перед запуском нового стека проверьте `.env`. Самые важные изменения:

| Было | Стало | Действие |
| --- | --- | --- |
| `TELEGRAM_WEBHOOK_SECRET` | `WEBHOOK_SECRET_TOKEN` | Перенести значение или сгенерировать новый stable secret. |
| `TELEGRAM_WEBHOOK_PATH` | удалена | Путь вебхука теперь рассчитывается автоматически. |
| `REQUIRED_CHANNEL_SUBSCRIBE_TO_USE` | удалена | Гейт включается, когда задан `REQUIRED_CHANNEL_ID`. |
| `STARS_PROVIDER_TOKEN` | удалена | Telegram Stars используются напрямую. |
| `POSTGRES_HOST=remnawave-tg-shop-db` | `postgres` внутри Compose | В compose-файлах `POSTGRES_HOST` переопределяется service name `postgres`. |
| `WEBHOOK_BASE_URL` | обязательна | Без публичного URL backend не стартует корректно. |
| - | `REDIS_URL=redis://redis:6379/0` | В compose-профилях задано автоматически. |
| - | `WEBAPP_SESSION_SECRET`, `WEBAPP_ENABLED`, `TARIFFS_CONFIG_PATH` | Новые настройки Web App и каталога тарифов. |

Остальные продуктовые настройки удобнее проверить после первого входа в
админку.

## Reverse Proxy

В старом стеке часто был один upstream `remnawave-tg-shop:8000`. В текущем
split-arch stack маршруты разделены:

| Назначение | Service | Port |
| --- | --- | --- |
| Telegram, платежные и panel webhooks | `backend` | `8080` |
| Health-check | `backend` | `8080` (`/healthz`) |
| Web App API и auth | `backend` | `8081` внутри Docker-сети |
| Статический Web App frontend | `frontend` | `80` |

Минимальная схема для внешнего Nginx:

```nginx
upstream remnawave_backend_webhooks { server backend:8080; }
upstream remnawave_frontend         { server frontend:80; }

server {
    server_name app.domain.com;
    listen 443 ssl;

    location /webhook/ { proxy_pass http://remnawave_backend_webhooks; }
    location /healthz  { proxy_pass http://remnawave_backend_webhooks; }
    location /         { proxy_pass http://remnawave_frontend; }
}
```

Готовые Caddy, Nginx, Pangolin/Newt и no-proxy профили уже содержат нужную
маршрутизацию.

## Проверка

После переноса:

```bash
docker compose ps
docker compose logs migrate
docker compose logs -f backend worker frontend
```

`migrate` должен завершиться успешно, а `backend`, `worker`, `frontend`,
`postgres` и `redis` должны быть running/healthy.

Когда убедитесь, что новый stack работает, старые volumes можно удалить вручную:

```bash
docker volume rm remnawave-tg-shop-db-data
docker volume rm remnawave-tg-shop-caddy-data remnawave-tg-shop-caddy-config 2>/dev/null || true
```
