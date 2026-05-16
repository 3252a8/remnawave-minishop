# Настройка окружения

Конфигурация читается из `.env`. За основу удобно взять `.env.example` и заполнить значения под свою панель, домены и платежные провайдеры.

```bash
cp .env.example .env
nano .env
```

## Основные настройки

| Переменная | Назначение |
| --- | --- |
| `BOT_TOKEN` | Токен Telegram-бота. |
| `ADMIN_IDS` | Telegram ID администраторов через запятую. |
| `DEFAULT_LANGUAGE` | Язык по умолчанию для пользователей: `ru` или `en`. |
| `DEFAULT_CURRENCY_SYMBOL` | Символ валюты по умолчанию в интерфейсе (например `RUB`, `USD`). |
| `SUPPORT_LINK` | Ссылка на поддержку. |
| `SERVER_STATUS_URL` | Ссылка на страницу статуса сервиса. |
| `TERMS_OF_SERVICE_URL` | Ссылка на условия использования (отдельно от пользовательского соглашения). |
| `PRIVACY_POLICY_URL` | Ссылка на политику конфиденциальности в Web App. |
| `USER_AGREEMENT_URL` | Ссылка на пользовательское соглашение в Web App. |
| `REQUIRED_CHANNEL_ID` | ID канала, на который пользователь должен подписаться перед использованием. |
| `REQUIRED_CHANNEL_LINK` | Ссылка на канал для кнопки проверки подписки. |
| `WEBHOOK_BASE_URL` | Публичный базовый URL для вебхуков (Telegram, платежи, панель). **Обязателен:** без него приложение не запускается. |
| `TRUSTED_PROXIES` | Список IP или CIDR reverse proxy, которым доверяют заголовок `X-Forwarded-For` (через запятую). |
| `START_COMMAND_DESCRIPTION` | Текст описания команды `/start` для меню Telegram (BotFather). |
| `DISABLE_WELCOME_MESSAGE` | Если `true`, приветственное сообщение на `/start` не отправляется. |

Если используется проверка подписки на канал, добавьте бота администратором в этот канал. После первой успешной проверки пользователь продолжает работу без повторной блокировки действий.

## Remnawave

| Переменная | Назначение |
| --- | --- |
| `PANEL_API_URL` | URL API панели Remnawave, например `https://panel.domain.com/api`. |
| `PANEL_API_KEY` | API-ключ панели. |
| `PANEL_WEBHOOK_SECRET` | Секрет для проверки вебхуков Remnawave. |
| `USER_SQUAD_UUIDS` | Internal Squads, в которые добавляются пользователи. |
| `USER_EXTERNAL_SQUAD_UUID` | External Squad для пользователей, если он используется. |
| `USER_TRAFFIC_LIMIT_GB` | Лимит трафика для режима без JSON-каталога тарифов. `0` означает безлимит. |
| `USER_TRAFFIC_STRATEGY` | Стратегия лимита трафика для режима без JSON-каталога тарифов. |
| `USER_HWID_DEVICE_LIMIT` | Лимит HWID-устройств для пользователей. `0` означает безлимит. |

При включенном каталоге тарифов значения `squad_uuids`, `monthly_gb`, `traffic_packages` и `hwid_device_limit` берутся из выбранного тарифа. Подробно это описано в [tariffs.md](tariffs.md).

## Платежи

| Переменная | Назначение |
| --- | --- |
| `PAYMENT_METHODS_ORDER` | Порядок кнопок оплаты через запятую: `severpay`, `freekassa`, `platega`, `yookassa`, `stars`, `cryptopay`. |
| `YOOKASSA_ENABLED` | Включает YooKassa. |
| `YOOKASSA_SHOP_ID` / `YOOKASSA_SECRET_KEY` | Данные магазина YooKassa. |
| `YOOKASSA_RETURN_URL` | URL возврата пользователя после оплаты. |
| `YOOKASSA_DEFAULT_RECEIPT_EMAIL` | Email по умолчанию для чеков YooKassa. |
| `YOOKASSA_VAT_CODE` | Код НДС для чеков. |
| `YOOKASSA_AUTOPAYMENTS_ENABLED` | Включает автопродление через сохраненные способы оплаты YooKassa. |
| `YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING` | Управляет обязательной привязкой карты при оплате. |
| `FREEKASSA_ENABLED` | Включает FreeKassa. |
| `FREEKASSA_MERCHANT_ID` / `FREEKASSA_API_KEY` / `FREEKASSA_SECOND_SECRET` | Данные FreeKassa и секрет уведомлений. |
| `FREEKASSA_PAYMENT_IP` | Внешний IP сервера для запроса оплаты FreeKassa. |
| `FREEKASSA_PAYMENT_METHOD_ID` | ID метода оплаты FreeKassa. |
| `FREEKASSA_TRUSTED_IPS` | Список IP источников вебхуков FreeKassa (через запятую). |
| `PLATEGA_ENABLED` | Включает Platega. |
| `PLATEGA_BASE_URL` | Базовый URL API Platega. |
| `PLATEGA_MERCHANT_ID` / `PLATEGA_SECRET` | Данные Platega. |
| `PLATEGA_PAYMENT_METHOD` | Общий ID метода в API Platega; при отдельных кнопках СБП/крипто может использоваться как fallback для метода СБП (см. `PLATEGA_SBP_METHOD`). |
| `PLATEGA_SBP_ENABLED` / `PLATEGA_CRYPTO_ENABLED` | Отдельные кнопки «СБП» и «крипто» в Platega. |
| `PLATEGA_SBP_METHOD` / `PLATEGA_CRYPTO_METHOD` | ID методов Platega для СБП и крипто. |
| `PLATEGA_RETURN_URL` / `PLATEGA_FAILED_URL` | URL возврата после оплаты или ошибки. |
| `SEVERPAY_ENABLED` | Включает SeverPay. |
| `SEVERPAY_MID` / `SEVERPAY_TOKEN` | Данные SeverPay. |
| `SEVERPAY_BASE_URL` | Базовый URL API SeverPay. |
| `SEVERPAY_RETURN_URL` | URL возврата после оплаты. |
| `SEVERPAY_LIFETIME_MINUTES` | Время жизни платежной ссылки. |
| `CRYPTOPAY_ENABLED` | Включает CryptoPay. |
| `CRYPTOPAY_TOKEN` | Токен CryptoPay App. |
| `CRYPTOPAY_NETWORK` | Сеть: `mainnet` или `testnet`. |
| `CRYPTOPAY_CURRENCY_TYPE` | Тип валюты: `fiat` или `crypto`. |
| `CRYPTOPAY_ASSET` | Актив (например `RUB`, `USDT`). |
| `STARS_ENABLED` | Включает Telegram Stars. |

Вебхуки платежных систем должны проксироваться на порт `WEB_SERVER_PORT`. Примеры маршрутов есть в [deployment.md](deployment.md).

## Тарифы

| Переменная | Назначение |
| --- | --- |
| `TARIFFS_CONFIG_PATH` | Путь к JSON-каталогу тарифов. По умолчанию `data/tariffs.json`. |
| `TARIFF_TRAFFIC_WARNING_LEVELS` | Проценты предупреждений по трафику, например `85,90,95`. |
| `RUB_PRICE_1_MONTH`, `RUB_PRICE_3_MONTHS`, `RUB_PRICE_6_MONTHS`, `RUB_PRICE_12_MONTHS` | Цены подписок в рублях для режима без JSON-каталога. |
| `STARS_PRICE_1_MONTH`, `STARS_PRICE_3_MONTHS`, `STARS_PRICE_6_MONTHS`, `STARS_PRICE_12_MONTHS` | Цены подписок в Telegram Stars для режима без JSON-каталога. |
| `1_MONTH_ENABLED`, `3_MONTHS_ENABLED`, `6_MONTHS_ENABLED`, `12_MONTHS_ENABLED` | Доступность периодов подписки для режима без JSON-каталога. |
| `TRAFFIC_PACKAGES` | Пакеты трафика в рублях для режима без JSON-каталога, например `10:199,50:799`. |
| `STARS_TRAFFIC_PACKAGES` | Пакеты трафика в Telegram Stars для режима без JSON-каталога. |

Если файл из `TARIFFS_CONFIG_PATH` существует, бот использует каталог тарифов. Если файла нет, применяется конфигурация из переменных `.env`.

В штатном `docker-compose.yml` данные хранятся в named volumes. Если для локальной разработки включён bind mount `./data:/app/data`, админка сможет сохранять `data/tariffs.json`, каталог тем (`data/themes`), кеш логотипа Web App (`data/webapp-logo`) и animated emoji (`data/webapp-emoji`) прямо в рабочую копию. Если bind mount включён на Ubuntu-сервере, создайте подкаталоги и отдайте `data` UID `10001`, под которым работает приложение внутри контейнера:

```bash
mkdir -p data/themes data/webapp-logo data/webapp-emoji
chown -R 10001:10001 data
chmod -R u+rwX data
```

После изменения compose-файла или прав пересоздайте контейнер:

```bash
docker compose up -d --build --force-recreate
```

Переопределения из веб-админки сохраняются в БД и применяются поверх `.env` без перезапуска. Для платежных методов кнопка отображается только если соответствующий `*_ENABLED=true` и сервис настроен.

Редактор тарифов в админке сохраняет не override в БД, а сам JSON-файл `TARIFFS_CONFIG_PATH`. Редактор настроек админки, наоборот, работает через allowlist из `backend/bot/app/web/admin_settings_manifest.py` и сохраняет overrides в БД. Через него можно менять только заявленные в manifest параметры приложения; остальные параметры остаются в `.env`. Подробнее: [admin.md](admin.md).

## Web App и email-вход

| Переменная | Назначение |
| --- | --- |
| `WEBAPP_ENABLED` | Включает Web App в том же контейнере. |
| `WEBAPP_SERVER_HOST` / `WEBAPP_SERVER_PORT` | Внутренний aiohttp server для WebApp API/auth/theme assets. По умолчанию порт `8081`; статический frontend отдается отдельным nginx image. |
| `SUBSCRIPTION_MINI_APP_URL` | Публичный URL Web App. |
| `WEBAPP_TITLE` | Заголовок Web App. |
| `WEBAPP_THEMES_DIR` | Каталог тем Web App. По умолчанию `data/themes`; внутри ожидаются папки `<key>/theme.json` и опциональные CSS/ассеты. |
| `WEBAPP_DEFAULT_THEME` | Опциональный override темы по ключу, например `light` или `neon`. Если пусто, используется `default` из дескрипторов тем. |
| `WEBAPP_SESSION_SECRET` | HMAC-секрет сессий Web App. |
| `WEBHOOK_SECRET_TOKEN` | Секретный токен, с которым Telegram шлёт обновления на вебхук. |
| `WEBAPP_SESSION_TTL_SECONDS` | Время жизни сессии Web App. |
| `WEBAPP_AUTH_MAX_AGE_SECONDS` | Максимальный возраст `initData` Telegram Mini App. |
| `WEBAPP_LOGIN_TOKEN_TTL_SECONDS` | Время жизни ссылки «войти с другого устройства» / внешнего логина. |
| `TELEGRAM_OAUTH_CLIENT_ID` / `TELEGRAM_OAUTH_CLIENT_SECRET` | Данные Telegram OAuth / OpenID Connect из BotFather. |
| `TELEGRAM_OAUTH_REQUEST_ACCESS` | Дополнительные разрешения Telegram Login, например `write`. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_FALLBACK_PORTS` | SMTP-подключение для email-кодов; резервные порты перебираются при ошибке основного. |
| `SMTP_TIMEOUT_SECONDS` | Таймаут одной попытки подключения и отправки. |
| `SMTP_STARTTLS` / `SMTP_USE_SSL` | STARTTLS на обычном порту (например 587) и SSL-обёртка (часто порт 465). |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Логин и пароль или SMTP key. |
| `SMTP_FROM_EMAIL` / `SMTP_FROM_NAME` | Отправитель писем с кодом; адрес из `SMTP_FROM_EMAIL` должен быть разрешён у провайдера. |
| `EMAIL_CODE_TTL_SECONDS` | Срок действия email-кода. |
| `EMAIL_CODE_RESEND_SECONDS` | Пауза перед повторной отправкой кода. |
| `EMAIL_CODE_MAX_ATTEMPTS` | Максимум попыток ввода одного кода. |
| `BRUTE_FORCE_MAX_FAILURES` | Количество неудачных попыток до временной блокировки. |
| `BRUTE_FORCE_WINDOW_SECONDS` | Окно учета неудачных попыток. |
| `BRUTE_FORCE_LOCK_SECONDS` | Длительность временной блокировки. |
| `MY_DEVICES_SECTION_ENABLED` | Показывает раздел "Мои устройства" и включает API устройств. |

Логотип, emoji-логотип, основной accent-цвет и тема редактируются в разделе **Админка -> Внешний вид** и сохраняются как overrides в базе. Переменные `WEBAPP_PRIMARY_COLOR`, `WEBAPP_LOGO_URL`, `WEBAPP_LOGO_USE_EMOJI`, `WEBAPP_LOGO_EMOJI` и `WEBAPP_LOGO_EMOJI_FONT` в `.env` считаются устаревшими для первичной настройки и игнорируются при загрузке env. Настройка домена, BotFather и callback URL описана в [webapp.md](webapp.md), а создание кастомных тем - в [webapp-themes.md](webapp-themes.md).

### SMTP и вход по email

Вход по email в Web App включается только если заполнены все обязательные поля SMTP: **`SMTP_HOST`**, **`SMTP_PORT`**, **`SMTP_USERNAME`**, **`SMTP_PASSWORD`**, **`SMTP_FROM_EMAIL`**. Имя отправителя **`SMTP_FROM_NAME`** необязательно. Пока конфигурация неполная, интерфейс входа по email не показывается.

Рекомендуемый типичный вариант — **порт 587** с **STARTTLS** (`SMTP_STARTTLS=True`, `SMTP_USE_SSL=False`), как в примере для Brevo в `.env.example`. Для **порта 465** обычно используют обёртку SSL: выставьте `SMTP_USE_SSL=True` и при необходимости `SMTP_STARTTLS=False`; приложение также считает порт 465 SSL-режимом автоматически при отправке.

Если основной порт недоступен, перебираются порты из **`SMTP_FALLBACK_PORTS`** (список через запятую, после `SMTP_PORT`). Таймаут одной попытки подключения и отправки задаёт **`SMTP_TIMEOUT_SECONDS`**.

Порядок действий при подключении нового SMTP:

1. В панели почтового провайдера создайте SMTP-доступ и подтвердите адрес отправителя (**from**), совпадающий с `SMTP_FROM_EMAIL`.
2. Перенесите хост, порт, логин и пароль (или API-ключ SMTP) в `.env`.
3. Перезапустите контейнер приложения, чтобы подхватить переменные.
4. Проверьте вход: на странице Web App запросите код на почту; при ошибках смотрите логи контейнера.

Для ограничений по частоте отправки кодов см. `EMAIL_CODE_*` и `BRUTE_FORCE_*` в таблице выше.

## Пробный период

| Переменная | Назначение |
| --- | --- |
| `TRIAL_ENABLED` | Включает пробный период. |
| `TRIAL_DURATION_DAYS` | Длительность пробного периода в днях. |
| `TRIAL_TRAFFIC_LIMIT_GB` | Лимит трафика пробного периода. `0` означает безлимит. |
| `TRIAL_TRAFFIC_STRATEGY` | Стратегия лимита трафика пробного периода. |

## Реферальная программа

| Переменная | Назначение |
| --- | --- |
| `REFERRAL_WELCOME_BONUS_DAYS` | Бонус пользователю, который пришел по реферальной ссылке. |
| `REFERRAL_ONE_BONUS_PER_REFEREE` | Ограничивает бонусы одним успешным платежом приглашенного пользователя. |
| `REFERRAL_BONUS_DAYS_*` | Бонусные дни пригласившему по периодам подписки. |
| `REFEREE_BONUS_DAYS_*` | Бонусные дни приглашенному по периодам подписки. |
| `LEGACY_REFS` | Разрешает ссылки формата `ref_<telegram_id>`. |

В режиме продажи трафика без JSON-каталога бонусы по периодам не отображаются, потому что покупка не привязана к сроку подписки.

## Уведомления о подписке

| Переменная | Назначение |
| --- | --- |
| `SUBSCRIPTION_NOTIFICATIONS_ENABLED` | Включает напоминания о подписке в Telegram. |
| `SUBSCRIPTION_NOTIFY_ON_EXPIRE` | Уведомлять в день окончания. |
| `SUBSCRIPTION_NOTIFY_AFTER_EXPIRE` | Уведомлять после окончания. |
| `SUBSCRIPTION_NOTIFY_DAYS_BEFORE` | За сколько дней до окончания напоминать. |

## Чеки самозанятого (LKNPD)

Интеграция с API lknpd.nalog.ru использует переменные с префиксом **`NALOGO_`**:

| Переменная | Назначение |
| --- | --- |
| `NALOGO_INN` | ИНН самозанятого. |
| `NALOGO_PASSWORD` | Пароль для LKNPD / «Мой налог». |
| `NALOGO_API_URL` | Базовый URL API (по умолчанию `https://lknpd.nalog.ru/api`). |
| `NALOGO_RECEIPT_NAME_SUBSCRIPTION` | Название позиции чека для подписки; в тексте можно использовать `{months}`. |
| `NALOGO_RECEIPT_NAME_TRAFFIC` | Название для пакета трафика; плейсхолдер `{gb}`. |

Нужны **оба** поля `NALOGO_INN` и `NALOGO_PASSWORD`; иначе отправка чеков отключается (в логах будет предупреждение).

## Happ crypt4 для ссылок подключения

| Переменная | Назначение |
| --- | --- |
| `CRYPT4_ENABLED` | Включить шифрование ссылок happ crypt4. |
| `CRYPT4_REDIRECT_URL` | Базовый URL редиректа для кнопки подключения (обёртка с query, например `?url=`). |

## Логирование и уведомления в Telegram

| Переменная | Назначение |
| --- | --- |
| `LOG_LEVEL` | Уровень логов: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `LOGS_PAGE_SIZE` | Размер страницы журнала в админке. |
| `LOG_CHAT_ID` | ID чата или группы для служебных уведомлений. |
| `LOG_THREAD_ID` | ID топика в супергруппе (опционально). |
| `LOG_NEW_USERS` | Уведомлять о новых регистрациях. |
| `LOG_PAYMENTS` | Уведомлять об успешных платежах. |
| `LOG_PROMO_ACTIVATIONS` | Уведомлять об активации промокодов. |
| `LOG_TRIAL_ACTIVATIONS` | Уведомлять об активации пробного периода. |
| `LOG_SUSPICIOUS_ACTIVITY` | Уведомлять о подозрительных попытках. |
| `LOG_ADMIN_ACTIONS` | Писать в журнал админки действия пользователей из `ADMIN_IDS`. |

Часть этих переключателей доступна для правки через Web App (allowlist в `backend/bot/app/web/admin_settings_manifest.py`), см. [admin.md](admin.md).

## Миниатюры inline-режима

Превью для inline-результатов задаются `INLINE_REFERRAL_THUMBNAIL_URL`, `INLINE_USER_STATS_THUMBNAIL_URL`, `INLINE_FINANCIAL_STATS_THUMBNAIL_URL`, `INLINE_SYSTEM_STATS_THUMBNAIL_URL` (значения по умолчанию есть в `.env.example`).

## Секреты

`WEBAPP_SESSION_SECRET` и `WEBHOOK_SECRET_TOKEN` могут генерироваться при старте, но для рабочего окружения их лучше задать явно. Иначе после рестарта сессии Web App станут невалидными, а Telegram получит новый `secret_token` для вебхука (старые запросы от API Telegram могут перестать проходить проверку до следующей переустановки вебхука).

```bash
openssl rand -hex 32
```
