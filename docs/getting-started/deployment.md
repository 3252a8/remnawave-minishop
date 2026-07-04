# Развертывание

Документ описывает продакшен-запуск после разделения проекта на `backend`, `frontend` и `worker`.
Перед стартом заполните минимальный `.env` по [configuration.md](configuration.md). Полный справочник переменных лежит в [configuration/env-vars.md](../configuration/env-vars.md); после первого входа большинство продуктовых настроек удобнее менять через Web App админку.

## Быстрый старт

```bash
cp .env.example .env
nano .env
docker compose up -d --build
docker compose ps
docker compose logs -f backend worker frontend
```

## Интерактивный install wizard

Для нового сервера скачайте install-скрипт и запустите его:

```bash
curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/install.sh -o install.sh
sh install.sh
```

Та же ссылка на install-скрипт в GitLab:

```bash
curl -fsSL https://gitlab.com/3252a8/remnawave-minishop/-/raw/main/scripts/install.sh -o install.sh
sh install.sh
```

Wizard работает через меню с цифрами и подтверждениями `y/n`. Он умеет:

- работать полностью на русском языке и по умолчанию предлагать папку
  `/opt/remnawave-minishop`;
- скачать выбранный compose-профиль (`Caddy`, `Nginx`, `Pangolin/Newt`, `no-proxy` или профиль существующего eGames reverse proxy);
- сгенерировать минимальный `.env`, включая пароли и стабильные secrets;
- проверить A-записи `WEBHOOK_HOST` и `MINIAPP_HOST` перед выпуском TLS;
- для Nginx выпустить сертификаты через Certbot Cloudflare DNS-01 или standalone
  HTTP-01, либо принять уже разложенные файлы `ssl/<hostname>/`;
- сохранить backup существующих файлов перед перезаписью;
- подготовить writable `data/` для файлов приложения и при необходимости
  обновить владельца каталога на пользователя контейнеров `10001:10001`;
- запустить `docker compose pull && docker compose up -d`;
- проверить текущий стек через `docker compose ps` и логи `migrate`;
- запустить миграцию из поддерживаемых ботов: Remnashop и старый
  `remnawave-tg-shop`;

Wizard не спрашивает repository/ref в обычном сценарии. По умолчанию он берет
`3252a8/remnawave-minishop` и ref `main`; для тестирования другой ветки, тега
или форка задайте источник перед запуском:

```bash
MINISHOP_INSTALL_REPO=3252a8/remnawave-minishop \
MINISHOP_INSTALL_REF=main \
sh install.sh
```

Миграция Remnashop в wizard сначала запускает проверку без записи (`dry-run`),
показывает короткую сводку и сохраняет полный JSON/raw-вывод в `.installer/`.
Если выбрана текущая compose-БД, wizard предлагает сделать бэкап целевой БД и
основных файлов деплоя в `backups/pre-remnashop-migration-*` с `restore.sh`.
После успешной проверки подтверждение применения имеет дефолт `Y`: Enter
применит миграцию, `n` остановит ее без записи. Если
указать старый Remnashop `.env`, wizard передаст importer-у `APP_CRYPT_KEY`,
Remnawave API settings и поддерживаемые payment provider settings из таблицы
`payment_gateways`. После применения wizard обновляет совместимые настройки,
перезапускает `backend`, `worker` и `frontend`, для профиля eGames делает
`nginx -t` и reload/restart eGames Nginx, отправляет Telegram-уведомление
админам/лог-чату и в самом конце печатает новые webhook URL для Remnawave Panel,
Telegram и платежных провайдеров.
Миграция со старого `remnawave-tg-shop` работает как upgrade совместимой БД:
либо копирует старый Docker volume, либо делает `pg_dump` по source DSN,
восстанавливает дамп в целевую compose-БД и запускает сервис `migrate`.

### Что спрашивает install wizard

Wizard старается предлагать безопасные значения по умолчанию. Если вы запускаете
его на обычном VPS с публичными доменами, чаще всего можно нажимать Enter там,
где уже показано подходящее значение.

| Вопрос | Что это значит | Что обычно выбрать |
| --- | --- | --- |
| `Папка установки` | Каталог, куда будут скачаны `docker-compose.yml`, `.env`, прокси-конфиги и где появятся `data/` и `backups/`. | Оставьте `/opt/remnawave-minishop`, если на сервере нет особой схемы каталогов. |
| `Профиль деплоя` | Как приложение будет опубликовано наружу. | `Caddy HTTPS` для нового публичного сервера; `Nginx HTTPS`, если уже управляете сертификатами; `Pangolin/Newt`, если входящие порты закрыты; `Без прокси`, если TLS завершается внешней платформой; `eGames`, если Remnawave уже стоит через eGames reverse proxy на этом же хосте. |
| `Имя Docker Compose проекта` | Префикс Docker-сети, volumes и контейнеров. | Оставьте `remnawave-minishop`. Меняйте только если на одном сервере нужно несколько независимых стеков. |
| `Тег Docker-образа` | Версия backend/worker/frontend образов. | Для обычной установки оставьте `latest` или укажите конкретный опубликованный релизный тег. |
| `Токен Telegram бота` | `BOT_TOKEN` из BotFather. | Вставьте токен бота, через которого пользователи будут открывать Mini App. |
| `Telegram ID администраторов` | Список Telegram ID, которым доступна админка и сервисные уведомления. | Укажите свой ID; несколько ID разделяйте запятыми. |
| `Пользователь/пароль/база PostgreSQL` | Учетные данные внутренней базы Minishop. | Пользователя и имя базы можно оставить по умолчанию; пароль wizard генерирует сам, его можно принять Enter. |
| `Название Web App` | Название приложения в интерфейсе. | Можно оставить `remnawave-minishop` и позже поменять в настройках. |
| `URL API Remnawave Panel` | Адрес API панели, обычно `https://panel.example.com/api`. | Укажите публичный URL панели с `/api` в конце. |
| `API-ключ Remnawave Panel` | Token из Remnawave Panel для чтения/изменения пользователей. | Вставьте API token с нужными правами. Если панель закрыта cookie-proxy, заполните и вопрос про Cookie. |
| `Webhook-секрет Remnawave Panel` | Секрет, которым панель подписывает webhook в Minishop. | Можно принять сгенерированный секрет, но тот же секрет нужно указать в Remnawave Panel. |
| `Telegram OAuth client secret` | Секрет BotFather Web Login для входа через браузер вне Telegram. | Можно оставить пустым, если нужен только Telegram Mini App. |
| `WEBHOOK_HOST` / `MINIAPP_HOST` | Публичные домены без `https://`, пути и порта. | Например `webhooks.example.com` и `app.example.com`. Для Caddy/Nginx/eGames DNS должен указывать на сервер или на прокси перед ним. |
| `HTTP_BIND` / `HTTPS_BIND` | На каком IP и портах Caddy/Nginx слушает входящий HTTP/HTTPS. | Обычно `0.0.0.0:80` и `0.0.0.0:443`. IP без порта указывать нельзя. |
| `WEB_SERVER_BIND` / `FRONTEND_BIND` | Порты прямой публикации backend и frontend в no-proxy/eGames профилях. | Для no-proxy обычно `0.0.0.0:8080` и `0.0.0.0:8082`; для eGames лучше `127.0.0.1:8080` и `127.0.0.1:8082`, чтобы сервисы были доступны только локальному Nginx. |
| `WEBHOOK_PUBLIC_URL` / `MINIAPP_PUBLIC_URL` | Публичные URL, по которым Telegram, платежные провайдеры и пользователи увидят приложение в no-proxy/eGames сценариях. | Для production это должны быть HTTPS URL. В no-proxy с локальной проверкой можно временно оставить `http://127.0.0.1:...`. |

Формат bind-полей (`HTTP_BIND`, `HTTPS_BIND`, `WEB_SERVER_BIND`,
`FRONTEND_BIND`) особенно важен: используйте `PORT` или `IP:PORT`, например
`80`, `0.0.0.0:80`, `<IP_СЕРВЕРА>:80`, `127.0.0.1:8080`. Значение
с одним IP без порта некорректно: Docker Compose воспринимает его как
порт хоста и падает с ошибкой `invalid hostPort`.

Если Docker Compose не найден, wizard предложит установить его автоматически.
Он сначала пробует системный пакетный менеджер (`apt`, `dnf/yum`, `apk`,
`pacman`), затем, если Docker CLI уже установлен, пробует поставить Compose как
Docker CLI plugin. Если автоматическая установка не подходит вашему серверу,
установите Docker Engine и Docker Compose plugin вручную и запустите wizard
повторно.

При ошибке `docker compose pull` или `docker compose up -d` wizard печатает не
только сырой вывод Docker, но и русское объяснение для частых случаев:
некорректный bind-адрес, занятый порт, IP не назначен серверу, не запущен
Docker daemon, нет прав на Docker socket, недоступен registry или указан
несуществующий `IMAGE_TAG`. Полный вывод последней Compose-ошибки сохраняется в
`.installer/compose-last-error.log` внутри папки установки.

Обычный `docker compose up -d --build` поднимает:

- `postgres` и `redis` с проверками здоровья;
- `migrate` как одноразовый сервис на backend-образе;
- `backend` только после успешных миграций;
- `worker` только после успешных миграций;
- `frontend` как отдельный nginx-образ без Python runtime.

Основной путь миграций — отдельный сервис `migrate`. `backend` и `worker` также выполняют
безопасную проверку схемы на старте под PostgreSQL advisory lock, поэтому прямой запуск сервиса
без compose тоже применит недостающие миграции и не создаст гонку на схеме БД.

## Готовые папки запуска

Для продакшена удобнее использовать не корневой compose, а отдельные Docker Compose-примеры из папки `deploy/examples`. В каждой папке лежат свой `docker-compose.yml`, `.env.example` и нужный конфиг прокси.

Предпочтительный вариант для обычного публичного сервера - **Caddy**: он сам выпускает и продлевает HTTPS-сертификаты, а конфигурация получается короче, чем с ручным Nginx.

| Папка | Когда использовать |
| --- | --- |
| [`deploy/examples/caddy`](https://github.com/3252a8/remnawave-minishop/tree/main/deploy/examples/caddy) | Нужен простой публичный HTTPS с автоматическими сертификатами Let's Encrypt. |
| [`deploy/examples/nginx`](https://github.com/3252a8/remnawave-minishop/tree/main/deploy/examples/nginx) | Уже используете Nginx и готовы положить TLS-сертификаты рядом с примером. |
| [`deploy/examples/newt`](https://github.com/3252a8/remnawave-minishop/tree/main/deploy/examples/newt) | Публикуете сервисы через Pangolin/Newt без входящих портов на сервере приложения. |
| [`deploy/examples/no-proxy`](https://github.com/3252a8/remnawave-minishop/tree/main/deploy/examples/no-proxy) | Нужно напрямую открыть HTTP-порты backend/frontend или проверить стек за внешним TLS-терминатором. |
| `Уже установленная Remnawave через eGames - использовать ее Nginx/TLS` в wizard | Remnawave Panel уже стоит на этом же хосте через [`eGamesAPI/remnawave-reverse-proxy`](https://github.com/eGamesAPI/remnawave-reverse-proxy); wizard использует no-proxy compose, добавляет backend/Mini App маршруты в найденный `nginx.conf` eGames и после миграции перечитывает Nginx. |

## Caddy (рекомендуемый вариант)

Caddy подходит, если DNS-записи `WEBHOOK_HOST` и `MINIAPP_HOST` смотрят на сервер приложения, а входящие `80/tcp` и `443/tcp` открыты.

```bash
cd deploy/examples/caddy
cp .env.example .env
nano .env
docker compose up -d
docker compose logs -f caddy backend worker frontend
```

Минимально поменяйте в `.env`:

- `WEBHOOK_HOST` и `MINIAPP_HOST`;
- `BOT_TOKEN`, `ADMIN_IDS`;
- `POSTGRES_PASSWORD`;
- `WEBAPP_SESSION_SECRET`, `WEBHOOK_SECRET_TOKEN`;
- `PANEL_API_URL`, `PANEL_API_KEY`, `PANEL_WEBHOOK_SECRET`.

Если нужна нестандартная логика Caddy, правьте `Caddyfile` рядом с compose и перезапускайте:

```bash
docker compose up -d --force-recreate caddy
```

## Nginx

Nginx-вариант поднимает Nginx в той же Docker-сети, что и приложение:

- `WEBHOOK_HOST` проксируется в `backend:8080`;
- `MINIAPP_HOST` проксируется в `frontend:80`;
- `frontend` сам проксирует внутренние `/api`, `/auth` и ассеты тем в `backend:8081`.

```bash
cd deploy/examples/nginx
cp .env.example .env
nano .env
```

Положите TLS-сертификаты в `ssl/`:

```text
ssl/
  webhooks.example.com/
    fullchain.pem
    privkey.pem
  app.example.com/
    fullchain.pem
    privkey.pem
```

Имена папок должны совпадать с `WEBHOOK_HOST` и `MINIAPP_HOST` в `.env`.

```bash
docker compose up -d
docker compose logs -f nginx backend worker frontend
```

Если нужно поменять заголовки, лимиты или TLS-настройки, правьте `nginx.conf.template` и перезапускайте Nginx:

```bash
docker compose up -d --force-recreate nginx
```

## Pangolin / Newt

Этот вариант не открывает входящие порты на сервере приложения. Newt подключается к Pangolin, а публичные домены настраиваются ресурсами в панели Pangolin.

```bash
cd deploy/examples/newt
cp .env.example .env
nano .env
docker compose up -d
```

В `.env` заполните:

- `WEBHOOK_HOST` и `MINIAPP_HOST` - публичные домены ресурсов в Pangolin;
- `PANGOLIN_ENDPOINT`, `NEWT_ID`, `NEWT_SECRET` - значения из настроек site/client в Pangolin;
- обычные переменные приложения: `BOT_TOKEN`, `ADMIN_IDS`, `POSTGRES_PASSWORD`, секреты и доступ к Remnawave.

В Pangolin создайте два HTTP-ресурса для этого Newt site:

| Публичный домен | Upstream |
| --- | --- |
| `https://webhooks.example.com` | `http://backend:8080` |
| `https://app.example.com` | `http://frontend:80` |

Проверка:

```bash
docker compose ps
docker compose logs -f newt backend worker frontend
```

## Без обратного прокси

Этот вариант напрямую публикует два HTTP-порта:

- backend/вебхуки: `WEB_SERVER_BIND`, по умолчанию `0.0.0.0:8080`;
- frontend/Mini App: `FRONTEND_BIND`, по умолчанию `0.0.0.0:8082`.

```bash
cd deploy/examples/no-proxy
cp .env.example .env
nano .env
docker compose up -d
```

Важно: контейнеры приложения сами не выпускают TLS-сертификаты. Для реального вебхука Telegram и Mini App публичные URL должны быть HTTPS. Используйте этот вариант для локальной проверки, внутренней сети или ситуации, когда HTTPS завершается внешней платформой и дальше трафик приходит на эти порты.

Проверка локально:

```bash
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8082/health
docker compose logs -f backend worker frontend
```

Корневой `docker-compose.yml` оставлен для локальной сборки из исходников. Примеры в `deploy/examples` используют готовые Docker Hub-образы и не требуют указывать `-f`.

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
падают, приложение не стартует поверх неподготовленной БД. При прямом запуске `backend` или
`worker` без compose тот же `init_db` применяет недостающие миграции перед стартом логики сервиса.

## Сервисы

- `backend`: aiohttp API, вебхук Telegram, платежные вебхуки, вебхуки панели, проверка здоровья `/healthz`.
- `worker`: TariffTrafficWorker, задачи синхронизации с панелью, обработка рассылок, потребители очереди вебхуков.
- `frontend`: статические Svelte-ассеты через nginx.
- `postgres`: PostgreSQL 17.
- `redis`: Redis 7 для FSM, кеша, rate-limit, очередей и locks.

В продакшен-примерах внешний доступ добавляют `caddy`, `nginx`, `newt` или прямые `ports` в соответствующем варианте из `deploy/examples`.

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
`127.0.0.1:${FRONTEND_PORT:-8082}`. В новых продакшен-примерах проверяйте bind-переменные
конкретной папки: `HTTP_BIND`, `HTTPS_BIND`, `WEB_SERVER_BIND` или `FRONTEND_BIND`.

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

### Автодеплой из GitHub Actions

Workflow `Deploy production` запускается на каждом push в `prod` и вручную через
`workflow_dispatch`. Он собирает `backend`, `worker` и `frontend`, публикует
production-теги `latest` и `prod-<sha>` в GHCR текущего владельца репозитория, затем по SSH
заходит на сервер и выполняет:

```bash
docker compose pull
docker compose up -d --remove-orphans
docker compose ps
```

Минимальные GitHub Secrets для environment `production` или всего репозитория:

| Secret | Назначение |
| --- | --- |
| `DEPLOY_HOST` | IP или hostname production-сервера. |
| `DEPLOY_USER` | SSH-пользователь, у которого есть доступ к Docker Compose каталогу и Docker socket. |
| `DEPLOY_SSH_KEY` | Private key для SSH-доступа. |

Опциональные Secrets:

| Secret | Значение по умолчанию | Когда менять |
| --- | --- | --- |
| `DEPLOY_PORT` | `22` | SSH слушает другой порт. |
| `DEPLOY_PATH` | `/opt/remnawave-minishop` | Compose-файлы лежат в другом каталоге. |
| `DEPLOY_COMPOSE_FILES` | `docker-compose.yml` | Нужны несколько compose-файлов, например `docker-compose.yml,docker-compose.override.yml`. |
| `DEPLOY_IMAGE_TAG` | `latest` | Сервер должен тянуть не `latest`, а фиксированный тег. |
| `DEPLOY_IMAGE_REPOSITORY_PREFIX` | `ghcr.io/<repo-owner>/remnawave-minishop` | Сервер должен тянуть Docker Hub или другой registry. |
| `DEPLOY_HEALTH_URL` | пусто | Нужна HTTP-проверка после рестарта, например `https://app.example.com/health`. |
| `DEPLOY_KNOWN_HOSTS` | `ssh-keyscan` на лету | Хотите закрепить SSH host key без сетевого сканирования. |
| `DEPLOY_REGISTRY` | `ghcr.io` | Используется другой registry для `docker login`. |
| `DEPLOY_REGISTRY_USERNAME` / `DEPLOY_REGISTRY_PASSWORD` | пусто | GHCR/Docker Hub package приватный и серверу нужен login перед `pull`. |

Если сервер должен тянуть образы из fork-owned GHCR, в compose `.env` или в секрет
`DEPLOY_IMAGE_REPOSITORY_PREFIX` укажите:

```bash
IMAGE_REPOSITORY_PREFIX=ghcr.io/kinm/remnawave-minishop
IMAGE_TAG=latest
```

Для публикации production-образов еще и в Docker Hub создайте repo variable
`PUBLISH_DOCKERHUB=true` и добавьте Secrets `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`.

## Образы GHCR и Docker Hub

Образы приложения называются единообразно:

```text
ghcr.io/3252a8/remnawave-minishop-backend:<tag>
ghcr.io/3252a8/remnawave-minishop-worker:<tag>
ghcr.io/3252a8/remnawave-minishop-frontend:<tag>
docker.io/3252a8/remnawave-minishop-backend:<tag>
docker.io/3252a8/remnawave-minishop-worker:<tag>
docker.io/3252a8/remnawave-minishop-frontend:<tag>
```

Чтобы собрать и сразу опубликовать все три образа в GHCR и Docker Hub, сначала выполните логин в оба registry:

```bash
docker login ghcr.io
docker login docker.io
IMAGE_TAG=v3.4.3 bash scripts/docker-build-push-images.sh
```

PowerShell-вариант:

```powershell
$env:IMAGE_TAG = "v3.4.3"
docker login ghcr.io
docker login docker.io
powershell -ExecutionPolicy Bypass -File .\scripts\docker-build-push-images.ps1
```

По умолчанию скрипты используют:

- `IMAGE_REGISTRIES=ghcr.io docker.io`
- `IMAGE_NAMESPACE=3252a8`
- `IMAGE_PREFIX=remnawave-minishop`
- `TARGETS=backend worker frontend`
- `DOCKERFILE=deploy/docker/Dockerfile`

Если нужен только один registry или другой namespace, переопределите переменные:

```bash
IMAGE_REGISTRIES=docker.io IMAGE_TAG=v3.4.3 bash scripts/docker-build-push-images.sh
IMAGE_REGISTRIES="ghcr.io docker.io" IMAGE_NAMESPACE=other IMAGE_TAG=v3.4.3 bash scripts/docker-build-push-images.sh
```

Старые раздельные команды тоже остаются:

```bash
IMAGE_TAG=v3.4.3 scripts/docker-build-images.sh
IMAGE_TAG=v3.4.3 scripts/docker-push-images.sh
```

Для PowerShell есть варианты `scripts/docker-build-images.ps1` и
`scripts/docker-push-images.ps1`. Если публикуете образы в другой registry, namespace или с другим
префиксом имени, переопределите `IMAGE_NAMESPACE`, `IMAGE_REGISTRY` или `IMAGE_PREFIX`.

Для совместимости оставлены Docker Hub-only скрипты:

```bash
docker login
IMAGE_TAG=v3.4.3 bash scripts/dockerhub-build-push-images.sh
```

PowerShell-вариант:

```powershell
$env:IMAGE_TAG = "v3.4.3"
docker login
powershell -ExecutionPolicy Bypass -File .\scripts\dockerhub-build-push-images.ps1
```

Если PowerShell блокирует локальные скрипты ошибкой `PSSecurityException` / Execution Policy,
запустите те же скрипты с обходом политики только для текущего процесса:

```powershell
$env:IMAGE_TAG = "v3.4.3"
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
В Caddy-варианте также используются `caddy-data` и `caddy-config`.

Файлы приложения монтируются из локальной папки `./data` рядом с выбранным `docker-compose.yml` в
`/app/data`; внутри нее лежат тарифы, темы, логотипы и прочие файловые данные приложения.

Тот же `/app/data` должен быть смонтирован в `migrate`, `backend` и `worker`. Это важно для `data/tariffs.json`: `docker compose run --rm migrate` читает тот же каталог тарифов, что и приложение. В текущих compose-файлах этот mount уже есть у всех трех сервисов.

Перед первым запуском на сервере заранее дайте права пользователю контейнера `10001`:

```bash
mkdir -p data/themes data/webapp-logo data/tariffs
touch data/locales-overrides.json
chown -R 10001:10001 data
chmod -R u+rwX data
docker compose run --rm migrate
docker compose up -d --force-recreate backend worker
```

Проверка прав:

```bash
docker compose exec backend sh -lc 'id; touch /app/data/themes/test && rm /app/data/themes/test'
```

## Резервная копия PostgreSQL

Для штатных автоматических ZIP-бэкапов, отправки в Telegram и восстановления через админку используйте раздел [бэкапы и восстановление](../features/backups.md). Команды ниже - минимальный ручной fallback для PostgreSQL.

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

Готовые reverse-proxy примеры описаны выше:

- [Caddy](#caddy-рекомендуемый-вариант) - автоматический HTTPS;
- [Nginx](#nginx) - сертификаты кладутся рядом в `ssl/`;
- [Newt/Pangolin](#pangolin--newt) - без входящих портов на сервере приложения.

Во всех вариантах схема одинаковая:

- webhook/backend-домен целиком идет в `backend:8080`;
- Mini App/frontend-домен целиком идет в `frontend:80`;
- API/auth/theme routes Mini App дальше проксируются frontend nginx в `backend:8081`.

Для платежных провайдеров с IP allowlist важно, чтобы reverse proxy передавал реальный IP
отправителя в `X-Forwarded-For`, а backend доверял IP последнего proxy-hop через
`TRUSTED_PROXIES`. Готовые профили `caddy`, `nginx` и `newt` уже доверяют loopback и
private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `fc00::/7`), чтобы
Docker/LAN/Kubernetes proxy не ломал проверки `YOOKASSA`, `FREEKASSA_TRUSTED_IPS`,
`WATA_TRUSTED_IPS`, `HELEKET_TRUSTED_IPS` и `PAYKILLA_TRUSTED_IPS`. Если в вашей
Docker-сети есть недоверенные контейнеры, сузьте `TRUSTED_PROXIES` до конкретного IP
Caddy/Nginx/Newt. Trust-all режим возможен через `0.0.0.0/0,::/0`, но используйте его
только когда backend недоступен напрямую, а внешний proxy очищает входящий `X-Forwarded-For`.

Минимальная логика Caddy:

```caddyfile
webhooks.example.com {
	reverse_proxy backend:8080
}

app.example.com {
	reverse_proxy frontend:80
}
```

Минимальная логика Nginx такая же: `webhooks.example.com` проксируется в `backend:8080`,
`app.example.com` - в `frontend:80`. В `deploy/examples/nginx/nginx.conf.template` уже есть
заголовки `X-Forwarded-*`, редирект HTTP -> HTTPS и пути сертификатов.

## Переменный env-файл

По умолчанию compose читает `.env`. Для smoke-тестов или отдельного окружения можно подставить
другой файл:

```bash
APP_ENV_FILE=.env.staging docker compose --env-file .env.staging up -d --build
```

## Dev dry-run рядом с production

Для проверки фичей на той же Remnawave Panel поднимайте dev-стек с отдельным
env-файлом, отдельным Telegram-ботом и локальной БД.
В dev-режиме приложение продолжает читать пользователей, squads, devices и
статистику из живой панели, но записи в пользователей Remnawave не отправляет:
payload валидируется, а в логах появляется строка вида
`[PANEL DRY-RUN OK] would PATCH /users ...`.

Минимальный фрагмент `.env.dev`:

```env
APP_RUNTIME_MODE=development
PANEL_WRITE_MODE=dry_run
PANEL_DRY_RUN_VALIDATE_REMOTE=True
PANEL_DRY_RUN_SYNTHETIC_CREATE=True

REDIS_KEY_PREFIX=remnawave-tg-shop-dev
BACKUP_ENABLED=False
```

Запуск:

```bash
APP_ENV_FILE=.env.dev docker compose --env-file .env.dev up -d --build
```

`PANEL_WRITE_MODE=live` можно поставить только для отдельной тестовой Remnawave
Panel, потому что этот режим реально меняет пользователей панели.

Если второй стек запускается на том же хосте, дополнительно разведите порты:
для корневого compose используйте `WEB_SERVER_PORT` и `FRONTEND_PORT`, а для
production examples без встроенного TLS - `WEB_SERVER_BIND` и `FRONTEND_BIND`.
Если production на другом сервере, локальные порты можно оставить стандартными.
