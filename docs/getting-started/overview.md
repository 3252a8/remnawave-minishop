# Обзор

Remnawave Minishop состоит из Telegram-бота, backend API, worker-процессов, frontend/Mini App и инфраструктурных сервисов PostgreSQL и Redis. В продакшене эти части запускаются через Docker Compose и общаются с Remnawave Panel по API и вебхукам.

## Основные компоненты

- **Backend** - вебхук Telegram, платежные вебхуки, вебхуки панели, API для Mini App и админки.
- **Worker** - фоновые задачи, синхронизация подписок, обработка очереди вебхуков и тарифных событий.
- **Frontend** - отдельный nginx-образ с Mini App и админкой.
- **PostgreSQL** - пользователи, платежи, настройки, поддержка, промокоды и служебные данные.
- **Redis** - FSM, кеши, rate limit, очередь вебхуков и distributed locks.

## Куда идти дальше

- [Установка](setup.md) - базовый запуск через Compose.
- [Развертывание](deployment.md) - Docker Compose, Caddy, Angie, Nginx, Pangolin/Newt и запуск без обратного прокси.
- [Способы входа](../features/login-methods.md) — email-код, email/пароль, Telegram, Google,
  Яндекс и passkey.
