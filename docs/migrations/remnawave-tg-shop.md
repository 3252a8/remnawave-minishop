# Миграция с `remnawave-tg-shop` (≤ v2.7.0) на `remnawave-minishop` (v3.4+)

Эта страница - готовый сценарий для legacy-стека `remnawave-tg-shop`. Это единственная миграция с другого бота, которая сейчас описана в документации. Для других Telegram-ботов, самописных панелей и ручных таблиц готового сценария пока нет: их нельзя переносить по этой инструкции без отдельного анализа схемы БД, тарифов, платежей и связи с Remnawave Panel.

Автоматический скрипт ниже рассчитан именно на родственный стек `remnawave-tg-shop`, где структура БД и Docker volumes известны заранее. Для других ботов нужен отдельный адаптер экспорта/импорта.

## Новый install wizard

Для нового сервера или переноса без клонирования репозитория используйте общий
`sh` wizard:

```bash
curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/install.sh -o install.sh
sh install.sh
```

В меню выберите `Install new stack and run legacy migration` или
`Run legacy migration only`, затем источник `Legacy remnawave-tg-shop`.
Wizard поддерживает два режима:

- `Copy old Docker volumes` - тот же безопасный сценарий, что и старый
  `migrate_to_minishop.sh`: старый volume `remnawave-tg-shop-db-data`
  копируется в `remnawave-minishop-db-data`, затем новый stack запускает
  сервис `migrate` и накатывает все схемные миграции;
- `Dump from a source PostgreSQL DSN` - новый режим для случаев, когда старая
  БД доступна как внешний PostgreSQL DSN. Wizard поднимает целевой `postgres`,
  сбрасывает целевую БД, делает `pg_dump` из старой БД, восстанавливает дамп в
  compose-БД и затем запускает `migrate`.

Старый helper `scripts/migrate_to_minishop.sh` ниже всё ещё полезен для
in-place обновления уже клонированного репозитория: он переключает git-ветку,
переносит volumes и стартует новый stack. Прямой source DSN он не поддерживал.

## Короткий путь без смены ветки и сборки

Если вы используете только готовые Docker-образы и не собираете проект
локально, git-команды из ручного способа не нужны. Достаточно обновить
compose-файл до одного из готовых примеров в `deploy/examples` и
перенести/обновить БД. Самый прямой вариант без встроенного обратного прокси -
`deploy/examples/no-proxy/docker-compose.yml`; для Caddy, Nginx и Newt есть
такие же самостоятельные папки.

Минимальная последовательность:

```bash
docker compose down

# Скопируйте старый .env в выбранную папку примера и обновите значения там.
cp .env deploy/examples/no-proxy/.env
nano deploy/examples/no-proxy/.env

# Подготовьте стек из готовых образов.
IMAGE_TAG=3.4.0 docker compose \
  --env-file deploy/examples/no-proxy/.env \
  -f deploy/examples/no-proxy/docker-compose.yml \
  up --no-start

# Нужно только при переходе со старого имени volume remnawave-tg-shop-db-data.
# Если у вас уже есть remnawave-minishop-db-data, этот шаг пропустите.
docker run --rm \
  -v remnawave-tg-shop-db-data:/from:ro \
  -v remnawave-minishop-db-data:/to \
  alpine sh -c "cd /from && cp -a . /to"

IMAGE_TAG=3.4.0 docker compose \
  --env-file deploy/examples/no-proxy/.env \
  -f deploy/examples/no-proxy/docker-compose.yml \
  up -d
docker compose \
  --env-file deploy/examples/no-proxy/.env \
  -f deploy/examples/no-proxy/docker-compose.yml \
  logs migrate
```

Сервис `migrate` сам применит недостающие схемные миграции к перенесённому
тому PostgreSQL. Новые тома `remnawave-minishop-redis-data` и
`remnawave-minishop-shop-data` переносить не нужно: они создаются пустыми.

Этот документ описывает обновление стека, поднятого по `remnawave-tg-shop`
(включая последний релиз `v2.7.0` форка `kavore/remnawave-tg-shop`), до
текущей версии `remnawave-minishop` (v3.4+). Между этими версиями произошли
две независимые перетряски, и скрипт пытается отработать обе одной командой:

1. **Переименование стека** (v3.1.0): контейнеры и тома `remnawave-tg-shop-*`
   стали `remnawave-minishop-*`. Простой `docker compose up -d` после
   `git pull` создаёт пустую БД — без переноса тома данные теряются.
2. **Разделение бота на сервисы** (v3.4.0): из одного контейнера выделены
   `backend`, `worker`, `frontend`, `migrate` + новые `postgres`, `redis`.
   Появились новые volumes `redis-data` и `shop-data`, новые обязательные
   переменные окружения, а схема БД обновляется автоматически one-shot
   сервисом `migrate`.

После миграции `docker compose ps` должен показать как минимум: `backend`,
`worker`, `frontend`, `postgres`, `redis` (running) и `migrate` (exited 0).
Логи: `docker compose logs -f backend worker frontend`.

Доступные пути:

- [Автоматический](#автоматический-способ-через-скрипт) — скрипт-обёртка
  останавливает старый стек, накатывает свежий код, переносит том БД,
  поднимает новые сервисы. Идемпотентный.
- [Ручной](#ручной-способ) — те же шаги командами, для тех, кому нужно
  понимать каждое действие или выполнить выборочно.

В обоих случаях:

- старые тома **не удаляются** автоматически — это безопасный бэкап на случай
  отката;
- сертификаты Caddy (если используется `deploy/examples/caddy/docker-compose.yml`)
  тоже переносятся, чтобы Let's Encrypt не выписывал их заново и не упереться
  в rate limit;
- схема БД обновляется автоматически: при первом `docker compose up -d` сервис
  `migrate` накатывает на перенесённый том все недостающие миграции (от
  alembic-схемы v2.7.0 до текущей).

## Что меняется в архитектуре

**Контейнеры**:

| Версия | Сервисы |
| --- | --- |
| `v2.7.0` | `remnawave-tg-shop`, `remnawave-tg-shop-db` |
| `v3.1.x–v3.3.x` | `remnawave-minishop`, `remnawave-minishop-db` |
| `v3.4+` (текущая) | `remnawave-minishop-backend`, `remnawave-minishop-worker`, `remnawave-minishop-frontend`, `remnawave-minishop-migrate`, `remnawave-minishop-postgres`, `remnawave-minishop-redis` |

Внутри Docker-сети сервисы доступны по коротким DNS-именам (`backend`, `worker`,
`frontend`, `postgres`, `redis`), а не по полному `container_name`. Это важно
для внешнего reverse-proxy — см. раздел [Внешний reverse-proxy](#внешний-reverse-proxy) ниже.

**Volumes**:

| Volume | v2.7.0 | v3.4+ | Что внутри |
| --- | --- | --- | --- |
| `remnawave-minishop-db-data` | переименовать из `remnawave-tg-shop-db-data` | переносится скриптом | PostgreSQL |
| `remnawave-minishop-redis-data` | — | создаётся пустым | Redis (FSM, rate-limit, cache, очередь вебхуков, distributed locks) |
| `remnawave-minishop-shop-data` | — | создаётся пустым | `/app/data`: `tariffs.json`, темы Web App, кэш логотипа/emoji |
| `remnawave-minishop-caddy-data` / `remnawave-minishop-caddy-config` | переименовать из `remnawave-tg-shop-caddy-*` | переносится скриптом | только при Caddy-варианте |

`redis-data` и `shop-data` стартуют пустыми — это нормально. Redis ничего
долгоживущего не хранит (всё либо FSM, либо кеш с TTL), а `data/` инициализируется
из образа при первом старте (`tariffs.json` пуст пока вы не сконфигурируете
тарифы через админ-панель).

## Переменные окружения, которые могли исчезнуть или переехать

Перед запуском нового стека проверьте `.env`. Ниже — только то, что точно
менялось между v2.7.0 и v3.4+:

| Было (v2.7.0) | Стало (v3.4+) | Действие |
| --- | --- | --- |
| `TELEGRAM_WEBHOOK_SECRET` | `WEBHOOK_SECRET_TOKEN` | Переименовать. Если пусто — будет сгенерирован при старте, но тогда Telegram переустановит webhook (на это не реагирует существующий запрос). |
| `TELEGRAM_WEBHOOK_PATH` | удалена | Путь вебхука теперь генерируется из `BOT_TOKEN` автоматически. |
| `REQUIRED_CHANNEL_SUBSCRIBE_TO_USE` | удалена | Гейт включается автоматически, как только задан `REQUIRED_CHANNEL_ID`. |
| `STARS_PROVIDER_TOKEN` | удалена | Telegram Stars (XTR) используются напрямую. |
| `REFERRAL_ENABLED` | удалена | Реферальная программа активна по умолчанию. В legacy-режиме без JSON-каталога отключайте платежные бонусы через нули в `REFERRAL_BONUS_DAYS_*` и `REFEREE_BONUS_DAYS_*`; в JSON-тарифах обнуляйте или удаляйте `referral_bonus_days_inviter` и `referral_bonus_days_referee` у period-тарифов. |
| `POSTGRES_HOST=remnawave-tg-shop-db` | в `.env` — `remnawave-minishop-db` или пусто | Под compose значение всё равно переопределяется на сервисное имя `postgres` (см. `environment:` в compose-файлах), поэтому скрипт правит `.env` только для bare-metal сценариев. |
| `WEBHOOK_BASE_URL` | **обязательна** | Polling-режим удалён, без публичного URL бот не стартует. |
| — | `REDIS_URL=redis://redis:6379/0` | Обязательна для воркера, очередей и rate-limit. По умолчанию в compose-файлах уже задана. |
| — | `WEBAPP_SESSION_SECRET`, `WEBAPP_ENABLED`, `WEBAPP_SERVER_PORT`, `WEBAPP_THEMES_DIR`, `TARIFFS_CONFIG_PATH` | Новые настройки Web App / тарифного каталога. Безопасные дефолты есть в `.env.example`. |

Полный референс — [docs/getting-started/configuration.md](../getting-started/configuration.md). Скрипт миграции
эти переменные **не правит** автоматически (только `POSTGRES_HOST`), потому
что у каждой инсталляции свой шаблон `.env` с кастомными значениями. Лучше
сравнить свой `.env` с `.env.example` глазами один раз, чем получить
несовместимый шаблон автоматом.

## Автоматический способ (через скрипт)

Если helper ещё не лежит у вас локально, запускайте его прямо из `raw` из
корня старого репозитория:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/migrate_to_minishop.sh)
```

> Команда выше рассчитана на `bash` / Git Bash / WSL. Если вы запускаете из
> PowerShell, удобнее сначала открыть Git Bash.

Если вы уже подтянули новую версию и файл есть локально, можно запускать так:

```bash
bash scripts/migrate_to_minishop.sh
```

По умолчанию скрипт работает с `docker-compose.yml` и переключается на ветку
`main`. Можно переопределить через переменные окружения:

| Переменная        | Назначение                                                              | По умолчанию           |
| ----------------- | ----------------------------------------------------------------------- | ---------------------- |
| `PROJECT_ROOT`    | Явный путь к корню старого репозитория, если запуск не из него          | текущая директория     |
| `COMPOSE_FILE`    | Какой compose-файл стартовать в конце                                   | `docker-compose.yml`   |
| `TARGET_BRANCH`   | На какую ветку переключаться и подтягивать обновления                   | `main`                 |
| `GIT_REMOTE`      | Какой remote использовать для `fetch`/`pull`                            | `origin`               |
| `NEW_ORIGIN_URL`  | Если задано и не совпадает с URL выбранного remote — он будет обновлён  | (не меняется)          |
| `ASSUME_YES`      | `1` — не задавать интерактивных вопросов                                | `0`                    |

Примеры:

```bash
# Caddy-вариант из raw-файла.
# Перед запуском скопируйте старый .env в deploy/examples/caddy/.env
# и заполните WEBHOOK_HOST / MINIAPP_HOST.
COMPOSE_FILE=deploy/examples/caddy/docker-compose.yml \
  bash <(curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/migrate_to_minishop.sh)

# С переключением origin на форк 3252a8
NEW_ORIGIN_URL=https://github.com/3252a8/remnawave-minishop.git \
  bash <(curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/migrate_to_minishop.sh)

# Без интерактива
ASSUME_YES=1 \
  bash <(curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/migrate_to_minishop.sh)
```

Что делает скрипт:

1. **Останавливает текущий стек**: ищет известные контейнеры старой схемы
   (`remnawave-tg-shop`, `…-db`, `…-caddy`), переходного периода
   (`remnawave-minishop`, `…-db`, `…-caddy`) и новой схемы
   (`…-backend`, `…-worker`, `…-frontend`, `…-migrate`, `…-postgres`, `…-redis`)
   и останавливает их, если запущены. Безопасно при повторном запуске.
2. **Переключает `origin`**, если задана переменная `NEW_ORIGIN_URL`, иначе
   оставляет как есть.
3. **Подтягивает целевую ветку** (`git fetch` + `git switch` + `git pull --ff-only`).
   Прерывается, если в рабочем дереве есть незакоммиченные изменения.
4. **Правит `POSTGRES_HOST` в `.env`** (только для bare-metal сценариев — в
   compose это значение перебивает `environment:` блок).
5. **Подготавливает новый стек в режиме `--no-start`**, чтобы Compose сам
   создал тома `db-data`, `redis-data`, `shop-data` и не ругался на уже
   существующий volume.
6. **Переносит том БД** `remnawave-tg-shop-db-data` → `remnawave-minishop-db-data`
   (и Caddy-тома, если применимо) через одноразовый `alpine`-контейнер. Если
   новый том уже непустой — копирование пропускается. Новые volumes
   `redis-data` и `shop-data` остаются пустыми (их и не должно быть в старом
   стеке).
7. **Стартует новый стек** (`docker compose up -d --remove-orphans` плюс
   `--build` для локальной сборки). `migrate` отработает первым, накатит
   на перенесённый том все недостающие миграции (от alembic-схемы v2.7.0 до
   текущей) и завершится. Затем стартуют `backend`, `worker`, `frontend`.

Скрипт идемпотентен: повторный запуск ничего не сломает, просто пропустит уже
выполненные шаги.

После того как убедитесь, что бот работает и данные на месте, удалите старые
тома:

```bash
docker volume rm remnawave-tg-shop-db-data
docker volume rm remnawave-tg-shop-caddy-data remnawave-tg-shop-caddy-config 2>/dev/null || true
```

## Ручной способ

1.  **Остановите старый стек и обновите код:**

    ```bash
    docker compose down
    git fetch origin
    git checkout main
    git pull --ff-only origin main
    ```

2.  **(Только для bare-metal без compose)** обновите `.env`, если в нём ещё
    жёстко прописан старый контейнер БД:

    ```bash
    sed -i.bak 's/^POSTGRES_HOST=remnawave-tg-shop-db$/POSTGRES_HOST=remnawave-minishop-db/' .env
    ```

    Под `docker compose up` это не нужно: compose сам выставляет
    `POSTGRES_HOST: postgres` (имя сервиса) в `environment:` и `.env`-значение
    не используется.

3.  **Проверьте `.env`** на наличие переменных, которые исчезли или
    переименовались — см. раздел
    [Переменные окружения](#переменные-окружения-которые-могли-исчезнуть-или-переехать)
    выше. Главное: `WEBHOOK_SECRET_TOKEN` (бывший `TELEGRAM_WEBHOOK_SECRET`),
    обязательный `WEBHOOK_BASE_URL` и наличие `REDIS_URL` (по умолчанию задано
    в compose).

4.  **Подготовьте новый стек без запуска**, чтобы Compose создал новые volumes
    (`db-data`, `redis-data`, `shop-data`) и контейнеры:

    ```bash
    # Локальная сборка
    docker compose up --no-start --build

    # Или готовый Caddy-вариант из GHCR-образов
    cp .env deploy/examples/caddy/.env
    nano deploy/examples/caddy/.env
    docker compose \
      --env-file deploy/examples/caddy/.env \
      -f deploy/examples/caddy/docker-compose.yml \
      up --no-start

    # Другие готовые варианты:
    # deploy/examples/nginx/docker-compose.yml
    # deploy/examples/newt/docker-compose.yml
    # deploy/examples/no-proxy/docker-compose.yml
    ```

5.  **Перенесите том БД в новое имя:**

    ```bash
    docker run --rm \
      -v remnawave-tg-shop-db-data:/from:ro \
      -v remnawave-minishop-db-data:/to \
      alpine sh -c "cd /from && cp -a . /to"
    ```

    `remnawave-minishop-redis-data` и `remnawave-minishop-shop-data` — новые,
    переносить нечего. Они инициализируются на лету: Redis пуст, а `data/`
    наполняется при первом обращении к настройкам Web App / каталогу тарифов.

6.  **(Только для Caddy)** перенесите тома Caddy с TLS-сертификатами и
    состоянием ACME:

    ```bash
    for v in caddy-data caddy-config; do
      docker run --rm \
        -v "remnawave-tg-shop-$v":/from:ro \
        -v "remnawave-minishop-$v":/to \
        alpine sh -c "cd /from && cp -a . /to"
    done
    ```

7.  **Запустите новый стек:**

    ```bash
    docker compose up -d
    # или
    docker compose \
      --env-file deploy/examples/caddy/.env \
      -f deploy/examples/caddy/docker-compose.yml \
      up -d
    ```

    Сервис `migrate` запустится первым, обнаружит перенесённый том,
    применит недостающие схемные миграции (`Base.metadata.create_all` +
    последовательные миграции `0001..00NN` из `backend/db/migrator.py`) и
    выйдет с кодом 0. Только после этого стартуют `backend` и `worker`.

8.  **Проверьте состояние:**

    ```bash
    docker compose ps
    docker compose logs -f backend worker frontend
    docker compose logs migrate   # должен закончиться "Migrator: migration 00NN applied successfully"
    ```

9.  **(Опционально) удалите старые тома**, когда убедитесь, что новый стек
    стабилен:

    ```bash
    docker volume rm remnawave-tg-shop-db-data
    docker volume rm remnawave-tg-shop-caddy-data remnawave-tg-shop-caddy-config 2>/dev/null || true
    ```

## Внешний reverse-proxy

В v2.7.0 был один upstream — `remnawave-tg-shop:8000`. В v3.4+ функциональность
разнесена по портам и сервисам:

| Назначение | DNS-имя сервиса | Порт |
| --- | --- | --- |
| Telegram / платежные / вебхуки панели | `backend` | `8080` |
| Health-чек | `backend` | `8080` (`/healthz`) |
| Web App API (`/api/*`, `/auth/*`, ассеты тем и логотипов) | `backend` | `8081` (доступен только из Docker-сети) |
| Статический фронт Web App | `frontend` | `80` (внутри `frontend` уже проксирует `/api/*` и `/auth/*` на `backend:8081`) |

Минимальная замена для внешнего Nginx, который раньше слал всё на один
upstream:

```nginx
upstream remnawave_backend_webhooks { server backend:8080; }
upstream remnawave_frontend         { server frontend:80; }

server {
    server_name app.domain.com;
    listen 443 ssl;
    http2 on;
    # ssl_certificate / ssl_certificate_key — без изменений

    location /webhook/ { proxy_pass http://remnawave_backend_webhooks; }
    location /healthz  { proxy_pass http://remnawave_backend_webhooks; }
    location /         { proxy_pass http://remnawave_frontend;         }
}
```

Полные примеры (Caddy, Nginx, Newt/Pangolin и запуск без обратного прокси) — в
[docs/getting-started/deployment.md](../getting-started/deployment.md) и [docs/features/web-app.md](../features/web-app.md). Если раньше прокси указывал на
`remnawave-tg-shop:8000` напрямую, после миграции нужно либо переключиться на
`backend:8080` / `frontend:80`, либо использовать готовый Caddy/Nginx/Newt
пример, который уже знает правильную маршрутизацию.

## Если что-то пошло не так

`migrate` упал → читайте `docker compose logs migrate`. Том БД остался
не тронут, можно откатиться, переключив compose-файл обратно на старый
коммит и подняв старый стек на старом томе `remnawave-tg-shop-db-data`
(пока вы его не удалили).

`backend` не стартует → чаще всего `WEBHOOK_BASE_URL` пуст, либо
`WEBHOOK_SECRET_TOKEN` отличается от того, что Telegram ждёт. Поставьте
свежий секрет в `.env` и перезапустите — Telegram переустановит webhook
автоматически.

Web App пуст / 502 → проверьте, что `frontend` живёт (`docker compose ps`),
а внешний прокси шлёт на `frontend:80`, а не на старый
`remnawave-tg-shop:8000`.
