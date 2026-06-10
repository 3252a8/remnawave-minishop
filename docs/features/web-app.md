# Веб-приложение / Mini App

Веб-приложение собирается в отдельный образ `frontend` и отдается через nginx. Статические запросы Mini App идут в `frontend:80`; frontend nginx проксирует `/api/*`, `/auth/*` и ассеты тем/логотипов во внутренний WebApp-сервер backend на `backend:8081`. Telegram, платежные и панельные webhook-маршруты остаются на backend-сервере вебхуков `backend:8080`.

## Что показывает веб-приложение

- текущую ссылку подключения;
- статус и дату окончания подписки;
- использованный и доступный трафик;
- отдельную карточку premium-трафика, если у активного тарифа настроены premium-сквады и premium-лимит;
- доступные тарифы, способы оплаты и платежный статус;
- смену тарифа, обычную докупку трафика и докупку premium-трафика при настроенном каталоге тарифов;
- встроенную инструкцию установки: подбор платформы, список приложений, deeplink-кнопки, QR и действия со ссылкой подписки;
- раздел "Мои устройства" при `MY_DEVICES_SECTION_ENABLED=True`;
- раздел "Поддержка" с тикетами и внешней ссылкой `SUPPORT_LINK` при включенном `SUPPORT_TICKETS_ENABLED`;
- реферальную ссылку и статистику приглашений;
- привязку email и Telegram к одному аккаунту.

Для администраторов из `ADMIN_IDS` веб-приложение также показывает админ-панель: статистику, **пользователей** (поиск, фильтры, premium-трафик), поддержку, рассылки, промокоды, логи, настройки и редактор тарифов. Подробности: [админ-панель](admin-panel.md).

## Настройки `.env`

```env
WEBAPP_ENABLED=True
WEBAPP_SERVER_HOST=0.0.0.0
WEBAPP_SERVER_PORT=8081
SUBSCRIPTION_MINI_APP_URL=https://app.domain.com/
SUBSCRIPTION_GUIDES_ENABLED=True
SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED=True
SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED=True
SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED=False
WEBAPP_TITLE="/minishop"
WEBAPP_THEMES_DIR=data/themes
WEBAPP_DEFAULT_THEME=
WEBAPP_SESSION_SECRET=<stable-random-secret>
WEBHOOK_SECRET_TOKEN=<stable-random-secret>
WEBAPP_SESSION_TTL_SECONDS=86400
WEBAPP_AUTH_MAX_AGE_SECONDS=86400
WEBAPP_LOGIN_TOKEN_TTL_SECONDS=600

SUPPORT_LINK=https://t.me/your_support_link
SUPPORT_TICKETS_ENABLED=True
SUPPORT_TICKET_RATE_LIMIT_PER_HOUR=5
```

`SUBSCRIPTION_MINI_APP_URL` - это публичный HTTPS URL именно frontend/Mini App, обычно отдельный домен вроде `https://app.domain.com/`. Его указывают в BotFather в Mini Apps, а бот использует его для кнопок личного кабинета, реферальных ссылок и входа по email. Не добавляйте в него `/api`, `/webhook` или путь конкретной страницы.

## Инструкции установки

Если `SUBSCRIPTION_GUIDES_ENABLED=True`, кнопка **Установить и настроить** в личном кабинете открывает внутренний экран `/install`. Если инструкции выключены, конфиг не загрузился или не прошел валидацию, сохраняется старое поведение: кнопка открывает финальную ссылку подключения из панели.

Экран `/install` доступен только авторизованному пользователю Web App. Он получает данные из `/api/subscription-guides`, определяет платформу по Telegram Mini Apps platform, `navigator.userAgentData.platform` и `navigator.userAgent`, а затем показывает приложения и шаги из Remnawave Subscription Page v1 config. Ссылки типа `happ://...` и другие deeplink-кнопки открываются прямо из Mini App; в шаблонах заменяются `{{SUBSCRIPTION_LINK}}`, `{{USERNAME}}`, `{{HAPP_CRYPT3_LINK}}` и `{{HAPP_CRYPT4_LINK}}`.

Конфиг инструкций загружается в таком порядке:

1. JSON из админки, только если включен `SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED`.
2. Subscription Page config из Remnawave Panel, если включен `SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED`.
3. Локальный файл `SUBSCRIPTION_PAGE_CONFIG_PATH` как fallback.

По умолчанию используются инструкции из Remnawave Panel, чтобы не дублировать настройку страницы подписки в Minishop. Локальный файл в `data/subpage-config/multiapp.json` не создается автоматически. Конфиг кешируется на backend и обновляется при изменении связанных настроек; ошибки загрузки кешируются кратко, чтобы не дергать панель на каждый пользовательский запрос.

Личный экран показывает QR-код финальной ссылки подписки, кнопку копирования и кнопку **Поделиться**. Для передачи инструкции генерируется публичная ссылка `/s/<token>`: она открывает тот же интерфейс инструкций без авторизации и нижней навигации, но без QR-блока. Публичный payload отдается через `/api/subscription-guides/public/{share_token}` только для активной локальной подписки с валидным share token.

`SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED=True` включает такое же поведение в Telegram-боте: кнопки подключения открывают Mini App `/install`, а после успешной оплаты, пробного периода или промокода пользователь получает публичную ссылку `/s/<token>`. Если настройку выключить, бот снова отправляет пользователя на финальную Remnawave Subscription Page.

Конфиг совместим с Remnawave Subscription Page v1 (`version`, `locales`, `brandingSettings`, `uiConfig`, `baseSettings`, `baseTranslations`, `svgLibrary`, `platforms`). Backend проверяет обязательные locale-строки, допустимые платформы и типы кнопок, ссылки на `svgIconKey`, а SVG из `svgLibrary` санитизирует перед отдачей в UI.

Если `WEBAPP_ENABLED=False`, пользовательское веб-приложение и админ-панель не регистрируются. Чтобы снова попасть в админку, включите `WEBAPP_ENABLED=True` в `.env` и перезапустите backend/frontend контейнеры.

Внешний вид настраивается в админке: раздел **Внешний вид** управляет логотипом, favicon, accent-цветом, выбранной темой и отдельным масштабом логотипа для desktop/mobile layout. Кастомные темы читаются из `WEBAPP_THEMES_DIR`, а `WEBAPP_DEFAULT_THEME` может принудительно выбрать тему по ключу. Подробный контракт `theme.json`, CSS/asset-роуты и пайплайн создания темы описаны в [webapp-themes.md](webapp-themes.md).

## Авторизация

Mini App поддерживает вход через Telegram Mini Apps `initData`, Telegram OAuth / OpenID Connect вне Telegram и email-код. Подробная настройка вынесена в отдельные разделы:

- [Telegram-авторизация](telegram-auth.md) - BotFather, Mini Apps, Web Login, callback `/auth/telegram/callback`, OAuth-переменные и типичные ошибки.
- [Вход по email](email-login.md) - SMTP, одноразовые коды, magic link, парольный вход и проверки доставки писем.

Если SMTP-настройки не заполнены, вход по email скрывается. Если Telegram OAuth не настроен, вход через Telegram продолжает работать внутри Telegram Mini App через `initData`, но внешняя браузерная авторизация не сможет стартовать.

Тикеты поддержки включаются через `SUPPORT_TICKETS_ENABLED`; внешний резервный контакт задается `SUPPORT_LINK`. Полный сценарий пользователя, админа и уведомлений описан в разделе [поддержка пользователей / тикеты](support.md).

## Проксирование

Рекомендуемая продакшен-схема - два публичных домена:

- `WEBHOOK_BASE_URL`, например `https://webhooks.domain.com`, целиком проксируется в `backend:8080`;
- `SUBSCRIPTION_MINI_APP_URL`, например `https://app.domain.com/`, целиком проксируется в `frontend:80`.

`frontend` уже сам проксирует `/api/*`, `/auth/*`, `/webapp-logo` и ассеты тем/логотипов во внутренний
WebApp API на `backend:8081`, поэтому внешний обратный прокси обычно не должен отправлять эти пути в
`backend:8081` напрямую.

Готовые варианты описаны в разделе [Развертывание](../getting-started/deployment.md#готовые-папки-запуска):

- [Caddy](../getting-started/deployment.md#caddy-рекомендуемый-вариант) - автоматический HTTPS;
- [Nginx](../getting-started/deployment.md#nginx) - сертификаты в соседней папке `ssl/`;
- [Pangolin/Newt](../getting-started/deployment.md#pangolin--newt) - публикация без входящих портов на сервере приложения;
- [без обратного прокси](../getting-started/deployment.md#без-обратного-прокси) - прямая публикация портов для проверки или внешней TLS-платформы.

В default `docker-compose.yml` наружу публикуются `frontend` и webhook/backend port, а внутри Docker
network сервисы доступны друг другу по service DNS names:

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

В разделе бонусов Web App показывает приветственный бонус за регистрацию и бонусы за оплату подписки. В legacy-режиме или при одном period-тарифе выводятся подробные строки по периодам. Если в JSON-каталоге включено несколько period-тарифов, Web App показывает, что бонус зависит от тарифа и периода оплаты друга, затем список тарифов с диапазоном "от N до N дней"; подробности по периодам раскрываются по иконке вопроса.

Веб-приложение учитывает `ref`, `start`, `start_param` и Telegram Mini Apps `start_param`, сохраняет найденный параметр до авторизации и передает его в Telegram OAuth или вход по email.

Для email-регистраций пользователь в Remnawave создается с username вида `em_<referral_code>`. Email добавляется в описание пользователя панели и, если API панели принимает поле `email`, передается отдельным полем. Для Telegram-регистраций используется username `tg_<telegram_id>`.
