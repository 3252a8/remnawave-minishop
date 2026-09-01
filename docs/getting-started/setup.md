# Быстрый запуск

Начните с `.env`, затем поднимите Compose-стек и проверьте backend, worker и frontend.

Перед началом проверьте [системные требования](system-requirements.md). Если подходящего сервера
еще нет, его можно выбрать у [друзей проекта — wCloud](https://wcloud.host/?from=yKyhIg2jXbNdWZsFzd_tyxLVBYiicNjK).

## Минимальный запуск

Для нового сервера удобнее начать с интерактивного install wizard: он скачает
нужный compose-профиль, соберет `.env`, проверит DNS, подготовит `data/` и при
необходимости запустит миграцию из Remnashop или старого `remnawave-tg-shop`.
Подробности: [интерактивный install wizard](deployment.md#интерактивный-install-wizard).

```bash
curl -fsSL https://gitlab.com/3252a8/remnawave-minishop/-/raw/main/scripts/install.sh -o install.sh
sh install.sh
```

Ручной минимальный запуск из уже скачанного репозитория:

```bash
cp .env.example .env
nano .env
docker compose up -d --build
docker compose ps
docker compose logs -f backend worker frontend
```

## Что заполнить в первую очередь

- `BOT_TOKEN` и `ADMIN_IDS` для доступа к боту и админке.
- `WEBHOOK_BASE_URL` для Telegram, платежных вебхуков и вебхуков панели.
- `SUBSCRIPTION_MINI_APP_URL` для Mini App и кнопок в Telegram.
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`.
- `WEBAPP_SESSION_SECRET`, `WEBHOOK_SECRET_TOKEN`, `PANEL_API_URL`, `PANEL_API_KEY`, `PANEL_WEBHOOK_SECRET`.

Для вебхуков Remnawave в панели укажите `WEBHOOK_URL` как `WEBHOOK_BASE_URL` + `/webhook/panel`, например `https://app.example.com/webhook/panel`. Секрет создается или задается в Remnawave Panel; тот же секрет вставьте в `PANEL_WEBHOOK_SECRET` в `.env` или позже в **Система -> Настройки -> Remnawave Panel**.

## Как выбрать Compose-вариант

Для продакшена по умолчанию берите [Caddy](deployment.md#caddy-рекомендуемый-вариант): это самый короткий путь к публичному HTTPS без ручной раскладки сертификатов.

```bash
cd deploy/examples/caddy
cp .env.example .env
nano .env
docker compose up -d
```

Остальные варианты описаны в [разделе развертывания](deployment.md#готовые-папки-запуска):

- [Angie](deployment.md#angie) - если нужен автоматический HTTPS как у Caddy, но в Nginx-синтаксисе;
- [Nginx](deployment.md#nginx) - если у вас уже есть TLS-сертификаты и нужен Nginx в Docker-сети;
- [Pangolin/Newt](deployment.md#pangolin--newt) - если нельзя открывать входящие порты на сервере приложения;
- [без обратного прокси](deployment.md#без-обратного-прокси) - для локальной проверки или внешнего TLS-терминатора.

## Настройки для веб апп

- [Способы входа](../features/login-methods.md) — email-код, email/пароль, Telegram, Google,
  Яндекс и passkey.

## После первого входа

1. Откройте админку через Mini App.
2. Проверьте платежные методы в настройках.
3. Настройте каталог тарифов.
4. Проверьте инструкции подключения.
5. Сделайте тестовую покупку или пробную активацию.

Подробности: [настройка окружения](configuration.md) и [развертывание](deployment.md).
