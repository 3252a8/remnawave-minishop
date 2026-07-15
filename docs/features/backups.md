# Бэкапы и восстановление

Minishop умеет автоматически собирать ZIP-бэкапы в worker-контейнере, хранить последние архивы на сервере, отправлять их в Telegram и восстанавливать БД/compose-папку из админки.

## Что попадает в архив

Архив создается в `BACKUP_DIR`, по умолчанию `data/backups` внутри volume `shop-data`.

Типовой файл называется так:

```text
minishop-20260527-12-00.zip
```

Внутри:

- `database/<POSTGRES_DB>.dump` - `pg_dump` в custom format для `pg_restore`;
- `compose/` - snapshot папки с `docker-compose.yml`, `.env` и соседними конфигами;
- `manifest.json` - дата создания, сведения о БД, compose snapshot и предупреждения.

Если compose-папка не смонтирована или недоступна, worker не роняет весь бэкап: архив будет создан с дампом БД и предупреждением в `manifest.json`.

## Настройка

Основные параметры доступны в админке: **Система -> Настройки -> Бэкапы**.

Минимальный `.env`, если `LOG_CHAT_ID` уже задан и подходит для бэкапов:

```env
BACKUP_ENABLED=True
```

Если бэкапы нужно отправлять в отдельный чат или topic/thread, добавьте только нужные переменные:

```env
BACKUP_CHAT_ID=-1001234567890
BACKUP_THREAD_ID=123
```

Остальные backup-переменные обычно не нужны в `.env`: `BACKUP_INTERVAL_SECONDS=3600` запускает бэкапы ровно на границе часа 12:00, 13:00 и т.д.; `BACKUP_LOCAL_RETENTION=100` хранит 100 последних ZIP-архивов; `BACKUP_COMPOSE_ENABLED=True`, `COMPOSE_BACKUP_SOURCE=.` и `COMPOSE_RESTORE_MODE=rw` уже совпадают со стандартным compose-сценарием.

`BACKUP_CHAT_ID` задает чат Telegram для отправки архивов. Если он пустой, используется `LOG_CHAT_ID`. Для topic/thread можно указать `BACKUP_THREAD_ID`; если он пустой, используется `LOG_THREAD_ID`.

Каждый архив содержит `manifest.json` с SHA-256 и размером каждого файла. Это позволяет проверить, что архив не поврежден и его содержимое не отличается от manifest.

Архив не привязан к текущему инстансу, `BOT_TOKEN` или серверу. Его можно загрузить и восстановить на другом сервере, если формат архива поддерживается и проверки целостности проходят.

## Mount compose-папки

В стандартных compose-файлах есть два mount:

- `worker`: `${COMPOSE_BACKUP_SOURCE:-.}:/app/compose-source:ro` - только читает папку для создания snapshot;
- `backend`: `${COMPOSE_BACKUP_SOURCE:-.}:/app/compose-source:${COMPOSE_RESTORE_MODE:-rw}` - читает список архивов и может восстановить compose-папку из админки.

`COMPOSE_BACKUP_SOURCE=.` означает папку рядом с текущим `docker-compose.yml`. Если compose лежит в другом месте, укажите абсолютный host-путь.

Ручное создание бэкапа из админки выполняется в `backend`-контейнере, а автоматический backup по расписанию - в `worker`-контейнере. Оба контейнера должны видеть `/app/compose-source`. Если ручной backup содержит compose-папку, а автоматический нет, пересоздайте worker после обновления compose:

```bash
docker compose up -d --force-recreate worker
docker compose exec worker ls -la /app/compose-source
```

Если нужно запретить восстановление compose-файлов из контейнера, задайте:

```env
COMPOSE_RESTORE_MODE=ro
```

В этом режиме восстановление БД останется доступным, а восстановление compose-папки вернет понятную ошибку о недоступной записи.

## Восстановление из админки

Откройте **Система -> Бэкапы**. В разделе можно:

- создать новый backup вручную, не дожидаясь следующего запуска по расписанию;
- выбрать архив, уже лежащий в `data/backups`;
- загрузить ZIP-архив вручную;
- отметить, что восстанавливать: `БД`, `compose-папка` или оба варианта;
- запустить восстановление после подтверждения.

Ручное создание использует тот же механизм, что и расписание: делает `pg_dump`, добавляет compose snapshot, сохраняет ZIP в `BACKUP_DIR`, отправляет архив в Telegram и применяет локальный retention. На время ручного запуска используется общий Redis lock, поэтому он не пересечется с плановым backup или restore.

БД восстанавливается через `pg_restore --clean --if-exists --no-owner --no-privileges`. На время восстановления лучше не запускать платежи, рассылки, массовую синхронизацию и ручные изменения подписок.

Compose-файлы восстанавливаются поверх текущей папки. Перед заменой backend создает pre-restore snapshot текущего compose-каталога рядом с остальными архивами:

```text
minishop-pre-restore-YYYYMMDD-HH-MM.zip
```

После восстановления compose-папки перезапустите нужные сервисы, чтобы изменения `docker-compose.yml`, `.env`, Caddyfile/Angie/Nginx-конфигов и других файлов реально применились:

```bash
docker compose up -d --build backend worker
docker compose ps
```

Если менялись proxy-конфиги, перезапустите соответствующий сервис (`caddy`, `angie`, `nginx`, `newt`).

## Проверка архива перед восстановлением

Backend валидирует архив до восстановления:

- файл должен быть валидным ZIP;
- `manifest.json` должен принадлежать `remnawave-minishop` и иметь поддерживаемую версию формата;
- SHA-256 и размер каждого файла должны совпадать с manifest;
- выбранный server-side файл должен лежать внутри `BACKUP_DIR`, путь вида `../backup.zip` отклоняется;
- пути внутри ZIP не могут быть абсолютными, содержать `..`, `\`, пустые сегменты или дубли;
- архивы с подозрительно большим числом файлов, размером или zip-bomb compression ratio отклоняются;
- для восстановления БД нужен `database/*.dump` или `database/*.backup`;
- для восстановления compose нужны файлы внутри `compose/`;
- compose restore стартует только если целевая папка существует и доступна на запись;
- backup/restore защищены одним Redis lock, чтобы две операции не выполнялись одновременно.

Это защищает от случайной загрузки мусорного файла, zip-slip-архивов и поврежденных ZIP. Проверка специально не привязана к секретам инстанса, чтобы архивы можно было использовать для переноса между серверами. Это не проверка доверенного источника: не восстанавливайте архивы, происхождение которых вы не контролируете.

## Перенос на другой сервер

Для переноса БД между инстансами:

1. Создайте backup на старом сервере или возьмите ZIP из Telegram.
2. На новом сервере загрузите архив в **Система -> Бэкапы**.
3. Выберите `БД`; `compose-папку` включайте только если хотите перенести `.env`, `docker-compose.yml` и proxy-конфиги.
4. Запустите restore и после восстановления выполните миграции/healthcheck.

Если переносите compose-папку, проверьте домены, токены, `WEBHOOK_BASE_URL`, `SUBSCRIPTION_MINI_APP_URL`, bind-порты и volume/mount пути: на новом сервере они могут отличаться.

## Ручное восстановление БД

Если админка недоступна, можно восстановить дамп вручную:

```bash
unzip minishop-YYYYMMDD-HH-MM.zip -d restore
docker compose cp restore/database/remnawave_minishop.dump postgres:/tmp/remnawave_minishop.dump
docker compose stop backend worker
docker compose exec postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-privileges /tmp/remnawave_minishop.dump'
docker compose up -d backend worker
```

После ручного восстановления проверьте миграции и healthcheck:

```bash
docker compose run --rm migrate
docker compose ps
docker compose logs -f backend worker
```

## Переменные

Полный справочник лежит в [переменных окружения](../configuration/env-vars.md#кеши-rate-limits-и-worker). Основные ключи:

| Переменная | Назначение |
| --- | --- |
| `BACKUP_ENABLED` | Включает периодические бэкапы. |
| `BACKUP_CHAT_ID` / `BACKUP_THREAD_ID` | Куда отправлять архивы в Telegram. |
| `BACKUP_INTERVAL_SECONDS` | Периодичность, по умолчанию `3600`. |
| `BACKUP_LOCAL_RETENTION` | Сколько последних архивов хранить на сервере. |
| `BACKUP_DIR` | Каталог ZIP-архивов. |
| `BACKUP_COMPOSE_ENABLED` | Добавлять compose snapshot. |
| `COMPOSE_BACKUP_SOURCE` | Host-путь compose-папки для mount в контейнеры. |
| `COMPOSE_RESTORE_MODE` | `rw` для восстановления compose из админки, `ro` для запрета записи. |
| `BACKUP_PG_DUMP_PATH` / `BACKUP_PG_RESTORE_PATH` | Пути к `pg_dump` и `pg_restore` внутри контейнеров. |
