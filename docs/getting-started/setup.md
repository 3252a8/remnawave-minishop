# Установка

Начните с `.env`, затем поднимите Compose-стек и проверьте backend, worker и frontend.

## Минимальный запуск

Для нового сервера удобнее начать с интерактивного install wizard: он скачает
нужный compose-профиль, соберет `.env`, проверит DNS, подготовит `data/` и при
необходимости запустит миграцию из Remnashop или старого `remnawave-tg-shop`.
Подробности: [интерактивный install wizard](deployment.md#интерактивный-install-wizard).

```bash
curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/install.sh -o install.sh
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

- [Настройка Telegram бота](../features/telegram-auth.md) - Telegram OAuth и Telegram Mini App.
- [Настройка SMTP](../features/email-login.md) - Вход и регистрация по email.

## После первого входа

1. Откройте админку через Mini App.
2. Проверьте платежные методы в настройках.
3. Настройте каталог тарифов.
4. Проверьте инструкции подключения.
5. Сделайте тестовую покупку или пробную активацию.

Подробности: [настройка окружения](configuration.md) и [развертывание](deployment.md).
