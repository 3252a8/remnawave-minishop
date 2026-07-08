# Remnawave Minishop

## Разработка

- [Единый dev stand](development/dev-stand.md) - локальный Docker Compose стенд
  с Mini Shop, Remnawave Panel, Subscription Page, сидами и командами
  `npm run dev:stand:*` для full-stack QA.
- [API и интеграции](api/index.md) - HTTP OpenAPI-контракт, интерактивная
  спецификация, доменные события и расширение через плагины.
- [API плагинов и расширений](development/plugins.md) - хуки Python-плагинов,
  доменные события, feature flags, миграции, локали и правила расширения
  секций админки.
- [Карта кодовой базы Graphify](development/graphify.md) - сгенерированный
  knowledge graph репозитория для architecture review, поиска связей и быстрого
  онбординга в кодовую базу.

Remnawave Minishop - Telegram-бот и Mini App для продажи и управления подписками Remnawave. Документация помогает развернуть стек, настроить платежи, тарифы, админку, поддержку и публичный личный кабинет.

> Проект работает вместе с Remnawave Panel: панель хранит пользователей и подписки, а Minishop отвечает за Telegram, платежи, Mini App, тарифы и операционную админку.

## Ключевые возможности

- **Продажа подписок** - тарифы на срок и по трафику, докупки трафика, HWID-устройства, [premium-сквады](features/tariffs.md#premium-сквады-и-отдельный-лимит)
- **Жизненный цикл пользователей** - регистрация, пробный период, продление, синхронизация с панелью и предупреждения по трафику.
- **Mini App** - личный кабинет, инструкции установки, [Telegram OAuth](features/telegram-auth.md), [вход по email](features/email-login.md) и публичные реферальные ссылки.
- **Операционные инструменты** - админка, тикеты поддержки, [промокоды](features/promocodes.md), рассылки, логи, [бэкапы и восстановление](features/backups.md), настройки поверх `.env`.
