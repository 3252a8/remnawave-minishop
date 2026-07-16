# Telegram-авторизация

Telegram-вход в Mini App работает двумя способами:

- внутри Telegram Mini App backend проверяет Telegram Mini Apps `initData`;
- при открытии сайта в обычном браузере используется Telegram OAuth / OpenID Connect Authorization Code Flow с PKCE, `nonce`, callback `/auth/telegram/callback` и серверной проверкой `id_token` по JWKS Telegram.

`initData` не требует отдельного OAuth-секрета, но требует корректного `BOT_TOKEN`, публичного HTTPS Mini App URL и настройки Mini Apps в BotFather. OAuth нужен для входа через кнопку Telegram вне клиента Telegram и для привязки Telegram к email-аккаунту из настроек профиля.

## Что нужно заранее

Минимальные переменные:

```ini
WEBAPP_ENABLED=True
SUBSCRIPTION_MINI_APP_URL=https://app.domain.com/
WEBAPP_SESSION_SECRET=<stable-random-secret>
WEBAPP_AUTH_MAX_AGE_SECONDS=86400
WEBAPP_LOGIN_TOKEN_TTL_SECONDS=600

TELEGRAM_OAUTH_CLIENT_ID=<client-id-from-botfather>
TELEGRAM_OAUTH_CLIENT_SECRET=<client-secret-from-botfather>
TELEGRAM_OAUTH_REQUEST_ACCESS=write
```

`SUBSCRIPTION_MINI_APP_URL` должен быть публичным HTTPS URL именно frontend/Mini App-домена. Не добавляйте сюда `/api`, `/auth`, webhook-путь или конкретную страницу.

`WEBAPP_SESSION_SECRET` должен быть стабильным между рестартами, иначе Web App-сессии и OAuth state-cookie станут невалидными.

`WEBAPP_AUTH_MAX_AGE_SECONDS` ограничивает возраст Telegram Mini Apps `initData` и OAuth `id_token`. По умолчанию это 24 часа. Слишком маленькое значение может ломать вход на устройствах с неточными часами.

`WEBAPP_LOGIN_TOKEN_TTL_SECONDS` управляет TTL OAuth state, nonce и login-token. По умолчанию 10 минут.

`TELEGRAM_OAUTH_CLIENT_ID` можно не задавать, если client id совпадает с bot id: приложение возьмет его из префикса `BOT_TOKEN`. `TELEGRAM_OAUTH_CLIENT_SECRET` для браузерного OAuth обязателен.

`TELEGRAM_OAUTH_REQUEST_ACCESS=write` добавляет scope `telegram:bot_access`, чтобы бот мог написать пользователю после логина. Если это не нужно, оставьте переменную пустой. Также поддерживается `phone`, если вы осознанно запрашиваете телефон.

Полный справочник переменных: [Веб-приложение, внешний вид и Telegram Login](../configuration/env-vars.md#веб-приложение-внешний-вид-и-telegram-login).

## Настройка в BotFather

1. Откройте `@BotFather` -> `/mybots` -> выберите бота.
2. В `Bot Settings` -> `Domain` укажите домен Web App без протокола и пути, например `app.domain.com`.
3. В `Bot Settings` -> `Mini Apps` укажите URL, например `https://app.domain.com/`.
4. В `Bot Settings` -> `Web Login` включите OpenID Connect Login, если BotFather предлагает переключение.
5. Скопируйте client id и client secret в `TELEGRAM_OAUTH_CLIENT_ID` и `TELEGRAM_OAUTH_CLIENT_SECRET`.
6. В `Web Login` -> `Allowed URLs` добавьте:

```text
https://app.domain.com/
https://app.domain.com/auth/telegram/callback
```

После изменения `.env` перезапустите backend и frontend:

```bash
docker compose up -d --force-recreate backend frontend
```

## Проксирование

Публичный домен `SUBSCRIPTION_MINI_APP_URL` должен идти в контейнер `frontend:80`. Frontend nginx сам проксирует `/api/*` и `/auth/*` во внутренний WebApp-сервер backend на `backend:8081`.

Если используете собственный reverse proxy, не отправляйте `/auth/telegram/start` и `/auth/telegram/callback` напрямую в webhook-сервер `backend:8080`: эти маршруты принадлежат Web App API на `backend:8081` и штатно проходят через frontend.

Готовые схемы Caddy, Angie, Nginx, Newt и прямой публикации описаны в [развертывании](../getting-started/deployment.md#готовые-папки-запуска).

## Как проверить

Внутри Telegram:

1. Откройте Mini App кнопкой бота или через URL, настроенный в BotFather.
2. Проверьте, что пользователь входит без OAuth-redirect и видит личный кабинет.
3. Если вход не проходит, проверьте `SUBSCRIPTION_MINI_APP_URL`, домен BotFather и возраст `initData`.

В обычном браузере:

1. Откройте `https://app.domain.com/`.
2. Нажмите вход через Telegram.
3. Проверьте redirect на Telegram OAuth и возврат на `https://app.domain.com/auth/telegram/callback`.
4. После успешного callback пользователь должен вернуться на `/` со статусом `telegram_auth=success`, который frontend очистит из URL.

Для диагностики полезны:

```bash
curl -i https://app.domain.com/auth/telegram/start
docker compose logs -f backend frontend
```

## Частые ошибки

- `telegram_oauth_not_configured` или `telegram_auth=not_configured`: не задан `TELEGRAM_OAUTH_CLIENT_SECRET` или client id не удалось получить из `TELEGRAM_OAUTH_CLIENT_ID`/`BOT_TOKEN`.
- `Telegram OAuth nonce mismatch`: сессия/state устарели, поменялся `WEBAPP_SESSION_SECRET`, пользователь открыл старую вкладку или callback пришел с другого домена.
- `Telegram OAuth ID token is stale`: `WEBAPP_AUTH_MAX_AGE_SECONDS` слишком маленький или на сервере/клиенте сбито время.
- `Telegram OAuth callback failed`: проверьте allowed URL в BotFather и что `/auth/*` доходит до frontend/WebApp API.
- Mini App не открывается внутри Telegram: домен в BotFather должен совпадать с `SUBSCRIPTION_MINI_APP_URL`, а URL должен быть HTTPS.

Общие логи по авторизации собраны в [разделе диагностики логов](../troubleshooting/logs.md#авторизация-mini-app-и-telegram-oauth).
