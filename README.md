# Remnawave Minishop

![Remnawave Minishop](docs/remnawave-minishop.webp)

Remnawave Minishop - Telegram-бот и Web App (Mini App) для продажи и управления подписками панели [Remnawave](https://docs.rw/). Бот обрабатывает регистрацию, оплату, продление, пробный период, промокоды, рефералов и поддержку в чате. Web App показывает ссылку подключения, срок действия, трафик, оплату, устройства и вход по Telegram Mini Apps `initData`, Telegram OAuth / OpenID Connect и одноразовому email-коду.

Проект является переработанным форком [kavore/remnawave-tg-shop](https://github.com/kavore/remnawave-tg-shop). Для переноса данных из прежнего стека используйте [инструкцию по миграции](docs/migration-to-minishop.md).

## Возможности

Для пользователей:

- регистрация с выбором русского или английского языка;
- просмотр статуса подписки, даты окончания, ссылки подключения и трафика;
- покупка подписок, пакетов трафика, обычная и premium-докупка трафика, докупка устройств по настроенному каталогу тарифов;
- Web App / Mini App с входом через Telegram или email;
- встроенные инструкции установки в Mini App: личный экран `/install` и публичная ссылка `/s/<token>` для передачи инструкции;
- пробный период, промокоды и реферальная программа;
- оплата через YooKassa, FreeKassa, Platega, SeverPay, Wata, CryptoPay, Heleket и Telegram Stars;
- тикеты поддержки в Web App и внешняя ссылка на поддержку;
- раздел "Мои устройства" при включенном `MY_DEVICES_SECTION_ENABLED`.

Для администраторов:

- админ-панель для пользователей из `ADMIN_IDS` (только при входе через Telegram, не для аккаунтов только с email);
- статистика пользователей, подписок, платежей и синхронизации с Remnawave;
- список пользователей с поиском, фильтрами и колонкой premium-трафика;
- блокировка пользователей, поддержка через тикеты, рассылки, промокоды, логи действий и настройка разрешенных параметров приложения поверх `.env`;
- редактор JSON-каталога тарифов с period/traffic-моделями, Internal Squads, premium-сквадами и HWID-пакетами;
- настройки инструкций подключения: чтение конфига Subscription Page из Remnawave Panel, опциональный JSON-override и переключатель поведения кнопок бота;
- ручная синхронизация пользователей и подписок с панелью.

## Документация

- [Настройка окружения](docs/configuration.md) - bootstrap `.env` и рекомендуемая настройка через Web App админку.
- [Переменные `.env`](docs/env-vars.md) - полный справочник всех env-ключей по разделам.
- [Тарифы](docs/tariffs.md) - каталог тарифов, period- и traffic-модели, обычные и premium-докупки, premium-сквады, смена тарифа, HWID-лимиты и обработка трафика.
- [Админ-панель](docs/admin.md) - права доступа, настройки, редактор тарифов, premium-сквады и сохранение JSON-каталога.
- [Web App / Mini App](docs/webapp.md) - отдельный порт, домен, Telegram OAuth, email-вход, инструкции установки и реферальные ссылки.
- [Поддержка](docs/support.md) - тикеты в Mini App, входящий список админки, уведомления, лимиты и внешняя ссылка поддержки.
- [Темы Web App](docs/webapp-themes.md) - кастомные темы, настройка внешнего вида, логотипы, CSS/ассеты и пайплайн создания новой темы.
- [Развертывание](docs/deployment.md) - Docker Compose, reverse proxy, Nginx, Caddy, вебхуки, запуск из образа и обновление версии (`IMAGE_TAG`).
- [Миграция с remnawave-tg-shop](docs/migration-to-minishop.md) - перенос данных из прежнего стека.

## Совместимость

Интеграция с API панели Remnawave (вебхуки, пользователи, подписки, статистика в админке и т.д.) **протестирована** на панели Remnawave версии **`> 2.7.0`**. Более старые версии могут работать частично или не работать из‑за изменений в API.

## Стек

Сборка и runtime задаются **deploy/docker/Dockerfile** и **docker-compose.yml**; точные версии пакетов — в **backend/requirements.txt** и **frontend/package.json**.

| Слой | Технологии |
| --- | --- |
| Backend | Python **3.12**, [aiogram](https://docs.aiogram.dev/) 3.x (Telegram), **aiohttp** (HTTP и Web App), **SQLAlchemy** 2 async, **asyncpg**, **Pydantic** / pydantic-settings, **httpx**, платёжные SDK (в т.ч. YooKassa, aiocryptopay), **PyJWT** |
| Данные | **PostgreSQL** **17** (сервис `postgres` в Compose) и **Redis** **7** (сервис `redis`) |
| Сборка Web App | **Node.js** **22**, **Svelte** **5**, **Vite**, **Tailwind CSS** 4; артефакты попадают в шаблоны `backend/bot/app/web/templates/` |

Локальная разработка без Docker возможна при установленных Python 3.12, PostgreSQL и (для пересборки фронта) Node 22; типичный сценарий — всё через Compose.

## Быстрый старт

Требования:

- Docker и Docker Compose;
- рабочая панель Remnawave версии **`> 2.7.0`** (см. раздел «Совместимость»);
- токен Telegram-бота;
- публичные домены для webhook и Mini App.

```bash
git clone https://github.com/3252a8/remnawave-minishop
cd remnawave-minishop
cp .env.example .env
nano .env
docker compose up -d --build
docker compose logs -f backend worker frontend
```

Минимально заполните в `.env`:

- `BOT_TOKEN` - токен Telegram-бота;
- `ADMIN_IDS` - Telegram ID администраторов через запятую;
- `WEBHOOK_BASE_URL` - публичный URL вебхуков;
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` - доступы PostgreSQL;
- `WEBAPP_ENABLED=True` - включает Web App и админку для первого входа;
- `WEBAPP_SESSION_SECRET`, `WEBHOOK_SECRET_TOKEN` - стабильные секреты;
- `SUBSCRIPTION_MINI_APP_URL` - публичный HTTPS URL Mini App/frontend, например `https://app.domain.com/`;
- `PANEL_API_URL`, `PANEL_API_KEY`, `PANEL_WEBHOOK_SECRET` - доступ к Remnawave;
- остальные настройки удобнее задать в Web App админке.

После первого входа в админку настройте тарифы, платежные провайдеры, внешний вид, поддержку, уведомления и инструкции подключения через UI. Инструкции установки включены по умолчанию, читают Subscription Page config из Remnawave Panel и при проблемах с конфигом откатываются к обычной ссылке подключения. Полный справочник env-переменных: [docs/env-vars.md](docs/env-vars.md).

Для каталога тарифов используется `TARIFFS_CONFIG_PATH` со значением по умолчанию `data/tariffs.json`. Пример формата лежит в [data/tariffs.example.json](data/tariffs.example.json), подробности - в [docs/tariffs.md](docs/tariffs.md).

Если в Docker Compose включаете bind mount `./data:/app/data`, заранее создайте каталог и отдайте его пользователю контейнера. Это нужно для сохранения `data/tariffs.json`, каталога тем `data/themes`, кеша логотипа Web App и animated emoji:

```bash
mkdir -p data/themes data/webapp-logo data/webapp-emoji
chown -R 10001:10001 data
chmod -R u+rwX data
```

## Полезные команды

```bash
# Локальная сборка и запуск
docker compose up -d --build

# Логи приложения
docker compose logs -f backend worker frontend

# Запуск с Caddy
docker compose -f deploy/compose/docker-compose-caddy.yml up -d

# Запуск из готового образа
IMAGE_TAG=3.1.0 docker compose -f deploy/compose/docker-compose-remote-server.yml up -d
```

GHCR image names for releases:

- `ghcr.io/3252a8/remnawave-minishop-backend`
- `ghcr.io/3252a8/remnawave-minishop-worker`
- `ghcr.io/3252a8/remnawave-minishop-frontend`

## Поддержать проект

- Crypto: `USDT/Other ERC-20 0xeD506D44aae634fEc0E01C8835744fBedb7B2a44 (Ethereum/Polygon/Gnosis)`
