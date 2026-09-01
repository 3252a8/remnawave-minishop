# Способы входа

Minishop поддерживает шесть способов входа:

1. **Email-код** — одноразовый код или magic link из письма.
2. **Email и пароль** — пароль, заданный после подтверждения email.
3. **Telegram** — Mini Apps `initData` внутри Telegram и OAuth / OpenID Connect в браузере.
4. **Google** — серверный OAuth 2.0 / OpenID Connect flow.
5. **Yandex ID** — OAuth-приложение Яндекса.
6. **Passkey** — ключ доступа WebAuthn.

В админке способы собраны в **Система → Настройки → Способы входа**. Пользователь управляет
паролем, passkey, привязанными провайдерами и адресом для уведомлений в
**Настройки → Безопасность**.

| Способ | Когда доступен | Что нужно настроить |
| --- | --- | --- |
| [Email-код](#email-код) | Включён `EMAIL_LOGIN_ENABLED` и готов SMTP | SMTP, адрес отправителя и публичный URL Mini App |
| [Email и пароль](#email-и-пароль) | Пользователь подтвердил email и задал пароль | Те же SMTP-настройки для подтверждения и восстановления |
| [Telegram](#telegram) | Включён `TELEGRAM_LOGIN_ENABLED` | BotFather и `BOT_TOKEN`; для браузера также Telegram OAuth |
| [Google](#google) | Включён `GOOGLE_OIDC_ENABLED` | OAuth client ID, secret и callback |
| [Yandex ID](#yandex-id) | Включён `YANDEX_OIDC_ENABLED` | OAuth client ID, secret и callback |
| [Passkey](#passkey) | Включён `PASSKEY_LOGIN_ENABLED` | HTTPS, RP ID и разрешённые origins |

Аккаунты без привязанного Telegram ID не получают права администратора: админка проверяет
Telegram ID из `ADMIN_IDS` независимо от способа входа пользователя в Mini App.

## Модель аккаунта и защита от дублей

Один пользователь Minishop может иметь несколько способов входа и несколько подтверждённых
email-адресов. Роли адресов разделены:

- **основной email** используется для входа по коду/паролю, восстановления доступа и синхронизации
  поля email в Remnawave Panel;
- **email для уведомлений** явно выбирается пользователем из подтверждённых адресов;
- Google и Yandex ID идентифицируются стабильной парой `provider + subject`, а не адресом почты;
- дополнительный адрес OIDC не становится логином по email и не меняет запись в Remnawave Panel
  сам по себе.

Если новый вход Google или Yandex ID возвращает email, уже занятый существующим аккаунтом,
backend **не создаёт второго пользователя и не связывает аккаунты только по совпавшей строке**.
После успешного OAuth backend отправляет одноразовый код на уже подтверждённый адрес. OAuth
подтверждает доступ к аккаунту провайдера, а код — владение существующим аккаунтом Minishop.
Только после обеих проверок identity привязывается к исходной записи и пользователь входит в неё.
Основной email, адрес уведомлений и поле email в Remnawave Panel при этом не меняются.

Контекст незавершённой привязки хранится в короткоживущей подписанной HttpOnly-cookie. Клиент
отправляет обратно только код: `provider`, стабильный `subject`, точный email и ID целевого
пользователя нельзя подменить в браузере. Перед повторной отправкой и подтверждением backend снова
проверяет владельца email, существующие identity и включённость провайдера. Истёкший контекст,
сменившийся владелец адреса и параллельная привязка завершаются ошибкой без создания пользователя.

При объединении сохраняются подтверждённые адреса обеих записей, но основной адрес целевого
аккаунта не меняется автоматически. Подписки, платежи, реферальные ограничения и другие сущности
проходят существующие проверки конфликтов. Если безопасное объединение невозможно, операция
останавливается без частичных изменений.

## Общие требования

Укажите публичный HTTPS URL Mini App и стабильный секрет сессий:

```ini
SUBSCRIPTION_MINI_APP_URL=https://app.example.com/
WEBAPP_SESSION_SECRET=<stable-random-secret>
```

Маршруты `/auth/*` должны попадать в Web App API. В штатном Docker Compose они проходят через
frontend nginx. Для собственного reverse proxy не отправляйте callback в webhook-сервер на порту
`8080` — Web App backend слушает внутренний порт `8081`.

Для production используйте отдельные OAuth-приложения и секреты. Не помещайте client secret в
frontend, публичные JSON-конфиги или URL.

## Общая настройка email

Email-код и вход по паролю используют один SMTP-контур. Включите способ входа и заполните все
обязательные параметры:

```ini
EMAIL_LOGIN_ENABLED=True

SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USERNAME=<smtp-login>
SMTP_PASSWORD=<smtp-password-or-api-key>
SMTP_FROM_EMAIL=no-reply@domain.com
```

Если хотя бы одно SMTP-поле пустое, backend возвращает `email_auth_enabled=false` в bootstrap, а
frontend скрывает email-вход. Для magic link также нужен корректный
`SUBSCRIPTION_MINI_APP_URL`, потому что ссылка в письме строится на его основе.

Типовой расширенный SMTP-конфиг:

```ini
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_FALLBACK_PORTS=2525,465
SMTP_TIMEOUT_SECONDS=30
SMTP_STARTTLS=True
SMTP_USE_SSL=False
SMTP_USERNAME=<smtp-login>
SMTP_PASSWORD=<smtp-password-or-api-key>
SMTP_FROM_EMAIL=no-reply@domain.com
SMTP_FROM_NAME=Remnawave Minishop

EMAIL_CODE_TTL_SECONDS=600
EMAIL_CODE_RESEND_SECONDS=60
EMAIL_CODE_MAX_ATTEMPTS=5
BRUTE_FORCE_MAX_FAILURES=5
BRUTE_FORCE_WINDOW_SECONDS=900
BRUTE_FORCE_LOCK_SECONDS=900
```

Для Brevo обычно подходит порт `587` с STARTTLS. Если основной порт недоступен, приложение
пробует порты из `SMTP_FALLBACK_PORTS`; порт `465` используется через SSL wrapper автоматически.
`SMTP_FROM_EMAIL` должен быть подтверждён у SMTP-провайдера, иначе письмо часто отклоняется или
попадает в спам. `SMTP_FROM_NAME` можно оставить пустым — тогда используется название Web App.

HTML-письма используют бренд Mini App: название из `WEBAPP_TITLE`, accent из внешнего вида и
логотип из раздела **Внешний вид**. Загруженный через админку файл backend прикладывает как inline
image (`cid:webapp-logo`), поэтому получателю не нужен доступ к внутреннему
`/webapp-uploaded-logo/...`. Публичный `https://` URL используется как внешний `<img>` и может
быть скрыт почтовым клиентом до разрешения загрузки изображений.

Полный справочник переменных:
[SMTP и вход по email](../configuration/env-vars.md#smtp-и-вход-по-email).

## Email-код

Email-код позволяет зарегистрироваться или войти без Telegram:

1. Пользователь вводит email.
2. Backend проверяет rate limit и создаёт одноразовый код.
3. Письмо отправляется через SMTP. При валидном `SUBSCRIPTION_MINI_APP_URL` оно также содержит
   magic link.
4. Пользователь вводит код в Mini App или открывает magic link.
5. Backend создаёт нового email-пользователя или находит существующего.
6. Referral-параметр из URL применяется к новой или существующей записи.
7. Пользователь получает Web App-сессию.

Коды хранятся в базе в хешированном виде, устаревают по `EMAIL_CODE_TTL_SECONDS`, повторная
отправка ограничена `EMAIL_CODE_RESEND_SECONDS`, а число попыток — `EMAIL_CODE_MAX_ATTEMPTS` и
общими brute-force настройками.

После входа пользователь может привязать email к Telegram-аккаунту через код или привязать
Telegram к email-аккаунту через Mini Apps `initData` либо Telegram OAuth.

### Проверка email-кода

1. Перезапустите backend и frontend после изменения `.env`.
2. Откройте `https://app.domain.com/` вне Telegram и убедитесь, что email-вход виден.
3. Запросите код на тестовый адрес.
4. Проверьте письмо, magic link и ручной ввод шестизначного кода.
5. Если письмо не пришло, проверьте backend:

```bash
docker compose logs -f backend
```

Частые причины:

- форма скрыта — не заполнено обязательное SMTP-поле или выключен `EMAIL_LOGIN_ENABLED`;
- письмо не отправляется — неверен порт, STARTTLS/SSL, SMTP login/API key или отправитель;
- magic link ведёт не туда — `SUBSCRIPTION_MINI_APP_URL` не является публичным HTTPS URL Mini App;
- код сразу устаревает — неверен `EMAIL_CODE_TTL_SECONDS` или время на сервере;
- `rate_limited` — ещё не прошёл `EMAIL_CODE_RESEND_SECONDS` либо сработала brute-force защита.

## Email и пароль

После подтверждения email пользователь может задать или изменить пароль в настройках профиля.
Пароль хранится как PBKDF2-SHA256 hash с солью. После установки доступен путь:

```text
https://app.domain.com/login/password
```

При неудачном входе frontend предлагает перейти к обычному email-коду. Установка, изменение и
восстановление пароля также подтверждаются email-кодом, поэтому рабочий SMTP остаётся обязательным.

## Telegram

Telegram-вход работает двумя способами:

- внутри Telegram Mini App backend проверяет Telegram Mini Apps `initData`;
- в обычном браузере используется Telegram OAuth / OpenID Connect Authorization Code Flow с
  PKCE, `nonce`, callback `/auth/telegram/callback` и серверной проверкой `id_token` по JWKS.

`initData` не требует отдельного OAuth-секрета, но требует корректного `BOT_TOKEN`, публичного
HTTPS Mini App URL и настройки Mini Apps в BotFather. OAuth нужен для кнопки Telegram вне клиента
Telegram и для привязки Telegram к email-аккаунту.

### Переменные Telegram

```ini
WEBAPP_ENABLED=True
SUBSCRIPTION_MINI_APP_URL=https://app.domain.com/
WEBAPP_SESSION_SECRET=<stable-random-secret>
WEBAPP_AUTH_MAX_AGE_SECONDS=86400
WEBAPP_LOGIN_TOKEN_TTL_SECONDS=600

TELEGRAM_LOGIN_ENABLED=True
TELEGRAM_OAUTH_CLIENT_ID=<client-id-from-botfather>
TELEGRAM_OAUTH_CLIENT_SECRET=<client-secret-from-botfather>
TELEGRAM_OAUTH_REQUEST_ACCESS=write
TELEGRAM_OAUTH_USE_BOT_PROXY=True
```

`TELEGRAM_OAUTH_CLIENT_ID` можно не задавать, если client ID совпадает с bot ID: приложение
возьмёт его из префикса `BOT_TOKEN`. `TELEGRAM_OAUTH_CLIENT_SECRET` для браузерного OAuth
обязателен.

`TELEGRAM_OAUTH_REQUEST_ACCESS=write` добавляет scope `telegram:bot_access`, чтобы бот мог
написать пользователю после входа. Если это не нужно, оставьте переменную пустой. Также
поддерживается `phone`, если вы осознанно запрашиваете телефон.

`WEBAPP_AUTH_MAX_AGE_SECONDS` ограничивает возраст `initData` и OAuth `id_token`, а
`WEBAPP_LOGIN_TOKEN_TTL_SECONDS` — TTL OAuth state, nonce и login-token.

Полный справочник:
[Веб-приложение, внешний вид и Telegram Login](../configuration/env-vars.md#веб-приложение-внешний-вид-и-telegram-login).

### Настройка Telegram в BotFather

1. Откройте `@BotFather` → `/mybots` → выберите бота.
2. В **Bot Settings → Domain** укажите домен без протокола и пути, например `app.domain.com`.
3. В **Bot Settings → Mini Apps** укажите `https://app.domain.com/`.
4. В **Bot Settings → Web Login** включите OpenID Connect Login, если переключатель доступен.
5. Скопируйте client ID и secret в `TELEGRAM_OAUTH_CLIENT_ID` и
   `TELEGRAM_OAUTH_CLIENT_SECRET`.
6. В **Web Login → Allowed URLs** добавьте:

```text
https://app.domain.com/
https://app.domain.com/auth/telegram/callback
```

После изменения `.env` пересоздайте backend и frontend:

```bash
docker compose up -d --force-recreate backend frontend
```

### Проксирование Telegram OAuth

Публичный домен `SUBSCRIPTION_MINI_APP_URL` должен идти в `frontend:80`. Frontend nginx сам
проксирует `/api/*` и `/auth/*` во внутренний Web App server на `backend:8081`. Готовые схемы
Caddy, Angie, Nginx, Newt и прямой публикации описаны в
[развертывании](../getting-started/deployment.md#готовые-папки-запуска).

Если backend не может напрямую открыть `oauth.telegram.org`, задайте SOCKS5 endpoint:

```ini
TELEGRAM_BOT_PROXY_URL=socks5://username:password@proxy.example.com:1080
TELEGRAM_OAUTH_USE_BOT_PROXY=True
```

Через proxy пойдут обмен authorization code на token и загрузка JWKS. Страница `/auth`
по-прежнему открывается через сеть пользователя, входящий Telegram webhook приходит на публичный
`WEBHOOK_BASE_URL`, а `initData` и legacy Login Widget проверяются локально. Чтобы Bot API
продолжал использовать proxy, а OAuth ходил напрямую, задайте
`TELEGRAM_OAUTH_USE_BOT_PROXY=False`.

### Проверка Telegram

Внутри Telegram:

1. Откройте Mini App кнопкой бота или URL из BotFather.
2. Убедитесь, что вход проходит без OAuth redirect.
3. При ошибке проверьте URL Mini App, домен BotFather и возраст `initData`.

В обычном браузере:

1. Откройте `https://app.domain.com/` и нажмите вход через Telegram.
2. Проверьте redirect на Telegram OAuth и возврат на
   `https://app.domain.com/auth/telegram/callback`.
3. После callback пользователь должен вернуться на `/` со статусом `telegram_auth=success`,
   который frontend удалит из URL.

Для диагностики:

```bash
curl -i https://app.domain.com/auth/telegram/start
docker compose logs -f backend frontend
```

Частые причины:

- `telegram_oauth_not_configured` — не задан secret или client ID не получен из настройки/токена;
- `Telegram OAuth nonce mismatch` — устарели session/state, изменился
  `WEBAPP_SESSION_SECRET` либо callback пришёл с другого домена;
- `Telegram OAuth ID token is stale` — слишком мал `WEBAPP_AUTH_MAX_AGE_SECONDS` или сбито время;
- callback не проходит — Allowed URL не совпадает либо `/auth/*` не доходит до Web App API;
- `invalid_token` — backend не имеет доступа к token endpoint/JWKS или неверно настроен proxy;
- Mini App не открывается — домен BotFather не совпадает с `SUBSCRIPTION_MINI_APP_URL`.

Общие логи: [авторизация Mini App и Telegram OAuth](../troubleshooting/logs.md#авторизация-mini-app-и-telegram-oauth).

## Google

1. Откройте [Google Cloud Console](https://console.cloud.google.com/apis/credentials) и выберите
   отдельный production-проект.
2. Настройте OAuth consent screen: название сервиса, контакты, домен, privacy policy и terms.
3. Создайте OAuth 2.0 Client ID типа **Web application**.
4. **Authorized JavaScript origins** оставьте пустым. Minishop использует серверный Authorization
   Code Flow с PKCE и не загружает Google Identity Services JavaScript SDK.
5. В **Authorized redirect URIs** добавьте точный адрес:

```text
https://app.example.com/auth/google/callback
```

6. Сохраните настройки и включите способ:

```ini
GOOGLE_OIDC_ENABLED=True
GOOGLE_OIDC_CLIENT_ID=<client-id>.apps.googleusercontent.com
GOOGLE_OIDC_CLIENT_SECRET=<client-secret>
```

Minishop запрашивает только `openid email profile`, проверяет подпись и стандартные OIDC claims
(`iss`, `aud`, `exp`, `nonce`) и принимает email только при `email_verified=true`.

Google требует точного совпадения redirect URI, включая схему, регистр, порт, путь и слеш.
Подробности:
[OAuth 2.0 for Web Server Applications](https://developers.google.com/identity/protocols/oauth2/web-server).

## Yandex ID

1. Откройте [Yandex OAuth](https://oauth.yandex.ru/) и создайте приложение для авторизации
   пользователей.
2. Добавьте платформу **Веб-сервисы**.
3. Укажите Redirect URI:

```text
https://app.example.com/auth/yandex/callback
```

4. Разрешите минимальные права `login:email`, `login:info` и `login:avatar`.
5. Сохраните настройки и включите способ:

```ini
YANDEX_OIDC_ENABLED=True
YANDEX_OIDC_CLIENT_ID=<client-id>
YANDEX_OIDC_CLIENT_SECRET=<client-secret>
```

Для контакта Minishop использует `default_email`, возвращённый Yandex ID. Адрес добавляется как
подтверждённый адрес провайдера, но не заменяет основной email существующего аккаунта.

Пошаговая регистрация:
[официальная документация Yandex ID](https://yandex.com/dev/id/doc/en/register-auth).

Настройки Google и Yandex ID, сохранённые в админке, применяются к следующим запросам
`/auth/{provider}/start` и `/auth/{provider}/callback` без перезапуска backend. Экран входа и
кешированные данные кабинета также обновляются после сохранения. Если админка сообщает, что ключ
«сохранён, но не применён», он не считается активным до перезапуска.

## Passkey

Passkey работает через WebAuthn и требует HTTPS. Исключение браузеров для локального `localhost`
не следует использовать как production-настройку.

```ini
PASSKEY_LOGIN_ENABLED=True
PASSKEY_RP_ID=app.example.com
PASSKEY_RP_NAME=Example VPN
PASSKEY_ORIGINS=https://app.example.com
PASSKEY_CHALLENGE_TTL_SECONDS=300
```

- `PASSKEY_RP_ID` — домен без протокола, порта и пути;
- `PASSKEY_RP_NAME` — имя сервиса, которое устройство показывает при создании ключа;
- `PASSKEY_ORIGINS` — полный origin с `https://`; несколько origins разделяются запятыми;
- после смены RP ID старые ключи перестанут работать для нового домена;
- не отключайте остальные способы, пока не проверили passkey на втором устройстве.

Подробнее:
[Passkeys на MDN](https://developer.mozilla.org/en-US/docs/Web/Security/Authentication/Passkeys).

## Привязка способов и адрес для уведомлений

В настройках профиля пользователь может:

- привязать email к Telegram-аккаунту через код;
- привязать Telegram через Mini Apps `initData` или Telegram OAuth;
- задать или изменить пароль;
- привязать Google, Yandex ID и passkey;
- выбрать email для уведомлений из подтверждённых адресов.

Если email уже принадлежит другой записи, backend выполняет безопасное объединение только после
подтверждения обеих сторон и инвалидирует старые Web App-кеши. Совпадение адреса OIDC само по себе
не создаёт пользователя и не разрешает объединение.

Основной email меняется отдельным двухэтапным сценарием: код сначала отправляется на текущий адрес,
затем второй код — на новый. После подтверждения новый адрес становится основным и адресом
уведомлений, а Minishop синхронизирует его в Remnawave Panel. Привязка или отвязка OIDC-провайдера
сама по себе поле email в Panel не меняет.

Смену основного адреса можно отключить независимо от email-входа:

```ini
EMAIL_ADDRESS_CHANGE_ENABLED=True
```

При отключении кнопка в кабинете становится неактивной, а backend отклоняет все этапы уже
начатого сценария. Это не мешает впервые привязать email, войти по коду/паролю или выбрать другой
подтверждённый OIDC-адрес для уведомлений.

Смена адреса проходит так:

1. Код отправляется на текущий основной адрес.
2. После проверки пользователь вводит новый адрес; занятый адрес отклоняется до создания записей.
3. Второй код отправляется на новый адрес и привязан к пользователю и точному адресу.
4. После подтверждения обновляются основной email, адрес уведомлений и email в Remnawave Panel.
   На старый адрес приходит уведомление безопасности, на новый — подтверждение смены.

Уникальность проверяется до отправки кода и повторно в транзакции. Ограничения базы закрывают
гонку параллельных запросов. Коды входа, восстановления и подтверждения основного email идут на
адрес соответствующей операции; автоматические уведомления — на выбранный адрес уведомлений.

## Общая проверка

1. Проверьте каждый включённый способ на экране входа.
2. Войдите по email-коду, задайте пароль, выйдите и войдите по паролю.
3. Проверьте Telegram внутри Mini App и отдельно в обычном браузере.
4. Войдите новыми Google и Yandex ID аккаунтами; для совпавшего email подтвердите связывание
   кодом и убедитесь, что дубль пользователя не создан.
5. Добавьте passkey, выйдите, войдите с ним и проверьте удаление ключа при наличии другого способа.
6. В **Настройки → Безопасность** проверьте список identity, основной email и адрес уведомлений.
7. Убедитесь, что подписка и email в Remnawave Panel не меняются от простой привязки OAuth.

Общие причины ошибок:

- кнопка скрыта — способ выключен или заполнены не все обязательные параметры;
- `redirect_uri_mismatch` — callback отличается схемой, доменом, портом, путём или слешем;
- `account_exists` — совпавший основной email ещё не подтверждён для автоматической привязки;
- OIDC-контекст устарел — повторите вход через провайдера;
- passkey недоступен — нет HTTPS, RP ID не соответствует домену или origin не разрешён;
- уведомления идут не туда — проверьте выбранный адрес, способ последнего входа его не меняет.

Email-уведомления поддержки, платежей и жизненного цикла подписки используют тот же SMTP-контур.
См. также [уведомления](notifications.md) и [поддержку пользователей](support.md).

## Настройка локального SMTP-сервера

Перед запуском настройте DNS-записи домена:

- A — `mail.example.com` с IP сервера;
- MX — `mail.example.com` с приоритетом 10;
- PTR — `mail.example.com` у хостера VPS;
- TXT — `v=spf1 ip4:1.2.3.4 ~all`, где `1.2.3.4` — реальный IPv4 сервера.

Изменения DNS могут применяться от нескольких часов до суток. Для STARTTLS нужен сертификат
домена `mail.example.com`. Например, в Caddy:

```txt
https://mail.example.com {
    respond "Mail server"
}
```

Установка:

1. Подготовьте Compose:

```bash
mkdir -p /opt/mailserver
cd /opt/mailserver
curl -O https://raw.githubusercontent.com/3252a8/remnawave-minishop/refs/heads/main/deploy/examples/mail/docker-compose.yml
nano docker-compose.yml
```

2. Запустите:

```bash
docker compose up -d
```

3. Создайте пользователя:

```bash
docker exec -it mailserver setup email add no-reply@example.com
docker exec -it mailserver setup email list
```

Созданный адрес и пароль можно использовать в почтовом клиенте и SMTP-настройках Minishop.
