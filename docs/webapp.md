# Web App / Mini App

Web App собирается в отдельный `frontend` image и отдается через nginx. Static/Mini App запросы идут в `frontend:80`; frontend nginx проксирует `/api/*`, `/auth/*` и theme/logo assets в backend WebApp server на `backend:8081`. Telegram, payment и panel webhook routes остаются на backend webhook server `backend:8080`.

## Что показывает Web App

- текущую ссылку подключения;
- статус и дату окончания подписки;
- использованный и доступный трафик;
- отдельную карточку premium-трафика, если у активного тарифа настроены premium-сквады и premium-лимит;
- доступные тарифы, способы оплаты и платежный статус;
- смену тарифа, обычную докупку трафика и докупку premium-трафика при настроенном каталоге тарифов;
- раздел "Мои устройства" при `MY_DEVICES_SECTION_ENABLED=True`;
- раздел "Поддержка" с тикетами и внешней ссылкой `SUPPORT_LINK` при включенном `SUPPORT_TICKETS_ENABLED`;
- реферальную ссылку и статистику приглашений;
- привязку email и Telegram к одному аккаунту.

Для администраторов из `ADMIN_IDS` Web App также показывает админ-панель: статистику, **пользователей** (поиск, фильтры, premium-трафик), поддержку, рассылки, промокоды, логи, настройки и редактор тарифов. Подробности: [admin.md](admin.md).

## Настройки `.env`

```env
WEBAPP_ENABLED=True
WEBAPP_SERVER_HOST=0.0.0.0
WEBAPP_SERVER_PORT=8081
SUBSCRIPTION_MINI_APP_URL=https://app.domain.com/
WEBAPP_TITLE="Моя подписка"
WEBAPP_THEMES_DIR=data/themes
WEBAPP_DEFAULT_THEME=
WEBAPP_SESSION_SECRET=<stable-random-secret>
WEBHOOK_SECRET_TOKEN=<stable-random-secret>
WEBAPP_SESSION_TTL_SECONDS=86400
WEBAPP_AUTH_MAX_AGE_SECONDS=86400
WEBAPP_LOGIN_TOKEN_TTL_SECONDS=600

TELEGRAM_OAUTH_CLIENT_ID=<client-id-from-botfather>
TELEGRAM_OAUTH_CLIENT_SECRET=<client-secret-from-botfather>
TELEGRAM_OAUTH_REQUEST_ACCESS=write

SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_FALLBACK_PORTS=2525,465
SMTP_STARTTLS=True
SMTP_USE_SSL=False
SMTP_USERNAME=<smtp-login>
SMTP_PASSWORD=<smtp-password-or-key>
SMTP_FROM_EMAIL=no-reply@domain.com
SMTP_FROM_NAME=Remnawave Minishop

SUPPORT_LINK=https://t.me/your_support_link
SUPPORT_TICKETS_ENABLED=True
SUPPORT_TICKET_RATE_LIMIT_PER_HOUR=5
```

`SUBSCRIPTION_MINI_APP_URL` - это публичный HTTPS URL именно frontend/Mini App, обычно отдельный домен вроде `https://app.domain.com/`. Его указывают в BotFather в Mini Apps, а бот использует его для кнопок личного кабинета, referral-ссылок и email-входа. Не добавляйте в него `/api`, `/webhook` или путь конкретной страницы.

Если `WEBAPP_ENABLED=False`, пользовательский Web App и админ-панель не регистрируются. Чтобы снова попасть в админку, включите `WEBAPP_ENABLED=True` в `.env` и перезапустите backend/frontend контейнеры.

Внешний вид настраивается в админке: раздел **Внешний вид** управляет логотипом, emoji-логотипом, accent-цветом, выбранной темой и масштабом логотипа. Кастомные темы читаются из `WEBAPP_THEMES_DIR`, а `WEBAPP_DEFAULT_THEME` может принудительно выбрать тему по ключу. Подробный контракт `theme.json`, CSS/asset-роуты и пайплайн создания темы описаны в [webapp-themes.md](webapp-themes.md).

Если SMTP-настройки не заполнены, вход по email скрывается.

Тикеты поддержки включаются через `SUPPORT_TICKETS_ENABLED`; внешний резервный контакт задается `SUPPORT_LINK`. Полный сценарий пользователя, админа и уведомлений описан в [support.md](support.md).

## Telegram-авторизация

Внутри Telegram Mini App пользователь авторизуется через Telegram Mini Apps `initData`. При открытии страницы вне Telegram используется Telegram OAuth / OpenID Connect Authorization Code Flow с PKCE, callback `/auth/telegram/callback`, `nonce` и серверной проверкой `id_token` по JWKS Telegram.

Настройка в BotFather:

1. Откройте `@BotFather` -> `/mybots` -> выберите бота.
2. В `Bot Settings` -> `Domain` укажите домен Web App без протокола и пути, например `app.domain.com`.
3. В `Bot Settings` -> `Mini Apps` укажите URL, например `https://app.domain.com/`.
4. В `Bot Settings` -> `Web Login` включите OpenID Connect Login, если BotFather предлагает переключение.
5. Скопируйте Client ID и Client Secret в `TELEGRAM_OAUTH_CLIENT_ID` и `TELEGRAM_OAUTH_CLIENT_SECRET`.
6. В `Web Login` -> `Allowed URLs` добавьте:

```text
https://app.domain.com/
https://app.domain.com/auth/telegram/callback
```

`TELEGRAM_OAUTH_REQUEST_ACCESS=write` разрешает боту написать пользователю после логина. Если дополнительные разрешения не нужны, оставьте переменную пустой.

## Email-вход

Email-вход работает через одноразовый код:

1. Пользователь вводит email.
2. Бот отправляет код через SMTP.
3. Код вводится в модальном окне Web App.
4. После подтверждения создается или находится пользователь, а email можно связать с Telegram-аккаунтом.

Для Brevo обычно подходит порт `587` с STARTTLS. Если основной порт недоступен, приложение пробует порты из `SMTP_FALLBACK_PORTS`; порт `465` используется через SSL.

Полный список переменных, обязательные поля для включения email-входа и типичные ошибки подключения описаны в разделе **SMTP и вход по email** в [configuration.md](configuration.md).

## Проксирование

Web App должен проксироваться отдельно от вебхуков:

```nginx
upstream remnawave_frontend {
    server frontend:80;
}

upstream remnawave_backend_webapp {
    server backend:8081;
}

upstream remnawave_backend_webhooks {
    server backend:8080;
}

server {
    server_name app.domain.com;
    listen 443 ssl;
    http2 on;

    ssl_certificate "/etc/nginx/ssl/app_fullchain.pem";
    ssl_certificate_key "/etc/nginx/ssl/app_privkey.key";

    location / {
        proxy_pass http://remnawave_frontend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location ~ ^/(api|auth)/ {
        proxy_pass http://remnawave_backend_webapp;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /webhook/ {
        proxy_pass http://remnawave_backend_webhooks;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

В default `docker-compose.yml` наружу публикуются `frontend` и webhook/backend port, а внутри Docker network сервисы доступны друг другу по service DNS names:

```yaml
services:
  frontend:
    expose:
      - "80"
  backend:
    expose:
      - "8080"
```

## Реферальные ссылки

Реферальные ссылки доступны в двух форматах:

- Telegram deep-link: `https://t.me/<bot>?start=ref_u<code>`;
- Web App ссылка: `https://app.domain.com/?ref=u<code>`.

Web App учитывает `ref`, `start`, `start_param` и Telegram Mini Apps `start_param`, сохраняет найденный параметр до авторизации и передает его в Telegram OAuth или email-вход.

Для email-регистраций пользователь в Remnawave создается с username вида `em_<referral_code>`. Email добавляется в описание пользователя панели и, если API панели принимает поле `email`, передается отдельным полем. Для Telegram-регистраций используется username `tg_<telegram_id>`.
