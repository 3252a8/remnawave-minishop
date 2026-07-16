# Переменные окружения

`.env` нужен прежде всего для bootstrap: токен бота, доступ к базе, публичный URL вебхуков и стабильные секреты. После первого входа большая часть продуктовых настроек меняется в Web App админке и сохраняется в БД как переопределения поверх `.env`.

Рекомендуемый порядок:

1. Заполнить минимальный `.env` по `.env.example`.
2. Запустить стек и войти в Web App под Telegram ID из `ADMIN_IDS`.
3. Настроить Remnawave, платежи, внешний вид, поддержку, уведомления и тарифы через админку.

## Минимальный bootstrap

| Переменная | Где менять | Назначение |
| --- | --- | --- |
| `BOT_TOKEN` | Только `.env` | Токен Telegram-бота. |
| `ADMIN_IDS` | Только `.env` | Telegram ID администраторов через запятую. Нужен для первого входа в админку. |
| `WEBHOOK_BASE_URL` | `.env` | Публичный URL backend/webhook-домена. Используется для URL вебхуков Telegram, платежных провайдеров и Remnawave. |
| `POSTGRES_USER` | `.env` / Compose | Пользователь PostgreSQL. |
| `POSTGRES_PASSWORD` | `.env` / Compose | Пароль PostgreSQL. |
| `POSTGRES_DB` | `.env` / Compose | Имя базы PostgreSQL. |
| `WEBAPP_ENABLED` | `.env` / админка | Включает Web App и админку. Держите `True` для первого запуска; если выключить, вернуть доступ можно только через `.env` и рестарт. |
| `WEBAPP_SESSION_SECRET` | `.env` | Стабильный HMAC-секрет сессий Web App. Если пустой, генерируется на процесс, но сессии сбросятся после рестарта. |
| `WEBHOOK_SECRET_TOKEN` | `.env` | Секрет вебхука Telegram. Если пустой, генерируется на процесс. |

## Инфраструктура и Compose

| Переменная | Где менять | Назначение |
| --- | --- | --- |
| `DEPLOYMENT_PROFILE` | install wizard | Информационный маркер выбранного профиля (`caddy`, `angie`, `nginx`, `newt`, `no-proxy`, `egames`). Для `egames` последующие migration-only запуски понимают, что нужно переиспользовать существующий `eGamesAPI/remnawave-reverse-proxy` Nginx. |
| `APP_ENV_FILE` | CLI/Compose | Путь к env-файлу вместо `.env`. |
| `IMAGE_TAG` | CLI/Compose | Тег Docker-образов. |
| `FRONTEND_PORT` | `.env` / Compose | Хостовый порт frontend nginx. По умолчанию `8082`. |
| `WEB_SERVER_HOST` | `.env` | Внутренний хост backend-сервера вебхуков. Обычно `0.0.0.0`. |
| `WEB_SERVER_PORT` | `.env` / Compose | Хостовый порт backend-сервера вебхуков. По умолчанию `8080`. |
| `WEB_SERVER_INTERNAL_PORT` | `.env` / container | Внутренний порт listener-а backend. Compose фиксирует `8080`; при прямом запуске без значения используется `WEB_SERVER_PORT`. |
| `WEBAPP_SERVER_HOST` | `.env` | Внутренний хост Web App API-сервера. Обычно `0.0.0.0`. |
| `WEBAPP_SERVER_PORT` | `.env` | Внутренний порт Web App API-сервера. По умолчанию `8081`. |
| `WEBAPP_API_BASE_URL` | `.env` / frontend | Browser-visible API base для Mini App frontend. Оставляйте `/api`; split frontend/backend настраивается через server-side `WEBAPP_BACKEND_UPSTREAM`. |
| `WEBAPP_BACKEND_UPSTREAM` | frontend env | Куда frontend nginx проксирует `/api`, `/auth`, `/open-app` и Web App assets. По умолчанию `http://backend:8081`; для split можно указать protected backend upstream, private IP/VPN или `http://rathole-server:18081`. |
| `WEBAPP_BACKEND_UPSTREAM_HOST` | frontend env | Host/SNI override для upstream, например `bot.example.com` при `WEBAPP_BACKEND_UPSTREAM=https://bot.example.com`. |
| `MINISHOP_EDGE_TOKEN` | backend/frontend proxy env | Необязательный server-side token для protected WebApp API plane `8081`. Его добавляет frontend nginx/API edge, браузер его не получает. |
| `MINISHOP_EDGE_TOKEN_HEADER` | backend/frontend proxy env | Имя header для edge token. По умолчанию `X-Minishop-Edge-Token`. |
| `FRONTEND_BACKEND_MODE` | install wizard | Информационный режим связи frontend/backend: `same-origin`, `protected-upstream` или `rathole`. |
| `INSTALL_NODE_ROLE` | install wizard | Роль текущего сервера: `full-stack`, `backend-node` или `frontend-node`. |
| `WEBAPP_SERVER_BIND` | split backend node | Host bind для WebApp API plane `8081`, если нужен loopback/private host upstream. Не публикуйте его на `0.0.0.0` без firewall/token. |
| `RATHOLE_IMAGE` | Rathole compose | Образ Rathole, по умолчанию `rapiz1/rathole:v0.5.0`; можно переопределить для другой архитектуры. |
| `RATHOLE_CONTROL_BIND` | Rathole frontend node | Публикуемый control port Rathole server, например `0.0.0.0:2333`. |
| `RATHOLE_CONTROL_REMOTE` | Rathole backend node | Адрес frontend Rathole control port для backend client. |
| `RATHOLE_SERVICE_TOKEN` | Rathole обе стороны | Обязательный token сервиса WebApp API tunnel, одинаковый на frontend и backend servers. |
| `RATHOLE_SERVICE_PORT` | Rathole frontend node | Внутренний service port Rathole server для frontend nginx, по умолчанию `18081`. |
| `POSTGRES_HOST` | Compose | Host PostgreSQL. В штатном Compose задается как `postgres`. |
| `POSTGRES_PORT` | `.env` | Порт PostgreSQL. |
| `DB_POOL_SIZE` | `.env` | Размер async SQLAlchemy pool. |
| `DB_MAX_OVERFLOW` | `.env` | Дополнительные transient DB-соединения сверх pool. |
| `DB_POOL_TIMEOUT_SECONDS` | `.env` | Таймаут ожидания соединения из pool. |
| `DB_POOL_RECYCLE_SECONDS` | `.env` | Период recycling DB-соединений. |
| `REDIS_URL` | Compose | Redis для FSM, кеша, rate-limit, очередей и locks. В Compose задается автоматически. |
| `REDIS_KEY_PREFIX` | `.env` | Префикс Redis-ключей. |
| `TRUSTED_PROXIES` | `.env` | IP/CIDR обратных прокси, которым доверяется `X-Forwarded-For`. По умолчанию включает loopback и private ranges для Docker/LAN/Kubernetes proxy. |
| `HTTP_BIND` / `HTTPS_BIND` | Caddy/Angie Compose | Адреса публикации Caddy- и Angie-вариантов. |
| `NEWT_ID` / `NEWT_SECRET` | Dev Compose | Доступы Newt в dev-compose. |
| `DEV_POSTGRES_PORT` | Dev Compose | Хостовый порт PostgreSQL единого dev stand для full-stack QA. По умолчанию `6768`. |

## Dev / QA only

Эти переменные предназначены для локального dev stand и CI full-stack QA. Не
включайте их в production `.env`.

| Переменная | Назначение |
| --- | --- |
| `QA_AUTH_ENABLED` | В `APP_RUNTIME_MODE=development|test` возвращает одноразовый email-код в ответе `/api/auth/email/request`, чтобы QA могла пройти обычную верификацию без SMTP. |
| `QA_PAYMENT_ENABLED` | Включает локальный provider `qa` для Mini App платежей в dev/test runtime. |
| `QA_PAYMENT_ADMIN_ONLY_ENABLED` | Делает provider `qa` доступным только администраторам. Обычно `False` в dev stand. |
| `QA_PAYMENT_SECRET` | HMAC-секрет для `/webhook/qa-payment`; тесты подписывают payload через `X-QA-Payment-Signature`. |

`TRUSTED_PROXIES` нужен не только для логов: платежные webhook-обработчики с IP-фильтром
сравнивают allowlist провайдера с client IP после обработки `X-Forwarded-For`. Если внешний
proxy не передает этот заголовок или его IP не входит в `TRUSTED_PROXIES`, backend увидит IP
proxy/Docker gateway и может отклонить валидный webhook. Для Caddy/Angie/Nginx/Newt из
`deploy/examples` дефолта достаточно; в кастомной инфраструктуре добавьте CIDR своего proxy
или сузьте значение до конкретных proxy IP. Если webhook-домен проксируется через Cloudflare,
backend безопасно использует `CF-Connecting-IP`, когда ближайший недоверенный hop принадлежит
официальной сети Cloudflare; добавлять сети Cloudflare в `TRUSTED_PROXIES` не нужно.
Trust-all вариант записывается как
`0.0.0.0/0,::/0`, но он безопасен только если backend не доступен напрямую, а внешний proxy
очищает входящий `X-Forwarded-For`.

## Кеши, rate limits и worker

Обычно эти значения не требуют правки.

Настройки `BACKUP_*` управляют автоматическими бэкапами и восстановлением. Практический сценарий, mount compose-папки и проверки архивов описаны в [разделе про бэкапы](../features/backups.md).

| Переменная | Назначение |
| --- | --- |
| `WEBAPP_ME_CACHE_TTL_SECONDS` | TTL кеша `/api/me`. |
| `WEBAPP_DEVICES_CACHE_TTL_SECONDS` | TTL кеша устройств Web App. |
| `PANEL_USER_CACHE_TTL_SECONDS` | TTL кеша Remnawave `/users/{uuid}`. |
| `PANEL_DEVICES_CACHE_TTL_SECONDS` | TTL кеша устройств пользователя Remnawave. |
| `PANEL_ALL_USERS_CACHE_TTL_SECONDS` | TTL кеша полных сканов пользователей Remnawave. |
| `PANEL_ALL_USERS_PAGE_SIZE` | Размер страницы Remnawave `/users`. |
| `PANEL_ALL_USERS_PAGE_DELAY_SECONDS` | Пауза между страницами при полном скане `/users` (по умолчанию `0.1`). На крупных панелях (100k+ пользователей) это десятки секунд ожидания за синк; можно снизить или выставить `0`, если панель выдерживает более частые запросы. |
| `PANEL_API_TOTAL_TIMEOUT_SECONDS` | Общий timeout запроса к Remnawave API. |
| `PANEL_API_CONNECT_TIMEOUT_SECONDS` | Timeout получения соединения с Remnawave API. |
| `PANEL_API_SOCK_CONNECT_TIMEOUT_SECONDS` | Timeout TCP/TLS-подключения к Remnawave API. |
| `PANEL_API_SOCK_READ_TIMEOUT_SECONDS` | Timeout ожидания данных ответа Remnawave API. |
| `ADMIN_PANEL_STATS_CACHE_TTL_SECONDS` | TTL статистики Remnawave в админке. |
| `ADMIN_DB_STATS_CACHE_TTL_SECONDS` | TTL дорогих DB-агрегатов админки. |
| `ADMIN_USERS_LIST_CACHE_TTL_SECONDS` | TTL списка пользователей админки. |
| `ADMIN_BROADCAST_AUDIENCE_COUNTS_CACHE_TTL_SECONDS` | TTL счетчиков целевых групп рассылки в админке. |
| `PROFILE_SYNC_CACHE_TTL_SECONDS` | Минимальная пауза между sync Telegram-профиля пользователя. |
| `PANEL_SYNC_LIFETIME_TRAFFIC_MIN_INTERVAL_SECONDS` | Минимальная пауза записи lifetime-трафика. |
| `PANEL_SYNC_LIFETIME_TRAFFIC_MIN_DELTA_BYTES` | Дельта lifetime-трафика для более ранней записи. |
| `WEBAPP_RATE_LIMIT_TTL_SECONDS` | Окно Web App rate limit. |
| `WEBAPP_RATE_LIMIT_MAX_REQUESTS` | Количество запросов в окне rate limit. |
| `TELEGRAM_DROP_NON_PRIVATE_UPDATES` | Отбрасывать group/channel Telegram-апдейты до DB-backed middleware. По умолчанию `True`. |
| `TELEGRAM_ANTIFLOOD_ENABLED` | Включает мягкие per-user/per-chat лимиты для экстремального Telegram-флуда. По умолчанию `True`. |
| `TELEGRAM_ANTIFLOOD_WINDOW_SECONDS` | Окно лимитов Telegram антифлуда. По умолчанию `60`. |
| `TELEGRAM_ANTIFLOOD_MAX_UPDATES_PER_WINDOW` | Глобальный лимит Telegram-апдейтов на источник за окно. По умолчанию `180`; `0` отключает лимит. |
| `TELEGRAM_ANTIFLOOD_MESSAGE_MAX_PER_WINDOW` | Лимит Telegram messages на источник за окно. По умолчанию `120`; `0` отключает лимит. |
| `TELEGRAM_ANTIFLOOD_CALLBACK_MAX_PER_WINDOW` | Лимит callback query на источник за окно. По умолчанию `240`; `0` отключает лимит. |
| `TELEGRAM_ANTIFLOOD_INLINE_MAX_PER_WINDOW` | Лимит inline query на источник за окно. По умолчанию `60`; `0` отключает лимит. |
| `TELEGRAM_ANTIFLOOD_START_MAX_PER_WINDOW` | Лимит `/start` на источник за окно. По умолчанию `30`; `0` отключает лимит. |
| `TELEGRAM_ANTIFLOOD_EXPENSIVE_CALLBACK_MAX_PER_WINDOW` | Лимит платежных, trial, promo и account-changing callback за окно. По умолчанию `60`; `0` отключает лимит. |
| `TELEGRAM_ACTION_COOLDOWN_ENABLED` | Дедуплицирует точные повторы платежных и trial callback от того же пользователя. По умолчанию `True`. |
| `TELEGRAM_PAYMENT_CALLBACK_COOLDOWN_SECONDS` | Cooldown точного повтора платежного callback. По умолчанию `20`; `0` отключает cooldown. |
| `TELEGRAM_TRIAL_CALLBACK_COOLDOWN_SECONDS` | Cooldown точного повтора trial callback. По умолчанию `30`; `0` отключает cooldown. |
| `WEBHOOK_QUEUE_NAME` | Redis queue для тяжелой обработки webhook. |
| `WEBHOOK_QUEUE_CONCURRENCY` | Количество worker consumers для webhook queue. |
| `WEBHOOK_QUEUE_MAX_ATTEMPTS` | Максимальное число попыток обработки webhook до переноса в dead-letter queue. По умолчанию `5`. |
| `WEBHOOK_QUEUE_RETRY_BASE_SECONDS` | Начальная задержка экспоненциального retry webhook. По умолчанию `1`. |
| `WEBHOOK_QUEUE_RETRY_MAX_SECONDS` | Максимальная задержка между retry webhook. По умолчанию `30`. |
| `WORKER_PANEL_SYNC_INTERVAL_SECONDS` | Интервал фоновой синхронизации с панелью. |
| `TARIFF_WORKER_LOCK_TTL_SECONDS` | TTL Redis lock для tariff worker. |
| `TARIFF_WORKER_TICK_SECONDS` | Интервал tariff worker. |
| `TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD` | Порог активных подписок для bulk fetch пользователей панели. |
| `BACKUP_ENABLED` | Включает периодические бэкапы в worker-контейнере. По умолчанию `False`. |
| `BACKUP_INTERVAL_SECONDS` | Интервал между бэкапами. По умолчанию `3600`; запуск выравнивается на границу часа: 12:00, 13:00 и т.д. |
| `BACKUP_CHAT_ID` | Telegram chat ID для архивов. Если пусто, используется `LOG_CHAT_ID`. |
| `BACKUP_THREAD_ID` | Topic/thread ID для архивов. Если пусто, используется `LOG_THREAD_ID`. |
| `BACKUP_DIR` | Локальная папка архивов внутри контейнера. По умолчанию `data/backups` в volume `shop-data`. |
| `BACKUP_LOCAL_RETENTION` | Сколько локальных ZIP-архивов хранить после отправки. По умолчанию `100`. |
| `BACKUP_POSTGRES_DUMP_ENABLED` | Добавлять в архив `pg_dump` базы PostgreSQL. |
| `BACKUP_PG_DUMP_PATH` | Путь к `pg_dump` внутри worker-контейнера. |
| `BACKUP_PG_DUMP_TIMEOUT_SECONDS` | Таймаут выполнения `pg_dump`. |
| `BACKUP_PG_RESTORE_PATH` | Путь к `pg_restore` внутри backend-контейнера для восстановления из админки. |
| `BACKUP_PG_RESTORE_TIMEOUT_SECONDS` | Таймаут выполнения `pg_restore`. |
| `BACKUP_COMPOSE_ENABLED` | Добавлять snapshot compose-каталога в архив. Если mount отсутствует, бэкап БД не падает. |
| `BACKUP_COMPOSE_SOURCE_DIR` | Путь внутри контейнера к compose-каталогу. В стандартном compose это `/app/compose-source`. |
| `BACKUP_COMPOSE_RESTORE_DIR` | Куда восстанавливать compose-файлы. Если пусто, используется `BACKUP_COMPOSE_SOURCE_DIR`. |
| `BACKUP_COMPOSE_EXCLUDE_DIRS` | Имена директорий, которые не попадают в compose snapshot. |
| `COMPOSE_BACKUP_SOURCE` | Host-путь, который Docker Compose монтирует как `/app/compose-source`. По умолчанию текущая папка compose-файла. |
| `COMPOSE_RESTORE_MODE` | Режим mount для backend: `rw` позволяет восстанавливать compose-папку из админки, `ro` оставляет только чтение. |

## Общие настройки

Эти поля доступны в админке: **Система -> Настройки**.

| Переменная | Назначение |
| --- | --- |
| `DEFAULT_LANGUAGE` | Язык по умолчанию: `ru` или `en`. |
| `DEFAULT_CURRENCY_SYMBOL` | Символ/код валюты в интерфейсе. |
| `SUPPORT_LINK` | Внешняя ссылка поддержки. |
| `SERVER_STATUS_URL` | Страница статуса сервиса. |
| `PRIVACY_POLICY_URL` | Политика конфиденциальности. |
| `USER_AGREEMENT_URL` | Пользовательское соглашение. |
| `REQUIRED_CHANNEL_ID` | ID обязательного Telegram-канала. Используется для проверки подписки и автоматического получения ссылки кнопки, если бот видит канал. |
| `REQUIRED_CHANNEL_LINK` | Необязательная запасная ссылка на обязательный канал (`@username` или invite-link), если ссылку нельзя получить по ID. |
| `START_COMMAND_DESCRIPTION` | Описание `/start` для меню Telegram. |
| `DISABLE_WELCOME_MESSAGE` | Отключить приветствие на `/start`. |
| `REGISTRATION_INVITE_ONLY_ENABLED` | По умолчанию `False`. Если включено, новые публичные регистрации разрешены только по валидной реферальной ссылке; существующие пользователи продолжают входить через Telegram, Web App, email-код, magic-link или пароль. |

## Remnawave

Эти поля стоит держать в `.env` как базовую конфигурацию интеграции с панелью. Они также доступны в админке, чтобы можно было быстро поправить доступы или временно переопределить их без ручного редактирования файла и перезапуска.

| Переменная | Назначение |
| --- | --- |
| `PANEL_API_URL` | URL API панели, например `https://panel.example.com/api`. |
| `PANEL_API_KEY` | API-ключ панели. |
| `PANEL_API_COOKIE` | Необязательный Cookie header для панелей, защищённых `eGamesAPI/remnawave-reverse-proxy`. |
| `APP_RUNTIME_MODE` | Профиль запуска: `production`, `development`, `staging`, `test`. |
| `PANEL_WRITE_MODE` | `auto`, `live` или `dry_run`. В `dry_run` приложение читает живую Remnawave Panel, но мутации пользователей только валидируются и логируются. `auto` включает dry-run для `development`/`test`, а в production остается live. |
| `PANEL_DRY_RUN_VALIDATE_REMOTE` | При dry-run проверять ссылки на panel users/internal squads через live `GET`. |
| `PANEL_DRY_RUN_SYNTHETIC_CREATE` | При dry-run возвращать синтетического panel user на попытку `POST /users`, чтобы dev-цепочки могли завершиться в локальной БД. |
| `PANEL_WEBHOOK_SECRET` | Секрет проверки Remnawave webhook. Задайте его в Remnawave Panel и вставьте то же значение сюда или в админку. |
| `USER_SQUAD_UUIDS` | Internal Squads по умолчанию для legacy-режима без JSON-каталога. |
| `USER_EXTERNAL_SQUAD_UUID` | Необязательный External Squad. |
| `USER_TRAFFIC_LIMIT_GB` | Legacy-лимит трафика пользователя. |
| `USER_TRAFFIC_STRATEGY` | Legacy-стратегия лимита трафика. |
| `USER_HWID_DEVICE_LIMIT` | Legacy-лимит HWID-устройств по умолчанию. |

В Remnawave Panel поле `WEBHOOK_URL` должно указывать на публичный Minishop webhook: `WEBHOOK_BASE_URL` + `/webhook/panel`. Если публичный домен приложения `https://app.example.com`, итоговый адрес будет `https://app.example.com/webhook/panel`.

## Веб-приложение, внешний вид и Telegram Login

Часть внешнего вида (`WEBAPP_PRIMARY_COLOR`, `WEBAPP_LOGO_*`, `WEBAPP_FAVICON_*`) сохранена для совместимости, но env-значения этих полей игнорируются при загрузке. Настраивайте их в **Админка -> Внешний вид**.

Практическая настройка Mini App вынесена в [веб-приложение](../features/web-app.md), а вход через Telegram - в [Telegram-авторизацию](../features/telegram-auth.md).

| Переменная | Где менять | Назначение |
| --- | --- | --- |
| `WEBAPP_ENABLED` | `.env` / админка | Включает Web App. Если `False`, пользовательский Web App и админка недоступны до включения через `.env` и рестарта. |
| `SUBSCRIPTION_MINI_APP_URL` | `.env` / админка | Публичный HTTPS URL Mini App/frontend, например `https://app.domain.com/`. Используется в Telegram-кнопках, реферальных ссылках, входе по email и настройках BotFather Mini App. Не указывайте здесь `/api` или webhook-пути. |
| `WEBAPP_API_BASE_URL` | `.env` | Browser-visible API base для `/bootstrap`, `/me`, платежей и админки. Оставьте `/api`; полный backend URL в браузер не передается. |
| `WEBAPP_BACKEND_UPSTREAM` | frontend env | Server-side upstream frontend nginx для `/api`, `/auth`, `/open-app` и Web App assets. |
| `WEBAPP_BACKEND_UPSTREAM_HOST` | frontend env | Host/SNI override для HTTPS upstream. |
| `MINISHOP_EDGE_TOKEN` | `.env` / frontend env | Server-side shared secret для protected upstream. Backend требует header только на WebApp API plane `8081`; frontend nginx добавляет header к upstream-запросам. |
| `MINISHOP_EDGE_TOKEN_HEADER` | `.env` / frontend env | Header edge-token, по умолчанию `X-Minishop-Edge-Token`. |
| `SUBSCRIPTION_GUIDES_ENABLED` | `.env` / админка | Включает встроенные инструкции установки в Web App. По умолчанию `True`; если конфиг недоступен или невалиден, кнопка подключения открывает обычную финальную ссылку подписки. |
| `SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED` | `.env` / админка | Включает открытие Mini App `/install` из кнопок бота и показ публичной ссылки инструкции `/s/<token>`. По умолчанию `True`; если выключить, бот ведет на финальную Remnawave Subscription Page. |
| `SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED` | `.env` / админка | Читать Remnawave Subscription Page config из панели для встроенных инструкций. По умолчанию `True`; для активной подписки сначала используется resolved config по `shortUuid`, включая настройки External Squad, затем default config панели. |
| `SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED` | `.env` / админка | Включает использование JSON из поля `SUBSCRIPTION_PAGE_CONFIG_JSON` вместо конфига панели. По умолчанию `False`. |
| `SUBSCRIPTION_PAGE_CONFIG_PATH` | `.env` / админка | Резервный путь к локальному JSON-конфигу Remnawave Subscription Page v1, если конфиг панели выключен или недоступен. По умолчанию `data/subpage-config/multiapp.json`; файл не создается автоматически. |
| `SUBSCRIPTION_PAGE_CONFIG_JSON` | Админка | Опциональное JSON-переопределение Remnawave Subscription Page v1. Применяется только при включенном `SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED`; backend валидирует JSON при сохранении. |
| `WEBAPP_TITLE` | Админка | Заголовок Web App. |
| `WEBAPP_THEMES_DIR` | `.env` | Каталог кастомных тем. |
| `WEBAPP_DEFAULT_THEME` | `.env` / админка | Ключ темы по умолчанию. |
| `WEBAPP_SESSION_TTL_SECONDS` | `.env` | Время жизни Web App-сессии. |
| `WEBAPP_AUTH_MAX_AGE_SECONDS` | `.env` | Максимальный возраст Telegram Mini Apps `initData`. |
| `WEBAPP_LOGIN_TOKEN_TTL_SECONDS` | `.env` | TTL ссылки внешнего логина. |
| `TELEGRAM_OAUTH_CLIENT_ID` | `.env` | Идентификатор клиента Telegram OAuth / OpenID Connect. Если пусто, берется bot ID из `BOT_TOKEN`. |
| `TELEGRAM_OAUTH_CLIENT_SECRET` | `.env` | Секрет клиента Telegram OAuth / OpenID Connect. |
| `TELEGRAM_OAUTH_REQUEST_ACCESS` | `.env` | Дополнительные разрешения, например `write`. |
| `WEBAPP_PRIMARY_COLOR` | Админка | Устаревшее env-поле, игнорируется. |
| `WEBAPP_LOGO_URL` | Админка | Устаревшее env-поле, игнорируется. |
| `WEBAPP_FAVICON_USE_CUSTOM` | Админка | Устаревшее env-поле, игнорируется. |
| `WEBAPP_FAVICON_URL` | Админка | Устаревшее env-поле, игнорируется. |
| `WEBAPP_LOGO_FAVICON_URL` | Админка | Устаревшее env-поле, игнорируется. |

Инструкции установки совместимы с Remnawave Subscription Page v1 config: `version`, `locales`, `brandingSettings`, `uiConfig`, `baseSettings`, `baseTranslations`, `svgLibrary` и `platforms`. Текстовые поля рендерятся как текст, а SVG из `svgLibrary` проходит санитарную проверку перед отдачей в Web App.

## SMTP и вход по email

Вход по email появляется только если заполнены `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` и `SMTP_FROM_EMAIL`.

Практический сценарий настройки SMTP, magic link и парольного входа описан в [разделе входа по email](../features/email-login.md).

| Переменная | Назначение |
| --- | --- |
| `SMTP_HOST` | SMTP host. |
| `SMTP_PORT` | Основной SMTP port. |
| `SMTP_FALLBACK_PORTS` | Резервные порты через запятую. |
| `SMTP_TIMEOUT_SECONDS` | Таймаут SMTP-попытки. |
| `SMTP_USERNAME` | SMTP login. |
| `SMTP_PASSWORD` | SMTP-пароль или API-ключ. |
| `SMTP_FROM_EMAIL` | Подтвержденный адрес отправителя. |
| `SMTP_FROM_NAME` | Имя отправителя. |
| `SMTP_STARTTLS` | Использовать STARTTLS. |
| `SMTP_USE_SSL` | Использовать SSL-wrapper. |
| `EMAIL_CODE_TTL_SECONDS` | TTL email-кода. |
| `EMAIL_CODE_RESEND_SECONDS` | Пауза перед повторной отправкой. |
| `EMAIL_CODE_MAX_ATTEMPTS` | Максимум попыток ввода кода. |
| `BRUTE_FORCE_MAX_FAILURES` | Количество ошибок до временной блокировки. |
| `BRUTE_FORCE_WINDOW_SECONDS` | Окно учета ошибок. |
| `BRUTE_FORCE_LOCK_SECONDS` | Длительность блокировки. |

## Платежи

Все включатели, секреты и настройки отображения провайдеров доступны в админке: **Система -> Настройки -> Платежи**.

| Переменная | Назначение |
| --- | --- |
| `PAYMENT_METHODS_ORDER` | Порядок кнопок оплаты: `severpay,wata,freekassa,platega,yookassa,stars,cryptopay,heleket,paykilla,lava,pally,cloudpayments,stripe`. |
| `SUBSCRIPTION_PURCHASE_DESCRIPTION_ENABLED` | Показывать описание подписки перед выбором срока. |
| `SUBSCRIPTION_PURCHASE_DESCRIPTION_RU` / `SUBSCRIPTION_PURCHASE_DESCRIPTION_EN` | Локализованное описание подписки. |
| `PAYMENT_REQUEST_TIMEOUT_SECONDS` | Общий таймаут одного API-запроса к платёжному провайдеру, в секундах. По умолчанию `20`. |
| `PAYMENT_<METHOD>_WEBAPP_LABEL_RU` / `PAYMENT_<METHOD>_WEBAPP_LABEL_EN` | Текст кнопки провайдера в Web App. |
| `PAYMENT_<METHOD>_WEBAPP_ICON` | Lucide-иконка кнопки в Web App. |
| `PAYMENT_<METHOD>_TELEGRAM_LABEL_RU` / `PAYMENT_<METHOD>_TELEGRAM_LABEL_EN` | Текст кнопки в Telegram. |
| `PAYMENT_<METHOD>_TELEGRAM_EMOJI` | Emoji кнопки в Telegram. |
| `STARS_ENABLED` | Включает Telegram Stars. |
| `YOOKASSA_ENABLED` | Включает YooKassa. |
| `FREEKASSA_ENABLED` | Включает FreeKassa. |
| `PLATEGA_ENABLED` | Включает Platega. |
| `PLATEGA_SBP_ENABLED` / `PLATEGA_CRYPTO_ENABLED` | Отдельные кнопки СБП/крипто Platega. |
| `SEVERPAY_ENABLED` | Включает SeverPay. |
| `WATA_ENABLED` | Включает Wata. |
| `CRYPTOPAY_ENABLED` | Включает CryptoPay. |
| `HELEKET_ENABLED` | Включает Heleket. |
| `PAYKILLA_ENABLED` | Включает PayKilla. |
| `LAVA_ENABLED` | Включает LAVA. |
| `PALLY_ENABLED` | Включает Pally / PayPalych. |
| `CLOUDPAYMENTS_ENABLED` | Включает CloudPayments. |
| `OVERPAY_ENABLED` | Включает Overpay. |

Конкретные ключи отображения:

```text
PAYMENT_YOOKASSA_WEBAPP_LABEL_RU
PAYMENT_YOOKASSA_WEBAPP_LABEL_EN
PAYMENT_YOOKASSA_WEBAPP_ICON
PAYMENT_YOOKASSA_TELEGRAM_LABEL_RU
PAYMENT_YOOKASSA_TELEGRAM_LABEL_EN
PAYMENT_YOOKASSA_TELEGRAM_EMOJI
PAYMENT_FREEKASSA_WEBAPP_LABEL_RU
PAYMENT_FREEKASSA_WEBAPP_LABEL_EN
PAYMENT_FREEKASSA_WEBAPP_ICON
PAYMENT_FREEKASSA_TELEGRAM_LABEL_RU
PAYMENT_FREEKASSA_TELEGRAM_LABEL_EN
PAYMENT_FREEKASSA_TELEGRAM_EMOJI
PAYMENT_PLATEGA_SBP_WEBAPP_LABEL_RU
PAYMENT_PLATEGA_SBP_WEBAPP_LABEL_EN
PAYMENT_PLATEGA_SBP_WEBAPP_ICON
PAYMENT_PLATEGA_SBP_TELEGRAM_LABEL_RU
PAYMENT_PLATEGA_SBP_TELEGRAM_LABEL_EN
PAYMENT_PLATEGA_SBP_TELEGRAM_EMOJI
PAYMENT_PLATEGA_CRYPTO_WEBAPP_LABEL_RU
PAYMENT_PLATEGA_CRYPTO_WEBAPP_LABEL_EN
PAYMENT_PLATEGA_CRYPTO_WEBAPP_ICON
PAYMENT_PLATEGA_CRYPTO_TELEGRAM_LABEL_RU
PAYMENT_PLATEGA_CRYPTO_TELEGRAM_LABEL_EN
PAYMENT_PLATEGA_CRYPTO_TELEGRAM_EMOJI
PAYMENT_SEVERPAY_WEBAPP_LABEL_RU
PAYMENT_SEVERPAY_WEBAPP_LABEL_EN
PAYMENT_SEVERPAY_WEBAPP_ICON
PAYMENT_SEVERPAY_TELEGRAM_LABEL_RU
PAYMENT_SEVERPAY_TELEGRAM_LABEL_EN
PAYMENT_SEVERPAY_TELEGRAM_EMOJI
PAYMENT_WATA_WEBAPP_LABEL_RU
PAYMENT_WATA_WEBAPP_LABEL_EN
PAYMENT_WATA_WEBAPP_ICON
PAYMENT_WATA_TELEGRAM_LABEL_RU
PAYMENT_WATA_TELEGRAM_LABEL_EN
PAYMENT_WATA_TELEGRAM_EMOJI
PAYMENT_STARS_WEBAPP_LABEL_RU
PAYMENT_STARS_WEBAPP_LABEL_EN
PAYMENT_STARS_WEBAPP_ICON
PAYMENT_STARS_TELEGRAM_LABEL_RU
PAYMENT_STARS_TELEGRAM_LABEL_EN
PAYMENT_STARS_TELEGRAM_EMOJI
PAYMENT_CRYPTOPAY_WEBAPP_LABEL_RU
PAYMENT_CRYPTOPAY_WEBAPP_LABEL_EN
PAYMENT_CRYPTOPAY_WEBAPP_ICON
PAYMENT_CRYPTOPAY_TELEGRAM_LABEL_RU
PAYMENT_CRYPTOPAY_TELEGRAM_LABEL_EN
PAYMENT_CRYPTOPAY_TELEGRAM_EMOJI
PAYMENT_HELEKET_WEBAPP_LABEL_RU
PAYMENT_HELEKET_WEBAPP_LABEL_EN
PAYMENT_HELEKET_WEBAPP_ICON
PAYMENT_HELEKET_TELEGRAM_LABEL_RU
PAYMENT_HELEKET_TELEGRAM_LABEL_EN
PAYMENT_HELEKET_TELEGRAM_EMOJI
PAYMENT_PAYKILLA_WEBAPP_LABEL_RU
PAYMENT_PAYKILLA_WEBAPP_LABEL_EN
PAYMENT_PAYKILLA_WEBAPP_ICON
PAYMENT_PAYKILLA_TELEGRAM_LABEL_RU
PAYMENT_PAYKILLA_TELEGRAM_LABEL_EN
PAYMENT_PAYKILLA_TELEGRAM_EMOJI
PAYMENT_LAVA_WEBAPP_LABEL_RU
PAYMENT_LAVA_WEBAPP_LABEL_EN
PAYMENT_LAVA_WEBAPP_ICON
PAYMENT_LAVA_TELEGRAM_LABEL_RU
PAYMENT_LAVA_TELEGRAM_LABEL_EN
PAYMENT_LAVA_TELEGRAM_EMOJI
PAYMENT_PALLY_WEBAPP_LABEL_RU
PAYMENT_PALLY_WEBAPP_LABEL_EN
PAYMENT_PALLY_WEBAPP_ICON
PAYMENT_PALLY_TELEGRAM_LABEL_RU
PAYMENT_PALLY_TELEGRAM_LABEL_EN
PAYMENT_PALLY_TELEGRAM_EMOJI
PAYMENT_CLOUDPAYMENTS_WEBAPP_LABEL_RU
PAYMENT_CLOUDPAYMENTS_WEBAPP_LABEL_EN
PAYMENT_CLOUDPAYMENTS_WEBAPP_ICON
PAYMENT_CLOUDPAYMENTS_TELEGRAM_LABEL_RU
PAYMENT_CLOUDPAYMENTS_TELEGRAM_LABEL_EN
PAYMENT_CLOUDPAYMENTS_TELEGRAM_EMOJI
PAYMENT_OVERPAY_WEBAPP_LABEL_RU
PAYMENT_OVERPAY_WEBAPP_LABEL_EN
PAYMENT_OVERPAY_WEBAPP_ICON
PAYMENT_OVERPAY_TELEGRAM_LABEL_RU
PAYMENT_OVERPAY_TELEGRAM_LABEL_EN
PAYMENT_OVERPAY_TELEGRAM_EMOJI
PAYMENT_STRIPE_WEBAPP_LABEL_RU
PAYMENT_STRIPE_WEBAPP_LABEL_EN
PAYMENT_STRIPE_WEBAPP_ICON
PAYMENT_STRIPE_TELEGRAM_LABEL_RU
PAYMENT_STRIPE_TELEGRAM_LABEL_EN
PAYMENT_STRIPE_TELEGRAM_EMOJI
```

### YooKassa

| Переменная | Назначение |
| --- | --- |
| `YOOKASSA_SHOP_ID` | ID магазина. |
| `YOOKASSA_SECRET_KEY` | Секретный ключ. |
| `YOOKASSA_RETURN_URL` | URL возврата после оплаты. |
| `YOOKASSA_DEFAULT_RECEIPT_EMAIL` | Email для чеков по умолчанию. |
| `YOOKASSA_VAT_CODE` | Код НДС. |
| `YOOKASSA_AUTOPAYMENTS_ENABLED` | Автопродление через сохраненные способы оплаты. |
| `YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING` | Требовать привязку карты. |

### FreeKassa

| Переменная | Назначение |
| --- | --- |
| `FREEKASSA_MERCHANT_ID` | ID магазина. |
| `FREEKASSA_API_KEY` | API-ключ. |
| `FREEKASSA_SECOND_SECRET` | Секрет уведомлений. |
| `FREEKASSA_PAYMENT_IP` | Публичный IP сервера для запроса оплаты. |
| `FREEKASSA_PAYMENT_METHOD_ID` | ID метода оплаты. |
| `FREEKASSA_TRUSTED_IPS` | Список доверенных IP webhook-источников. |

### Platega

| Переменная | Назначение |
| --- | --- |
| `PLATEGA_BASE_URL` | Базовый URL API. |
| `PLATEGA_MERCHANT_ID` | ID мерчанта. |
| `PLATEGA_SECRET` | Секрет API. |
| `PLATEGA_PAYMENT_METHOD` | Устаревший/резервный ID метода оплаты. |
| `PLATEGA_SBP_METHOD` | ID метода оплаты для СБП. |
| `PLATEGA_CRYPTO_METHOD` | ID метода оплаты для крипто. |
| `PLATEGA_RETURN_URL` | URL успешного возврата. |
| `PLATEGA_FAILED_URL` | URL неуспешного возврата. |

### SeverPay

| Переменная | Назначение |
| --- | --- |
| `SEVERPAY_BASE_URL` | Базовый URL API. |
| `SEVERPAY_MID` | Merchant MID. |
| `SEVERPAY_TOKEN` | API-токен или секрет. |
| `SEVERPAY_RETURN_URL` | URL возврата. |
| `SEVERPAY_LIFETIME_MINUTES` | Время жизни платежной ссылки. |

### Wata

| Переменная | Назначение |
| --- | --- |
| `WATA_BASE_URL` | Базовый URL API. |
| `WATA_API_TOKEN` | Bearer-токен. |
| `WATA_RETURN_URL` | URL успешного возврата. |
| `WATA_FAILED_URL` | URL неуспешного возврата. |
| `WATA_LINK_TTL_MINUTES` | TTL платежной ссылки в минутах (по умолчанию 15, минимум 15, максимум 43200). |
| `WATA_WEBHOOK_VERIFY_SIGNATURE` | Проверять `X-Signature`. |
| `WATA_PUBLIC_KEY` | Закешированный публичный ключ; если пусто, загружается из API. |
| `WATA_TRUSTED_IPS` | Список доверенных IP webhook-источников. |

### CryptoPay

| Переменная | Назначение |
| --- | --- |
| `CRYPTOPAY_TOKEN` | API-токен CryptoPay. |
| `CRYPTOPAY_NETWORK` | `mainnet` или `testnet`. |
| `CRYPTOPAY_CURRENCY_TYPE` | `fiat` или `crypto`. |
| `CRYPTOPAY_ASSET` | Актив, например `RUB`, `USDT`, `BTC`. |

### Heleket

| Переменная | Назначение |
| --- | --- |
| `HELEKET_BASE_URL` | Базовый URL API. |
| `HELEKET_MERCHANT_ID` | UUID мерчанта. |
| `HELEKET_API_KEY` | Ключ платежного API. |
| `HELEKET_CURRENCY` | Валюта инвойса. |
| `HELEKET_TO_CURRENCY` | Целевая криптовалюта для конвертации. |
| `HELEKET_NETWORK` | Сеть, например `tron`, `bsc`, `eth`. |
| `HELEKET_RETURN_URL` | URL после отмены/истечения. |
| `HELEKET_SUCCESS_URL` | URL после успешной оплаты. |
| `HELEKET_LIFETIME_SECONDS` | TTL инвойса: 300..43200. |
| `HELEKET_VERIFY_WEBHOOK_SIGNATURE` | Проверять подпись webhook. |
| `HELEKET_TRUSTED_IPS` | Список доверенных IP webhook-источников. |

### PayKilla

Для приема оплат нужен API key типа **HMAC** с правом **INVOICE**. Право **WITHDRAWAL** для оплаты подписок не требуется; включайте его только для отдельной интеграции выплат.

Webhook настраивается в PayKilla Dashboard: **Settings -> Webhooks**. Укажите `WEBHOOK_BASE_URL` + `/webhook/paykilla`, например `https://bot.example.com/webhook/paykilla`. Включите события `INVOICE_PAID` и `INVOICE_EXPIRED` как минимум. Рекомендуемый набор галочек: `INVOICE_PAID`, `PAYMENT_COMPLETED`, `PAYMENT_FAILED`, `PAYMENT_OVERPAID`, `PAYMENT_UNDERPAID`, `PAYMENT_PARTIAL`, `INVOICE_EXPIRED`, `COMPLIANCE_FAILED`. Если хотите видеть промежуточные статусы в логах PayKilla, дополнительно включите `INVOICE_CREATED`, `PAYMENT_PENDING`, `TRANSACTION_CONFIRMED` и `TRANSACTION_FINAL`.

| Переменная | Назначение |
| --- | --- |
| `PAYKILLA_BASE_URL` | Базовый URL API, по умолчанию `https://account-api.paykilla.com`. |
| `PAYKILLA_WIDGET_URL` | URL hosted checkout, по умолчанию `https://gopay.paykilla.com`. |
| `PAYKILLA_API_KEY` / `PAYKILLA_V2_API_KEY` | Public HMAC key с правом `INVOICE`. |
| `PAYKILLA_SECRET_KEY` / `PAYKILLA_V2_SECRET_KEY` | Secret HMAC key для подписи API-запросов и проверки webhook. |
| `PAYKILLA_CURRENCY` | Резервная валюта инвойса PayKilla для платежей, чья валюта тарифа не входит в `PAYKILLA_INVOICE_CURRENCIES`. По умолчанию `USD`. |
| `PAYKILLA_INVOICE_CURRENCIES` | Валюты, которые PayKilla принимает в поле `currency` при создании invoice. По умолчанию `USD,EUR`. Если тариф в `RUB`, Minishop конвертирует сумму в `PAYKILLA_CURRENCY`. |
| `PAYKILLA_PAYMENT_CURRENCIES` | Crypto tickers для оплаты. По умолчанию `USDTTRC,BTC,ETH,USDTBSC,USDTTON`; оставляйте в списке только тикеры, доступные в PayKilla Dashboard для merchant account. |
| `PAYKILLA_SUPPORTED_CURRENCIES` | Валюты тарифов/платежей, которым разрешено использовать PayKilla в этом магазине. |
| `PAYKILLA_INVOICE_TYPE` | Необязательный override: `FIAT_BASED`, `FIXED_AMOUNT` или `OPEN_AMOUNT`. |
| `PAYKILLA_LIFETIME_SECONDS` | TTL инвойса, отправляется как `expiredAt`. |
| `PAYKILLA_RECV_WINDOW_MS` | `recvWindow` для подписанных API-запросов. |
| `PAYKILLA_USER_PAYS_SERVICE_FEE` | `true`, если пользователь оплачивает service fee. |
| `PAYKILLA_USER_PAYS_NETWORK_FEE` | `true`, если пользователь оплачивает network fee. |
| `PAYKILLA_EXCHANGE_RATE_URL` | Бесплатный no-key endpoint курса для конвертации валюты тарифа в валюту инвойса. По умолчанию `https://open.er-api.com/v6/latest/{source}`. Поддерживает placeholders `{source}` и `{target}`. |
| `PAYKILLA_EXCHANGE_RATE_CACHE_SECONDS` | Кэш курса и PayKilla currency limits в секундах. По умолчанию `3600`. |
| `PAYKILLA_MIN_PAYMENT_AMOUNT` | Минимальная сумма платежа через PayKilla. По умолчанию `10`. |
| `PAYKILLA_MIN_PAYMENT_CURRENCY` | Валюта для `PAYKILLA_MIN_PAYMENT_AMOUNT`. По умолчанию `USD`; для рублевых тарифов порог конвертируется по `PAYKILLA_EXCHANGE_RATE_URL`. |
| `PAYKILLA_VERIFY_WEBHOOK_SIGNATURE` | Проверять `X-API-SIGN` по raw body webhook. |
| `PAYKILLA_WEBHOOK_URL` | Точный публичный webhook URL для проверки подписи, если он отличается от `WEBHOOK_BASE_URL` + `/webhook/paykilla`. |
| `PAYKILLA_TRUSTED_IPS` | Необязательный список доверенных IP webhook-источников. |

### LAVA

Счета LAVA Business выставляются только в рублях. Исходящие запросы подписываются HMAC-SHA256 от raw body (заголовок `Signature`), webhook проверяется по заголовку `Authorization`.

| Переменная | Назначение |
| --- | --- |
| `LAVA_BASE_URL` | Базовый URL API, по умолчанию `https://api.lava.ru`. |
| `LAVA_SHOP_ID` | ID магазина в LAVA Business. |
| `LAVA_SECRET_KEY` | Секретный ключ магазина для подписи исходящих API-запросов. |
| `LAVA_WEBHOOK_SECRET` | Дополнительный ключ магазина для проверки подписи webhook; если пусто, используется `LAVA_SECRET_KEY`. |
| `LAVA_RETURN_URL` | URL возврата после оплаты (`successUrl`/`failUrl`). |
| `LAVA_LIFETIME_MINUTES` | Время жизни счета в минутах: 1..7200. |
| `LAVA_INCLUDE_SERVICES` | Способы оплаты на странице счета через запятую, например `card,sbp`. |

### Pally

Pally / PayPalych создает счета через `POST /api/v1/bill/create`. Запросы авторизуются Bearer-токеном, postback приходит как `application/x-www-form-urlencoded` и проверяется по `SignatureValue = strtoupper(md5(OutSum:InvId:token))`.

| Переменная | Назначение |
| --- | --- |
| `PALLY_BASE_URL` | Базовый URL API, по умолчанию `https://pally.info/api/v1`. Старый домен `https://pal24.pro/api/v1` можно указать вручную, если он используется в кабинете. |
| `PALLY_API_TOKEN` | Bearer-токен из раздела API-интеграций Pally. |
| `PALLY_SIGNATURE_TOKEN` | Токен для проверки подписи postback; если пусто, используется `PALLY_API_TOKEN`. |
| `PALLY_SHOP_ID` | ID магазина Pally. Без него Result URL, Success URL и Fail URL у счета не работают. |
| `PALLY_RETURN_URL` | URL ссылки "Вернуться в магазин" на платежной странице. |
| `PALLY_SUCCESS_URL` | URL успешного возврата после оплаты. |
| `PALLY_FAIL_URL` | URL возврата после неуспешной оплаты. |
| `PALLY_TTL_SECONDS` | Время жизни счета в секундах. |
| `PALLY_PAYER_PAYS_COMMISSION` | Передает `payer_pays_commission=1`, если комиссию должен платить покупатель. |
| `PALLY_PAYMENT_METHOD` | Необязательный предвыбор способа оплаты: `BANK_CARD` или `SBP`. |
| `PALLY_LOCALE` | Локаль платежной формы: `ru` или `en`; если пусто, бот пробует передать язык пользователя. |
| `PALLY_NAME` | Название ссылки на платежной форме. |

### CloudPayments

CloudPayments принимает оплату картами через Orders API. Исходящие запросы авторизуются HTTP Basic auth (`CLOUDPAYMENTS_PUBLIC_ID`/`CLOUDPAYMENTS_API_SECRET`); уведомления Pay/Fail подписываются HMAC-SHA256 (base64) в заголовке `Content-HMAC`.

| Переменная | Назначение |
| --- | --- |
| `CLOUDPAYMENTS_BASE_URL` | Базовый URL API, по умолчанию `https://api.cloudpayments.ru`. |
| `CLOUDPAYMENTS_PUBLIC_ID` | Public ID из кабинета CloudPayments (логин HTTP Basic auth). |
| `CLOUDPAYMENTS_API_SECRET` | API Secret из кабинета CloudPayments (пароль HTTP Basic auth и ключ проверки подписи). |
| `CLOUDPAYMENTS_RETURN_URL` | URL успешного возврата после оплаты. |
| `CLOUDPAYMENTS_FAILED_URL` | URL возврата при ошибке оплаты; если пусто, используется `CLOUDPAYMENTS_RETURN_URL`. |
| `CLOUDPAYMENTS_RECURRING_ENABLED` | Включает списания по сохранённому CloudPayments `Token` для автопродления подписок. |
| `CLOUDPAYMENTS_VERIFY_WEBHOOK_SIGNATURE` | Проверять заголовок `Content-HMAC` у уведомлений. |
| `CLOUDPAYMENTS_TRUSTED_IPS` | Необязательный список доверенных IP webhook-источников. |

### Overpay

Overpay построен на платформе BeGateway: бот создаёт hosted-checkout (payment token) и перенаправляет пользователя на `redirect_url`. Исходящие запросы авторизуются HTTP Basic auth (`OVERPAY_SHOP_ID`/`OVERPAY_SECRET_KEY`); уведомления приходят JSON POST'ом с теми же HTTP Basic-кредами. Автопродление списывает сохранённый `credit_card.token` через gateway API. Настройте notification URL: `WEBHOOK_BASE_URL` + `/webhook/overpay`.

| Переменная | Назначение |
| --- | --- |
| `OVERPAY_SHOP_ID` | Shop ID из кабинета Overpay (логин HTTP Basic auth). |
| `OVERPAY_SECRET_KEY` | Secret Key из кабинета Overpay (пароль HTTP Basic auth и проверка входящих webhook'ов). |
| `OVERPAY_CHECKOUT_URL` | Базовый URL checkout API, по умолчанию `https://checkout.overpay.io`. |
| `OVERPAY_GATEWAY_URL` | Базовый URL gateway API для списаний по токену, по умолчанию `https://gateway.overpay.io`. |
| `OVERPAY_RETURN_URL` | URL "Вернуться в магазин" на платёжной странице. |
| `OVERPAY_SUCCESS_URL` | URL успешного возврата после оплаты. |
| `OVERPAY_DECLINE_URL` | URL возврата при отклонении оплаты. |
| `OVERPAY_FAIL_URL` | URL возврата при ошибке оплаты. |
| `OVERPAY_LANGUAGE` | Язык платёжной формы (например `ru`, `en`); если пусто, бот пробует передать язык пользователя. |
| `OVERPAY_TEST_MODE` | Отправлять транзакции в песочницу Overpay. |
| `OVERPAY_RECURRING_ENABLED` | Запрашивать токен карты на checkout и списывать его для автопродления подписок. |
| `OVERPAY_VERIFY_WEBHOOK_SIGNATURE` | Требовать HTTP Basic auth (Shop ID / Secret Key) у входящих webhook'ов. |
| `OVERPAY_TRUSTED_IPS` | Необязательный список доверенных IP webhook-источников. |

### Stripe

Stripe создает hosted Checkout Sessions и подтверждает автопродление, управляемое приложением, через off-session PaymentIntents. Настройте webhook-эндпоинт: `WEBHOOK_BASE_URL` + `/webhook/stripe`.

Рекомендуемые события Stripe: `checkout.session.completed`, `checkout.session.expired`, `payment_intent.succeeded`, `payment_intent.payment_failed`, `payment_intent.canceled`.

| Переменная | Назначение |
| --- | --- |
| `STRIPE_ENABLED` | Включает Stripe. |
| `STRIPE_SECRET_KEY` | Secret API key из Stripe Dashboard. |
| `STRIPE_WEBHOOK_SECRET` | Signing secret эндпоинта (`whsec_...`) для проверки `Stripe-Signature`. |
| `STRIPE_BASE_URL` | Базовый URL API Stripe, по умолчанию `https://api.stripe.com`. |
| `STRIPE_RETURN_URL` | URL успешного возврата после Checkout; если пусто, используется ссылка на бота. |
| `STRIPE_CANCEL_URL` | URL возврата при отмене Checkout; если пусто, используется `STRIPE_RETURN_URL`. |
| `STRIPE_PAYMENT_METHOD_TYPES` | Типы способов оплаты Checkout через запятую, по умолчанию `card`. |
| `STRIPE_SUPPORTED_CURRENCIES` | Необязательный список валют отображения через запятую, разрешенных в UI. Пусто — без локального фильтра. |
| `STRIPE_RECURRING_ENABLED` | Сохраняет способы оплаты из Checkout для off-session автопродления. |
| `STRIPE_VERIFY_WEBHOOK_SIGNATURE` | Проверять `Stripe-Signature` с помощью `STRIPE_WEBHOOK_SECRET`. |
| `STRIPE_WEBHOOK_TOLERANCE_SECONDS` | Допустимое расхождение часов для подписей webhook, по умолчанию `300`. |

## Тарифы и legacy-цены

Рекомендуемый способ настройки тарифов - раздел **Система -> Тарифы** в админке. Он сохраняет JSON в `TARIFFS_CONFIG_PATH`.

Если JSON-каталог существует и проходит валидацию, цены, периоды и реферальные бонусы period-тарифов берутся из JSON. Legacy-переменные ниже используются только без JSON-каталога.

| Переменная | Назначение |
| --- | --- |
| `TARIFFS_CONFIG_PATH` | Путь к JSON-каталогу тарифов. |
| `TARIFF_TRAFFIC_WARNING_LEVELS` | Уровни предупреждений по трафику в процентах. |
| `1_MONTH_ENABLED` | Legacy-доступность периода 1 месяц без JSON-каталога. |
| `3_MONTHS_ENABLED` | Legacy-доступность периода 3 месяца без JSON-каталога. |
| `6_MONTHS_ENABLED` | Legacy-доступность периода 6 месяцев без JSON-каталога. |
| `12_MONTHS_ENABLED` | Legacy-доступность периода 12 месяцев без JSON-каталога. |
| `RUB_PRICE_1_MONTH`, `RUB_PRICE_3_MONTHS`, `RUB_PRICE_6_MONTHS`, `RUB_PRICE_12_MONTHS` | Legacy-цены RUB. Дефолты: `200`, `600`, `1200`, `2400`. |
| `STARS_PRICE_1_MONTH`, `STARS_PRICE_3_MONTHS`, `STARS_PRICE_6_MONTHS`, `STARS_PRICE_12_MONTHS` | Legacy-цены Stars. |
| `TRAFFIC_PACKAGES` | Legacy-пакеты трафика RUB, формат `10:199,50:799`. |
| `STARS_TRAFFIC_PACKAGES` | Legacy-пакеты трафика Stars. |

## Промокоды

Подробный сценарий описан в разделе [промокоды](../features/promocodes.md).

| Переменная | Назначение |
| --- | --- |
| `PROMO_DURATION_MULTIPLIER_MAX` | Максимальный множитель срока подписки для промокодов. По умолчанию `12.0`. |
| `PROMO_TRAFFIC_MULTIPLIER_MAX` | Максимальный множитель выдаваемого трафика для промокодов. По умолчанию `12.0`. |
| `MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED` | Режим совместимости импортированных Remnashop-кодов: сначала поиск в исходном регистре, затем обычная нормализация в верхний регистр. |

## Пробный период, рефералы и уведомления

Эти настройки доступны в админке.

| Переменная | Назначение |
| --- | --- |
| `TRIAL_ENABLED` | Включает пробный период. |
| `TRIAL_DURATION_DAYS` | Длительность пробного периода. |
| `TRIAL_TRAFFIC_LIMIT_GB` | Лимит трафика пробного периода. |
| `TRIAL_PREMIUM_TRAFFIC_LIMIT_GB` | Отдельный лимит premium-трафика пробного периода. `0` отключает отдельное ограничение. |
| `TRIAL_TRAFFIC_STRATEGY` | Стратегия лимита пробного периода. |
| `TRIAL_WITHOUT_TELEGRAM_ENABLED` | Разрешает активацию trial пользователям без привязанного Telegram. Disposable email домены всё равно требуют Telegram. |
| `TRIAL_SQUAD_UUIDS` | Internal Squads для trial через запятую. Если пусто, используется `USER_SQUAD_UUIDS`. |
| `TRIAL_PREMIUM_SQUAD_UUIDS` | Premium Internal Squads для trial через запятую. Если пусто, premium-доступ в trial не выдаётся. |
| `REFERRAL_ONE_BONUS_PER_REFEREE` | Если включено, реферальные бонусы за оплату начисляются только за первый успешный платёж приглашенного; повторные покупки того же пользователя не дают бонус ни ему, ни пригласившему. |
| `REFERRAL_WELCOME_BONUS_DAYS` | Приветственный бонус пришедшему по реферальной ссылке. |
| `REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED` | Разрешает начислять реферальный приветственный бонус пользователям без привязанного Telegram. Disposable email домены всё равно требуют Telegram. |
| `LEGACY_REFS` | Разрешить старые ссылки вида `/start ref_<telegram_id>`, где payload содержит Telegram/user ID пригласившего. |
| `DISPOSABLE_EMAIL_DOMAINS` | Домены одноразовой почты через запятую. Для таких email trial и реферальный welcome bonus доступны только после привязки Telegram. |
| `REFERRAL_BONUS_DAYS_1_MONTH`, `REFERRAL_BONUS_DAYS_3_MONTHS`, `REFERRAL_BONUS_DAYS_6_MONTHS`, `REFERRAL_BONUS_DAYS_12_MONTHS` | Legacy-бонусы пригласившему без JSON-каталога. В JSON-тарифах используйте `referral_bonus_days_inviter`. |
| `REFEREE_BONUS_DAYS_1_MONTH`, `REFEREE_BONUS_DAYS_3_MONTHS`, `REFEREE_BONUS_DAYS_6_MONTHS`, `REFEREE_BONUS_DAYS_12_MONTHS` | Legacy-бонусы приглашенному без JSON-каталога. В JSON-тарифах используйте `referral_bonus_days_referee`. |
| `SUBSCRIPTION_NOTIFICATIONS_ENABLED` | Включает напоминания о подписке. |
| `SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED` | Дублирует пользовательские уведомления жизненного цикла подписки на email, если SMTP настроен и у пользователя есть email. |
| `SUBSCRIPTION_NOTIFY_ON_EXPIRE` | Уведомлять в день окончания. |
| `SUBSCRIPTION_NOTIFY_AFTER_EXPIRE` | Уведомлять после окончания. |
| `SUBSCRIPTION_NOTIFY_DAYS_BEFORE` | За сколько дней предупреждать. |
| `SUBSCRIPTION_NOTIFY_HOURS_BEFORE` | За сколько часов предупреждать дополнительно. |
| `SUBSCRIPTION_NOTIFICATION_WORKER_TICK_SECONDS` | Период локальной проверки уведомлений. |

## Поддержка

Подробный сценарий описан в разделе [поддержка пользователей / тикеты](../features/support.md).

| Переменная | Назначение |
| --- | --- |
| `SUPPORT_TICKETS_ENABLED` | Включает тикеты в Mini App. |
| `SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED` | Email-уведомления администраторам. |
| `SUPPORT_TICKET_MAX_BODY_LENGTH` | Максимальная длина сообщения. |
| `SUPPORT_TICKET_MAX_SUBJECT_LENGTH` | Максимальная длина темы. |
| `SUPPORT_TICKET_RATE_LIMIT_PER_HOUR` | Лимит новых тикетов в час. |
| `SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS` | Пауза между Telegram/log уведомлениями. |
| `SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS` | Пауза между email-уведомлениями. |

## Логирование

Часть настроек доступна в админке.

| Переменная | Назначение |
| --- | --- |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `LOGS_PAGE_SIZE` | Размер страницы логов в админке. |
| `LOG_CHAT_ID` | Telegram chat/group ID для служебных уведомлений. |
| `LOG_THREAD_ID` | Topic/thread ID общего лог-чата. |
| `LOG_SUPPORT_THREAD_ID` | Topic/thread ID поддержки. |
| `LOG_NEW_USERS` | Логировать новые регистрации. |
| `LOG_PAYMENTS` | Логировать платежи. |
| `LOG_SUPPORT` | Логировать тикеты поддержки. |
| `LOG_PROMO_ACTIVATIONS` | Логировать активации промокодов. |
| `LOG_TRIAL_ACTIVATIONS` | Логировать активации trial. |
| `LOG_SUSPICIOUS_ACTIVITY` | Логировать подозрительную активность. |
| `LOG_ADMIN_ACTIONS` | Логировать действия администраторов. |

## Чеки, ссылки подключения и inline

| Переменная | Назначение |
| --- | --- |
| `NALOGO_INN` | ИНН самозанятого для LKNPD. |
| `NALOGO_PASSWORD` | Пароль LKNPD / «Мой налог». |
| `NALOGO_API_URL` | Базовый URL LKNPD API. |
| `NALOGO_RECEIPT_NAME_SUBSCRIPTION` | Название позиции чека подписки. |
| `NALOGO_RECEIPT_NAME_TRAFFIC` | Название позиции чека пакета трафика. |
| `CRYPT4_ENABLED` | Включает happ crypt4 для ссылок подключения. |
| `CRYPT4_REDIRECT_URL` | URL-обертка для кнопки подключения. |
| `CRYPT4_LINK_CACHE_TTL_SECONDS` | TTL кеша crypt4-ссылок. |
| `MY_DEVICES_SECTION_ENABLED` | Показывать раздел «Мои устройства». |
| `INLINE_REFERRAL_THUMBNAIL_URL` | Превью inline-результата рефералов. |
| `INLINE_USER_STATS_THUMBNAIL_URL` | Превью inline-результата пользовательской статистики. |
| `INLINE_FINANCIAL_STATS_THUMBNAIL_URL` | Превью inline-результата финансовой статистики. |
| `INLINE_SYSTEM_STATS_THUMBNAIL_URL` | Превью inline-результата системной статистики. |
