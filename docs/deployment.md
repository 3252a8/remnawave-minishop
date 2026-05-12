# Развертывание

Документ описывает запуск через Docker Compose, маршруты вебхуков и варианты reverse proxy. Перед запуском заполните `.env` по [configuration.md](configuration.md).

## Docker Compose

Локальная сборка:

```bash
docker compose up -d --build
docker compose logs -f remnawave-minishop
```

Запуск из готового образа:

```bash
IMAGE_TAG=3.1.0 docker compose -f docker-compose-remote-server.yml up -d
```

`docker-compose-remote-server.yml` можно использовать как шаблон и заменить `image:` на нужный образ. По умолчанию используется `ghcr.io/3252a8/remnawave-minishop:latest`.

## Обновление версии

Образ приложения: `ghcr.io/3252a8/remnawave-minishop`. Тег задаётся переменной окружения **`IMAGE_TAG`** (в Compose подставляется как `${IMAGE_TAG:-latest}`). Для продакшена разумно закрепить **конкретный тег релиза** вместо `latest`, чтобы обновляться осознанно и иметь откат.

**Запуск из готового образа** (`docker-compose-remote-server.yml` или свой файл с тем же шаблоном):

1. Сделайте резервную копию базы (особенно перед крупными обновлениями) — см. раздел «Резервная копия и восстановление PostgreSQL» ниже на этой странице.
2. Укажите нужный тег, например в `.env`: `IMAGE_TAG=3.2.0` (или экспортируйте переменную перед командой).
3. Подтяните образ и пересоздайте контейнер приложения (БД при этом не удаляется, том данных сохраняется):

```bash
docker compose -f docker-compose-remote-server.yml pull remnawave-minishop
docker compose -f docker-compose-remote-server.yml up -d --no-deps remnawave-minishop
```

При необходимости перезапустите оба сервиса: `docker compose -f docker-compose-remote-server.yml up -d`. Флаг `--force-recreate` добавляют, если нужно гарантированно пересоздать контейнер при неизменённом образе.

**Локальная сборка из репозитория** (ваш `Dockerfile`):

```bash
git pull
docker compose up -d --build
```

После обновления проверьте логи (`docker compose logs -f remnawave-minishop`), работу бота, вебхуков и Web App. Совместимость с панелью Remnawave — см. раздел «Совместимость» в [README.md](../README.md).

## Резервная копия и восстановление PostgreSQL

Имя контейнера БД в типичном Compose — `remnawave-minishop-db`. Учётные данные уже передаются в контейнер через `env_file: .env`, поэтому надёжнее вызывать `pg_dump` / `psql` **внутри** контейнера через `sh -c '...'`, чтобы переменные раскрылись там, а не на хосте.

Если написать на хосте `pg_dump -U "$POSTGRES_USER" ...` без экспорта переменных из `.env`, подставится пустая строка: PostgreSQL тогда берёт имя пользователя ОС (часто `root`) и выдаёт `FATAL: role "root" does not exist`. В **PowerShell** `$POSTGRES_DB` из файла `.env` сам не подхватывается — пустое имя базы даёт у `dropdb` ошибку `missing required argument database name`.

**Вариант A (рекомендуется):** переменные только внутри контейнера:

```bash
docker exec remnawave-minishop-db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > backup.sql
```

**Вариант B:** сначала загрузить `.env` в текущую сессию на сервере, затем обычная команда (переменные раскроются на хосте):

```bash
set -a && source .env && set +a
docker exec remnawave-minishop-db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" > backup.sql
```

Такой файл удобно хранить вне сервера. При необходимости добавьте к `pg_dump` параметры сжатия или расписание через cron.

### Восстановление из `backup.sql`

Дамп выше — **обычный текст SQL** без удаления существующих объектов. Чтобы накатить его на **чистую** базу с тем же именем:

1. Остановите приложение, чтобы не было записей в БД:

```bash
docker compose -f docker-compose-remote-server.yml stop remnawave-minishop
```

(или ваш файл Compose без `-f`, если работаете из каталога проекта.)

2. Удалите базу и создайте пустую с тем же именем — пользователь из `.env` в официальном образе PostgreSQL обычно суперпользователь и может это сделать:

```bash
docker exec remnawave-minishop-db sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"'
docker exec remnawave-minishop-db sh -c 'createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

Имя базы у `dropdb` — последний аргумент; флаг **`--if-exists`** ставьте перед ним (иначе клиент может неверно разобрать командную строку).

Если `dropdb` сообщает, что база занята, убедитесь, что остановлен сервис `remnawave-minishop` и к базе нет других подключений.

3. Восстановите данные из файла на хосте. Переменные снова должны раскрываться **внутри** контейнера; на стороне `psql` имеет смысл включить **`ON_ERROR_STOP`**, чтобы при первой ошибке в дампе команда завершилась с ненулевым кодом.

**Bash:**

```bash
docker exec -i remnawave-minishop-db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backup.sql
```

**PowerShell** (перенаправление `<` в `docker exec` часто не подходит; надёжнее передать дамп в stdin через pipe; явная **UTF-8**, чтобы кириллица в комментариях/SQL не исказилась):

```powershell
Get-Content backup.sql -Encoding utf8 | docker exec -i remnawave-minishop-db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Если путь к файлу содержит пробелы, используйте кавычки: `Get-Content "E:\backups\backup.sql" -Encoding utf8 | ...`

4. Запустите приложение снова:

```bash
docker compose -f docker-compose-remote-server.yml start remnawave-minishop
```

Проверьте логи и работу бота. При ошибках импорта убедитесь, что версия приложения совместима со схемой в дампе (после обновлений бота иногда нужны шаги из changelog релиза).

### Замечание про «накат поверх» без пересоздания БД

Если нужно применить дамп к уже заполненной базе без `dropdb`, создавайте резервные копии с **`pg_dump --clean --if-exists`** — в файл попадут команды `DROP` перед `CREATE`, и `psql` сможет перезаписать объекты. Это разрушительно для текущих данных; перед таким сценарием сделайте отдельный свежий бэкап.

## Порты

| Порт | Назначение |
| --- | --- |
| `WEB_SERVER_PORT` (`8080`) | Telegram webhook, платежные вебхуки, Remnawave webhook. |
| `WEBAPP_SERVER_PORT` (`8081`) | Web App / Mini App. |

Web App не должен проксироваться на `WEB_SERVER_PORT`.

## Маршруты вебхуков

Проксируйте платежные и системные вебхуки на `WEB_SERVER_PORT`:

- `https://<webhook-domain>/webhook/yookassa` -> `http://remnawave-minishop:<WEB_SERVER_PORT>/webhook/yookassa`;
- `https://<webhook-domain>/webhook/freekassa` -> `http://remnawave-minishop:<WEB_SERVER_PORT>/webhook/freekassa`;
- `https://<webhook-domain>/webhook/platega` -> `http://remnawave-minishop:<WEB_SERVER_PORT>/webhook/platega`;
- `https://<webhook-domain>/webhook/severpay` -> `http://remnawave-minishop:<WEB_SERVER_PORT>/webhook/severpay`;
- `https://<webhook-domain>/webhook/cryptopay` -> `http://remnawave-minishop:<WEB_SERVER_PORT>/webhook/cryptopay`;
- `https://<webhook-domain>/webhook/panel` -> `http://remnawave-minishop:<WEB_SERVER_PORT>/webhook/panel`.

Telegram webhook устанавливается приложением, если задан `WEBHOOK_BASE_URL`. Путь формируется как `https://<webhook-domain>/<BOT_TOKEN>`.

## Nginx рядом с Remnawave

Пример upstream и server-блока для домена вебхуков:

```nginx
upstream remnawave-minishop {
    server remnawave-minishop:8080;
}

map $http_upgrade $connection_upgrade {
    default upgrade;
    "" close;
}

server {
    server_name webhook.domain.com;
    listen 443 ssl;
    http2 on;

    ssl_certificate "/etc/nginx/ssl/webhook_fullchain.pem";
    ssl_certificate_key "/etc/nginx/ssl/webhook_privkey.key";
    ssl_trusted_certificate "/etc/nginx/ssl/webhook_fullchain.pem";

    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
    proxy_intercept_errors on;
    error_page 400 404 500 502 @redirect;

    location / {
        proxy_pass http://remnawave-minishop$request_uri;
    }

    location @redirect {
        return 404;
    }
}
```

Для Web App используйте отдельный upstream на `WEBAPP_SERVER_PORT`; пример есть в [webapp.md](webapp.md).

## SSL для домена вебхуков

Пример выпуска сертификата через `acme.sh`:

```bash
sudo apt-get install cron socat
curl https://get.acme.sh | sh -s email=EMAIL
source ~/.bashrc
ufw allow 80/tcp
ufw reload

acme.sh --set-default-ca --server letsencrypt
acme.sh --issue --standalone -d 'webhook.domain.com' \
  --key-file /opt/remnawave/nginx/webhook_privkey.key \
  --fullchain-file /opt/remnawave/nginx/webhook_fullchain.pem
```

Если Nginx панели Remnawave запускается в Docker, добавьте сертификаты в `volumes` сервиса Nginx:

```yaml
services:
  remnawave-nginx:
    volumes:
      - ./webhook_fullchain.pem:/etc/nginx/ssl/webhook_fullchain.pem:ro
      - ./webhook_privkey.key:/etc/nginx/ssl/webhook_privkey.key:ro
```

После изменения конфигурации перезапустите Nginx:

```bash
cd /opt/remnawave/nginx
docker compose down
docker compose up -d
docker compose logs -f -t
```

## Caddy

Для схемы с Caddy используйте `docker-compose-caddy.yml` и `Caddyfile`. Caddy публикует наружу `80` и `443`, выпускает TLS-сертификаты и проксирует вебхуки и Web App на разные внутренние порты.

Пример `Caddyfile`:

```caddyfile
webhook.domain.com {
    encode zstd gzip
    reverse_proxy remnawave-minishop:{$WEB_SERVER_PORT:8080}
}

app.domain.com {
    encode zstd gzip
    reverse_proxy remnawave-minishop:{$WEBAPP_SERVER_PORT:8081}
}
```

В `.env` укажите:

```env
WEBHOOK_BASE_URL=https://webhook.domain.com
SUBSCRIPTION_MINI_APP_URL=https://app.domain.com/
```

Запуск:

```bash
docker compose -f docker-compose-caddy.yml up -d --build
```

В BotFather укажите домен Mini App через настройки домена, чтобы он совпадал с `SUBSCRIPTION_MINI_APP_URL`.

## Проверка

```bash
docker compose ps
docker compose logs -f remnawave-minishop
```

Проверьте:

- бот отвечает в Telegram;
- Telegram webhook установлен без ошибок в логах;
- платежные вебхуки доходят до приложения;
- Remnawave webhook проходит проверку `PANEL_WEBHOOK_SECRET`;
- Web App открывается по домену из `SUBSCRIPTION_MINI_APP_URL`;
- в BotFather разрешены URL Web App и callback.
