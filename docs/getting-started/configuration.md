# Настройка окружения

Проект поддерживает два слоя конфигурации:

- `.env` - bootstrap, инфраструктура, стабильные секреты и базовые доступы к Remnawave;
- Web App админка - основной рекомендуемый способ менять продуктовые настройки после первого запуска.

Админка сохраняет overrides в базе данных и применяет их поверх `.env`. Это удобно для платежей, внешнего вида, поддержки, уведомлений, legacy-цен и большинства пользовательских параметров. Тарифы редактируются отдельно в разделе **Система -> Тарифы** и сохраняются в JSON-файл `TARIFFS_CONFIG_PATH`.

Полный справочник всех переменных вынесен в [configuration/env-vars.md](../configuration/env-vars.md).

## Минимальный `.env`

Начните с короткого примера:

```bash
cp .env.example .env
nano .env
```

Минимально заполните:

| Переменная | Зачем нужна |
| --- | --- |
| `BOT_TOKEN` | Токен Telegram-бота. |
| `ADMIN_IDS` | Telegram ID администраторов через запятую; без этого не попасть в Web App админку. |
| `WEBHOOK_BASE_URL` | Публичный URL webhook-домена backend. Для Remnawave Panel `WEBHOOK_URL` будет `WEBHOOK_BASE_URL` + `/webhook/panel`, например `https://app.example.com/webhook/panel`. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Доступы PostgreSQL для Compose и backend. |
| `WEBAPP_ENABLED` | Включает Web App и админку. Для первого запуска держите `True`. |
| `WEBAPP_SESSION_SECRET` | Стабильный секрет сессий Web App. |
| `WEBHOOK_SECRET_TOKEN` | Стабильный секретный токен вебхука Telegram. |
| `SUBSCRIPTION_MINI_APP_URL` | Публичный HTTPS URL Mini App/frontend, например `https://app.domain.com/`. Это URL, который открывают кнопки Telegram и который указывается в BotFather; не добавляйте сюда `/api` или webhook-пути. |
| `SUBSCRIPTION_GUIDES_ENABLED`, `SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED` | Встроенные инструкции установки в Web App и кнопках бота. По умолчанию включены; обычно их достаточно менять в админке. |
| `PANEL_API_URL`, `PANEL_API_KEY`, `PANEL_WEBHOOK_SECRET` | Базовая интеграция с Remnawave. Секрет вебхука задайте в Remnawave Panel и вставьте то же значение в настройки бота; эти значения стоит хранить в `.env`, но при необходимости их можно переопределить из админки. |

`WEBAPP_SESSION_SECRET` и `WEBHOOK_SECRET_TOKEN` можно сгенерировать так:

```bash
openssl rand -hex 32
```

Если оставить эти секреты пустыми, приложение сгенерирует их на процесс, но после рестарта Web App-сессии станут невалидными, а вебхук Telegram получит новый `secret_token`.

## Если Web App выключен

`WEBAPP_ENABLED=False` отключает пользовательский Web App и вместе с ним админ-панель. В таком состоянии нельзя зайти в **Система -> Настройки** и включить Web App обратно через UI.

Чтобы восстановить доступ:

1. В `.env` выставьте `WEBAPP_ENABLED=True`.
2. Перезапустите backend/frontend контейнеры, например `docker compose up -d --force-recreate backend frontend`.
3. Откройте `SUBSCRIPTION_MINI_APP_URL` под Telegram-аккаунтом из `ADMIN_IDS` и при необходимости проверьте настройку в админке.

## Настройка через админку

После запуска откройте Mini App под аккаунтом, чей Telegram ID указан в `ADMIN_IDS`, и перейдите в админ-панель.

Рекомендуемый порядок первичной настройки:

1. **Система -> Настройки -> Remnawave Panel**: проверьте `PANEL_API_URL`, `PANEL_API_KEY`, `PANEL_WEBHOOK_SECRET`, базовые squads. Рядом с настройками Remnawave админка показывает вычисленный адрес для `WEBHOOK_URL` в панели, например `https://app.example.com/webhook/panel`.
2. **Система -> Тарифы**: создайте JSON-каталог тарифов, выберите Internal Squads, настройте модели на срок/по трафику, premium-сквады и HWID-пакеты.
3. **Система -> Настройки -> Инструкции подключения**: проверьте, что Remnawave Panel отдает нужный конфиг Subscription Page. JSON-переопределение включайте только если нужно временно заменить конфиг панели.
4. **Система -> Настройки -> Платежи**: включите нужные провайдеры и заполните их ключи.
5. **Внешний вид**: настройте название, тему, логотип, favicon и accent.
6. **Система -> Настройки -> Поддержка / Уведомления**: настройте тикеты, лог-чат, email-уведомления и напоминания.
7. **Общие настройки**: заполните ссылки на поддержку, документы, статус сервиса и обязательный канал, если он нужен.

Изменения из админки пишутся в таблицу `app_setting_overrides`. При сбросе override снова используется значение из `.env` или дефолт из кода.

## Что оставить только в `.env`

Не все настройки стоит переносить в базу. В `.env` остаются:

- токен бота и `ADMIN_IDS`;
- параметры PostgreSQL, Redis, портов и Compose;
- `WEBHOOK_BASE_URL`, потому что вебхук Telegram устанавливается при старте;
- стабильные секреты `WEBAPP_SESSION_SECRET` и `WEBHOOK_SECRET_TOKEN`;
- `WEBAPP_THEMES_DIR`, `TARIFFS_CONFIG_PATH` и низкоуровневые TTL/pool/worker-параметры;
- Remnawave-доступы как базовый источник правды, даже если для удобства они доступны в админке.

Конфиг инструкций установки обычно не нужно хранить в локальном `data`-файле: по умолчанию приложение читает конфиг Subscription Page из Remnawave Panel. `SUBSCRIPTION_PAGE_CONFIG_PATH` и `SUBSCRIPTION_PAGE_CONFIG_JSON` нужны как резервный путь или явное переопределение из админки.

## Файловые данные

В compose-примерах данные монтируются из локальной папки `./data` рядом с выбранным `docker-compose.yml`. Внутри нее лежат тарифы, темы, логотипы и прочие файловые данные приложения.

Папка `./data` монтируется в `/app/data` для `migrate`, `backend` и `worker`. Если вы меняете compose-файл вручную, не убирайте этот mount у `migrate`: иначе `docker compose run --rm migrate` не увидит `data/tariffs.json` из `TARIFFS_CONFIG_PATH`.

Перед первым запуском создайте каталоги и отдайте их пользователю контейнера:

```bash
mkdir -p data/themes data/webapp-logo data/tariffs
touch data/locales-overrides.json
chown -R 10001:10001 data
chmod -R u+rwX data
docker compose run --rm migrate
docker compose up -d --force-recreate backend worker
```

Проверить права можно так:

```bash
docker compose exec backend sh -lc 'id; touch /app/data/themes/test && rm /app/data/themes/test'
```

## Дополнительные разделы

- [configuration/env-vars.md](../configuration/env-vars.md) - полный справочник переменных `.env`.
- [features/admin-panel.md](../features/admin-panel.md) - как устроены overrides и allowlist настроек.
- [features/tariffs.md](../features/tariffs.md) - JSON-каталог тарифов и редактор тарифов.
- [Веб-приложение / Mini App](../features/web-app.md) - домен Mini App, инструкции установки и проксирование.
- [Telegram-авторизация](../features/telegram-auth.md) - BotFather, Mini Apps и OAuth.
- [Вход по email](../features/email-login.md) - SMTP, коды, magic link и парольный вход.
- [Поддержка пользователей / тикеты](../features/support.md) - тикеты поддержки и уведомления.
- [Развертывание](deployment.md) - Docker Compose, обратный прокси, Caddy/Angie/Nginx и обновления.
