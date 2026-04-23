# Telegram-бот для продажи подписок Remnawave

Этот Telegram-бот предназначен для автоматизации продажи и управления подписками для панели **Remnawave**. Он интегрируется с API Remnawave для управления пользователями и подписками, а также использует различные платежные системы для приема платежей.

## ✨ Ключевые возможности

### Для пользователей:
-   **Регистрация и выбор языка:** Поддержка русского и английского языков.
-   **Просмотр подписки:** Пользователи могут видеть статус своей подписки, дату окончания и ссылку на конфигурацию.
-   **Web App (Mini App):** отдельный веб-интерфейс для просмотра ссылки подключения, остатка времени и оплаты подписки.
-   **Мои устройства:** Опциональный раздел для просмотра и отключения подключенных устройств (активируется через переменную `MY_DEVICES_SECTION_ENABLED`).
-   **Пробная подписка:** Система пробных подписок для новых пользователей (активируется вручную по кнопке).
-   **Промокоды:** Возможность применять промокоды для получения скидок или бонусных дней.
-   **Реферальная программа:** Пользователи могут приглашать друзей и получать за это бонусные дни подписки.
    -   **Оплата:** Поддержка оплаты через YooKassa, FreeKassa (REST API), Platega, SeverPay, CryptoPay и Telegram Stars.

### Для администраторов:
-   **Защищенная админ-панель:** Доступ только для администраторов, указанных в `ADMIN_IDS`.
-   **Статистика:** Просмотр статистики использования бота (общее количество пользователей, забаненные, активные подписки), недавние платежи и статус синхронизации с панелью.
-   **Управление пользователями:** Блокировка/разблокировка пользователей, просмотр списка забаненных и детальной информации о пользователе.
-   **Рассылка:** Отправка сообщений всем пользователям, пользователям с активной или истекшей подпиской.
-   **Управление промокодами:** Создание и просмотр промокодов.
-   **Синхронизация с панелью:** Ручной запуск синхронизации пользователей и подписок с панелью Remnawave.
-   **Логи действий:** Просмотр логов всех действий пользователей.

## 🚀 Технологии

-   **Python 3.12**
-   **Aiogram 3.x:** Асинхронный фреймворк для Telegram ботов.
-   **aiohttp:** Для запуска веб-сервера (вебхуки).
-   **SQLAlchemy 2.x & asyncpg:** Асинхронная работа с базой данных PostgreSQL.
-   **YooKassa, FreeKassa API, Platega, SeverPay, aiocryptopay:** Интеграции с платежными системами.
-   **Pydantic:** Для управления настройками из `.env` файла.
-   **Docker & Docker Compose:** Для контейнеризации и развертывания.

## ⚙️ Установка и запуск

### Предварительные требования

-   Установленные Docker и Docker Compose.
-   Рабочая панель Remnawave.
-   Токен Telegram-бота.
-   Данные для подключения к платежным системам (YooKassa, CryptoPay и т.д.).

### Шаги установки

1.  **Клонируйте репозиторий:**
    ```bash
    git clone https://github.com/3252a8/remnawave-tg-shop
    cd remnawave-tg-shop
    ```

2.  **Создайте и настройте файл `.env`:**
    Скопируйте `env.example` в `.env` и заполните своими данными.
    ```bash
    cp .env.example .env
    nano .env 
    ```
    Ниже перечислены ключевые переменные.

    <details>
    <summary><b>Основные настройки</b></summary>

    | Переменная | Описание | Пример |
    | --- | --- | --- |
    | `BOT_TOKEN` | **Обязательно.** Токен вашего Telegram-бота. | `1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11` |
    | `ADMIN_IDS` | **Обязательно.** ID администраторов в Telegram через запятую. | `12345678,98765432` |
    | `DEFAULT_LANGUAGE` | Язык по умолчанию для новых пользователей. | `ru` |
| `SUPPORT_LINK` | (Опционально) Ссылка на поддержку. | `https://t.me/your_support` |
| `PRIVACY_POLICY_URL` | (Опционально) Ссылка на политику конфиденциальности, показывается внизу Web App. | `https://example.com/privacy` |
| `USER_AGREEMENT_URL` | (Опционально) Ссылка на пользовательское соглашение, показывается внизу Web App. | `https://example.com/agreement` |
| `SUBSCRIPTION_MINI_APP_URL` | (Опционально) Публичный URL Mini App для показа подписки. Если задан, кнопка «Моя подписка» откроет Web App. | `https://app.domain.com/` |
| `WEBAPP_ENABLED` | Включить Web App в том же контейнере, но на отдельном порту. | `true` |
| `WEBAPP_SERVER_PORT` | Внутренний порт Web App. | `8081` |
| `WEBAPP_TITLE` | Заголовок Web App. | `Моя подписка` |
| `WEBAPP_PRIMARY_COLOR` | Основной цвет Web App. | `#00fe7a` |
| `WEBAPP_LOGO_URL` | (Опционально) URL логотипа Web App. Если значение пустое, логотип не показывается вообще; если задано, он отображается в шапке и на экране логина. | `https://domain.com/logo.png` |
| `MY_DEVICES_SECTION_ENABLED` | Включить раздел «Мои устройства» в меню подписки (`true`/`false`). | `false` |
    | `REQUIRED_CHANNEL_ID` | (Опционально) ID канала, на который пользователь должен подписаться перед использованием. Оставьте пустым, если проверка не нужна. | `-1001234567890` |
    | `REQUIRED_CHANNEL_LINK` | (Опционально) Публичная ссылка или invite на канал для кнопки «Проверить подписку». | `https://t.me/your_channel` |
    </details>

    <details>
    <summary><b>Настройки платежей и вебхуков</b></summary>

    | Переменная | Описание |
    | --- | --- |
| `WEBHOOK_BASE_URL`| **Обязательно.** Базовый URL для вебхуков, например `https://your.domain.com`. |
| `WEB_SERVER_HOST` | Хост для веб-сервера. | `0.0.0.0` |
| `WEB_SERVER_PORT` | Порт для веб-сервера. | `8080` |
| `WEBAPP_SERVER_HOST` | Хост отдельного веб-сервера Mini App. | `0.0.0.0` |
| `WEBAPP_SERVER_PORT` | Порт отдельного веб-сервера Mini App. | `8081` |
| `PAYMENT_METHODS_ORDER` | (Опционально) Порядок отображения кнопок оплаты через запятую. Поддерживаемые ключи: `severpay`, `freekassa`, `platega`, `yookassa`, `stars`, `cryptopay`. Первый будет сверху. |
    | `YOOKASSA_ENABLED` | Включить/выключить YooKassa (`true`/`false`). |
    | `YOOKASSA_SHOP_ID` | ID вашего магазина в YooKassa. |
    | `YOOKASSA_SECRET_KEY`| Секретный ключ магазина YooKassa. |
    | `YOOKASSA_AUTOPAYMENTS_ENABLED` | Включить автопродление (сохранение карт, автосписания, управление способами оплаты). |
    | `YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING` | Требовать обязательную привязку карты при оплате с автосписанием. Установите `false`, чтобы пользователю показывался чекбокс «Сохранить карту». |
    | `NALOGO_INN` | ИНН для авторизации в nalog.ru (самозанятый). |
    | `NALOGO_PASSWORD` | Пароль для авторизации в nalog.ru (самозанятый). |
    | `CRYPTOPAY_ENABLED` | Включить/выключить CryptoPay (`true`/`false`). |
    | `CRYPTOPAY_TOKEN` | Токен из вашего CryptoPay App. |
    | `FREEKASSA_ENABLED` | Включить/выключить FreeKassa (`true`/`false`). |
    | `FREEKASSA_MERCHANT_ID` | ID вашего магазина в FreeKassa. |
    | `FREEKASSA_API_KEY` | API-ключ для запросов к FreeKassa REST API. |
    | `FREEKASSA_SECOND_SECRET` | Секретное слово №2 — используется для проверки уведомлений от FreeKassa. |
    | `FREEKASSA_PAYMENT_URL` | (Опционально, legacy SCI) Базовый URL платёжной формы FreeKassa. По умолчанию `https://pay.freekassa.ru/`. |
    | `FREEKASSA_PAYMENT_IP` | Внешний IP вашего сервера, который будет передаваться в запрос оплаты. |
    | `FREEKASSA_PAYMENT_METHOD_ID` | ID метода оплаты через магазин FreeKassa. По умолчанию `44`. |
    | `STARS_ENABLED` | Включить/выключить Telegram Stars (`true`/`false`). |
    | `PLATEGA_ENABLED`| Включить/выключить Platega (`true`/`false`). |
    | `PLATEGA_MERCHANT_ID`| MerchantId из личного кабинета Platega. |
    | `PLATEGA_SECRET`| API секрет для запросов Platega. |
    | `PLATEGA_PAYMENT_METHOD`| ID способа оплаты (2 — SBP QR, 10 — РФ карты, 12 — международные карты, 13 — crypto). |
    | `PLATEGA_RETURN_URL`| (Опционально) URL редиректа после успешной оплаты. По умолчанию ссылка на бота. |
    | `PLATEGA_FAILED_URL`| (Опционально) URL редиректа при ошибке/отмене. По умолчанию как `PLATEGA_RETURN_URL`. |
    | `SEVERPAY_ENABLED` | Включить/выключить SeverPay (`true`/`false`). |
    | `SEVERPAY_MID` | MID магазина в SeverPay. |
    | `SEVERPAY_TOKEN` | Секрет/токен для подписи запросов SeverPay. |
    | `SEVERPAY_BASE_URL` | (Опционально) Базовый URL API SeverPay. По умолчанию `https://severpay.io/api/merchant`. |
    | `SEVERPAY_RETURN_URL` | (Опционально) URL редиректа после оплаты (по умолчанию ссылка на бота). |
    | `SEVERPAY_LIFETIME_MINUTES` | (Опционально) Время жизни платежной ссылки в минутах (30–4320). |
    </details>

    <details>
    <summary><b>Настройки подписок</b></summary>

    Для каждого периода (1, 3, 6, 12 месяцев) можно настроить доступность и цены:
    - `1_MONTH_ENABLED`: `true` или `false`
    - `RUB_PRICE_1_MONTH`: Цена в рублях
    - `STARS_PRICE_1_MONTH`: Цена в Telegram Stars
    Аналогичные переменные есть для `3_MONTHS`, `6_MONTHS`, `12_MONTHS`.
    </details>

    <details>
    <summary><b>Настройки панели Remnawave</b></summary>
    
    | Переменная | Описание |
    | --- | --- |
    | `PANEL_API_URL` | URL API вашей панели Remnawave. |
    | `PANEL_API_KEY` | API ключ для доступа к панели. |
    | `PANEL_WEBHOOK_SECRET`| Секретный ключ для проверки вебхуков от панели. |
    | `USER_SQUAD_UUIDS` | ID отрядов для новых пользователей. |
    | `USER_EXTERNAL_SQUAD_UUID` | Опционально. UUID внешнего отряда (External Squad) из [документации Remnawave](https://docs.rw/api), куда автоматически добавляются новые пользователи. |
    | `USER_TRAFFIC_LIMIT_GB`| Лимит трафика в ГБ (0 - безлимит). |
    | `USER_HWID_DEVICE_LIMIT`| Лимит устройств (HWID) для новых пользователей (0 - безлимит). |

    > Раздел "Мои устройства" становится доступен пользователям только при включении `MY_DEVICES_SECTION_ENABLED`. Значение лимита устройств при создании записей в панели берётся из `USER_HWID_DEVICE_LIMIT`.
    </details>

    <details>
    <summary><b>Настройки пробного периода</b></summary>

    | Переменная | Описание |
    | --- | --- |
    | `TRIAL_ENABLED` | Включить/выключить пробный период (`true`/`false`). |
    | `TRIAL_DURATION_DAYS`| Длительность пробного периода в днях. |
    | `TRIAL_TRAFFIC_LIMIT_GB`| Лимит трафика для пробного периода в ГБ. |
    </details>

3.  **Запустите контейнеры:**
    ```bash
    docker compose up -d
    ```
    Эта команда скачает образ и запустит сервис в фоновом режиме.

4.  **Настройка вебхуков (Обязательно):**
    Вебхуки являются **обязательным** компонентом для работы бота, так как они используются для получения уведомлений от платежных систем (YooKassa, FreeKassa, CryptoPay, Platega, SeverPay) и панели Remnawave.

    Вам понадобится обратный прокси (например, Nginx) для обработки HTTPS-трафика и перенаправления запросов на контейнер с ботом.

    **Пути для перенаправления:**
    -   `https://<ваш_домен>/webhook/yookassa` → `http://remnawave-tg-shop:<WEB_SERVER_PORT>/webhook/yookassa`
    -   `https://<ваш_домен>/webhook/freekassa` → `http://remnawave-tg-shop:<WEB_SERVER_PORT>/webhook/freekassa`
    -   `https://<ваш_домен>/webhook/platega` → `http://remnawave-tg-shop:<WEB_SERVER_PORT>/webhook/platega`
    -   `https://<ваш_домен>/webhook/severpay` → `http://remnawave-tg-shop:<WEB_SERVER_PORT>/webhook/severpay`
    -   `https://<ваш_домен>/webhook/cryptopay` → `http://remnawave-tg-shop:<WEB_SERVER_PORT>/webhook/cryptopay`
    -   `https://<ваш_домен>/webhook/panel` → `http://remnawave-tg-shop:<WEB_SERVER_PORT>/webhook/panel`
    -   **Для Telegram:** Бот автоматически установит вебхук, если в `.env` указан `WEBHOOK_BASE_URL`. Путь будет `https://<ваш_домен>/<BOT_TOKEN>`.

    Где `remnawave-tg-shop` — это имя сервиса из `docker-compose.yml`, а `<WEB_SERVER_PORT>` — порт, указанный в `.env`.

    **Отдельный порт Web App:**
    -   `https://<домен_web_app>/` → `http://remnawave-tg-shop:<WEBAPP_SERVER_PORT>/`

    Web App не должен проксироваться на `WEB_SERVER_PORT`: этот порт оставьте для Telegram, платежных и Remnawave webhooks.

5.  **Просмотр логов:**
    ```bash
    docker compose logs -f remnawave-tg-shop
    ```

    > 💡 Если включена проверка подписки на канал (`REQUIRED_CHANNEL_ID`), добавьте бота администратором в этот канал. Пользователь увидит кнопку «Проверить подписку», и, после первого успешного подтверждения, дальнейшие действия блокироваться не будут.

### Настройка Web App / Mini App

Web App запускается в том же контейнере, что и бот, но слушает отдельный порт `WEBAPP_SERVER_PORT` (по умолчанию `8081`). Внутри Web App пользователь авторизуется через Telegram Mini Apps `initData`; если страницу открыть вне Telegram, показывается официальный Telegram Login Widget. После успешного входа страница обновляет данные сразу, без сообщений боту.

1.  Укажите в `.env` публичный URL Web App и порт:

    ```env
    WEBAPP_ENABLED=True
    WEBAPP_SERVER_HOST=0.0.0.0
    WEBAPP_SERVER_PORT=8081
    SUBSCRIPTION_MINI_APP_URL=https://app.domain.com/
    WEBAPP_TITLE="Моя подписка"
    WEBAPP_PRIMARY_COLOR="#00fe7a"
    WEBAPP_LOGO_URL=
    ```

2.  Убедитесь, что `docker-compose.yml` публикует порт Web App:

    ```yaml
    ports:
      - 127.0.0.1:8080:8080
      - 127.0.0.1:${WEBAPP_SERVER_PORT:-8081}:${WEBAPP_SERVER_PORT:-8081}
    ```

3.  Проксируйте отдельный домен или location на порт Web App:

    ```nginx
    upstream remnawave-tg-shop-webapp {
        server remnawave-tg-shop:8081;
    }

    server {
        server_name app.domain.com;
        listen 443 ssl;
        http2 on;

        ssl_certificate "/etc/nginx/ssl/app_fullchain.pem";
        ssl_certificate_key "/etc/nginx/ssl/app_privkey.key";

        location / {
            proxy_pass http://remnawave-tg-shop-webapp;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
    ```

4.  В BotFather настройте домен Mini App для бота (`/setdomain`) и укажите домен из `SUBSCRIPTION_MINI_APP_URL`. Этот же домен используется и Telegram Login Widget.

5.  Перезапустите контейнер:

    ```bash
    docker compose up -d --build
    ```

После этого кнопка «Моя подписка» в меню бота откроет Web App. В MVP Web App показывает текущую ссылку подключения, остаток времени и трафик. Оплата открывается отдельной кнопкой «Продлить подписку/Добавить дни»: пользователь пошагово выбирает срок, способ оплаты и создает платежную ссылку через уже настроенные платежные системы. Успешные оплаты обрабатываются существующими webhook-обработчиками.

Шапка и модальные окна Web App учитывают Telegram safe area через `--tg-content-safe-area-inset-top` и `--tg-safe-area-inset-top`, а сверху добавлен повышенный дополнительный буфер, чтобы интерфейс не уезжал под панель Telegram при открытии из списка чатов.

Для настройки внешнего вида без запуска бота можно открыть файл `bot/app/web/templates/subscription_webapp.html` напрямую в браузере. Рядом с ним лежат `telegram-web-app.js`, `telegram-widget.js`, `subscription_webapp.css` и `subscription_webapp.js`, поэтому локальный предпросмотр работает без сервера и без внешнего CDN. При отдаче страницы через Web App сервер dev-mock автоматически вырезается и не попадает пользователям.

Локальная копия Telegram Web App SDK хранится в `bot/app/web/templates/telegram-web-app.js`, а локальная копия Telegram Login Widget - в `bot/app/web/templates/telegram-widget.js`. В контейнере обе копии автоматически обновляются при старте Web App и затем раз в 24 часа; если источник временно недоступен, используется уже сохраненная версия. У локального `telegram-widget.js` есть минимальная нормализация, чтобы при загрузке с вашего домена виджет все равно открывал iframe на Telegram-origin, а не на `/embed/...` вашего сайта. Для ручного обновления можно запустить команды:

```bash
python scripts/update_telegram_web_app_js.py
python scripts/update_telegram_widget_js.py
```

При необходимости оба скрипта принимают `--source-url` и `--target`, если нужно скачать файл в другое место или проверить альтернативный источник.

## Подробная инструкция для развертывания на сервере с панелью Remnawave

### 1. Клонирование репозитория

```bash
git clone https://github.com/3252a8/remnawave-tg-shop && cd remnawave-tg-shop
```

### 2. Настройка переменных окружения

```bash
cp .env.example .env && nano .env
```

**Обязательные поля для заполнения:**
- `BOT_TOKEN` - токен телеграмм бота, например, `234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`
- `ADMIN_IDS` - TG ID администраторов, например, `12345678,98765432` и т.д. (через запятую без пробелов)
- `WEBHOOK_BASE_URL` - Обязательно. Базовый URL для вебхуков, например `https://webhook.domain.com`
- `PANEL_API_URL` - URL API вашей панели Remnawave (например, `http://remnawave:3000/api` или `https://panel.domain.com/api`)
- `PANEL_API_KEY` - API ключ для доступа к панели (генерируется из UI-интерфейса панели)
- `PANEL_WEBHOOK_SECRET` - Секретный ключ для проверки вебхуков от панели (берётся из `.env` самой панели)
- `USER_SQUAD_UUIDS` - ID отрядов для новых пользователей

### 3. Настройка Reverse Proxy (Nginx)

Перейдите в директорию конфигурации Nginx панели Remnawave:

```bash
cd /opt/remnawave/nginx && nano nginx.conf
```

Добавьте в `nginx.conf` следующую конфигурацию:

```nginx
upstream remnawave-tg-shop {
    server remnawave-tg-shop:8080;
}

map $http_upgrade $connection_upgrade {
    default upgrade;
    "" close;
}

server {
    server_name webhook.domain.com; # Домен для отправки Webhook'ов
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
        proxy_pass http://remnawave-tg-shop$request_uri;
    }

    location @redirect {
        return 404;
    }
}
```

### 4. Выпуск SSL-сертификата для домена webhook

Убедитесь, что установлены необходимые компоненты, а также откройте 80 порт:

```bash
sudo apt-get install cron socat
curl https://get.acme.sh | sh -s email=EMAIL && source ~/.bashrc
ufw allow 80/tcp && ufw reload
```

Выпустите сертификат:

```bash
acme.sh --set-default-ca --server letsencrypt
acme.sh --issue --standalone -d 'webhook.domain.com' \
  --key-file /opt/remnawave/nginx/webhook_privkey.key \
  --fullchain-file /opt/remnawave/nginx/webhook_fullchain.pem
```

### 5. Добавление сертификатов в Docker Compose Nginx

Отредактируйте `docker-compose.yml` панели Nginx:

```bash
cd /opt/remnawave/nginx && nano docker-compose.yml
```

Добавьте две строки в секцию `volumes`:

```yaml
services:
    remnawave-nginx:
        image: nginx:1.26
        container_name: remnawave-nginx
        hostname: remnawave-nginx
        volumes:
            - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
            - ./fullchain.pem:/etc/nginx/ssl/fullchain.pem:ro
            - ./privkey.key:/etc/nginx/ssl/privkey.key:ro
            - ./subdomain_fullchain.pem:/etc/nginx/ssl/subdomain_fullchain.pem:ro
            - ./subdomain_privkey.key:/etc/nginx/ssl/subdomain_privkey.key:ro
            - ./webhook_fullchain.pem:/etc/nginx/ssl/webhook_fullchain.pem:ro     # Добавьте эту строку
            - ./webhook_privkey.key:/etc/nginx/ssl/webhook_privkey.key:ro         # Добавьте эту строку
        restart: always
        ports:
            - '0.0.0.0:443:443'
        networks:
            - remnawave-network

networks:
    remnawave-network:
        name: remnawave-network
        driver: bridge
        external: true
```

### 6. Запуск бота и перезапуск Nginx

Запустите бота:

```bash
cd /root/remnawave-tg-shop && docker compose up -d && docker compose logs -f -t
```

Перезапустите Nginx:

```bash
cd /opt/remnawave/nginx && docker compose down && docker compose up -d && docker compose logs -f -t
```

## 🐳 Docker

Файлы `Dockerfile` и `docker-compose.yml` уже настроены для локальной сборки и запуска проекта.

Если нужен запуск из готового образа, используйте `docker-compose-remote-server.yml` как шаблон и укажите свой `image:` вместо локальной сборки.

Этот репозиторий больше не публикует образы автоматически через GitHub Actions. В GHCR сохранён только тег `3.0.0`; `latest` и `0.1.0` больше не используются.

Чтобы использовать сохранённый образ, можно запустить:
```bash
IMAGE_TAG=3.0.0 docker compose -f docker-compose-remote-server.yml up -d
```

## 📁 Структура проекта

```
.
├── bot/
│   ├── filters/          # Пользовательские фильтры Aiogram
│   ├── handlers/         # Обработчики сообщений и колбэков
│   ├── keyboards/        # Клавиатуры
│   ├── middlewares/      # Промежуточные слои (i18n, проверка бана)
│   ├── services/         # Бизнес-логика (платежи, API панели)
│   ├── states/           # Состояния FSM
│   └── main_bot.py       # Основная логика бота
├── config/
│   └── settings.py       # Настройки Pydantic
├── db/
│   ├── dal/              # Слой доступа к данным (DAL)
│   ├── database_setup.py # Настройка БД
│   └── models.py         # Модели SQLAlchemy
├── locales/              # Файлы локализации (ru, en)
├── .env.example          # Пример файла с переменными окружения
├── Dockerfile            # Инструкции для сборки Docker-образа
├── docker-compose.yml    # Файл для оркестрации контейнеров
├── requirements.txt      # Зависимости Python
└── main.py               # Точка входа в приложение
```

## 🔮 Планы на будущее

-   Расширенные типы промокодов (например, скидки в процентах).

## ❤️ Поддержка
- Карты РФ и зарубежные: [Tribute](https://t.me/tribute/app?startapp=dqdg)
- Crypto: `USDT TRC-20 TT3SqBbfU4vYm6SUwUVNZsy278m2xbM4GE`
