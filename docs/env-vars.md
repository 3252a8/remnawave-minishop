# Переменные окружения

`.env` нужен прежде всего для bootstrap: токен бота, доступ к базе, публичный webhook URL и стабильные секреты. После первого входа большая часть продуктовых настроек меняется в Web App админке и сохраняется в БД как override поверх `.env`.

Рекомендуемый порядок:

1. Заполнить минимальный `.env` по `.env.example`.
2. Запустить стек и войти в Web App под Telegram ID из `ADMIN_IDS`.
3. Настроить Remnawave, платежи, внешний вид, поддержку, уведомления и тарифы через админку.

## Минимальный bootstrap

| Переменная | Где менять | Назначение |
| --- | --- | --- |
| `BOT_TOKEN` | Только `.env` | Токен Telegram-бота. |
| `ADMIN_IDS` | Только `.env` | Telegram ID администраторов через запятую. Нужен для первого входа в админку. |
| `WEBHOOK_BASE_URL` | `.env` | Публичный URL backend/webhook-домена. Используется для Telegram, платежных и Remnawave webhook URL. |
| `POSTGRES_USER` | `.env` / Compose | Пользователь PostgreSQL. |
| `POSTGRES_PASSWORD` | `.env` / Compose | Пароль PostgreSQL. |
| `POSTGRES_DB` | `.env` / Compose | Имя базы PostgreSQL. |
| `WEBAPP_ENABLED` | `.env` / админка | Включает Web App и админку. Держите `True` для первого запуска; если выключить, вернуть доступ можно только через `.env` и рестарт. |
| `WEBAPP_SESSION_SECRET` | `.env` | Стабильный HMAC-секрет сессий Web App. Если пустой, генерируется на процесс, но сессии сбросятся после рестарта. |
| `WEBHOOK_SECRET_TOKEN` | `.env` | Секрет Telegram webhook. Если пустой, генерируется на процесс. |

## Инфраструктура и Compose

| Переменная | Где менять | Назначение |
| --- | --- | --- |
| `APP_ENV_FILE` | CLI/Compose | Путь к env-файлу вместо `.env`. |
| `IMAGE_TAG` | CLI/Compose | Тег Docker-образов. |
| `FRONTEND_PORT` | `.env` / Compose | Хостовый порт frontend nginx. По умолчанию `8082`. |
| `WEB_SERVER_HOST` | `.env` | Внутренний host backend webhook server. Обычно `0.0.0.0`. |
| `WEB_SERVER_PORT` | `.env` / Compose | Хостовый порт backend webhook server. По умолчанию `8080`. |
| `WEBAPP_SERVER_HOST` | `.env` | Внутренний host Web App API server. Обычно `0.0.0.0`. |
| `WEBAPP_SERVER_PORT` | `.env` | Внутренний порт Web App API server. По умолчанию `8081`. |
| `POSTGRES_HOST` | Compose | Host PostgreSQL. В штатном Compose задается как `postgres`. |
| `POSTGRES_PORT` | `.env` | Порт PostgreSQL. |
| `DB_POOL_SIZE` | `.env` | Размер async SQLAlchemy pool. |
| `DB_MAX_OVERFLOW` | `.env` | Дополнительные transient DB-соединения сверх pool. |
| `DB_POOL_TIMEOUT_SECONDS` | `.env` | Таймаут ожидания соединения из pool. |
| `DB_POOL_RECYCLE_SECONDS` | `.env` | Период recycling DB-соединений. |
| `REDIS_URL` | Compose | Redis для FSM, кеша, rate-limit, очередей и locks. В Compose задается автоматически. |
| `REDIS_KEY_PREFIX` | `.env` | Префикс Redis-ключей. |
| `TRUSTED_PROXIES` | `.env` | IP/CIDR reverse proxy, которым доверяется `X-Forwarded-For`. |
| `HTTP_BIND` / `HTTPS_BIND` | Caddy Compose | Адреса публикации Caddy-варианта. |
| `NEWT_ID` / `NEWT_SECRET` | Dev Compose | Доступы Newt в dev-compose. |

## Кеши, rate limits и worker

Обычно эти значения не требуют правки.

| Переменная | Назначение |
| --- | --- |
| `WEBAPP_ME_CACHE_TTL_SECONDS` | TTL кеша `/api/me`. |
| `WEBAPP_DEVICES_CACHE_TTL_SECONDS` | TTL кеша устройств Web App. |
| `PANEL_USER_CACHE_TTL_SECONDS` | TTL кеша Remnawave `/users/{uuid}`. |
| `PANEL_DEVICES_CACHE_TTL_SECONDS` | TTL кеша устройств пользователя Remnawave. |
| `PANEL_ALL_USERS_CACHE_TTL_SECONDS` | TTL кеша полных сканов пользователей Remnawave. |
| `PANEL_ALL_USERS_PAGE_SIZE` | Размер страницы Remnawave `/users`. |
| `ADMIN_PANEL_STATS_CACHE_TTL_SECONDS` | TTL статистики Remnawave в админке. |
| `ADMIN_DB_STATS_CACHE_TTL_SECONDS` | TTL дорогих DB-агрегатов админки. |
| `ADMIN_USERS_LIST_CACHE_TTL_SECONDS` | TTL списка пользователей админки. |
| `PROFILE_SYNC_CACHE_TTL_SECONDS` | Минимальная пауза между sync Telegram-профиля пользователя. |
| `PANEL_SYNC_LIFETIME_TRAFFIC_MIN_INTERVAL_SECONDS` | Минимальная пауза записи lifetime-трафика. |
| `PANEL_SYNC_LIFETIME_TRAFFIC_MIN_DELTA_BYTES` | Дельта lifetime-трафика для более ранней записи. |
| `WEBAPP_RATE_LIMIT_TTL_SECONDS` | Окно Web App rate limit. |
| `WEBAPP_RATE_LIMIT_MAX_REQUESTS` | Количество запросов в окне rate limit. |
| `WEBHOOK_QUEUE_NAME` | Redis queue для тяжелой обработки webhook. |
| `WEBHOOK_QUEUE_CONCURRENCY` | Количество worker consumers для webhook queue. |
| `WORKER_PANEL_SYNC_INTERVAL_SECONDS` | Интервал фоновой синхронизации с панелью. |
| `TARIFF_WORKER_LOCK_TTL_SECONDS` | TTL Redis lock для tariff worker. |
| `TARIFF_WORKER_TICK_SECONDS` | Интервал tariff worker. |
| `TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD` | Порог активных подписок для bulk fetch пользователей панели. |

## Общие настройки

Эти поля доступны в админке: **Система -> Настройки**.

| Переменная | Назначение |
| --- | --- |
| `DEFAULT_LANGUAGE` | Язык по умолчанию: `ru` или `en`. |
| `DEFAULT_CURRENCY_SYMBOL` | Символ/код валюты в интерфейсе. |
| `SUPPORT_LINK` | Внешняя ссылка поддержки. |
| `SERVER_STATUS_URL` | Страница статуса сервиса. |
| `TERMS_OF_SERVICE_URL` | Условия использования. |
| `PRIVACY_POLICY_URL` | Политика конфиденциальности. |
| `USER_AGREEMENT_URL` | Пользовательское соглашение. |
| `REQUIRED_CHANNEL_ID` | ID обязательного Telegram-канала. |
| `REQUIRED_CHANNEL_LINK` | Ссылка на обязательный канал. |
| `START_COMMAND_DESCRIPTION` | Описание `/start` для меню Telegram. |
| `DISABLE_WELCOME_MESSAGE` | Отключить приветствие на `/start`. |

## Remnawave

Эти поля стоит держать в `.env` как базовую конфигурацию интеграции с панелью. Они также доступны в админке, чтобы можно было быстро поправить доступы или временно переопределить их без ручного редактирования файла и перезапуска.

| Переменная | Назначение |
| --- | --- |
| `PANEL_API_URL` | URL API панели, например `https://panel.example.com/api`. |
| `PANEL_API_KEY` | API-ключ панели. |
| `PANEL_WEBHOOK_SECRET` | Секрет проверки Remnawave webhook. |
| `USER_SQUAD_UUIDS` | Internal Squads по умолчанию для legacy-режима без JSON-каталога. |
| `USER_EXTERNAL_SQUAD_UUID` | Необязательный External Squad. |
| `USER_TRAFFIC_LIMIT_GB` | Legacy-лимит трафика пользователя. |
| `USER_TRAFFIC_STRATEGY` | Legacy-стратегия лимита трафика. |
| `USER_HWID_DEVICE_LIMIT` | Legacy-лимит HWID-устройств по умолчанию. |

## Web App, внешний вид и Telegram Login

Часть внешнего вида (`WEBAPP_PRIMARY_COLOR`, `WEBAPP_LOGO_*`, `WEBAPP_FAVICON_*`) сохранена для совместимости, но env-значения этих полей игнорируются при загрузке. Настраивайте их в **Админка -> Внешний вид**.

| Переменная | Где менять | Назначение |
| --- | --- | --- |
| `WEBAPP_ENABLED` | `.env` / админка | Включает Web App. Если `False`, пользовательский Web App и админка недоступны до включения через `.env` и рестарта. |
| `SUBSCRIPTION_MINI_APP_URL` | `.env` / админка | Публичный HTTPS URL Mini App/frontend, например `https://app.domain.com/`. Используется в Telegram-кнопках, referral-ссылках, email-входе и BotFather Mini App settings. Не указывайте здесь `/api` или webhook-пути. |
| `SUBSCRIPTION_GUIDES_ENABLED` | `.env` / админка | Включает встроенные инструкции установки в Web App. По умолчанию `True`; если конфиг недоступен или невалиден, кнопка подключения открывает обычную финальную ссылку подписки. |
| `SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED` | `.env` / админка | Включает открытие Mini App `/install` из кнопок бота и показ публичной ссылки инструкции `/s/<token>`. По умолчанию `True`; если выключить, бот ведет на финальную Remnawave Subscription Page. |
| `SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED` | `.env` / админка | Читать Remnawave Subscription Page config из панели для встроенных инструкций. По умолчанию `True`, чтобы не дублировать настройку страницы подписки в приложении. |
| `SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED` | `.env` / админка | Включает использование JSON из поля `SUBSCRIPTION_PAGE_CONFIG_JSON` вместо конфига панели. По умолчанию `False`. |
| `SUBSCRIPTION_PAGE_CONFIG_PATH` | `.env` / админка | Fallback-путь к локальному Remnawave Subscription Page v1 JSON config, если конфиг панели выключен или недоступен. По умолчанию `data/subpage-config/multiapp.json`; файл не создается автоматически. |
| `SUBSCRIPTION_PAGE_CONFIG_JSON` | Админка | Опциональный JSON-override Remnawave Subscription Page v1. Применяется только при включенном `SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED`; backend валидирует JSON при сохранении. |
| `WEBAPP_TITLE` | Админка | Заголовок Web App. |
| `WEBAPP_THEMES_DIR` | `.env` | Каталог кастомных тем. |
| `WEBAPP_DEFAULT_THEME` | `.env` / админка | Ключ темы по умолчанию. |
| `WEBAPP_SESSION_TTL_SECONDS` | `.env` | Время жизни Web App-сессии. |
| `WEBAPP_AUTH_MAX_AGE_SECONDS` | `.env` | Максимальный возраст Telegram Mini Apps `initData`. |
| `WEBAPP_LOGIN_TOKEN_TTL_SECONDS` | `.env` | TTL ссылки внешнего логина. |
| `TELEGRAM_OAUTH_CLIENT_ID` | `.env` | Client ID Telegram OAuth / OpenID Connect. Если пусто, берется bot ID из `BOT_TOKEN`. |
| `TELEGRAM_OAUTH_CLIENT_SECRET` | `.env` | Client Secret Telegram OAuth / OpenID Connect. |
| `TELEGRAM_OAUTH_REQUEST_ACCESS` | `.env` | Дополнительные permissions, например `write`. |
| `WEBAPP_PRIMARY_COLOR` | Админка | Устаревшее env-поле, игнорируется. |
| `WEBAPP_LOGO_URL` | Админка | Устаревшее env-поле, игнорируется. |
| `WEBAPP_LOGO_USE_EMOJI` | Админка | Устаревшее env-поле, игнорируется. |
| `WEBAPP_LOGO_EMOJI` | Админка | Устаревшее env-поле, игнорируется. |
| `WEBAPP_LOGO_EMOJI_FONT` | Админка | Устаревшее env-поле, игнорируется. |
| `WEBAPP_FAVICON_USE_CUSTOM` | Админка | Устаревшее env-поле, игнорируется. |
| `WEBAPP_FAVICON_URL` | Админка | Устаревшее env-поле, игнорируется. |
| `WEBAPP_LOGO_FAVICON_URL` | Админка | Устаревшее env-поле, игнорируется. |

Инструкции установки совместимы с Remnawave Subscription Page v1 config: `version`, `locales`, `brandingSettings`, `uiConfig`, `baseSettings`, `baseTranslations`, `svgLibrary` и `platforms`. Текстовые поля рендерятся как текст, а SVG из `svgLibrary` проходит санитарную проверку перед отдачей в Web App.

## SMTP и email-вход

Email-вход появляется только если заполнены `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` и `SMTP_FROM_EMAIL`.

| Переменная | Назначение |
| --- | --- |
| `SMTP_HOST` | SMTP host. |
| `SMTP_PORT` | Основной SMTP port. |
| `SMTP_FALLBACK_PORTS` | Резервные порты через запятую. |
| `SMTP_TIMEOUT_SECONDS` | Таймаут SMTP-попытки. |
| `SMTP_USERNAME` | SMTP login. |
| `SMTP_PASSWORD` | SMTP password/API key. |
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

Все включатели, секреты и presentation-настройки провайдеров доступны в админке: **Система -> Настройки -> Платежи**.

| Переменная | Назначение |
| --- | --- |
| `PAYMENT_METHODS_ORDER` | Порядок кнопок оплаты: `severpay,wata,freekassa,platega,yookassa,stars,cryptopay,heleket`. |
| `SUBSCRIPTION_PURCHASE_DESCRIPTION_ENABLED` | Показывать описание подписки перед выбором срока. |
| `SUBSCRIPTION_PURCHASE_DESCRIPTION_RU` / `SUBSCRIPTION_PURCHASE_DESCRIPTION_EN` | Локализованное описание подписки. |
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

Конкретные presentation-ключи:

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
```

### YooKassa

| Переменная | Назначение |
| --- | --- |
| `YOOKASSA_SHOP_ID` | ID магазина. |
| `YOOKASSA_SECRET_KEY` | Secret key. |
| `YOOKASSA_RETURN_URL` | URL возврата после оплаты. |
| `YOOKASSA_DEFAULT_RECEIPT_EMAIL` | Email для чеков по умолчанию. |
| `YOOKASSA_VAT_CODE` | Код НДС. |
| `YOOKASSA_AUTOPAYMENTS_ENABLED` | Автопродление через сохраненные способы оплаты. |
| `YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING` | Требовать привязку карты. |

### FreeKassa

| Переменная | Назначение |
| --- | --- |
| `FREEKASSA_MERCHANT_ID` | ID магазина. |
| `FREEKASSA_API_KEY` | API key. |
| `FREEKASSA_SECOND_SECRET` | Секрет уведомлений. |
| `FREEKASSA_PAYMENT_IP` | Публичный IP сервера для запроса оплаты. |
| `FREEKASSA_PAYMENT_METHOD_ID` | ID метода оплаты. |
| `FREEKASSA_TRUSTED_IPS` | IP-allowlist webhook-источников. |

### Platega

| Переменная | Назначение |
| --- | --- |
| `PLATEGA_BASE_URL` | Базовый URL API. |
| `PLATEGA_MERCHANT_ID` | Merchant ID. |
| `PLATEGA_SECRET` | API secret. |
| `PLATEGA_PAYMENT_METHOD` | Legacy/fallback method ID. |
| `PLATEGA_SBP_METHOD` | Method ID для СБП. |
| `PLATEGA_CRYPTO_METHOD` | Method ID для крипто. |
| `PLATEGA_RETURN_URL` | URL успешного возврата. |
| `PLATEGA_FAILED_URL` | URL неуспешного возврата. |

### SeverPay

| Переменная | Назначение |
| --- | --- |
| `SEVERPAY_BASE_URL` | Базовый URL API. |
| `SEVERPAY_MID` | Merchant MID. |
| `SEVERPAY_TOKEN` | API token/secret. |
| `SEVERPAY_RETURN_URL` | URL возврата. |
| `SEVERPAY_LIFETIME_MINUTES` | Время жизни платежной ссылки. |

### Wata

| Переменная | Назначение |
| --- | --- |
| `WATA_BASE_URL` | Базовый URL API. |
| `WATA_API_TOKEN` | Bearer token. |
| `WATA_RETURN_URL` | URL успешного возврата. |
| `WATA_FAILED_URL` | URL неуспешного возврата. |
| `WATA_PAYMENT_LINK_TTL_DAYS` | TTL платежной ссылки в днях. |
| `WATA_WEBHOOK_VERIFY_SIGNATURE` | Проверять `X-Signature`. |
| `WATA_PUBLIC_KEY` | Cached public key; если пусто, загружается из API. |
| `WATA_TRUSTED_IPS` | IP-allowlist webhook-источников. |

### CryptoPay

| Переменная | Назначение |
| --- | --- |
| `CRYPTOPAY_TOKEN` | API token CryptoPay. |
| `CRYPTOPAY_NETWORK` | `mainnet` или `testnet`. |
| `CRYPTOPAY_CURRENCY_TYPE` | `fiat` или `crypto`. |
| `CRYPTOPAY_ASSET` | Актив, например `RUB`, `USDT`, `BTC`. |

### Heleket

| Переменная | Назначение |
| --- | --- |
| `HELEKET_BASE_URL` | Базовый URL API. |
| `HELEKET_MERCHANT_ID` | UUID мерчанта. |
| `HELEKET_API_KEY` | Payment API key. |
| `HELEKET_CURRENCY` | Валюта инвойса. |
| `HELEKET_TO_CURRENCY` | Целевая криптовалюта для конвертации. |
| `HELEKET_NETWORK` | Сеть, например `tron`, `bsc`, `eth`. |
| `HELEKET_RETURN_URL` | URL после отмены/истечения. |
| `HELEKET_SUCCESS_URL` | URL после успешной оплаты. |
| `HELEKET_LIFETIME_SECONDS` | TTL инвойса: 300..43200. |
| `HELEKET_VERIFY_WEBHOOK_SIGNATURE` | Проверять подпись webhook. |
| `HELEKET_TRUSTED_IPS` | IP-allowlist webhook-источников. |

## Тарифы и legacy-цены

Рекомендуемый способ настройки тарифов - раздел **Система -> Тарифы** в админке. Он сохраняет JSON в `TARIFFS_CONFIG_PATH`.

| Переменная | Назначение |
| --- | --- |
| `TARIFFS_CONFIG_PATH` | Путь к JSON-каталогу тарифов. |
| `TARIFF_TRAFFIC_WARNING_LEVELS` | Уровни предупреждений по трафику в процентах. |
| `1_MONTH_ENABLED` | Legacy-доступность периода 1 месяц без JSON-каталога. |
| `3_MONTHS_ENABLED` | Legacy-доступность периода 3 месяца без JSON-каталога. |
| `6_MONTHS_ENABLED` | Legacy-доступность периода 6 месяцев без JSON-каталога. |
| `12_MONTHS_ENABLED` | Legacy-доступность периода 12 месяцев без JSON-каталога. |
| `RUB_PRICE_1_MONTH`, `RUB_PRICE_3_MONTHS`, `RUB_PRICE_6_MONTHS`, `RUB_PRICE_12_MONTHS` | Legacy-цены RUB. |
| `STARS_PRICE_1_MONTH`, `STARS_PRICE_3_MONTHS`, `STARS_PRICE_6_MONTHS`, `STARS_PRICE_12_MONTHS` | Legacy-цены Stars. |
| `TRAFFIC_PACKAGES` | Legacy-пакеты трафика RUB, формат `10:199,50:799`. |
| `STARS_TRAFFIC_PACKAGES` | Legacy-пакеты трафика Stars. |

## Trial, referral и уведомления

Эти настройки доступны в админке.

| Переменная | Назначение |
| --- | --- |
| `TRIAL_ENABLED` | Включает пробный период. |
| `TRIAL_DURATION_DAYS` | Длительность пробного периода. |
| `TRIAL_TRAFFIC_LIMIT_GB` | Лимит трафика пробного периода. |
| `TRIAL_TRAFFIC_STRATEGY` | Стратегия лимита пробного периода. |
| `REFERRAL_ONE_BONUS_PER_REFEREE` | Ограничить бонусы одним успешным платежом приглашенного. |
| `REFERRAL_WELCOME_BONUS_DAYS` | Приветственный бонус пришедшему по реферальной ссылке. |
| `LEGACY_REFS` | Разрешить ссылки `ref_<telegram_id>`. |
| `REFERRAL_BONUS_DAYS_1_MONTH`, `REFERRAL_BONUS_DAYS_3_MONTHS`, `REFERRAL_BONUS_DAYS_6_MONTHS`, `REFERRAL_BONUS_DAYS_12_MONTHS` | Legacy-бонусы пригласившему. |
| `REFEREE_BONUS_DAYS_1_MONTH`, `REFEREE_BONUS_DAYS_3_MONTHS`, `REFEREE_BONUS_DAYS_6_MONTHS`, `REFEREE_BONUS_DAYS_12_MONTHS` | Legacy-бонусы приглашенному. |
| `SUBSCRIPTION_NOTIFICATIONS_ENABLED` | Включает напоминания о подписке. |
| `SUBSCRIPTION_NOTIFY_ON_EXPIRE` | Уведомлять в день окончания. |
| `SUBSCRIPTION_NOTIFY_AFTER_EXPIRE` | Уведомлять после окончания. |
| `SUBSCRIPTION_NOTIFY_DAYS_BEFORE` | За сколько дней предупреждать. |

## Поддержка

Подробный сценарий описан в [support.md](support.md).

| Переменная | Назначение |
| --- | --- |
| `SUPPORT_TICKETS_ENABLED` | Включает тикеты в Mini App. |
| `SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED` | Email-уведомления администраторам. |
| `SUPPORT_TICKET_MAX_BODY_LENGTH` | Максимальная длина сообщения. |
| `SUPPORT_TICKET_MAX_SUBJECT_LENGTH` | Максимальная длина темы. |
| `SUPPORT_TICKET_RATE_LIMIT_PER_HOUR` | Лимит новых тикетов в час. |
| `SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS` | Cooldown Telegram/log уведомлений. |
| `SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS` | Cooldown email-уведомлений. |

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
