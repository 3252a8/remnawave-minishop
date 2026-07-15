# Логи

Логи - главный источник диагностики при проблемах запуска, платежей, вебхуков и синхронизации с Remnawave Panel.

## Основные команды

```bash
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f frontend
docker compose logs migrate
```

## Что искать

- ошибки миграций в `migrate`;
- ошибки вебхука Telegram и платежных вебхуков в `backend`;
- проблемы очереди вебхуков и фоновых задач в `worker`;
- ошибки проксирования `/api`, `/auth` и ассетов тем во `frontend`;
- ошибки авторизации Mini App и Telegram OAuth.

## Проксирование frontend, `/api`, `/auth` и ассеты тем

`frontend` - это nginx-контейнер Mini App. Он отдает статику и проксирует маршруты Web App во внутренний WebApp-сервер backend на `backend:8081`.

Сначала смотрите nginx-логи:

```bash
docker compose logs -f frontend
```

Если видите `404`, `502`, `upstream` или `connect() failed`, проверьте маршруты:

- `/api/*` и `/auth/*` должны попадать в `frontend:80`, а уже frontend проксирует их в `backend:8081`;
- `/webapp-logo`, `/webapp-uploaded-logo/*`, `/webapp-favicon/*`, `/webapp-theme-css/*` и `/webapp-theme-assets/*` тоже проксируются через frontend;
- внешний обратный прокси не должен отдельно уводить `/api` или `/auth` на webhook-сервер `backend:8080`.

Быстрые проверки снаружи:

```bash
curl -i https://app.domain.com/health
curl -i https://app.domain.com/api/bootstrap
curl -i https://app.domain.com/auth/telegram/start
curl -i https://app.domain.com/webapp-theme-css/dark/style.css
```

Если `/health` отвечает, а `/api/bootstrap` или ассеты тем падают, смотрите одновременно frontend и backend:

```bash
docker compose logs -f frontend backend
```

Где проверять конфигурацию:

- frontend nginx: `deploy/docker/frontend/nginx.conf`;
- внешний Caddy/Angie/Nginx: `deploy/examples/caddy/Caddyfile`, `deploy/examples/angie/angie.conf.template` или `deploy/examples/nginx/nginx.conf.template`;
- домен Web App: `SUBSCRIPTION_MINI_APP_URL`, он должен быть публичным HTTPS URL frontend, без `/api`, `/auth` или webhook-пути;
- WebApp-сервер backend: `WEBAPP_ENABLED=True`, `WEBAPP_SERVER_HOST=0.0.0.0`, `WEBAPP_SERVER_PORT=8081`.

Для split frontend/backend дополнительно проверьте:

- startup banner `frontend` показывает `api base :: /api` и ожидаемый `upstream :: ...`;
- `WEBAPP_BACKEND_UPSTREAM` доступен с frontend-сервера;
- при protected upstream frontend nginx добавляет `X-Minishop-Edge-Token`, но прямой запрос к backend `/api/bootstrap` без token возвращает `401/403`;
- webhook routes на backend-домене продолжают идти в `backend:8080`, а не в `frontend` и не в `backend:8081`.

## Авторизация Mini App и Telegram OAuth

Ошибки авторизации почти всегда видны в `backend`, потому что проверка Telegram Mini Apps `initData`, Telegram OAuth `id_token`, nonce/state и сессий выполняется на WebApp-сервере backend.

```bash
docker compose logs -f backend
```

Ищите сообщения:

- `Telegram WebApp initData hash mismatch`;
- `Telegram WebApp initData auth_date is stale`;
- `Failed to validate Telegram WebApp initData`;
- `Telegram OAuth nonce mismatch`;
- `Telegram OAuth ID token is stale`;
- `Failed to validate Telegram OAuth ID token`;
- `Telegram OAuth token exchange failed`;
- `Telegram OAuth callback failed`;
- `WebApp auth failed`.

Для Mini App внутри Telegram проверьте:

- `SUBSCRIPTION_MINI_APP_URL` совпадает с доменом, указанным в BotFather Mini Apps;
- открывается именно HTTPS frontend-домен, а не backend webhook-домен;
- время на сервере синхронизировано, иначе `auth_date is stale`;
- `WEBAPP_AUTH_MAX_AGE_SECONDS` не слишком маленький;
- `WEBAPP_SESSION_SECRET` постоянный между рестартами.

Для Telegram OAuth вне Mini App проверьте:

- `TELEGRAM_OAUTH_CLIENT_ID` и `TELEGRAM_OAUTH_CLIENT_SECRET`;
- callback в Telegram OAuth/BotFather: `https://app.domain.com/auth/telegram/callback`;
- `/auth/telegram/start` и `/auth/telegram/callback` проходят через frontend nginx в `backend:8081`;
- в браузере после callback нет статуса `telegram_auth=invalid_state`, `invalid_token`, `not_configured`, `unauthorized` или `failed`.

Подробности по маршрутам и настройке OAuth: [Telegram-авторизация](../features/telegram-auth.md).

## После изменения конфигурации

```bash
docker compose up -d
docker compose logs -f backend worker frontend
```

См. также [проблемы](issues.md) и [развертывание](../getting-started/deployment.md).
