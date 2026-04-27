# Миграция с `remnawave-tg-shop` на `remnawave-minishop`

Начиная с этой версии контейнеры и тома названы `remnawave-minishop*` вместо `remnawave-tg-shop*`. Старый и новый стеки используют **разные имена томов**, поэтому простой `docker compose up -d` после `git pull` создаст пустую БД. Эта инструкция описывает, как перенести данные.

Есть два пути:

- [Автоматический](#автоматический-способ-через-скрипт) — один скрипт, идемпотентный, проверяет состояние на каждом шаге.
- [Ручной](#ручной-способ) — команды, которые делает скрипт, если хочется понимать происходящее или выполнить выборочно.

В обоих случаях:
- старые тома **не удаляются** автоматически — это безопасный бэкап на случай отката;
- сертификаты Caddy (если используется `docker-compose-caddy.yml`) тоже переносятся, чтобы Let's Encrypt не выписывал их заново и не упереться в rate limit.

## Автоматический способ (через скрипт)

Если helper ещё не лежит у вас локально, запускайте его прямо из `raw` из корня старого репозитория:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/migrate_to_minishop.sh)
```

> Команда выше рассчитана на `bash` / Git Bash / WSL. Если вы запускаете из PowerShell, удобнее сначала открыть Git Bash.

Если вы уже подтянули новую версию и файл есть локально, можно запускать и так:

```bash
bash scripts/migrate_to_minishop.sh
```

По умолчанию скрипт работает с `docker-compose.yml` и переключается на ветку `main`. Можно переопределить через переменные окружения:

| Переменная        | Назначение                                                              | По умолчанию           |
| ----------------- | ----------------------------------------------------------------------- | ---------------------- |
| `PROJECT_ROOT`    | Явный путь к корню старого репозитория, если запуск не из него          | текущая директория     |
| `COMPOSE_FILE`    | Какой compose-файл стартовать в конце                                   | `docker-compose.yml`   |
| `TARGET_BRANCH`   | На какую ветку переключаться и подтягивать обновления                   | `main`                 |
| `GIT_REMOTE`     | Какой remote использовать для `fetch`/`pull`                            | `origin`               |
| `NEW_ORIGIN_URL`  | Если задано и не совпадает с URL выбранного remote — он будет обновлён  | (не меняется)          |
| `ASSUME_YES`      | `1` — не задавать интерактивных вопросов                                | `0`                    |

Примеры:

```bash
# Caddy-вариант из raw
COMPOSE_FILE=docker-compose-caddy.yml \
  bash <(curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/migrate_to_minishop.sh)

# С переключением origin на форк 3252a8
NEW_ORIGIN_URL=https://github.com/3252a8/remnawave-minishop.git \
  bash <(curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/migrate_to_minishop.sh)

# Без интерактива
ASSUME_YES=1 \
  bash <(curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/migrate_to_minishop.sh)
```

Что делает скрипт:

1. **Останавливает текущий стек**: проверяет известные контейнеры старой и новой схемы и останавливает их, если они запущены.
2. **Переключает `origin`**, если задана переменная `NEW_ORIGIN_URL`, иначе оставляет как есть.
3. **Подтягивает целевую ветку** (`git fetch` + `git switch` + `git pull --ff-only`). Прерывается, если в рабочем дереве есть незакоммиченные изменения.
4. **Обновляет `.env`** и правит `POSTGRES_HOST`, если он ещё указывает на старый контейнер.
5. **Подготавливает новый стек в режиме `--no-start`**, чтобы Compose сам создал тома и не ругался на уже существующий volume.
6. **Переносит тома** `remnawave-tg-shop-*` → `remnawave-minishop-*` через одноразовый `alpine`-контейнер. Если новый том уже непустой, копирование пропускается.
7. **Стартует новый стек** (`docker compose -f $COMPOSE_FILE up -d --remove-orphans`, а для локальной сборки ещё и `--build`) и печатает `docker compose ps`.

Скрипт идемпотентен: повторный запуск ничего не сломает, просто пропустит уже выполненные шаги.

После того как убедитесь, что бот работает и данные на месте, удалите старые тома:

```bash
docker volume rm remnawave-tg-shop-db-data
docker volume rm remnawave-tg-shop-caddy-data remnawave-tg-shop-caddy-config 2>/dev/null || true
```

> ⚠️ Если у вас есть внешний reverse proxy (Nginx и т.п.), не забудьте поправить в его конфиге `upstream`/`proxy_pass`: имя хоста контейнера изменилось с `remnawave-tg-shop` на `remnawave-minishop`. Скрипт не трогает внешние конфиги.

## Ручной способ

1.  **Остановите старый стек и обновите код:**

    ```bash
    docker compose down
    git fetch origin
    git checkout main
    git pull --ff-only origin main
    ```

2.  **Обновите `.env`:**

    ```bash
    sed -i.bak 's/^POSTGRES_HOST=remnawave-tg-shop-db$/POSTGRES_HOST=remnawave-minishop-db/' .env
    ```

3.  **Подготовьте новый стек без запуска:**

    ```bash
    # Локальная сборка
    docker compose up --no-start --build

    # Или Caddy-вариант
    docker compose -f docker-compose-caddy.yml up --no-start --build

    # Или готовый образ
    docker compose -f docker-compose-remote-server.yml up --no-start
    ```

4.  **Перенесите том БД в новое имя:**

    ```bash
    docker run --rm \
      -v remnawave-tg-shop-db-data:/from:ro \
      -v remnawave-minishop-db-data:/to \
      alpine sh -c "cd /from && cp -a . /to"
    ```

5.  **(Только для Caddy)** перенесите тома Caddy с TLS-сертификатами и состоянием ACME:

    ```bash
    for v in caddy-data caddy-config; do
      docker run --rm \
        -v "remnawave-tg-shop-$v":/from:ro \
        -v "remnawave-minishop-$v":/to \
        alpine sh -c "cd /from && cp -a . /to"
    done
    ```

6.  **Запустите новый стек:**

    ```bash
    docker compose up -d
    # или
    docker compose -f docker-compose-caddy.yml up -d --build
    # или
    docker compose -f docker-compose-remote-server.yml up -d
    ```

7.  **Проверьте:**

    ```bash
    docker compose ps
    docker compose logs -f remnawave-minishop
    ```

8.  **(Опционально) удалите старые тома**, когда убедитесь, что новый стек стабилен:

    ```bash
    docker volume rm remnawave-tg-shop-db-data
    docker volume rm remnawave-tg-shop-caddy-data remnawave-tg-shop-caddy-config 2>/dev/null || true
    ```
