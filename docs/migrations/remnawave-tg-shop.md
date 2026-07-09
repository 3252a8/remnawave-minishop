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

Wizard полностью русскоязычный. В главном меню выберите
`Установить новый remnawave-minishop и мигрировать данные из другого бота` для
нового сервера или `Мигрировать данные в уже установленный remnawave-minishop`,
если compose-папка уже готова. Затем выберите источник
`Старый remnawave-tg-shop`.

Wizard переносит базу безопасным `pg_dump`-путем. Он не копирует raw PostgreSQL
volume старого стека в новый, потому что raw volume уже инициализирован старыми
ролями и паролем PostgreSQL. Вместо этого wizard:

- пытается сам найти старый контейнер PostgreSQL (`remnawave-tg-shop-db` или
  `LEGACY_TGSHOP_DB_CONTAINER`) и собрать source DSN из его
  `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`;
- если автодетект невозможен, просит `LEGACY_TGSHOP_SOURCE_DSN` / source DSN
  вручную;
- до удаления целевого volume сохраняет `pg_dump` старой БД в
  `backups/pre-remnawave-tg-shop-source-*`;
- удаляет целевой DB volume Minishop и поднимает чистый PostgreSQL с новыми
  `POSTGRES_*` из `.env`;
- восстанавливает сохраненный dump в compose-БД и запускает сервис `migrate`.

Старый DB volume `remnawave-tg-shop-db-data` и старая БД не удаляются
автоматически; они остаются на хосте для отката.

## Как работает перенос

`remnawave-tg-shop` и `remnawave-minishop` имеют совместимую историю схемы.
После переноса старой PostgreSQL-БД сервис `migrate` накатывает недостающие
миграции из `backend/db/migrator/`: сначала применяются `Base.metadata`,
затем последовательные записи `schema_migrations`. Это one-shot сервис: он
должен завершиться с кодом `0`, после чего стартуют `backend` и `worker`.

При миграции wizard:

1. Читает source DSN старого PostgreSQL автоматически из старого контейнера
   или из `LEGACY_TGSHOP_SOURCE_DSN`.
2. Подключает старый DB-контейнер к compose-сети целевого стека, если source
   DSN указывает на локальный контейнер.
3. Сохраняет backup источника:

   ```bash
   pg_dump --clean --if-exists --no-owner --no-privileges "$SOURCE_DSN" \
     > backups/pre-remnawave-tg-shop-source-*/dumps/remnawave-tg-shop-source.sql
   ```

4. Сохраняет бэкап файлов целевого Minishop и, если текущий target PostgreSQL
   доступен, логический дамп перед заменой.
5. Останавливает целевой compose-стек и удаляет целевой DB volume:

   ```bash
   docker volume rm remnawave-minishop-db-data
   ```

6. Поднимает `postgres` и `redis`; новый PostgreSQL инициализируется текущими
   `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` из `.env`.
7. Восстанавливает заранее сохраненный dump:

   ```bash
   psql "$TARGET_DSN" -v ON_ERROR_STOP=1 \
     < backups/pre-remnawave-tg-shop-source-*/dumps/remnawave-tg-shop-source.sql
   ```

8. Запускает миграции схемы Minishop и затем полный stack.

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
| `remnawave-minishop-db-data` | пересоздается и восстанавливается из source DSN; raw volume старого PostgreSQL не копируется |
| `remnawave-minishop-redis-data` | создается пустым |
| `remnawave-minishop-shop-data` | создается пустым; runtime-файлы в `/app/data` дальше настраиваются через админку или вручную |
| `remnawave-minishop-caddy-data` / `remnawave-minishop-caddy-config` | создаются новым Caddy-профилем; старые `remnawave-tg-shop-caddy-*` остаются как источник для ручного отката |

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
