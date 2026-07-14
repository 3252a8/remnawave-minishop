# Безопасность

Безопасность Minishop в первую очередь держится на стабильных секретах, корректном разделении публичных доменов и ограниченном доступе к админке.

## Секреты

- `WEBAPP_SESSION_SECRET` должен быть постоянным между рестартами, иначе Web App-сессии станут невалидными.
- `WEBHOOK_SECRET_TOKEN` защищает вебхук Telegram.
- `PANEL_WEBHOOK_SECRET` проверяет входящие события Remnawave Panel. Секрет задается в Remnawave Panel и вставляется в настройки бота.
- Платежные токены и webhook-секреты храните в `.env` или настройках админки с учетом доступа к серверу.

Сгенерировать секрет можно так:

```bash
openssl rand -hex 32
```

## Telegram антифлуд

Апдейты Telegram-бота проходят через ранний anti-flood middleware до sync
профиля, проверки каналов и логирования действий, которые обращаются к базе.
Профиль по умолчанию специально мягкий: он не должен мешать быстрым обычным
нажатиям кнопок, но отбрасывает экстремальные всплески сообщений и callback от
одного источника до того, как они разгонят записи в БД, платежные обработчики
или Telegram FloodWait.

Настройки доступны в **Админка -> Система -> Настройки -> Система -> Telegram
антифлуд**. Для обычного приватного продающего бота дефолтов достаточно, поэтому
они не добавлены в `.env.example`. Меняйте их только если реальный трафик
показывает, что пороги нужно расширить или сузить.

- `TELEGRAM_DROP_NON_PRIVATE_UPDATES=True` отбрасывает апдейты из групп и
  каналов до дорогих middleware. Оставляйте включенным, если бот не должен
  работать вне приватных чатов.
- `TELEGRAM_ANTIFLOOD_ENABLED=True` включает per-user/per-chat лимиты. Значение
  `0` у отдельного числового лимита отключает только этот лимит.
- `TELEGRAM_ANTIFLOOD_WINDOW_SECONDS=60` задает общее скользящее окно. Дефолты
  рассчитаны на нормальные button-heavy флоу: `180` всех апдейтов, `120`
  сообщений, `240` callback, `60` inline-запросов, `30` команд `/start` и `60`
  тяжелых callback за окно.
- `TELEGRAM_ACTION_COOLDOWN_ENABLED=True` дедуплицирует точные повторные
  платежные и trial callback от того же пользователя. Разные платежные payload
  не объединяются, поэтому обычный checkout остается независимым.

## Доступ администраторов

- `ADMIN_IDS` задает Telegram ID администраторов.
- Админка доступна только пользователям из `ADMIN_IDS` при входе через Telegram.
- Email-only аккаунты не получают админский доступ.

## Публичные URL

- `WEBHOOK_BASE_URL` должен вести на backend-сервер вебхуков.
- В Remnawave Panel `WEBHOOK_URL` должен быть `WEBHOOK_BASE_URL` + `/webhook/panel`, например `https://app.example.com/webhook/panel`.
- `SUBSCRIPTION_MINI_APP_URL` должен вести на frontend/Mini App-домен.
- Не добавляйте `/api`, `/auth` или webhook-пути в `SUBSCRIPTION_MINI_APP_URL`.

## Split frontend/backend

- Браузер пользователя должен ходить только на frontend origin: `https://app.example.com/api/...`.
- `WEBAPP_API_BASE_URL` оставляйте `/api`; отдельный backend origin в frontend JS не является защитой и делает WebApp API напрямую видимым пользователю.
- Для protected upstream используйте `WEBAPP_BACKEND_UPSTREAM` у frontend nginx и `MINISHOP_EDGE_TOKEN`, который nginx добавляет к upstream-запросам server-side.
- `MINISHOP_EDGE_TOKEN` нельзя отдавать в runtime config или frontend bundle: browser-visible token виден в DevTools.
- Token/firewall/VPN применяются к WebApp API plane `backend:8081`. Telegram, payment provider и Remnawave Panel webhook остаются на public webhook plane `backend:8080` и не должны требовать `MINISHOP_EDGE_TOKEN`.
- При upstream `https://bot.example.com` настройте Host/SNI (`WEBAPP_BACKEND_UPSTREAM_HOST=bot.example.com`) и route order так, чтобы `/api/*`, `/auth/*`, `/open-app`, logo/theme/favicon paths попадали в `8081` раньше generic webhook fallback.

## IP allowlist вебхуков

- Reverse proxy для `WEBHOOK_BASE_URL` должен передавать `X-Forwarded-For` с реальным IP отправителя.
- `TRUSTED_PROXIES` должен включать IP/CIDR последнего proxy-hop до backend. Иначе платежные webhook-обработчики будут проверять allowlist по IP proxy или Docker gateway.
- Для домена за Cloudflare backend принимает `CF-Connecting-IP`, только если ближайший недоверенный hop входит в [официальные сети Cloudflare](https://www.cloudflare.com/ips/). Добавлять эти публичные CIDR в `TRUSTED_PROXIES` не требуется.
- В Docker Compose профилях Caddy, Nginx и Pangolin/Newt дефолт покрывает loopback и private ranges: `127.0.0.1`, `::1`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `fc00::/7`.
- Если backend находится в общей Docker-сети с недоверенными контейнерами, сузьте `TRUSTED_PROXIES` до конкретных IP ваших reverse proxy.
- Если вы сознательно хотите доверять любому proxy-hop, используйте `0.0.0.0/0,::/0`, но только когда backend не опубликован напрямую, а внешний proxy очищает входящий `X-Forwarded-For`.

## Дополнительно

- Используйте HTTPS на всех публичных доменах.
- Ограничивайте доступ к серверу и `.env`.
- Следите за логами платежных вебхуков и вебхуков панели.
- После ротации секретов перезапускайте соответствующие сервисы и проверяйте вебхуки.

См. также [переменные окружения](env-vars.md) и [развертывание](../getting-started/deployment.md).
